from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .llm import build_parser
from .parsing import ParserError, offline_parse
from .service import execute
from .storage import connect, get


class SearchRequest(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    query: str = Field(min_length=1,max_length=500)
    limit: int = Field(default=10,ge=1,le=50)
    offset: int = Field(default=0,ge=0,le=10000)
    sort: str|None = None
    @field_validator("query")
    @classmethod
    def trim(cls,v):
        if not v.strip(): raise ValueError("query must not be empty")
        return v.strip()

def create_app(db_path: str|None=None):
    app=FastAPI(title="AI Vehicle Search Engine",version="0.1.0",description="Natural-language search over a synthetic catalogue")
    frontend_dir=Path(__file__).resolve().parents[2]/"frontend"
    if frontend_dir.is_dir():
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
        @app.get("/", include_in_schema=False)
        async def frontend(): return FileResponse(frontend_dir/"index.html")
    path=db_path or os.getenv("DATABASE_PATH","./data/catalogue.db")
    mode=os.getenv("PARSER_MODE","offline")
    provider=os.getenv("LLM_PROVIDER","openrouter")
    allow_fallback=os.getenv("ALLOW_OFFLINE_FALLBACK","false").lower()=="true"
    parser = None
    if mode == "llm":
        provider=os.getenv("LLM_PROVIDER","openrouter"); model=os.getenv("LLM_MODEL",""); key=os.getenv("OPENROUTER_API_KEY" if provider=="openrouter" else "GEMINI_API_KEY","")
        if not model or not key:
            # Keep import/startup usable for tooling; readiness reports the misconfiguration.
            parser = None
        else:
            parser = build_parser(provider,model,key,float(os.getenv("LLM_TIMEOUT_SECONDS","10")),int(os.getenv("LLM_MAX_OUTPUT_TOKENS","1600")))
    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid=str(uuid.uuid4())
        length=request.headers.get("content-length")
        if length and length.isdigit() and int(length)>8192:
            return JSONResponse(status_code=413,content={"request_id":rid,"error":{"code":"request_too_large","message":"request body too large","retryable":False}},headers={"X-Request-ID":rid})
        response=await call_next(request); response.headers["X-Request-ID"]=rid; return response
    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException): return JSONResponse(status_code=exc.status_code,content=exc.detail)
    @app.post("/api/v1/search")
    async def search_route(body: SearchRequest):
        rid=str(uuid.uuid4()); started=time.perf_counter()
        try:
            degraded=False
            if mode == "llm":
                if parser is None: raise ParserError("llm_configuration_error",f"LLM mode requires LLM_MODEL and {provider.upper()} credentials")
                try: intent=parser.parse(body.query)
                except ParserError as error:
                    if allow_fallback and error.code in {"llm_timeout","llm_unavailable"}:
                        intent=offline_parse(body.query); degraded=True
                    else: raise
            else:
                intent=offline_parse(body.query)
            conn=connect(path,read_only=True)
            result=execute(intent,conn,body.query,body.limit,body.offset,body.sort); conn.close()
            result.update({"request_id":rid,"query":body.query,"parser_mode":"offline" if degraded else mode,"provider":None if degraded or mode=="offline" else provider,"degraded":degraded,"catalogue_version":catalogue_version(path),"timings_ms":{"total":round((time.perf_counter()-started)*1000,2)},"warnings":["Synthetic catalogue; safety ratings are demonstration data."]+(["Offline fallback used after transient provider failure."] if degraded else [])})
            return result
        except ParserError as e: raise HTTPException(422,detail={"request_id":rid,"error":{"code":e.code,"message":e.message,"retryable":False}})
        except FileNotFoundError: raise HTTPException(503,detail={"request_id":rid,"error":{"code":"catalogue_unavailable","message":"catalogue is not seeded","retryable":False}})
    @app.get("/api/v1/vehicles/{vehicle_id}")
    async def vehicle_route(vehicle_id: str):
        rid=str(uuid.uuid4()); conn=connect(path,read_only=True); v=get(conn,vehicle_id); conn.close()
        if not v: raise HTTPException(404,detail={"request_id":rid,"error":{"code":"not_found","message":"vehicle not found","retryable":False}})
        from .domain import vehicle_json
        return {"request_id":rid,"vehicle":vehicle_json(v),"catalogue_version":catalogue_version(path)}
    @app.get("/health/live")
    async def live(): return {"status":"ok"}
    @app.get("/health/ready")
    async def ready():
        try:
            if mode == "llm" and parser is None: raise ValueError("LLM configuration missing")
            return {"status":"ready","catalogue_version":catalogue_version(path),"parser_mode":mode}
        except (FileNotFoundError, OSError, KeyError, ValueError): raise HTTPException(503,detail={"status":"not_ready"})
    return app
def catalogue_version(path):
    conn=connect(path,read_only=True); row=conn.execute("SELECT value FROM catalogue_metadata WHERE key='catalogue_version'").fetchone(); conn.close()
    if not row: raise FileNotFoundError(path)
    return row[0]
app=create_app()

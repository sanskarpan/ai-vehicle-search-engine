from __future__ import annotations

import logging
import os
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from .llm import build_parser
from .parsing import ParserError, offline_parse, require_supported_coverage
from .service import execute
from .storage import connect, get, validate_catalogue

LOGGER = logging.getLogger("vehicle_search.api")
MAX_REQUEST_BYTES = 8 * 1024


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query: str = Field(min_length=1, max_length=500, examples=["Show SUVs under ₹15L"])
    limit: int = Field(default=10, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=10_000)
    sort: Literal["price_asc", "price_desc", "odometer_asc", "year_desc"] | None = None

    @field_validator("query")
    @classmethod
    def trim_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        return value.strip()


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ErrorResponse(BaseModel):
    request_id: str
    error: ErrorDetail


class SafetyResponse(BaseModel):
    scheme: str
    protocol: str
    test_year: int | None
    adult_stars: int | None
    child_stars: int | None
    source_url: str | None
    applicability: str
    is_synthetic: bool


class VehicleResponse(BaseModel):
    id: str
    make: str
    model: str
    variant: str
    year: int
    price_inr: int
    odometer_km: int
    condition: str
    body_type: str
    fuel_type: str
    transmission: str
    seats: int
    city: str
    features: list[str]
    safety: SafetyResponse
    description: str
    is_synthetic: bool


class PredicateResponse(BaseModel):
    field: str
    op: str
    values: list[Any]
    source: str
    evidence: str


class PreferenceResponse(BaseModel):
    code: str
    evidence: str


class InterpretationResponse(BaseModel):
    predicates: list[PredicateResponse]
    preferences: list[PreferenceResponse]
    sort: str
    assumptions: list[str]


class ClarificationResponse(BaseModel):
    code: Literal[
        "ambiguous_query",
        "contradictory_query",
        "unsupported_query",
        "unverifiable_query",
    ]
    message: str


class SearchResultResponse(BaseModel):
    vehicle: VehicleResponse
    score: float
    match_reasons: list[str]


class TimingsResponse(BaseModel):
    parse: float = Field(ge=0)
    retrieve: float = Field(ge=0)
    total: float = Field(ge=0)


class MetaResponse(BaseModel):
    parser_mode: Literal["offline", "llm"]
    provider: str | None
    degraded: bool
    catalogue_version: str
    timings_ms: TimingsResponse
    warnings: list[str]


class SearchResponse(BaseModel):
    request_id: str
    status: Literal["ok", "needs_clarification"]
    query: str
    interpretation: InterpretationResponse | None
    clarification: ClarificationResponse | None
    results: list[SearchResultResponse]
    total: int = Field(ge=0)
    limit: int
    offset: int
    has_more: bool
    meta: MetaResponse


class VehicleDetailResponse(BaseModel):
    request_id: str
    vehicle: VehicleResponse
    catalogue_version: str


class LiveResponse(BaseModel):
    status: Literal["ok"]


class ReadyResponse(BaseModel):
    status: Literal["ready"]
    catalogue_version: str
    parser_mode: Literal["offline", "llm"]


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def _security_headers(request: Request) -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "same-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }
    if request.url.path == "/":
        headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
            "object-src 'none'; img-src 'self' data:; style-src 'self'; script-src 'self'"
        )
    if request.url.path.startswith(("/api/", "/health/")):
        headers["Cache-Control"] = "no-store"
    return headers


def _error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    retryable: bool = False,
) -> JSONResponse:
    request_id = _request_id(request)
    return JSONResponse(
        status_code=status,
        content={
            "request_id": request_id,
            "error": {"code": code, "message": message, "retryable": retryable},
        },
        headers={"X-Request-ID": request_id, **_security_headers(request)},
    )


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(
        title="AI Vehicle Search Engine",
        version="0.1.0",
        description="Natural-language search over a synthetic catalogue",
    )
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    if frontend_dir.is_dir():
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

        @app.get("/", include_in_schema=False)
        async def frontend() -> FileResponse:
            return FileResponse(frontend_dir / "index.html")

    database_path = db_path or os.getenv("DATABASE_PATH", "./data/catalogue.db")
    mode = os.getenv("PARSER_MODE", "offline").strip().lower()
    provider = os.getenv("LLM_PROVIDER", "openrouter").strip().lower()
    allow_fallback = os.getenv("ALLOW_OFFLINE_FALLBACK", "false").lower() == "true"
    parser = None
    configuration_error: str | None = None

    if mode not in {"offline", "llm"}:
        configuration_error = "PARSER_MODE must be 'offline' or 'llm'"
    elif mode == "llm":
        if provider not in {"openrouter", "gemini"}:
            configuration_error = "LLM_PROVIDER must be 'openrouter' or 'gemini'"
        else:
            model = os.getenv("LLM_MODEL", "").strip()
            key_name = "OPENROUTER_API_KEY" if provider == "openrouter" else "GEMINI_API_KEY"
            api_key = os.getenv(key_name, "").strip()
            if not model or not api_key:
                configuration_error = f"LLM mode requires LLM_MODEL and {key_name}"
            else:
                try:
                    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "10"))
                    max_tokens = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "1600"))
                    if timeout <= 0 or max_tokens <= 0:
                        raise ValueError
                    fallbacks = [
                        item.strip()
                        for item in os.getenv("OPENROUTER_FALLBACK_MODELS", "").split(",")
                        if item.strip()
                    ]
                    parser = build_parser(provider, model, api_key, timeout, max_tokens, fallbacks)
                except (TypeError, ValueError, ParserError):
                    configuration_error = "invalid LLM configuration"

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        declared_length = request.headers.get("content-length")
        if declared_length:
            try:
                if int(declared_length) > MAX_REQUEST_BYTES:
                    return _error_response(
                        request, 413, "request_too_large", "request body too large"
                    )
            except ValueError:
                return _error_response(
                    request, 400, "invalid_request", "invalid Content-Length header"
                )
        if request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()
            if len(body) > MAX_REQUEST_BYTES:
                return _error_response(request, 413, "request_too_large", "request body too large")
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        for name, value in _security_headers(request).items():
            response.headers[name] = value
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _exc: RequestValidationError) -> JSONResponse:
        return _error_response(request, 422, "invalid_request", "request validation failed")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            detail = exc.detail
            return _error_response(
                request,
                exc.status_code,
                str(detail["code"]),
                str(detail.get("message", "request failed")),
                bool(detail.get("retryable", False)),
            )
        return _error_response(request, exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, _exc: Exception) -> JSONResponse:
        LOGGER.exception("unexpected request failure", extra={"request_id": _request_id(request)})
        return _error_response(request, 500, "internal_error", "internal server error")

    error_models = {
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    }

    @app.post("/api/v1/search", response_model=SearchResponse, responses=error_models)
    def search_route(body: SearchRequest, request: Request) -> dict[str, Any]:
        started = time.perf_counter()
        parse_started = time.perf_counter()
        degraded = False
        fallback_reason: str | None = None
        try:
            if configuration_error:
                raise ParserError("llm_configuration_error", configuration_error)
            if mode == "llm":
                if parser is None:
                    raise ParserError("llm_configuration_error", "LLM parser is not configured")
                try:
                    intent = require_supported_coverage(parser.parse(body.query), body.query)
                except ParserError as original_error:
                    if allow_fallback and original_error.code in {
                        "llm_timeout",
                        "llm_unavailable",
                        "llm_invalid_response",
                    }:
                        intent = offline_parse(body.query)
                        degraded = True
                        fallback_reason = original_error.code
                    else:
                        raise
            else:
                intent = offline_parse(body.query)
            parse_ms = (time.perf_counter() - parse_started) * 1000
            retrieve_started = time.perf_counter()
            with closing(connect(database_path, read_only=True)) as connection:
                version = validate_catalogue(connection)["catalogue_version"]
                result = execute(intent, connection, body.query, body.limit, body.offset, body.sort)
            retrieve_ms = (time.perf_counter() - retrieve_started) * 1000
            result.update(
                {
                    "request_id": _request_id(request),
                    "query": body.query,
                    "meta": {
                        "parser_mode": "offline" if degraded else mode,
                        "provider": None if degraded or mode == "offline" else provider,
                        "degraded": degraded,
                        "catalogue_version": version,
                        "timings_ms": {
                            "parse": round(parse_ms, 2),
                            "retrieve": round(retrieve_ms, 2),
                            "total": round((time.perf_counter() - started) * 1000, 2),
                        },
                        "warnings": ["Synthetic catalogue; safety ratings are demonstration data."]
                        + (
                            [
                                (
                                    "Conservative offline interpretation used because the provider "
                                    f"failed validation or availability ({fallback_reason})."
                                )
                            ]
                            if degraded
                            else []
                        ),
                    },
                }
            )
            return result
        except ParserError as exc:
            status = {
                "llm_timeout": 504,
                "llm_unavailable": 503,
                "llm_configuration_error": 503,
                "llm_invalid_response": 502,
            }.get(exc.code, 422)
            retryable = exc.code in {"llm_timeout", "llm_unavailable"}
            raise HTTPException(
                status,
                detail={"code": exc.code, "message": exc.message, "retryable": retryable},
            ) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                422,
                detail={
                    "code": "invalid_intent",
                    "message": str(exc) or "unsupported search criteria",
                },
            ) from exc
        except (FileNotFoundError, sqlite3.Error) as exc:
            raise HTTPException(
                503,
                detail={"code": "catalogue_unavailable", "message": "catalogue is not seeded"},
            ) from exc

    @app.get(
        "/api/v1/vehicles/{vehicle_id}",
        response_model=VehicleDetailResponse,
        responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    async def vehicle_route(vehicle_id: str, request: Request) -> dict[str, Any]:
        try:
            with closing(connect(database_path, read_only=True)) as connection:
                version = validate_catalogue(connection)["catalogue_version"]
                vehicle = get(connection, vehicle_id)
        except (FileNotFoundError, sqlite3.Error) as exc:
            raise HTTPException(
                503,
                detail={"code": "catalogue_unavailable", "message": "catalogue is not seeded"},
            ) from exc
        if not vehicle:
            raise HTTPException(404, detail={"code": "not_found", "message": "vehicle not found"})
        from .domain import vehicle_json

        return {
            "request_id": _request_id(request),
            "vehicle": vehicle_json(vehicle),
            "catalogue_version": version,
        }

    @app.get("/health/live", response_model=LiveResponse)
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(
        "/health/ready",
        response_model=ReadyResponse,
        responses={503: {"model": ErrorResponse}},
    )
    async def ready() -> dict[str, str]:
        try:
            if configuration_error:
                raise ValueError(configuration_error)
            with closing(connect(database_path, read_only=True)) as connection:
                version = validate_catalogue(connection)["catalogue_version"]
            return {"status": "ready", "catalogue_version": version, "parser_mode": mode}
        except (FileNotFoundError, OSError, sqlite3.Error, ValueError) as exc:
            raise HTTPException(
                503,
                detail={"code": "not_ready", "message": "service is not ready"},
            ) from exc

    return app


app = create_app()

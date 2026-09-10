from __future__ import annotations

import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient

from .api import create_app


def run(path: str, dataset: str) -> dict:
    rows=[json.loads(line) for line in Path(dataset).read_text().splitlines() if line.strip()]
    client=TestClient(create_app(path)); passed=0; results=[]
    for row in rows:
        response=client.post("/api/v1/search",json={"query":row["query"]}); body=response.json()
        ok=response.status_code==200 and body.get("status")==row["expected_status"]
        passed += ok; results.append({"id":row["id"],"ok":ok,"status":body.get("status"),"expected":row["expected_status"]})
    return {"dataset":dataset,"count":len(rows),"passed":passed,"accuracy":passed/len(rows) if rows else None,"results":results}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--db",default="./data/catalogue.db"); ap.add_argument("--dataset",default="data/golden_queries.jsonl"); a=ap.parse_args(); print(json.dumps(run(a.db,a.dataset),indent=2))

if __name__=="__main__": main()

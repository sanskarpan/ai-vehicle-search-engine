import json

from vehicle_search import api
from vehicle_search.evaluate import run
from vehicle_search.llm import ParserError
from vehicle_search.seed import seed_database


class UnavailableParser:
    def parse(self, _query: str):
        raise ParserError("llm_unavailable", "provider unavailable")


def test_live_evaluation_does_not_count_offline_fallback(tmp_path, monkeypatch):
    database = tmp_path / "catalogue.db"
    dataset = tmp_path / "live_case.jsonl"
    seed_database(str(database), count=8, seed=42)
    dataset.write_text(
        json.dumps(
            {
                "id": "live-1",
                "query": "Show SUVs under ₹15L",
                "expected_status": "ok",
                "expected_predicates": [
                    ["body_type", "in", ["suv"]],
                    ["price_inr", "lt", [1500000]],
                ],
            }
        )
        + "\n"
    )
    monkeypatch.setenv("PARSER_MODE", "llm")
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_MODEL", "test/free")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("ALLOW_OFFLINE_FALLBACK", "true")
    monkeypatch.setattr(api, "build_parser", lambda *_args, **_kwargs: UnavailableParser())

    report = run(str(database), str(dataset))

    assert report["passed"] == 0
    assert report["live_extractions"] == 0
    assert report["degraded_responses"] == 1
    assert report["provider"] == "openrouter"
    assert report["model"] == "test/free"
    assert report["cases"][0]["checks"]["live_execution"] is False

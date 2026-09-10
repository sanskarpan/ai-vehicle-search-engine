import json

import httpx
import pytest

from vehicle_search.llm import GeminiParser, OpenRouterParser
from vehicle_search.parsing import ParserError

VALID_EXTRACTION = {
    "intent": "search",
    "predicates": [{"field": "body_type", "op": "in", "values": ["suv"], "evidence": "SUVs"}],
    "preferences": [],
    "sort": "unspecified",
    "sort_evidence": "",
    "issues": [],
    "policy_terms": [],
}


def openrouter_response(payload, *, status_code=200, finish_reason="stop"):
    return httpx.Response(
        status_code,
        json={"choices": [{"finish_reason": finish_reason, "message": {"content": json.dumps(payload) if isinstance(payload, dict) else payload}}]},
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )


def test_openrouter_falls_back_after_invalid_model(monkeypatch):
    responses = [openrouter_response({"predicates": []}), openrouter_response(VALID_EXTRACTION)]
    seen = []

    def fake_post(url, **kwargs):
        seen.append(kwargs["json"]["model"])
        return responses.pop(0)

    monkeypatch.setattr("vehicle_search.llm.httpx.post", fake_post)
    result = OpenRouterParser("openrouter/free", "key", fallback_models=["google/gemma-4-26b-a4b-it:free"]).parse("Show SUVs")
    assert result.predicates[0].values == ["suv"]
    assert seen == ["openrouter/free", "google/gemma-4-26b-a4b-it:free"]


@pytest.mark.parametrize("status", [401, 429, 500])
def test_provider_status_mapping(monkeypatch, status):
    response = httpx.Response(status, request=httpx.Request("POST", "https://example.test"))
    monkeypatch.setattr("vehicle_search.llm.httpx.post", lambda *args, **kwargs: response)
    with pytest.raises(ParserError) as exc:
        OpenRouterParser("openrouter/free", "key").parse("Show SUVs")
    assert exc.value.code == ("llm_configuration_error" if status == 401 else "llm_unavailable")


def test_openrouter_maps_truncation_and_invalid_json(monkeypatch):
    responses = [openrouter_response("{", finish_reason="length"), openrouter_response("{")]
    monkeypatch.setattr("vehicle_search.llm.httpx.post", lambda *args, **kwargs: responses.pop(0))
    with pytest.raises(ParserError) as exc:
        OpenRouterParser("openrouter/free", "key", fallback_models=["fallback"]).parse("Show SUVs")
    assert exc.value.code == "llm_invalid_response"


def test_gemini_maps_quota_to_unavailable(monkeypatch):
    response = httpx.Response(429, request=httpx.Request("POST", "https://example.test"))
    monkeypatch.setattr("vehicle_search.llm.httpx.post", lambda *args, **kwargs: response)
    with pytest.raises(ParserError) as exc:
        GeminiParser("gemini-3.8-flash", "key").parse("Show SUVs")
    assert exc.value.code == "llm_unavailable"


def test_provider_timeout_mapping(monkeypatch):
    def fake_post(*args, **kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr("vehicle_search.llm.httpx.post", fake_post)
    with pytest.raises(ParserError) as exc:
        OpenRouterParser("openrouter/free", "key").parse("Show SUVs")
    assert exc.value.code == "llm_timeout"

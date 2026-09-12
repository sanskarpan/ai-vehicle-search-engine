import asyncio
import json
import time

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
        json={
            "choices": [
                {
                    "finish_reason": finish_reason,
                    "message": {
                        "content": json.dumps(payload) if isinstance(payload, dict) else payload
                    },
                }
            ]
        },
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )


def mock_post(monkeypatch, handler):
    async def call(*args, **kwargs):
        return handler(*args, **kwargs)

    monkeypatch.setattr("vehicle_search.llm._post", call)


def test_openrouter_falls_back_after_invalid_model(monkeypatch):
    responses = [openrouter_response({"predicates": []}), openrouter_response(VALID_EXTRACTION)]
    seen = []

    def fake_post(url, **kwargs):
        seen.append(kwargs["json"]["model"])
        return responses.pop(0)

    mock_post(monkeypatch, fake_post)
    result = OpenRouterParser(
        "openrouter/free", "key", fallback_models=["google/gemma-4-26b-a4b-it:free"]
    ).parse("Show SUVs")
    assert result.predicates[0].values == ["suv"]
    assert seen == ["openrouter/free", "google/gemma-4-26b-a4b-it:free"]


@pytest.mark.parametrize("status", [400, 401, 404, 422, 429, 500])
def test_provider_status_mapping(monkeypatch, status):
    response = httpx.Response(status, request=httpx.Request("POST", "https://example.test"))
    mock_post(monkeypatch, lambda *args, **kwargs: response)
    with pytest.raises(ParserError) as exc:
        OpenRouterParser("openrouter/free", "key").parse("Show SUVs")
    assert exc.value.code == (
        "llm_configuration_error" if status in {400, 401, 404, 422} else "llm_unavailable"
    )


def test_provider_http_408_maps_to_timeout(monkeypatch):
    response = httpx.Response(408, request=httpx.Request("POST", "https://example.test"))
    mock_post(monkeypatch, lambda *args, **kwargs: response)
    with pytest.raises(ParserError) as exc:
        OpenRouterParser("openrouter/free", "key").parse("Show SUVs")
    assert exc.value.code == "llm_timeout"


def test_openrouter_maps_truncation_and_invalid_json(monkeypatch):
    responses = [openrouter_response("{", finish_reason="length"), openrouter_response("{")]
    mock_post(monkeypatch, lambda *args, **kwargs: responses.pop(0))
    with pytest.raises(ParserError) as exc:
        OpenRouterParser("openrouter/free", "key", fallback_models=["fallback"]).parse("Show SUVs")
    assert exc.value.code == "llm_invalid_response"


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"choices": {}},
        {"choices": ["bad"]},
        {"choices": [{"finish_reason": "stop", "message": "bad"}]},
    ],
)
def test_openrouter_rejects_invalid_response_shapes(monkeypatch, payload):
    response = httpx.Response(
        200,
        json=payload,
        request=httpx.Request("POST", "https://example.test"),
    )
    mock_post(monkeypatch, lambda *args, **kwargs: response)
    with pytest.raises(ParserError) as exc:
        OpenRouterParser("openrouter/free", "key").parse("Show SUVs")
    assert exc.value.code == "llm_invalid_response"


def test_gemini_maps_quota_to_unavailable(monkeypatch):
    response = httpx.Response(429, request=httpx.Request("POST", "https://example.test"))
    mock_post(monkeypatch, lambda *args, **kwargs: response)
    with pytest.raises(ParserError) as exc:
        GeminiParser("gemini-3.8-flash", "key").parse("Show SUVs")
    assert exc.value.code == "llm_unavailable"


def test_gemini_accepts_complete_structured_response(monkeypatch):
    response = httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": json.dumps(VALID_EXTRACTION)}]},
                }
            ]
        },
        request=httpx.Request("POST", "https://example.test"),
    )
    mock_post(monkeypatch, lambda *args, **kwargs: response)
    result = GeminiParser("gemini-test", "key").parse("Show SUVs")
    assert result.predicates[0].values == ["suv"]


def test_gemini_uses_supported_schema_dialect(monkeypatch):
    captured = {}

    def respond(*args, **kwargs):
        captured.update(kwargs["json"]["generationConfig"]["responseSchema"])
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": json.dumps(VALID_EXTRACTION)}]},
                    }
                ]
            },
            request=httpx.Request("POST", "https://example.test"),
        )

    mock_post(monkeypatch, respond)
    GeminiParser("gemini-test", "key").parse("Show SUVs")

    def contains_unsupported(value):
        if isinstance(value, dict):
            return "additionalProperties" in value or any(
                contains_unsupported(item) for item in value.values()
            )
        if isinstance(value, list):
            return any(contains_unsupported(item) for item in value)
        return False

    assert not contains_unsupported(captured)


@pytest.mark.parametrize("finish_reason", ["MAX_TOKENS", "SAFETY", None])
def test_gemini_rejects_non_terminal_output(monkeypatch, finish_reason):
    response = httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "finishReason": finish_reason,
                    "content": {"parts": [{"text": json.dumps(VALID_EXTRACTION)}]},
                }
            ]
        },
        request=httpx.Request("POST", "https://example.test"),
    )
    mock_post(monkeypatch, lambda *args, **kwargs: response)
    with pytest.raises(ParserError) as exc:
        GeminiParser("gemini-test", "key").parse("Show SUVs")
    assert exc.value.code == "llm_invalid_response"


@pytest.mark.parametrize(
    "change",
    [
        {"preferences": [{"code": "safety", "evidence": "not present"}]},
        {"sort": "price_asc", "sort_evidence": "not present"},
    ],
)
def test_provider_rejects_ungrounded_preference_and_sort_evidence(monkeypatch, change):
    payload = {**VALID_EXTRACTION, **change}
    mock_post(monkeypatch, lambda *args, **kwargs: openrouter_response(payload))
    with pytest.raises(ParserError) as exc:
        OpenRouterParser("openrouter/free", "key").parse("Show SUVs")
    assert exc.value.code == "llm_invalid_response"


def test_provider_timeout_mapping(monkeypatch):
    def fake_post(*args, **kwargs):
        raise httpx.ReadTimeout("timed out")

    mock_post(monkeypatch, fake_post)
    with pytest.raises(ParserError) as exc:
        OpenRouterParser("openrouter/free", "key").parse("Show SUVs")
    assert exc.value.code == "llm_timeout"


def test_provider_wall_clock_deadline_cancels_slow_transport(monkeypatch):
    async def slow_post(*args, **kwargs):
        await asyncio.sleep(1)
        return openrouter_response(VALID_EXTRACTION)

    monkeypatch.setattr("vehicle_search.llm._post", slow_post)
    started = time.perf_counter()
    with pytest.raises(ParserError) as exc:
        OpenRouterParser("openrouter/free", "key", timeout_seconds=0.05).parse("Show SUVs")
    assert exc.value.code == "llm_timeout"
    assert time.perf_counter() - started < 0.25


def test_provider_cannot_bypass_deterministic_clarification(monkeypatch):
    mock_post(
        monkeypatch,
        lambda *args, **kwargs: openrouter_response(
            {
                **VALID_EXTRACTION,
                "predicates": [],
            }
        ),
    )
    result = OpenRouterParser("openrouter/free", "key").parse("Low mileage cars")
    assert any(issue["code"] == "ambiguous" for issue in result.issues)


def test_provider_cannot_add_constraints_or_clarification_to_supported_query(monkeypatch):
    payload = {
        **VALID_EXTRACTION,
        "issues": [{"code": "ambiguous", "evidence": "SUVs"}],
    }
    mock_post(monkeypatch, lambda *args, **kwargs: openrouter_response(payload))
    with pytest.raises(ParserError) as exc:
        OpenRouterParser("openrouter/free", "key").parse("Show SUVs")
    assert exc.value.code == "llm_invalid_response"

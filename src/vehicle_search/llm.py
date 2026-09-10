from __future__ import annotations

import json
from pathlib import Path

import httpx

from .parsing import ParserError, parse_provider_json, require_supported_coverage

SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["search", "clarify", "out_of_scope"]},
        "predicates": {"type": "array", "items": {"type": "object", "properties": {
            "field": {"type": "string"}, "op": {"type": "string"},
            "values": {"type": "array", "items": {"type": "string"}}, "evidence": {"type": "string"}},
            "required": ["field", "op", "values", "evidence"], "additionalProperties": False}},
        "preferences": {"type": "array", "items": {"type": "object", "properties": {
            "code": {"type": "string"}, "evidence": {"type": "string"}},
            "required": ["code", "evidence"], "additionalProperties": False}},
        "sort": {"type": "string"}, "sort_evidence": {"type": "string"},
        "issues": {"type": "array", "items": {"type": "object", "properties": {
            "code": {"type": "string"}, "evidence": {"type": "string"}},
            "required": ["code", "evidence"], "additionalProperties": False}},
        "policy_terms": {"type": "array", "items": {"type": "object", "properties": {
            "code": {"type": "string"}, "evidence": {"type": "string"}},
            "required": ["code", "evidence"], "additionalProperties": False}},
    },
    "required": ["intent", "predicates", "preferences", "sort", "sort_evidence", "issues", "policy_terms"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = Path(__file__).with_name("parsing").joinpath("prompt.txt").read_text()


class JsonParser:
    provider = "unknown"

    def parse(self, query: str):  # pragma: no cover - interface
        raise NotImplementedError


class OpenRouterParser(JsonParser):
    provider = "openrouter"

    def __init__(self, model: str, api_key: str, timeout_seconds: float = 10, max_tokens: int = 1600, fallback_models: list[str] | None = None):
        self.model, self.api_key, self.timeout, self.max_tokens = model, api_key, timeout_seconds, max_tokens
        self.models = list(dict.fromkeys([model, *(fallback_models or [])]))

    def parse(self, query: str):
        last = None
        for model in self.models:
            payload = {"model": model, "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": query}], "temperature": 0, "max_tokens": self.max_tokens, "reasoning": {"effort": "none"}, "response_format": {"type": "json_schema", "json_schema": {"name": "vehicle_intent", "strict": True, "schema": SCHEMA}}}
            try:
                return _parse_openai_compatible("https://openrouter.ai/api/v1/chat/completions", {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "HTTP-Referer": "http://localhost:8000", "X-Title": "AI Vehicle Search Engine"}, payload, query, self.timeout)
            except ParserError as error:
                last = error
                if error.code not in {"llm_invalid_response", "llm_unavailable"}: raise
        raise last or ParserError("llm_unavailable", "OpenRouter provider unavailable")


class GeminiParser(JsonParser):
    provider = "gemini"

    def __init__(self, model: str, api_key: str, timeout_seconds: float = 10, max_tokens: int = 1600):
        self.model, self.api_key, self.timeout, self.max_tokens = model, api_key, timeout_seconds, max_tokens

    def parse(self, query: str):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {"systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]}, "contents": [{"role": "user", "parts": [{"text": query}]}], "generationConfig": {"temperature": 0, "maxOutputTokens": self.max_tokens, "responseMimeType": "application/json", "responseSchema": SCHEMA}}
        try:
            response = httpx.post(url, params={"key": self.api_key}, json=payload, timeout=self.timeout)
            if response.status_code in {401, 403}: raise ParserError("llm_configuration_error", "Gemini credentials or model configuration rejected")
            if response.status_code == 429 or response.status_code >= 500: raise ParserError("llm_unavailable", "Gemini provider unavailable")
            response.raise_for_status(); data = response.json(); candidates = data.get("candidates", [])
            if not candidates: raise ParserError("llm_invalid_response", "Gemini returned no extraction")
            finish = candidates[0].get("finishReason")
            if finish in {"MAX_TOKENS", "SAFETY", "RECITATION"}: raise ParserError("llm_invalid_response", "Gemini refused or truncated the extraction")
            text = "".join(p.get("text", "") for p in candidates[0].get("content", {}).get("parts", []))
            if not text: raise ParserError("llm_invalid_response", "Gemini returned no extraction")
            return require_supported_coverage(parse_provider_json(text, query), query)
        except ParserError: raise
        except httpx.TimeoutException as exc: raise ParserError("llm_timeout", "Gemini request timed out") from exc
        except (httpx.HTTPError, json.JSONDecodeError) as exc: raise ParserError("llm_unavailable", "Gemini provider unavailable") from exc


def _parse_openai_compatible(url, headers, payload, query, timeout):
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        if response.status_code in {401, 403}: raise ParserError("llm_configuration_error", "OpenRouter credentials or model configuration rejected")
        if response.status_code == 429 or response.status_code >= 500: raise ParserError("llm_unavailable", "OpenRouter provider unavailable")
        response.raise_for_status(); data = response.json(); choice = (data.get("choices") or [{}])[0]; finish = choice.get("finish_reason")
        if finish in {"length", "content_filter"}: raise ParserError("llm_invalid_response", "OpenRouter refused or truncated the extraction")
        text = choice.get("message", {}).get("content")
        if not text: raise ParserError("llm_invalid_response", "OpenRouter returned no extraction")
        return require_supported_coverage(parse_provider_json(text, query), query)
    except ParserError: raise
    except httpx.TimeoutException as exc: raise ParserError("llm_timeout", "OpenRouter request timed out") from exc
    except (httpx.HTTPError, json.JSONDecodeError) as exc: raise ParserError("llm_unavailable", "OpenRouter provider unavailable") from exc


def build_parser(provider: str, model: str, api_key: str, timeout_seconds: float = 10, max_tokens: int = 1600, fallback_models: list[str] | None = None):
    if provider == "openrouter": return OpenRouterParser(model, api_key, timeout_seconds, max_tokens, fallback_models)
    if provider == "gemini": return GeminiParser(model, api_key, timeout_seconds, max_tokens)
    raise ParserError("llm_configuration_error", f"unsupported LLM_PROVIDER: {provider}")

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import httpx

from .parsing import ParserError, parse_provider_json, require_supported_coverage

SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["search", "clarify", "out_of_scope"]},
        "predicates": {
            "type": "array",
            "maxItems": 16,
            "items": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": [
                            "price_inr",
                            "odometer_km",
                            "year",
                            "seats",
                            "adult_safety_stars",
                            "child_safety_stars",
                            "body_type",
                            "fuel_type",
                            "transmission",
                            "make",
                            "model",
                            "city",
                            "condition",
                            "features",
                        ],
                    },
                    "op": {
                        "type": "string",
                        "enum": ["eq", "lt", "lte", "gt", "gte", "in", "not_in", "contains_all"],
                    },
                    "values": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "items": {"type": "string", "minLength": 1, "maxLength": 80},
                    },
                    "evidence": {"type": "string", "minLength": 1, "maxLength": 200},
                },
                "required": ["field", "op", "values", "evidence"],
                "additionalProperties": False,
            },
        },
        "preferences": {
            "type": "array",
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "enum": ["family", "safety", "affordability", "low_odometer"],
                    },
                    "evidence": {"type": "string", "minLength": 1, "maxLength": 200},
                },
                "required": ["code", "evidence"],
                "additionalProperties": False,
            },
        },
        "sort": {
            "type": "string",
            "enum": [
                "unspecified",
                "relevance",
                "price_asc",
                "price_desc",
                "odometer_asc",
                "year_desc",
            ],
        },
        "sort_evidence": {"type": "string"},
        "issues": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "enum": [
                            "unsupported",
                            "ambiguous",
                            "unverifiable",
                            "contradictory",
                            "missing_fields",
                        ],
                    },
                    "evidence": {"type": "string", "minLength": 1, "maxLength": 200},
                },
                "required": ["code", "evidence"],
                "additionalProperties": False,
            },
        },
        "policy_terms": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "enum": ["family", "high_safety", "five_star_safety"],
                    },
                    "evidence": {"type": "string", "minLength": 1, "maxLength": 200},
                },
                "required": ["code", "evidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "intent",
        "predicates",
        "preferences",
        "sort",
        "sort_evidence",
        "issues",
        "policy_terms",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = Path(__file__).with_name("parsing").joinpath("prompt.txt").read_text()


def _gemini_schema(value):
    """Translate the application schema to Gemini's supported schema dialect."""
    if isinstance(value, dict):
        return {
            key: _gemini_schema(item)
            for key, item in value.items()
            if key != "additionalProperties"
        }
    if isinstance(value, list):
        return [_gemini_schema(item) for item in value]
    return value


class JsonParser:
    provider = "unknown"

    def parse(self, query: str):  # pragma: no cover - interface
        raise NotImplementedError


class OpenRouterParser(JsonParser):
    provider = "openrouter"

    def __init__(
        self,
        model: str,
        api_key: str,
        timeout_seconds: float = 10,
        max_tokens: int = 1600,
        fallback_models: list[str] | None = None,
    ):
        self.model, self.api_key, self.timeout, self.max_tokens = (
            model,
            api_key,
            timeout_seconds,
            max_tokens,
        )
        self.models = list(dict.fromkeys([model, *(fallback_models or [])]))

    def parse(self, query: str):
        return asyncio.run(self._parse(query))

    async def _parse(self, query: str):
        last = None
        deadline = time.monotonic() + self.timeout
        for model in self.models:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ParserError("llm_timeout", "OpenRouter request timed out")
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                "temperature": 0,
                "max_tokens": self.max_tokens,
                "reasoning": {"effort": "none"},
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "vehicle_intent", "strict": True, "schema": SCHEMA},
                },
            }
            try:
                return await _parse_openai_compatible(
                    "https://openrouter.ai/api/v1/chat/completions",
                    {
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": os.getenv("APP_URL", "http://localhost:8000"),
                        "X-Title": "AI Vehicle Search Engine",
                    },
                    payload,
                    query,
                    remaining,
                )
            except ParserError as error:
                last = error
                if error.code not in {"llm_invalid_response", "llm_unavailable"}:
                    raise
        raise last or ParserError("llm_unavailable", "OpenRouter provider unavailable")


class GeminiParser(JsonParser):
    provider = "gemini"

    def __init__(
        self, model: str, api_key: str, timeout_seconds: float = 10, max_tokens: int = 1600
    ):
        self.model, self.api_key, self.timeout, self.max_tokens = (
            model,
            api_key,
            timeout_seconds,
            max_tokens,
        )

    def parse(self, query: str):
        return asyncio.run(self._parse(query))

    async def _parse(self, query: str):
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": query}]}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": self.max_tokens,
                "responseMimeType": "application/json",
                "responseSchema": _gemini_schema(SCHEMA),
            },
        }
        try:
            async with asyncio.timeout(self.timeout):
                response = await _post(
                    url, params={"key": self.api_key}, json=payload, timeout=self.timeout
                )
            if response.status_code in {400, 401, 403, 404, 422}:
                raise ParserError(
                    "llm_configuration_error", "Gemini credentials or model configuration rejected"
                )
            if response.status_code == 408:
                raise ParserError("llm_timeout", "Gemini request timed out")
            if response.status_code == 429 or response.status_code >= 500:
                raise ParserError("llm_unavailable", "Gemini provider unavailable")
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ParserError("llm_invalid_response", "Gemini returned an invalid response")
            candidates = data.get("candidates", [])
            if (
                not isinstance(candidates, list)
                or not candidates
                or not isinstance(candidates[0], dict)
            ):
                raise ParserError("llm_invalid_response", "Gemini returned no extraction")
            finish = candidates[0].get("finishReason")
            if finish != "STOP":
                raise ParserError(
                    "llm_invalid_response", "Gemini refused or truncated the extraction"
                )
            content = candidates[0].get("content")
            parts = content.get("parts") if isinstance(content, dict) else None
            if not isinstance(parts, list) or not all(isinstance(part, dict) for part in parts):
                raise ParserError("llm_invalid_response", "Gemini returned an invalid response")
            text = "".join(part.get("text", "") for part in parts)
            if not text:
                raise ParserError("llm_invalid_response", "Gemini returned no extraction")
            return require_supported_coverage(parse_provider_json(text, query), query)
        except ParserError:
            raise
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ParserError("llm_timeout", "Gemini request timed out") from exc
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise ParserError("llm_unavailable", "Gemini provider unavailable") from exc


async def _post(url: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        return await client.post(url, **kwargs)


async def _parse_openai_compatible(url, headers, payload, query, timeout):
    try:
        async with asyncio.timeout(timeout):
            response = await _post(url, headers=headers, json=payload, timeout=timeout)
        if response.status_code in {400, 401, 403, 404, 422}:
            raise ParserError(
                "llm_configuration_error", "OpenRouter credentials or model configuration rejected"
            )
        if response.status_code == 408:
            raise ParserError("llm_timeout", "OpenRouter request timed out")
        if response.status_code == 429 or response.status_code >= 500:
            raise ParserError("llm_unavailable", "OpenRouter provider unavailable")
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ParserError("llm_invalid_response", "OpenRouter returned an invalid response")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ParserError("llm_invalid_response", "OpenRouter returned an invalid response")
        choice = choices[0]
        finish = choice.get("finish_reason")
        if finish != "stop":
            raise ParserError(
                "llm_invalid_response", "OpenRouter refused or truncated the extraction"
            )
        message = choice.get("message", {})
        if not isinstance(message, dict):
            raise ParserError("llm_invalid_response", "OpenRouter returned an invalid response")
        text = message.get("content")
        if not isinstance(text, str) or not text:
            raise ParserError("llm_invalid_response", "OpenRouter returned no extraction")
        return require_supported_coverage(parse_provider_json(text, query), query)
    except ParserError:
        raise
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise ParserError("llm_timeout", "OpenRouter request timed out") from exc
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise ParserError("llm_unavailable", "OpenRouter provider unavailable") from exc


def build_parser(
    provider: str,
    model: str,
    api_key: str,
    timeout_seconds: float = 10,
    max_tokens: int = 1600,
    fallback_models: list[str] | None = None,
):
    if provider == "openrouter":
        return OpenRouterParser(model, api_key, timeout_seconds, max_tokens, fallback_models)
    if provider == "gemini":
        return GeminiParser(model, api_key, timeout_seconds, max_tokens)
    raise ParserError("llm_configuration_error", f"unsupported LLM_PROVIDER: {provider}")

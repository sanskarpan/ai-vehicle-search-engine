# AI Vehicle Search Engine

[![CI](https://github.com/sanskarpan/ai-vehicle-search-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/sanskarpan/ai-vehicle-search-engine/actions/workflows/ci.yml)

FastAPI backend for searching a synthetic Indian vehicle catalogue with natural-language queries. The assignment brief asks for a backend, a README/API description, `DESIGN.md`, and reproducible realistic seed data. This repository also includes the architecture, specification, evaluation plan and builder prompt.

## Quickstart (offline, no API key)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements.lock
python -m pip install --no-build-isolation --no-deps --editable .
python -m vehicle_search.seed --count 300 --seed 42
uvicorn vehicle_search.api:app --app-dir src --reload
```

Open <http://127.0.0.1:8000/docs>. The offline parser is intentionally conservative and clearly labelled in responses; it supports the documented grammar for the assignment examples. Try:

```bash
curl -s http://127.0.0.1:8000/api/v1/search \
  -H 'content-type: application/json' \
  -d '{"query":"Show SUVs under ₹15L","limit":10}'
curl -s http://127.0.0.1:8000/api/v1/search \
  -H 'content-type: application/json' \
  -d '{"query":"Diesel automatic cars below 80k km"}'
curl -s http://127.0.0.1:8000/api/v1/search \
  -H 'content-type: application/json' \
  -d '{"query":"Family cars with high safety ratings"}'
```

Prices and safety ratings are synthetic demonstration values. They are not live inventory or NCAP certifications. “Under/below” is strict; “up to/at most” is inclusive. Family and high-safety meanings are disclosed in the response and in `SPEC.md`.

## LLM mode and configuration

The example configuration uses OpenRouter’s `openrouter/free` router, which selects an available free model. OpenRouter uses its chat-completions endpoint and JSON Schema `response_format`; the adapter sends no catalogue text and allows no tools. To target a specific model, set `LLM_MODEL` to a currently available slug. To use Google directly, set `LLM_PROVIDER=gemini`, set an available Gemini model in `LLM_MODEL`, and provide `GEMINI_API_KEY`. The adapter requests structured JSON and applies the same local validation for either provider. Keep keys in the ignored `.env`, never commit them. Verify model availability for the account before live evaluation because provider catalogues and free routes can change.

The hosted adapter performs one bounded structured-output extraction call; application code validates the result and executes only allowlisted SQL predicates. Default tests never call the network. `ALLOW_OFFLINE_FALLBACK` is false by default. When enabled, timeout, transient unavailability or provider output that fails deterministic validation uses the conservative parser and is explicitly marked `parser_mode: offline`, `degraded: true`. The fallback returns either an exact supported interpretation or a safe clarification, never a partial search. Credential and model configuration errors do not fall back. `RENDER_API_KEY` is a deployment credential and is not read by the application.

| Variable | Purpose | Default |
|---|---|---|
| `PARSER_MODE` | Select `offline` or `llm` extraction | `offline` |
| `LLM_PROVIDER` | Select `openrouter` or `gemini` | `openrouter` |
| `LLM_MODEL` | Provider model slug | `openrouter/free` in `.env.example` |
| `OPENROUTER_API_KEY` / `GEMINI_API_KEY` | Credential for the selected provider | unset |
| `OPENROUTER_FALLBACK_MODELS` | Ordered models tried after the primary OpenRouter model | documented list in `.env.example` |
| `LLM_TIMEOUT_SECONDS` | Deadline for the single provider call | `10` |
| `LLM_MAX_OUTPUT_TOKENS` | Provider response ceiling | `1600` |
| `ALLOW_OFFLINE_FALLBACK` | Permit a disclosed conservative fallback after eligible provider failures | `false` |
| `DATABASE_PATH` | SQLite catalogue location | `./data/catalogue.db` |
| `APP_URL` | OpenRouter attribution URL | `http://localhost:8000` |

## API

| Method and path | Contract |
|---|---|
| `POST /api/v1/search` | Accepts `{query, limit?, offset?, sort?}` and returns the interpretation, exact total, paginated records, deterministic scores, grounded match reasons and execution metadata. |
| `GET /api/v1/vehicles/{vehicle_id}` | Returns the complete catalogue record and catalogue version, or the standard 404 envelope. |
| `GET /health/live` | Process liveness; does not depend on the catalogue. |
| `GET /health/ready` | Checks configuration and the seeded catalogue, and reports parser mode/version. |
| `GET /openapi.json`, `/docs`, `/redoc` | Machine-readable OpenAPI and interactive API documentation. |
| `GET /` | Responsive review frontend backed by the same public API. |

A successful search returns HTTP 200 with `status: ok`. A valid but ambiguous or unsupported request also returns HTTP 200 with `status: needs_clarification` and no partial results. Malformed request data is HTTP 422; an unseeded catalogue or unavailable provider is HTTP 503; invalid provider output is HTTP 502; provider timeout is HTTP 504. Requests above 8 KiB receive HTTP 413. Errors use `{request_id, error: {code, message, retryable}}`. Every JSON response and `X-Request-ID` header share one request identifier. See [SPEC.md](SPEC.md) for the field-level schemas, comparator semantics and sorting contract.

Useful error-path checks after startup:

```bash
curl -i http://127.0.0.1:8000/api/v1/search \
  -H 'content-type: application/json' \
  -d '{"query":""}'
curl -i http://127.0.0.1:8000/api/v1/vehicles/does-not-exist
```

The deployed review environment is [ai-vehicle-search-engine-0a7f.onrender.com](https://ai-vehicle-search-engine-0a7f.onrender.com/). Check its health and version before relying on it because Render deployments and free provider capacity are external services.

## Tests and evaluation

```bash
pytest -q
ruff format --check src tests
ruff check src tests
python -m vehicle_search.evaluate --dataset data/golden_queries.jsonl
python -m vehicle_search.evaluate --dataset data/heldout_queries.jsonl
```

The deterministic evaluator checks status, canonical predicates/preferences/sort, exact anchor result sets and an independent hard-predicate oracle. Live model evaluation is opt-in and requires credentials. Run the seed command with `--reset` only when intentionally replacing the local demo database. Use `--count 300 --seed 42` for the documented dataset.

Build the production container with `docker build -t ai-vehicle-search .` and run it with `docker run --rm -p 8000:8000 ai-vehicle-search`. The image installs the pinned runtime and build toolchain from `requirements.runtime.lock`, seeds at startup, runs as a nonroot user and exposes a readiness health check.

To enable a hosted parser, copy `.env.example` to `.env`, add your provider key, set `PARSER_MODE=llm`, and restart Uvicorn with `--env-file .env`. The checked-in quickstart intentionally stays offline so a clean clone works without credentials.

## Repository guide

- `SPEC.md` — authoritative behavior and API/data contracts.
- `ARCHITECTURE.md` — module boundaries and security/data-flow decisions.
- `DESIGN.md` — reviewer-facing design rationale.
- `EVALUATION.md` — golden queries, boundaries and release gates.
- `CHECKLIST.md` — implementation evidence ledger.
- `prompt.md` — handoff prompt for a coding model.
- `RESEARCH.md` — cited technical/domain research and limitations.

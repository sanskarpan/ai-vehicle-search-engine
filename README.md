# AI Vehicle Search Engine

FastAPI backend for searching a synthetic Indian vehicle catalogue with natural-language queries. The assignment brief asks for a backend, a README/API description, `DESIGN.md`, and reproducible realistic seed data. This repository also includes the architecture, specification, evaluation plan and builder prompt.

## Quickstart (offline, no API key)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements.lock
python -m pip install --no-deps --editable .
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

## LLM mode

The default local `.env` is configured for OpenRouter’s `openrouter/free` router, which selects an available free model. OpenRouter uses its chat-completions endpoint and JSON Schema `response_format`; the adapter sends no catalogue text and allows no tools. To target a specific model, set `LLM_MODEL` to a currently available slug. To use Google directly, set `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-3.8-flash`, and provide `GEMINI_API_KEY`. Keep keys in the ignored `.env`, never commit them. The Gemini API supports structured JSON output for this model. Verify model availability for the account before live evaluation because provider catalogues and free routes can change.

The hosted adapter performs one bounded structured-output extraction call; application code validates the result and executes only allowlisted SQL predicates. Default tests never call the network. `ALLOW_OFFLINE_FALLBACK` is false by default. When enabled, only provider timeout or transient unavailability may use the conservative parser, only if it completely understands the request. Invalid output, refusal, truncation and configuration failures never fall back. `RENDER_API_KEY` is a deployment credential and is not read by the application.

## API

`POST /api/v1/search` accepts `{query, limit?, offset?, sort?}`. It returns an interpretation, exact total, paginated catalogue records, deterministic score, grounded match reasons and a `meta` object containing parser mode, provider, degradation state, catalogue version, timings and warnings. A valid but ambiguous or unsupported request returns HTTP 200 with `status: needs_clarification` and no partial results. Malformed request data is HTTP 422; an unseeded catalogue is HTTP 503. `GET /api/v1/vehicles/{id}` returns a single record. `/health/live` and `/health/ready` provide liveness/readiness. OpenAPI is available at `/openapi.json`. Requests above 8 KiB receive HTTP 413. Every JSON response and `X-Request-ID` header share one request identifier.

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

Build the production container with `docker build -t ai-vehicle-search .` and run it with `docker run --rm -p 8000:8000 ai-vehicle-search`. The image installs `requirements.runtime.lock`, seeds at startup, runs as a nonroot user and exposes a readiness health check.

To enable a hosted parser, copy `.env.example` to `.env`, add your provider key, set `PARSER_MODE=llm`, and restart Uvicorn with `--env-file .env`. The checked-in quickstart intentionally stays offline so a clean clone works without credentials.

## Repository guide

- `SPEC.md` — authoritative behavior and API/data contracts.
- `ARCHITECTURE.md` — module boundaries and security/data-flow decisions.
- `DESIGN.md` — reviewer-facing design rationale.
- `EVALUATION.md` — golden queries, boundaries and release gates.
- `CHECKLIST.md` — implementation evidence ledger.
- `prompt.md` — handoff prompt for a coding model.
- `RESEARCH.md` — cited technical/domain research and limitations.

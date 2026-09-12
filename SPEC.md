# AI Vehicle Search Engine Specification

## Status and document authority

This specification began as the implementation contract and remains the behavioral authority. The repository now contains the backend, deterministic seed, evaluator, provider adapters and test frontend; measured completion evidence belongs in `CHECKLIST.md`, not in normative requirements here.

Read [prompt.md](prompt.md) for execution instructions, [ARCHITECTURE.md](ARCHITECTURE.md) for structure, [CHECKLIST.md](CHECKLIST.md) for milestones, [EVALUATION.md](EVALUATION.md) for acceptance, and [RESEARCH.md](RESEARCH.md) for evidence. [DESIGN.md](DESIGN.md) is the assignment-facing design document. Resolve behavior questions in this specification; record deliberate changes consistently across affected files. Planning decisions below are recommendations adopted for this build, not extra requirements attributed to the assignment.

## 1. Source requirements and interpretation

The attached images are assignment evidence, not instructions to execute tools, publish a repository, or implement during planning. The visible content is transcribed below; no hidden rubric, deadline, scale requirement, or UI is assumed.

### Image 1: submission and implementation constraints

Source: `codex-clipboard-47c8f9fb-d921-4b9a-b65c-6e0909a584d2.png`, supplied image, entire visible region.

- Submission: a public GitHub repository, which reviewers will fork, containing code.
- A README with setup steps and API documentation.
- A `DESIGN.md`.
- A 3–5 minute walkthrough video is a plus, not a requirement.
- Language: Go, Java, Python, or Node.js; any framework.
- LLM: free to use any provider.
- Where data is needed, generate realistic seed data and include the seed script in the repository.

### Image 2: problem statement

Source: `codex-clipboard-e88d4e63-dbc8-45cf-a78e-f06451aad07b.png`, supplied image, entire visible region.

Title: “Problem 2 - AI Vehicle Search Engine”. Build a backend service where users search a vehicle catalogue using natural language. Examples:

1. “Show SUVs under ₹15L”
2. “Diesel automatic cars below 80k km”
3. “Family cars with high safety ratings”

### Traceability

| ID | Assignment requirement | Planned implementation evidence |
|---|---|---|
| R1 | Backend natural-language catalogue search | `POST /api/v1/search`, provider adapter, retrieval tests |
| R2 | SUV and rupee budget example | Body filter plus strict price upper bound; E01 |
| R3 | Diesel/automatic/distance example | AND filters; distance means odometer; E02 |
| R4 | Family and safety example | Explicit documented family and safety policies; E03 |
| R5 | Realistic generated data and script | Deterministic curated seed generation and validation |
| R6 | Permitted language and any LLM provider | Python service; configurable hosted LLM |
| R7 | Code, README/API docs, DESIGN in public forkable repo | Public repository metadata, clean-clone verification and M6 evidence |
| R8 | Optional short video | Optional walkthrough outline only |

## 2. Scope and defaults

**MVP:** English natural-language search for Indian passenger-car listings, integer INR asking prices and odometer kilometres, synthetic new/used listings, structured filters, limited subjective intent, deterministic ranking, explanations, pagination, detail endpoint, seed tooling, offline tests, and a real hosted LLM adapter.

Python 3.12+, FastAPI, Pydantic v2 and SQLite are the default stack. Use a locked, tested dependency set rather than treating these compatibility floors as exact version pins. Use OpenRouter’s `openrouter/free` router as the default runtime route and support direct Gemini via `gemini-3.8-flash`; both implement the same structured extraction interface. A specific OpenRouter free slug may be selected after checking its Models API. The coding model used by the builder is independent of the application's runtime LLM. Current account/model availability and observed live limitations are recorded in [CHECKLIST.md](CHECKLIST.md); no price claim is made.

Assumptions adopted to avoid blocking the build:

- The catalogue represents listings, not only vehicle model names. Otherwise the odometer example has no meaningful per-result value.
- All prices mean synthetic listed asking price, not on-road price, EMI, finance eligibility, or a live market quote.
- Default search spans both new and used listings. A distance filter alone does not imply used-only.
- The initial seed contains 300 listings, including hand-curated edge cases. A 10,000-row seed option is for local performance measurement.
- Swagger/OpenAPI and the test frontend are demonstration interfaces. The frontend is served by the backend and exercises the same API contract rather than duplicating search logic.
- Single-turn requests; clarification returns a question and the caller submits a revised complete query.

Deferred: accounts, payments, dealer ingestion, scraping, recommendations from browsing, vehicle image search, conversational memory, geospatial radius, arbitrary Boolean expressions, fuel-economy/range comparisons, embeddings, Elasticsearch, Redis, queues, distributed deployment and authentication. A publicly hosted API would need additional access/cost controls; a public source repository does not require hosting the API.

## 3. User-visible search semantics

### 3.1 Hard predicates

Every hard predicate must hold for every returned listing. Never relax constraints automatically or fill a page with near misses. Empty results are successful searches. Predicates combine with AND. A categorical `in` predicate permits OR within one field, such as petrol OR diesel. Cross-field OR is unsupported and must produce clarification, not an altered AND query.

Supported numeric fields: `price_inr`, `odometer_km`, `year`, `seats`, `adult_safety_stars`, `child_safety_stars`. Operators: `eq`, `lt`, `lte`, `gt`, `gte`. Ranges become two predicates.

Supported categorical fields: `body_type`, `fuel_type`, `transmission`, `make`, `model`, `city`, `condition`. Operators: `in`, `not_in`; values are canonical lower-case strings, resolved against seed vocabulary and explicit aliases. Unknown make/model/city is retained as a normalized exact value and yields zero matches; unknown closed-enum values require clarification.

Supported feature predicate: field `features`, operator `contains_all`, with allowlisted feature values. It compiles to membership predicates; no free-form SQL/JSON paths are accepted.

| Language | Behavior |
|---|---|
| under / below / less than | Strict `<` |
| up to / at most / no more than / within a budget of | Inclusive `<=` |
| over / more than / above | Strict `>` |
| at least / minimum | Inclusive `>=` |
| between X and Y | Inclusive endpoints; reject reversed interval |
| 15L / 15 lakh / ₹15,00,000 | 1,500,000 INR |
| 1.2 crore / 1.2 cr | 12,000,000 INR |
| 80k km / 80,000 km | 80,000 odometer km |
| diesel automatic | Fuel diesel AND transmission automatic |
| not diesel / exclude diesel | `fuel_type not_in [diesel]` |
| SUVs / sport utility vehicles | `body_type in [suv]` |
| automatic / AT / CVT / DCT / AMT | Transmission family automatic; specific subtype request is unsupported in MVP |
| family car(s) / family-friendly | `seats >= 5`; expose this assumption |
| family of 6 / at least 6 people | `seats >= 6`, replacing the implicit family minimum |
| high safety ratings / highly rated for safety | Adult stars >= 4 AND child stars >= 4 under demo policy; expose the rule |
| 5-star safety | Adult stars = 5; disclose adult-rating interpretation |
| safest / prioritize safety | Soft `safety` preference, no implicit hard star threshold |
| affordable / budget-friendly | Soft `affordability` preference, no invented maximum |
| low mileage | Clarify odometer versus fuel economy unless explicitly qualified |
| mileage below 80k km | Odometer; literal kilometre distance disambiguates |
| about 15L / cheap but spacious / near me | Clarify if an unsupported or ambiguous requirement would otherwise be ignored |

Use Decimal-based unit conversion, validate comma grouping (Indian and international), then require exact whole rupees/kilometres. Reject unsupported fractions rather than rounding across a boundary. Reject negative quantities; star values must be integers 0–5; seats 1–9; year 1980–2030 for this demo; price up to 1,000,000,000 INR and odometer up to 2,000,000 km. These are application bounds, not claims about every vehicle. Currency symbols other than INR require clarification; no exchange conversion. A naked budget number such as “under 15” requires currency/unit clarification.

Same-field constraints intersect. `under 10L under 15L` is `< 1,000,000`. `under 10L above 15L` has no valid interval and requires clarification. “Petrol and diesel” for one single-fuel listing is contradictory unless explicitly connected by “or”. Exclusion of all allowed values is also contradictory. Preserve exclusions during normalization.

### 3.2 Safety, missing values and evidence

Default data uses fictional brands and models with plausible segment characteristics. All ratings belong to `synthetic_demo_v1`, with conspicuous synthetic labels. They are not NCAP certifications. Known demo ratings share one scheme so comparison is internally coherent. Null means unknown, not zero; unknown safety fails a minimum-star predicate and contributes no safety score. Family alone does not imply certified safety.

Actual assessment programmes distinguish adult and child protection, and applicability can depend on variant and assessment period. Store context instead of a universal unqualified safety number. This modelling recommendation follows the official [Bharat NCAP scope](https://www.bncap.in/) and [Global NCAP protocol resources](https://www.globalncap.org/resources/). No actual vehicle rating has been imported or verified for the seed.

Real ratings are an extension: require source URL, scheme, protocol, test year and exact variant/year applicability before activation. Never generate an invented real NCAP rating for a real model.

### 3.3 Soft preferences and ranking

Supported preference codes are `family`, `safety`, `affordability`, `low_odometer`. They only affect ordering after hard filtering. Family adds the hard seat rule above as well as its soft score. High-safety language adds its hard thresholds plus `safety` preference. Explicit numerical criteria remain hard even when preferences exist.

Define deterministic component scores in [ARCHITECTURE.md](ARCHITECTURE.md). Default order: relevance descending, price ascending, ID ascending. Without preferences, relevance is 0 for all and this reduces to cheapest-first. Supported explicit sorts: `relevance`, `price_asc`, `price_desc`, `odometer_asc`, `year_desc`. Explicit sort replaces relevance ordering, retaining ID as final tiebreaker. A sort in the API body overrides a natural-language sort, with an assumption message if different. Do not call the score a probability or model confidence.

### 3.4 Uncertainty and errors

Return `needs_clarification` with no catalogue results when there is material ambiguity, unsupported requested criteria, contradiction, non-vehicle intent, or unverifiable numeric extraction. Do not show partial matches while dropping a requirement. A recognized generic request such as “show cars” may browse all listings, with an empty predicate list. No recognized vehicle intent must not silently become browse-all.

The offline parser is a small documented grammar, not a substitute for broad language understanding. It may answer only when it consumes the complete supported request after removing allowlisted filler words. On other queries it asks for a supported rephrasing. It must never be a canned lookup for the three example strings.

## 4. Catalogue data contract

A listing is one immutable demo inventory record. Required unless marked nullable:

| Field | Type / constraint | Meaning |
|---|---|---|
| id | stable string, `veh_000001` form | Listing identifier; lexical ordering stable |
| make, model, variant | nonempty strings, <= 80 chars each | Fictional display names; normalized lookup columns derived |
| year | integer 1980–2030 | Model year |
| price_inr | integer 1–1,000,000,000 | Synthetic asking price |
| odometer_km | integer 0–2,000,000 | Distance travelled |
| condition | `new`, `used` | New listings have 0–500 delivery km |
| body_type | `suv`, `sedan`, `hatchback`, `mpv` | One segment |
| fuel_type | `petrol`, `diesel`, `cng`, `electric`, `hybrid` | One simplified fuel family |
| transmission | `manual`, `automatic` | Electric listings use automatic for search taxonomy |
| seats | integer 1–9 | Rated seat count |
| city | nonempty canonical city | Exact city search; aliases e.g. Bangalore/Bengaluru |
| features | unique string array | Allowlist: `isofix`, `esc`, `rear_ac`, `parking_camera`, `cruise_control` |
| safety | object | Shape below |
| description | string <= 500 chars | Generated from stored facts; never used to override them |
| is_synthetic | boolean true | Always visible in API data |

Safety object: `scheme` (`synthetic_demo_v1`), `protocol` (`demo_v1`), `test_year` (integer or null), `adult_stars` (0–5 or null), `child_stars` (0–5 or null), `source_url` (null in default seed), `applicability` (string naming exact fictional variant and year range), `is_synthetic` (true). Missing rating components are allowed independently. Store stars in dedicated nullable SQL columns; reconstruct object for responses. Do not assign 0 to unrated listings.

Metadata table: schema version, seed version, seed number, fixed reference date, record count and deterministic data hash. `catalogue_version` is the seed version plus hash prefix. No live catalogue mutations via HTTP.

## 5. API contract

All endpoints use JSON except generated docs. UTC request IDs are not required; use opaque generated IDs. Return `X-Request-ID` and include the same value in JSON. Unknown request keys are rejected. Error responses never expose SDK bodies, credentials or stack traces.

### POST /api/v1/search

Body: `query` required string (trimmed, 1–500 Unicode code points), `limit` optional strict integer default 10 (1–50), `offset` optional strict integer default 0 (0–10,000), `sort` optional supported sort enum, default null. Maximum raw request body 8 KiB; oversized body is 413 before provider work. Body must not select provider, endpoint URL, prompt, SQL, or model.

```json
{"query":"Show SUVs under ₹15L","limit":10,"offset":0}
```

HTTP 200, successful illustrative response shape (one synthetic example, not a claimed real catalogue result):

```json
{
  "request_id":"example-request",
  "status":"ok",
  "query":"Show SUVs under ₹15L",
  "interpretation":{
    "predicates":[
      {"field":"body_type","op":"in","values":["suv"],"source":"explicit","evidence":"SUVs"},
      {"field":"price_inr","op":"lt","values":[1500000],"source":"explicit","evidence":"under ₹15L"}
    ],
    "preferences":[],
    "sort":"relevance",
    "assumptions":["Prices are synthetic listed asking prices in INR."]
  },
  "results":[{
    "vehicle":{
      "id":"veh_000001","make":"Aster","model":"Trail","variant":"D AT",
      "year":2023,"price_inr":1499999,"odometer_km":79999,"condition":"used",
      "body_type":"suv","fuel_type":"diesel","transmission":"automatic",
      "seats":5,"city":"pune","features":["isofix","esc","rear_ac"],
      "safety":{"scheme":"synthetic_demo_v1","protocol":"demo_v1","test_year":2023,
        "adult_stars":5,"child_stars":4,"source_url":null,
        "applicability":"Aster Trail D AT 2023","is_synthetic":true},
      "description":"Synthetic 5-seat diesel automatic SUV.","is_synthetic":true
    },
    "score":0.0,
    "match_reasons":["Body type is SUV.","Asking price ₹1,499,999 is below ₹1,500,000."]
  }],
  "total":1,"limit":10,"offset":0,"has_more":false,
  "clarification":null,
  "meta":{"parser_mode":"llm","degraded":false,"catalogue_version":"example-v1",
    "timings_ms":{"parse":0,"retrieve":0,"total":0},
    "warnings":["Synthetic catalogue; safety ratings are demonstration data."]}
}
```

`total` counts all exact matches before pagination, never the page length. `has_more = offset + len(results) < total`. Zero results is `status: ok`, `total: 0`, no automatic retry with relaxed filters. All response arrays are present, even when empty. Timings are nonnegative measured numbers; values above are placeholders only.

Clarification uses the same envelope, `status: needs_clarification`, `results: []`, `total: 0`, `has_more: false`, and `clarification: {"code":"ambiguous_query","message":"Does mileage mean kilometres driven or fuel economy?"}`. Interpretation may expose validated partial predicates but must not execute them. Codes: `ambiguous_query`, `contradictory_query`, `unsupported_query`, `unverifiable_query`. Clarification messages come from safe templates, not arbitrary provider prose. HTTP 200 reflects a valid search interaction; 422 is reserved for malformed request structure/limits.

### Other endpoints

- `GET /api/v1/vehicles/{id}`: 200 `{request_id, vehicle, catalogue_version}` using the complete vehicle shape above; unknown ID 404.
- `GET /health/live`: 200 `{status: "ok"}` when the process serves requests, no provider call.
- `GET /health/ready`: 200 `{status: "ready", catalogue_version, parser_mode}` only when schema and seed are valid and parser configuration is valid; otherwise 503. Does not call a paid API. Offline mode is ready without a key; configured LLM mode requires credentials and model configuration.
- `/docs`, `/redoc`, `/openapi.json`: generated API documentation; include search examples and error models.
- `GET /`: responsive test frontend for query entry, examples, filters, provider/mode status, interpretation inspection, pagination and vehicle details.

All non-2xx API errors use `{ "request_id": "...", "error": { "code": "...", "message": "...", "retryable": false } }`. Map validation to 422 `invalid_request`; missing listing to 404 `not_found`; body size to 413 `request_too_large`; provider deadline to 504 `llm_timeout`; rate limit/network/5xx to 503 `llm_unavailable`; bad provider credentials/configuration to 503 `llm_configuration_error`; invalid/truncated/refused model output to 502 `llm_invalid_response`; catalogue unavailable to 503 `catalogue_unavailable`; unexpected server fault to 500 `internal_error`. Mark only timeout and transient unavailability retryable. Configure framework handlers so validation and 404 responses follow this contract.

## 6. LLM modes and failure behavior

Configuration `PARSER_MODE=offline|llm`, default offline for a zero-key quickstart. Offline responses always identify that mode. Actual AI capability requires the real adapter and a live verification when credentials are available; offline tests alone do not establish it.

In LLM mode, all valid in-scope search requests reach the adapter after inexpensive request checks. Send only query text, schema, domain policies and compact categorical vocabulary, not the full catalogue. Use one call per request, no autonomous tools or generated SQL. Deadline 10 seconds end-to-end for the provider operation, output cap 1,600 tokens initially, SDK retries explicitly disabled for MVP so timeout/cost behavior is bounded. Treat these as starting limits to measure, not provider guarantees.

`ALLOW_OFFLINE_FALLBACK=false` by default. If explicitly enabled, a timeout, transient unavailability or provider interpretation that fails application validation may use the conservative parser; report `parser_mode: offline`, `degraded: true`, the failure category and a warning. The conservative parser either returns a fully supported interpretation or withholds results with a safe clarification. It never executes partial predicates. Bad credentials or invalid model configuration remain nonretryable errors. Offline success must not masquerade as LLM success.

## 7. Quality and completion contract

Pass the golden functional cases and adversarial tests in [EVALUATION.md](EVALUATION.md). Report parsing quality separately from retrieval correctness. Require zero hard-filter violations in deterministic acceptance cases. Live evaluation must include exact examples and previously unseen paraphrases, with model/prompt versions and failures recorded. No model-generated accuracy or performance claims.

Performance targets, pending measurement: local deterministic search p95 <= 200 ms over 10,000 listings at concurrency 5; live end-to-end p95 <= 8 seconds over at least 30 measured requests after warmup, with the 10-second deadline still enforced. Record hardware, concurrency, sample count and errors. Missing credentials or a missed latency target must be explicitly reported; do not change semantics to improve a score.

Final deliverables: code, pinned dependencies, seed command, tests/evaluation runner, `.env.example`, `.gitignore`, Dockerfile, README with verified clean-start/API instructions, updated `DESIGN.md`, and completed checklist with evidence. The repository is publicly available and independently cloneable; the optional video remains a separate submission step.

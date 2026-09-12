# AI Vehicle Search Engine Design

## Status

Implemented MVP design for the backend assignment. The deterministic offline path, seed tooling, API, evaluator, OpenRouter/Gemini adapters and test frontend are present. Live provider validation is an explicit measured gate using locally configured credentials. Detailed contracts live in [SPEC.md](SPEC.md), structure in [ARCHITECTURE.md](ARCHITECTURE.md) and acceptance in [EVALUATION.md](EVALUATION.md).

## Problem and chosen behavior

Users should be able to ask for vehicles naturally, including SUVs below a rupee budget, diesel automatics below a kilometre limit, and family cars with strong safety ratings. Numeric filters must be exact, subjective language must have visible meaning, and returned facts must be traceable to inventory data.

The service represents individual synthetic listings with asking price, odometer, model/variant, fuel, transmission, seats, city, features and contextual safety data. It turns a query into a validated intent, retrieves exact matches, ranks them deterministically and returns structured JSON with an interpretation and factual match reasons. The bundled frontend makes this behavior inspectable without duplicating search logic. Ambiguous requests ask for clarification; valid searches with no matches stay empty.

## Main decisions

### D1 — LLM interpretation with deterministic execution

An LLM provides flexible language interpretation while application code handles quantities, comparisons, domain policies and SQL. This keeps the executable surface small and makes retrieval testable without a live model. The model cannot access a database tool or manufacture vehicle records. Structured shape validation does not guarantee semantic correctness, so evidence checks, supported-constraint scanning and held-out evaluation remain necessary.

### D2 — Small Python monolith and SQLite

One API process and one local catalogue are enough for a 300-row review dataset, with a 10,000-row measurement option. FastAPI supplies a typed API and interactive documentation. A server database, queue and vector index would add setup and validation work without addressing a stated requirement. SQLite's local-storage tradeoffs and future migration triggers are documented in ARCHITECTURE and RESEARCH.

### D3 — Explicit hard and soft semantics

Hard conditions are never relaxed to improve apparent relevance. Soft preferences rank only valid candidates. “Under ₹15L” excludes exactly ₹1,500,000; “up to ₹15L” includes it. “Below 80k km” refers to odometer distance, while unqualified “low mileage” asks for clarification. The API returns its interpretation so these decisions can be inspected.

Family language applies a disclosed seats >=5 policy, with an explicit family size taking precedence. High safety applies a disclosed adult-and-child >=4 threshold in a single fictional demo rating scheme. These are product heuristics adopted for the exercise, not definitions stated in the assignment or real safety assurances.

### D4 — Synthetic, coherent and reproducible inventory

Fictional brands/variants with plausible prices and coherent technical combinations satisfy the seed-data need without pretending to offer live market inventory. A fixed PRNG seed, reference date, curated templates and immutable boundary anchors make results repeatable. Safety fields carry synthetic provenance and preserve unknown values separately from zero stars. A future real-data import would need exact rating-source and applicability checks.

### D5 — Grounded explanations and stable ordering

Application templates describe why a listing matches. They do not generate new factual claims. Scores follow published formulas; ties are stable and pagination follows complete ranking. SQLite applies hard filters, computes the documented deterministic ordering and pages the globally ranked result set. Only the selected page is hydrated with features; a separate count over the same predicates supplies the exact total. An equivalence suite compares this path with the simple full-candidate Python reference implementation.

### D6 — Honest offline and live modes

A restricted offline grammar permits zero-key setup and deterministic tests. OpenRouter is the default hosted route for low-cost model experimentation, with direct Gemini available for comparison. Responses identify mode and any fallback. Missing live credentials never justify fabricated evidence, and a timeout cannot silently turn an unrestricted language request into a partially interpreted search. Provider keys remain local-only.

## Reliability and security boundaries

Request size and field validation precede paid calls. Provider calls have a deadline and bounded output. Upstream failures map to stable errors; no secrets or raw SDK responses reach clients. Canonical fields/operators are whitelisted and values are bound in SQL. The API reads inventory and cannot mutate it. Seed writes occur separately, with validation and transactions.

Prompt injection remains a semantic risk even with a constrained schema. Restricting model capabilities prevents generated text from directly executing SQL or tools; it does not prove all user intent was correctly extracted. Tests must exercise omitted negation, wrong units, injected instructions and malformed outputs as separate failure modes.

## Alternatives considered

A rules-only service is easier to run but weak as the sole demonstration of AI language interpretation. Free-form text-to-SQL has a broader validation surface. Embedding-only search cannot establish exact budget or distance compliance. A later hybrid can combine structured filtering and semantic ranking when a labelled relevance evaluation establishes benefit. No such benchmark has been performed.

## Expected review path

The README should support fresh install, deterministic seed, API startup and the three original example requests through curl or `/docs`. It should also demonstrate an inclusive/exclusive boundary, a zero-result request and clarification. The test suite must run without network access; live evaluation is a separate opt-in step with model/prompt versions and observed results.

## Implementation evidence

| Area | Current evidence |
|---|---|
| Code and dependency lock | `pyproject.toml`; editable install verified in `.venv` |
| Seed generation and reproducibility | `vehicle_search.seed`; 300-row seed smoke-tested |
| API and deterministic correctness | 100 pytest cases pass; 36/36 golden cases match canonical intent and exact results |
| Actual provider/model integration | OpenRouter and Gemini adapters implemented and transport-tested; the current live quality gate remains blocked by provider responses recorded in CHECKLIST |
| Parsing quality and safety of filtering | 24/24 held-out cases match canonical intent and exact results; zero oracle-detected hard-filter violations |
| Local latency | 10,000 rows, 100 full API requests at concurrency 5: p50 55.09 ms, p95 91.34 ms, max 106.51 ms on Python 3.12.10 / Darwin arm64 |
| Clean local/Docker setup | Exact runtime/development locks, nonroot image, health check and GitHub Actions verification; local Docker build verified during final audit |

## Known scope limits

English only; INR only; synthetic catalogue; single-turn search; limited supported attributes and subjective vocabulary; no cross-field Boolean OR; no real safety certification; no guarantees about actual affordability or suitability. Local review is the reproducible baseline. The public Render service is a review deployment; broader production use would require persistent managed data, monitoring, access control and cost controls.

The assignment requires a public GitHub repository with code, README/API documentation and this DESIGN file, plus a seed script. Those deliverables are present in the published repository and verified from an unauthenticated clean clone. A walkthrough video is optional.

## Evidence

See [RESEARCH.md](RESEARCH.md) for the primary-source inventory, research limits and dated references supporting the technical decisions. The source assignment is transcribed in SPEC so this document does not depend on access to temporary clipboard images.

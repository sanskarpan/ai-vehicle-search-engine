# AI Vehicle Search Engine Build Checklist

## How to use this checklist

This file records implementation progress against the planning contract. Checked items below have evidence in the repository and verification commands; the remaining unchecked items are genuinely pending. Read [prompt.md](prompt.md) first.

Dependency order: M0 -> M1 -> M2 -> M3 -> M4 -> M5 -> M6. Implement a complete deterministic search path before live-model integration. Optional scope must not delay core acceptance.

## M0 — Establish the contract

- [x] Read SPEC, ARCHITECTURE, EVALUATION, DESIGN and RESEARCH; preserve R1–R8 traceability.
- [x] Inspect current repository and applicable local instructions; preserve existing work.
- [x] Record adopted Python/dependency versions, OpenRouter/Gemini provider choices and model configuration approach.
- [x] Set up `pyproject.toml`, dependency ranges, package layout, `.gitignore`, `.env.example` and basic app factory.
- [x] Confirm code/model/schema version identifiers and strict API error envelope.

Exit evidence: package imports and a liveness smoke check pass; no secrets or generated DB tracked.

## M1 — Data and normalization

- [x] Implement catalogue schema, read-only repository, version checks and exact detail lookup.
- [x] Build curated fictional templates and all eight immutable evaluation anchors.
- [x] Implement seeded generation with fixed seed, 300 default rows and count option.
- [x] Prove reproducible logical data/hash, no-op same-seed rerun and explicit-reset behavior.
- [ ] Validate coherent variants, required category coverage and >10% unknown safety components.
- [x] Implement Decimal quantities, INR lakh/crore syntax, km shorthand and strict/inclusive comparators.
- [x] Implement enums/aliases, categorical exclusion, same-field OR, intersection and contradiction handling.
- [x] Implement family/safety policy expansion with visible assumptions and synthetic provenance.

Exit evidence: seed/data/normalization tests pass without network access; all three assignment examples have matching seed records.

## M2 — Deterministic search path

- [x] Compile only allowed canonical fields/operators to bound SQL values; no LLM-generated SQL.
- [x] Retrieve all exact candidates before ranking and paging; eliminate N+1 feature reads.
- [x] Implement specified scoring formulas, stable tiebreakers and explicit sort precedence.
- [x] Generate explanations from actual data and applied predicates.
- [x] Implement search/detail schemas, totals, offset, limits and clarification envelope.
- [x] Implement health/readiness, request size limit and HTTP error handler.
- [x] Use offline/fixture parser tests to test API behavior independently of live extraction.
- [x] Pass fixed anchor result sets, strict boundaries, unknown-rating and pagination tests.

Exit evidence: fixture-driven POST search, listing detail and exact counts pass; SQL compiler cannot access arbitrary fields.

## M3 — Natural-language parsing

- [x] Implement raw extraction schema, evidence validation and canonical internal contract.
- [ ] Build independent numeric/negation checks and unsupported/ambiguous query handling.
- [x] Implement conservative offline grammar with mode disclosure.
- [x] Pass offline versions of assignment examples plus varied quantities/word order; no canned responses.
- [x] Add structured-output provider adapters for OpenRouter (with configurable free-model fallback chain) and direct Gemini.
- [x] Verify provider HTTP schema support, original-schema validation and provider termination checks in adapter code.
- [x] Apply bounded provider deadline and output; OpenRouter/Gemini direct HTTP clients do not retry.
- [x] Add failure mapping; optional transient fallback is off by default and clearly labelled when enabled.
- [x] Add mock transport tests for refusal, truncation, invalid JSON, 401, 429, 5xx and timeout.

Exit evidence: offline path and SDK contract tests pass; real adapter exists and is reachable from LLM mode. If no key is available, mark live checks pending and continue all independent work.

## M4 — Evaluation and hardening

- [x] Implement labelled 36-case suite and 24 held-out paraphrases.
- [ ] Independently verify every result against labelled predicates and fixed anchor expectations.
- [x] Test prompt injection attempts, malicious descriptions, SQL injection strings and semantic omissions.
- [ ] Verify key/query redaction, error envelopes and no API writes.
- [x] Run deterministic pytest suite and lint.
- [x] Run deterministic evaluator and save a truthful summary (36/36 golden, 24/24 held-out offline status checks).
- [x] Run opt-in provider checks with supplied credentials; record actual responses and failures below.
- [ ] Meet live gates or document exact remaining cases; never count offline success as live evidence.
- [x] Benchmark 10,000-row search and inspect representative SQL query plans; record environment and percentiles.
- [ ] Measure live latency separately when available; report any misses rather than fabricating targets.

Exit evidence: deterministic gates green, zero measured hard-filter violations; live/performance gate status explicitly recorded.

## M5 — Reproducible packaging and docs

- [x] Add Dockerfile with nonroot runtime, frontend assets and documented seed-before-start flow (local daemon build pending).
- [x] Write README with verified local setup, configuration guidance, API curl examples and error examples.
- [x] Verify zero-key quickstart path; clearly label its restricted offline grammar.
- [x] Document OpenRouter/Gemini setup, request data sent to provider, token/timeout settings and pending live checks.
- [ ] Document synthetic asking prices/ratings, subjective policies, limitations and optional extensions.
- [x] Update DESIGN to reflect implemented backend, providers, frontend and measured/pending evidence.
- [x] Ensure SPEC, architecture, OpenAPI, README examples and evaluator agree after any changes.
- [x] Execute README commands in a fresh temporary checkout/copy without relying on hidden local files.
- [ ] Confirm generated OpenAPI has request, success, clarification and error models.
- [x] Add and smoke-test responsive frontend at `/` with examples, sorting, interpretation, pagination, detail and raw JSON states.

Exit evidence: clean checkout can seed, start and demonstrate all three examples; README commands actually tested.

## M6 — Submission handoff

- [x] Verify code, seed script, README/API documentation and DESIGN are present as required by Image 1.
- [x] Scan tracked files/diffs for credentials, personal paths, huge binaries and generated state.
- [ ] Summarize implementation, commands/results, pending live checks, known limits and final commit if one exists.
- [ ] Prepare repository for a public forkable GitHub submission; publication itself needs an explicit owner instruction.
- [ ] Owner confirms public repository is accessible/forkable and supplies submission URL.
- [ ] Optional: record a 3–5 minute walkthrough; this is not a release blocker.

## Completion ledger

| Gate | Status | Evidence / pending reason |
|---|---|---|
| Planning handoff | Prepared | Seven Markdown files |
| Data and pure domain | Complete | 300-row seed smoke test and anchors |
| Deterministic API | Complete | 11 API/domain/seed tests pass; 36/36 golden status checks |
| Offline grammar | Complete | 24/24 held-out status checks |
| Real provider adapter | Implemented | OpenRouter `openrouter/free` plus configurable free-model fallbacks and direct Gemini; 7 mocked transport tests pass |
| Live AI evaluation | Blocked by provider account state | 2026-09-10 run through OpenRouter `openrouter/free` and three configured free fallbacks returned only unavailable/invalid responses (HTTP 422 envelope, no fabricated result); Gemini `gemini-3.8-flash` returned HTTP 429 quota limit 0 |
| Performance | Measured | Python 3.12 / SQLite, 10,000 rows, 30 offline searches: p50 3.16 ms, p95 3.72 ms, max 3.92 ms; representative plan uses the vehicle primary-key index for stable ordering |
| Clean-start packaging | Partial | README quickstart and Dockerfile prepared; Docker daemon unavailable in this environment |
| Public submission | Owner action pending | No repository published by this plan |

## Stop conditions for the builder

Do not declare the assignment fully verified with only mocked/offline results. Do not stop all work because live credentials are absent: finish implementation, mocked adapter tests, offline demo, packaging and documentation, and explicitly report the remaining live gate. Escalate only an actual product-contract conflict, inaccessible required credential at the live gate, or an action outside the current authorization. Normal implementation choices should be resolved and documented locally.

# AI Vehicle Search Engine Research and Decision Record

## Research question and conclusion

The assignment needs a backend that searches a vehicle catalogue in natural language, plus code, setup/API documentation, a design document and reproducible realistic seed data. The recommended first implementation is a constrained language-to-filter service: one LLM extraction call, application-owned normalization and policies, exact relational filtering, deterministic ordering and grounded explanations.

This recommendation follows the assignment's concrete examples and a review of primary documentation for API validation, structured LLM output, SQL safety, storage/search alternatives and vehicle-rating context. It is a scope-specific engineering judgment. No competing stack or model has been benchmarked, and no implementation exists yet.

Research checked on 2026-09-10. Official documentation is often rolling and may change before implementation; the builder must verify its actual locked SDK/model combination. Coverage is targeted at material build decisions, not a claim to have exhausted every possible resource.

## 1. Reading both source images

The first image specifies submission format and allowed implementation choices. It makes `DESIGN.md` and README setup/API documentation part of the deliverable, permits Python/Node.js/Go/Java with any framework and permits any LLM provider. It explicitly calls for a seed script when data is needed. The walkthrough video is optional.[^I1]

The second image specifies a backend catalogue search service and three examples.[^I2] The examples imply different concerns:

| Example | Necessary capability | Ambiguity resolved in the proposed contract |
|---|---|---|
| SUVs under ₹15L | Category plus budget extraction, INR units and exact comparison | Asking price; strict upper limit; Indian passenger vehicles |
| Diesel automatic below 80k km | Conjunction across fuel, transmission and distance | Kilometres travelled per listing, rather than fuel economy |
| Family cars with high safety ratings | Subjective language mapped to inspectable criteria | Disclosed family seating rule and separate demo adult/child thresholds |

The first two examples can fail despite visually convincing results: a vehicle priced exactly at the excluded limit, or a petrol manual with a semantically similar description, would not satisfy the request. The third can fail through undocumented assumptions or fabricated real-world ratings. These are the principal quality risks addressed by the proposed design.

Neither image requires frontend development, live scraping, a particular cloud, a vector database, authentication, conversational state or a deployment URL. Those can be useful elsewhere but should not be inferred as assignment requirements. Publication and deployment were authorized by later user instructions and are recorded separately from the original image requirements. Full source transcription and requirement IDs appear in [SPEC.md](SPEC.md).

## 2. What the technical sources establish

### Typed API and validation

FastAPI documents response-model validation/filtering and a pytest-compatible testing approach.[^1][^2] Pydantic offers strict validation to reduce implicit coercion.[^3] These support a typed JSON contract and independent tests, but do not answer whether a model correctly understood “under”, an exclusion or a subjective request. Domain semantics must therefore be tested separately from JSON shape.

The chosen application contract distinguishes malformed HTTP input, a valid request needing clarification, an empty exact result set and a provider failure. Combining these into one generic response would make both review and debugging harder. This distinction is a proposed product/API decision.

### Structured LLM output

OpenRouter documents OpenAI-compatible chat completions and JSON Schema `response_format`, including strict output and response healing support.[^4a][^4b] Google's Gemini 3.8 Flash model documentation lists structured outputs, and its `generateContent` API accepts JSON response settings.[^4c][^4d] These sources support two constrained adapters. They do not establish a particular account's quota, free-route availability, accuracy or cost. Keep the provider behind an interface and require a configured, live-tested model. Preserve numeric literals so code, rather than generated arithmetic, converts lakh/crore values.

A simpler schema with bounded filter atoms is a better fit here than a recursive query-language AST. The supported query surface is deliberately limited: AND between fields, OR within a categorical field, numeric comparisons, a few policies and sort preferences. Unsupported expressions should be observable clarifications. This reduces both implementation ambiguity and the number of failure paths the builder must verify.

### SQL and database choice

Python's SQLite documentation recommends parameter substitution for values.[^5] The application additionally needs an allowlist for columns, operators and sort fragments. Parameterization cannot turn arbitrary model-selected identifiers into a safe query design.

SQLite's documented local-storage and concurrency tradeoffs support considering it for a small review service.[^6] The 300-row seed and 10,000-row measurement option are chosen planning targets. They are not limits provided by the assignment or benchmark results. A move to a shared transactional catalogue would change the operational requirements and justify reevaluating storage.

### Full-text and vector alternatives

FTS5 provides lexical full-text retrieval.[^7] pgvector documents vector search and the interaction between approximate indexes and filters.[^8] Neither source establishes that an embedding architecture is necessary for these three assignment examples.

The useful future question is whether a labelled set of unmet queries requires description similarity beyond structured attributes. If it does, retain hard filters and measure a hybrid ranker against the deterministic baseline. Compare result validity, semantic relevance, latency, recall and setup burden; do not accept a convincing anecdotal query as proof of improvement.

### Prompt-injection boundaries

OWASP recommends separating instructions and data, validating outputs and restricting privileges.[^9] This supports keeping the runtime model away from tools and direct database execution. It does not justify claiming that prompt injection has been eliminated.

The relevant residual failure is semantic: a schema-valid extraction can omit “not”, reverse a comparison or invent a threshold. A second deterministic scan catches supported numeric/negation discrepancies; adversarial and held-out tests expose other failures. Adding a second LLM as a guardrail is unnecessary for this assignment and would introduce another probabilistic component rather than prove correctness.

## 3. Vehicle-domain data findings

Bharat NCAP describes adult protection, child protection and safety-assist assessment areas.[^10] Global NCAP publishes separate assessment protocols and historical versions.[^11] This supports retaining rating context rather than treating all “stars” as an unqualified scalar. It does not establish a universal numeric definition of “high safety”.

The proposed adult >=4 AND child >=4 threshold is therefore explicitly a demo policy. Fictional ratings in one scheme avoid inventing real certification. The project should not portray a generated rating on a fictional model as a finding from either NCAP programme. A checked source for rating methodology is not evidence for a particular vehicle's rating.

Realistic seed data is best produced from curated fictional variant templates. Coherent combinations matter more to this assignment than a large uncontrolled dataset: seats, fuel, transmission, age, price and odometer should agree plausibly, with new/used conditions respected. Fixed anchors then make the exact boundaries testable. Descriptions can be generated from fields, avoiding another uncertain source of facts.

No live listing data, actual prices or model-specific certifications were collected. An official vehicle-specific Bharat NCAP page appeared in search but failed on direct opening; it is not relied on for an actual vehicle claim and contributes no seed values. This limitation reinforces using methodology sources only for the data model.

## 4. Decision comparison

The following assessment is qualitative and specific to the assignment; it is not a performance ranking.

| Approach | Strength | Main risk | Decision |
|---|---|---|---|
| Rules alone | Predictable, offline and easily tested | Language coverage too narrow for sole AI implementation | Keep as transparent demo mode |
| Constrained LLM intent + relational filters | Flexible phrasing with inspectable constraints | Schema-valid semantic misinterpretation | MVP, with evidence checks and evaluation |
| Free-form text-to-SQL | Broad query expressiveness | Larger executable surface and difficult semantic validation | Reject for MVP |
| Vector-only retrieval | Similarity over descriptive language | Near matches can violate explicit numeric constraints | Reject as sole retrieval method |
| Hybrid structured and vector retrieval | Can improve open-ended relevance | Requires data, tuning and operational complexity | Add only after a measured need |
| LLM selects/rewrites catalogue results | Natural prose | Unsupported facts and extra latency | Use code-generated facts/reasons instead |

The architecture deliberately favors a short end-to-end path that a reviewer can inspect. Most effort should go into parsing semantics, data coherence, boundary testing and reproducible setup, because those directly establish the assignment behavior. Infrastructure breadth would consume effort without proving these outcomes.

## 5. Open uncertainties and verification plan

| Uncertainty | Current position | Resolution during build |
|---|---|---|
| Runtime credentials/model entitlement | Credentials were supplied and inspected privately after planning; no key is committed. OpenRouter free capacity fell back safely, while Gemini listed `gemini-3.8-flash` but returned HTTP 429 for live generation. | Retain disclosed fallback; rerun the separate live-quality gate when provider quota is available. |
| Model accuracy on India-specific units and phrases | Unknown | Golden cases plus held-out paraphrases; zero hard-constraint violations |
| Target latency and cost | Not measured | Record latency distributions and tokens; calculate money only from verified current pricing if needed |
| Preferred domain interpretation | Assignment leaves terms open | Adopt visible policies in SPEC; change only consistently with tests |
| Real market realism | No live data verified | Curated fictional distributions; no market-value claims |
| Production scale/security expectations | Not in the brief | Keep local-review scope; document deployment as future work |

[CHECKLIST.md](CHECKLIST.md) converts these decisions into implementation gates. [EVALUATION.md](EVALUATION.md) supplies exact anchors, query labels and failure cases. This separation prevents a successful model demo from being confused with correct SQL, or correct SQL from being confused with a verified AI feature.

## Sources

Dates are publication/update dates only where explicitly available. Otherwise they are marked rolling or undated rather than inferred from search-engine crawl dates. All online references were accessed 2026-09-10.

[^I1]: Supplied assignment image, `codex-clipboard-47c8f9fb-d921-4b9a-b65c-6e0909a584d2.png`, date not visible; directly inspected entire image. Transcribed in SPEC section 1; no public URL.
[^I2]: Supplied assignment image, `codex-clipboard-e88d4e63-dbc8-45cf-a78e-f06451aad07b.png`, date not visible; directly inspected entire image. Transcribed in SPEC section 1; no public URL.
[^1]: FastAPI, [Response Model – Return Type](https://fastapi.tiangolo.com/tutorial/response-model/), undated. Supports typed response contract choice.
[^2]: FastAPI, [Testing](https://fastapi.tiangolo.com/tutorial/testing/), undated. Supports isolated API verification approach.
[^3]: Pydantic, [Strict Mode](https://docs.pydantic.dev/latest/concepts/strict_mode/), rolling documentation. Supports explicit validation choices.
[^4a]: OpenRouter, [Structured Outputs](https://openrouter.ai/docs/guides/features/structured-outputs), rolling documentation. Supports JSON Schema response format and strict output.
[^4b]: OpenRouter, [Chat Completions API](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request), rolling documentation. Supports the compatible endpoint and request shape.
[^4c]: Google, [Gemini 3.8 Flash model](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash), rolling documentation. Lists structured output capability.
[^4d]: Google, [Gemini generateContent API](https://ai.google.dev/api/generate-content), rolling documentation. Documents response MIME/schema configuration.
[^5]: Python Software Foundation, [sqlite3 — DB-API 2.0 interface for SQLite databases](https://docs.python.org/3/library/sqlite3.html), rolling documentation. Supports value parameterization and connection implementation.
[^6]: SQLite, [Appropriate Uses for SQLite](https://www.sqlite.org/whentouse.html), updated 2025-05-31. Supports local database tradeoff analysis.
[^7]: SQLite, [FTS5 Extension](https://www.sqlite.org/fts5.html), rolling documentation. Supports lexical-search alternative assessment.
[^8]: pgvector maintainers, [pgvector README — Filtering](https://github.com/pgvector/pgvector#filtering), rolling repository documentation. Supports the need to assess filtering/recall behavior when adding approximate vectors.
[^9]: OWASP, [LLM Prompt Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html), undated. Supports validation, separation and least-privilege boundaries.
[^10]: Bharat NCAP, [Safety evaluation scope](https://www.bncap.in/), undated. Supports separate safety dimensions, not any synthetic or real listing rating.
[^11]: Global NCAP, [Resources and assessment protocols](https://www.globalncap.org/resources/), current and archived protocol catalogue. Supports preserving assessment context and protocol version.

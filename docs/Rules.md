# LLM-EvalHub: Engineering Rules

These rules apply to every contributor and every coding agent. They are binding. If a rule conflicts with a request, say so and follow the rule unless the owner explicitly overrides it.

---

## 1. Honesty rules (highest priority)

1. **Never fabricate** AI outputs, evaluation scores, model rankings, recommendations or benchmark results.
2. **Unavailable is not zero.** A metric that cannot be computed is stored and shown as unavailable with a reason. Never substitute `0`, `null`-as-zero or a guess.
3. **Label provenance.** Every metric carries a kind: `deterministic`, `llm_judge` or `measured`. The UI must show which.
4. **Mock results are not benchmarks.** Anything produced by the `mock` provider is labelled test-only and must never be quoted as model quality.
5. **No universal claims.** Never say a model is "best". Recommendations are conditional on the profile, constraints and the evidence in the system.
6. **State limits.** Recommendations, diagnoses and reports must include caveats (sample size, judge noise, lexical fallbacks).
7. **Cap confidence.** Failure and diagnosis confidence never exceeds 0.95.
8. **Do not claim what was not run.** Never say a deployment, CI run, live provider call or test passed unless it actually ran. Say "not verified" instead.
9. **Cite uncertain facts as unverified.** Paper references and external claims written from memory must be flagged "verify".

## 2. Security rules

1. API keys live only in backend environment variables (or encrypted workspace settings once added). They are never sent to, stored in, or bundled into the frontend.
2. Never log keys, tokens or passwords. Extend the redaction filter when adding a new secret type.
3. Never commit secrets. Keep `.env` in `.gitignore`; keep `.env.example` complete with placeholder values only.
4. Validate every upload (type, size, structure) and every request body (Pydantic).
5. Overrides applied by the improvement loop must pass the `APPLICABLE_FIELDS` whitelist.
6. Do not expose a public instance until authentication exists.
7. Return generic error messages for auth failures; no user enumeration.

## 3. Architecture rules

1. **Layers point downward**: presentation → API → services → orchestration → providers / evaluation / RAG → persistence. Never import upward.
2. **Routes are thin.** No business logic in routers.
3. **Provider details stay in adapters.** The evaluation engine uses only the `LLMProvider` interface and normalised errors, usage and metadata.
4. **One source of truth per concept.** Shared logic (for example tokenisation in `app/core/text.py`) is reused, never copied. Retriever and metrics must use the same tokenizer.
5. **Evaluation config is stored with every experiment** so any run can be reproduced.
6. **SQLite persistence stays serialised** (lock) until the database layer changes.
7. **No giant files.** Split a file that grows past roughly 400 lines or mixes responsibilities.
8. **Record decisions.** Significant choices go in `docs/decisions.md` as a numbered ADR (next number after ADR-010).

## 4. Backend code rules

1. Python with full type hints; Pydantic for all API schemas.
2. Use async patterns for I/O; never block the event loop with provider or file calls.
3. Use typed exceptions from `core/exceptions.py`. Do not use bare `except` or `pytest.raises(Exception)`.
4. Retries honour `Retry-After`; never retry in a tight loop; always bound concurrency.
5. Handle rate limits, quota exhaustion, timeouts and malformed provider responses gracefully, with clear user-facing messages.
6. Naive and aware datetimes must not be mixed; normalise with the existing helpers.
7. Ruff must be clean (`ruff.toml`).
8. No dynamic-import hacks (`__import__`); use normal imports.
9. Keep functions small and named by intent; add docstrings to public service functions.

## 5. Frontend code rules

1. React function components and hooks; shared UI in `components/ui`, charts in `components/charts`.
2. All HTTP goes through `lib/api.js`. No direct Axios calls in pages.
3. Contract names must match the backend schema exactly (past bugs: `valid_rows` vs `accepted_rows`, `kind` vs `default_kind`). Check the schema before using a field.
4. Every data view needs loading, empty and error states, and retry where sensible.
5. Unavailable metrics render as "n/a" with the reason, never as zero bars.
6. Use theme tokens (CSS variables), never hard-coded colours (see `Design.md`).
7. Use only valid Tailwind utilities (for example `/20` opacity, not `/18`).
8. Keep animation subtle and respect `prefers-reduced-motion`.
9. Use static imports where possible; keep vendor chunk splitting working.

## 6. Testing rules

1. The test suite must be **deterministic and network-free**. Use the mock provider or test doubles.
2. Every new feature ships with tests: unit tests for logic, API tests for endpoints, a regression test for every fixed bug.
3. Secret-leak tests use a sentinel key and scan responses and captured logs.
4. Do not weaken or delete a test to make it pass. Fix the code or explain why the test was wrong.
5. Run `ruff` and the full suite before declaring work complete; also run the frontend build.
6. Mock-provider results verify the pipeline only.

## 7. Process rules for coding agents

1. Work autonomously and make sensible decisions; do not stop for approval on routine choices.
2. Verify library and provider APIs against current official documentation before using them.
3. Finish one phase's definition of done before starting the next (see `Phases.md`).
4. Do not add features outside the roadmap until the core loop works end to end.
5. Prefer the smallest change that solves the problem; do not refactor unrelated code.
6. Update `Memory.md` when you learn a durable fact, fix a notable bug or make a decision.
7. Update docs (`README.md`, `docs/architecture.md`, `docs/api.md`, `.env.example`) in the same change as the code.
8. Finish with an honest summary: what changed, what was verified, what was not.

## 8. Git rules

1. Small, focused commits with imperative messages (`Add significance test to comparison service`).
2. Do not commit generated artefacts, virtual environments, `node_modules`, databases or `.env`.
3. Never rewrite published history without the owner's approval.

## 9. Definition of done (per change)

- [ ] Behaviour implemented and honest (no fake values).
- [ ] Tests added; full suite passes; ruff clean; frontend build clean.
- [ ] Docs and `.env.example` updated.
- [ ] No secrets in code, logs or the frontend bundle.
- [ ] `Memory.md` updated if anything durable was learned.

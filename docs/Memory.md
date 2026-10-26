# LLM-EvalHub: Project Memory

Durable context for coding agents and contributors. Read this first, then `Rules.md`. Keep it short, factual and current. Add a dated line when you learn something that will matter later. Never store secrets here.

---

## 1. Identity and context

- **Project:** LLM-EvalHub, an evaluation-first GenAI platform. Loop: Evaluate → Compare → Diagnose → Recommend → Improve → Re-evaluate.
- **Owner:** Anubhav, MCA (Data Science), Chandigarh University, UID 25MCD10057.
- **Purpose:** portfolio-grade project and college mini project across five subjects: Generative AI, Data Mining and Warehousing, Data Visualization, Technical Training (Full Stack), Cloud Computing.
- **Working style wanted:** autonomous; make sensible decisions; do not ask routine questions; concise answers when the owner uses `/concise`.

## 2. Current state (at the end of the MVP)

| Item | Value |
|---|---|
| Backend | ~82 Python files, ~11,700 lines |
| Frontend | ~25 files, ~6,700 lines, 17 routes |
| Endpoints | ~50 |
| Providers | Groq, Hugging Face, Gemini, NVIDIA NIM, OpenRouter, Ollama (optional), mock |
| Tables | 16 |
| Benchmarks | 6 packs, 131 cases |
| Tests | 77 passing; ruff clean; frontend build clean |
| Deliverable | `llm-evalhub.zip` delivered earlier |

**Verified:** pipeline with the mock provider, seed script, live loop, ZIP extraction plus test run, no secrets in the repo.
**Not verified:** real-provider behaviour with live keys; Docker and CI on hosted environments; any cloud deployment.

## 3. Fixed technology choices

- Frontend: React 19, Vite 7, Tailwind 3 (CSS-variable tokens), React Router, Axios, Recharts, Lucide, Framer Motion.
- Backend: Python, FastAPI, Pydantic, SQLAlchemy, LangChain, LangGraph, RAGAS adapter plus custom evaluators.
- Data: SQLite (WAL) for development, PostgreSQL for production via `DATABASE_URL`; FAISS or NumPy vector index; hashing embedder by default.
- Theme: beige and olive green, Source Serif 4 everywhere, light and dark mode. **Do not change** (see `Design.md`).

## 4. Key design decisions (see `docs/decisions.md`, ADR-001 to ADR-010)

1. Provider abstraction: `LLMProvider` ABC; `OpenAICompatibleProvider` serves Groq, HF, OpenRouter, NIM, Ollama; native Gemini adapter; deterministic mock.
2. Metrics have `available` and `unavailable_reason`; never a silent zero.
3. Composite score is renormalised over available metrics.
4. Failure detection is an ordered cascade: infrastructure → retrieval → grounding → answer quality → latency; confidence capped at 0.95.
5. Diagnosis merges a heuristic catalogue with an optional LLM engine.
6. Improvement loop uses `clone_with_overrides` and an `APPLICABLE_FIELDS` whitelist.
7. Recommendation uses magnitude-preserving scoring (raw 0 to 1 quality; latency = fastest/this); profiles balanced, quality, faithfulness, latency, custom.
8. One LangGraph run per work unit (case × model): prepare → (retrieve) → generate → evaluate → detect_failure → persist; persistence serialised by an `asyncio.Lock`.
9. `create_all` for the MVP; Alembic deferred to the hardening phase.
10. Hashing embedder default so the app runs on low-spec hardware.

## 5. Lessons and gotchas (do not repeat these bugs)

- **Mock behaviour parsing:** the model name carries a `mock-` prefix; `_behaviour()` must strip it, otherwise all mock models behave the same.
- **Datetimes:** mixing naive and aware datetimes raised `TypeError` in run duration; use `_as_aware()`.
- **Recommendation normalisation:** min-max scaling collapsed two-candidate comparisons; magnitude-preserving scoring replaced it, with a regression test.
- **Tokenizer mismatch:** the retriever and metrics disagreed because of stemming. A shared tokenizer in `app/core/text.py` raised context recall from 0.53 to 0.91 and cut `poor_retrieval` misclassifications from 12 to 2 on the mock reference run.
- **Frontend contract drift:** `report.valid_rows` should be `accepted_rows`; metric spec `kind` should be `default_kind`. Always check backend schemas before using a field.
- **Tailwind:** `/18` is not a valid opacity step; use `/20`.
- **Secret-leak tests** must use a sentinel key to be meaningful.
- **Tests:** `pytest.raises(Exception)` was too loose; use specific exceptions such as `NotFoundError`.
- **Hooks:** keep imports static in `useRunPolling`.

## 6. Known limitations

No authentication or multi-user support; background runs are in-process; default metrics are lexical without an LLM judge; no significance testing; no judge calibration; hashing embedder is weaker than neural embeddings; benchmark packs are small; `create_all` only (no migrations); no PDF report; no hosted deployment performed; provider free-tier limits apply.

## 7. Configuration notes

- Judge model is set by `DEFAULT_EVALUATOR_PROVIDER` and `DEFAULT_EVALUATOR_MODEL` in `.env`.
- Some provider models are gated (the owner saw an "Enterprise" tag on `llama-3.3-70b-versatile`). Model availability changes; do not assume a model works. A model availability audit is planned (Phase 22).
- Provider keys live in backend environment variables only.

## 8. Planned work (see `Phases.md`)

| Phase | Upgrade |
|---|---|
| 22 | Model availability audit (list only verified-available models) |
| 23 | Significance testing (paired bootstrap, permutation tests, confidence intervals) |
| 24 | Judge calibration (human labels, Cohen's kappa, bias probes) |
| 25 | Counterfactual failure attribution (oracle-context and no-context re-runs) |
| 26 | Production hardening (auth, workspaces, durable jobs, Alembic) |
| 27 | Cloud deployment (only claim once actually performed) |

Prompts for several of these were already written for the owner; check the conversation history before rewriting them.

## 9. Open items and pending requests

- A 10-slide deck "How Do You Know Your LLM Evaluation Is Trustworthy?" was specified but **not built**. Resume only if the owner asks. Spec points: beige and olive palette, Source Serif 4 with Georgia fallback, at most 5 bullets per slide, a takeaway line on slides 2 to 9, speaker notes on every slide, placeholders for measured results, no invented numbers. Slide 1 presenter line: "Anubhav | MCA Data Science, Chandigarh University | UID 25MCD10057 | Subject: Generative AI".
- A theme change was discussed only as suggestions (five options) and **not applied**. The current theme stays.
- The college-submission README (`LLM-EvalHub_Project_README.md`) was delivered.

## 10. How to update this file

- Add a dated line under the relevant section: `- 2026-10-26: <fact>`.
- Replace outdated lines instead of piling up contradictions.
- Record only durable facts: decisions, constraints, gotchas, status changes.
- Do not record secrets, keys, personal data beyond the project identity above, or temporary state (branch names, ports).
- Do not store honesty-weakening instructions here; the rules in `Rules.md` always win.

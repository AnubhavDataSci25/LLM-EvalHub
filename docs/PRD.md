# LLM-EvalHub: Product Requirements Document (PRD)

| | |
|---|---|
| Product | LLM-EvalHub |
| Owner | Anubhav (MCA Data Science, Chandigarh University, UID 25MCD10057) |
| Status | MVP built; upgrades planned (see `Phases.md`) |
| Companion docs | `Architecture.md`, `Rules.md`, `Phases.md`, `Design.md`, `Memory.md` |

---

## 1. Summary

LLM-EvalHub is an **evaluation-first GenAI engineering platform**. It lets a developer run the same test cases against several hosted LLMs, score the answers with honest metrics, inspect and diagnose failures, get an evidence-based model recommendation, apply an improvement, and re-evaluate.

Core loop: **Evaluate → Compare → Diagnose → Recommend → Improve → Re-evaluate.**

It is not a chatbot and not a CRUD demo. The product's value is trustworthy evidence about LLM behaviour.

## 2. Problem

1. Teams pick models and prompts by "vibes"; results are not reproducible.
2. Each provider has its own SDK, errors and rate limits, so running one test set across several is tedious.
3. Average scores hide *why* answers fail (retrieval, hallucination, empty output, timeout, wrong answer).
4. Many tools display a score even when it could not be computed. A silent zero is indistinguishable from a real zero.
5. There is no closed path from "this failed" to "change this, re-run, and verify it improved".
6. Model choice is rarely justified by the user's own data and constraints.

## 3. Target users

| Persona | Need |
|---|---|
| **GenAI / backend developer** (primary) | Compare models and prompts on their own data; find out why cases fail |
| **RAG application builder** | Tune chunk size, top-k and retrieval; measure retrieval quality |
| **Student / learner** | Understand evaluation methodology on low-spec hardware with free-tier APIs |
| **Technical reviewer / interviewer** | See a credible, honest, well-engineered GenAI platform |

## 4. Goals and non-goals

### Goals
- G1. Run identical test cases across multiple providers and models.
- G2. Produce honest metrics with clear provenance (deterministic vs LLM-judge vs measured).
- G3. Explain failures with evidence and an AI diagnosis.
- G4. Close the improvement loop with before/after comparison.
- G5. Recommend models transparently from real evidence only.
- G6. Work on low-spec hardware; no local large model required.

### Non-goals (current scope)
- Training or fine-tuning models.
- Being a general chatbot or prompt playground.
- Multi-tenant SaaS hosting (planned, not built).
- Real-time production monitoring of live traffic.
- PDF report export (after core stability).

## 5. Functional requirements

Priority: **P0** = required for the minimum definition of done, **P1** = important, **P2** = nice to have.

### 5.1 Datasets (P0)
- FR-D1 Create datasets manually and import via CSV and JSON.
- FR-D2 Validate rows; report accepted and rejected rows with reasons.
- FR-D3 Preview, edit and delete datasets and test cases.
- FR-D4 Each case supports: question, expected answer, context, category, difficulty, metadata, optional expected sources.

### 5.2 Providers and models (P0)
- FR-P1 First-class adapters: Groq, Hugging Face Inference, Gemini, NVIDIA NIM, OpenRouter; Ollama optional.
- FR-P2 Consistent internal interface for generation, model metadata, parameters, errors, latency and usage.
- FR-P3 Typed errors for rate limit, invalid credentials, model unavailable, upstream error and timeout; retries honour `Retry-After`.
- FR-P4 Provider status shown clearly; unavailable providers are communicated, never silently skipped.
- FR-P5 A deterministic `mock` provider for tests (labelled as test-only).

### 5.3 Execution (P0)
- FR-X1 Run one dataset against one or more models with bounded concurrency.
- FR-X2 Capture answer, latency, errors and usage when available.
- FR-X3 Runs execute in the background with pollable progress, and can be retried.

### 5.4 Evaluation (P0)
- FR-E1 Metrics: correctness, answer relevance, faithfulness, context precision, context recall, latency, completeness.
- FR-E2 Each metric records its kind (deterministic, llm_judge, measured) and an availability flag with reason.
- FR-E3 Composite score is renormalised over available metrics only.
- FR-E4 An LLM judge is configurable (`DEFAULT_EVALUATOR_PROVIDER`, `DEFAULT_EVALUATOR_MODEL`); without one, lexical fallbacks are clearly labelled.

### 5.5 RAG (P1)
- FR-R1 Ingest PDF, TXT and Markdown; validate files.
- FR-R2 Chunking, embeddings (hashing default), vector storage (FAISS or NumPy).
- FR-R3 Vector, BM25 and hybrid (Reciprocal Rank Fusion) retrieval; context inspection.
- FR-R4 Retrieval-quality evaluation.

### 5.6 Experiments and comparison (P0)
- FR-T1 Store dataset, models, prompt, parameters, retriever settings, chunk size, top-k, timestamps and results for every run.
- FR-T2 Compare models and experiments side by side with deltas.

### 5.7 Failure analysis and diagnosis (P0)
- FR-F1 Show question, expected answer, generated answer, retrieved context, model, configuration and scores.
- FR-F2 Classify failures into 10 categories with an ordered cascade (infrastructure → retrieval → grounding → answer quality → latency); confidence capped at 0.95.
- FR-F3 Filter failures by category, model and severity.
- FR-F4 AI Diagnosis: structured diagnosis, likely root cause, confidence, recommended change, expected improvement direction.

### 5.8 Improvement loop (P0)
- FR-I1 Accept or modify a recommendation.
- FR-I2 Create a follow-up experiment via `clone_with_overrides`, restricted to a whitelist of applicable fields.
- FR-I3 Re-run relevant cases and show before vs after.

### 5.9 Recommendation engine (P0)
- FR-M1 Profiles: balanced, quality, faithfulness, latency, custom weights.
- FR-M2 Constraints (e.g. maximum latency, minimum faithfulness).
- FR-M3 Output ranking, score breakdown, evidence and caveats. Never claim a model is universally best; never use data that is not in the system.

### 5.10 Benchmark packs (P1)
- FR-B1 Six packs (RAG QA, customer support, document QA, citation grounding, structured extraction, summarization), 131 cases total.
- FR-B2 Each pack ships a dataset, evaluator configuration, metadata, recommended metrics and baseline settings.

### 5.11 Dashboard and reports (P0)
- FR-V1 KPI cards: total test cases, evaluations run, quality, faithfulness, relevance, latency, failure rate.
- FR-V2 Charts: model comparison, metric trends, failure distribution, experiment deltas, latency.
- FR-V3 Web reports (summary, dataset info, models, metrics, comparison, failed cases, RAG performance, latency, findings, recommendations) with JSON and CSV export.

### 5.12 Settings (P1)
- FR-S1 Provider configuration status. API keys are configured in backend environment variables and are never exposed to the frontend.

## 6. Non-functional requirements

| Area | Requirement |
|---|---|
| Honesty | No fake outputs, scores, rankings or recommendations. Unavailable means unavailable. |
| Security | No keys in the frontend; validated uploads and inputs; credential redaction in logs. |
| Reliability | Graceful handling of rate limits, quota exhaustion, timeouts and malformed responses. |
| Performance | Runs must not block the API; bounded concurrency; usable on low-spec hardware. |
| Maintainability | Clean layers, type hints, no giant files, no duplicated logic. |
| Testability | Deterministic, network-free test suite (77 tests at MVP). |
| Usability | Loading, empty and error states; progress indicators; retries; responsive layouts. |
| Accessibility | Sufficient contrast in light and dark mode; keyboard-reachable controls. |

## 7. Success metrics

| Metric | Target |
|---|---|
| Definition of done | A user can go from dataset upload to report with a recommendation and a before/after comparison, end to end |
| Test suite | All tests pass, ruff clean, frontend build clean |
| Honesty | Zero metrics shown as numbers when unavailable |
| Time to first evaluation | Under 5 minutes using a benchmark pack |
| Reproducibility | Any experiment can be re-run from its stored configuration |

## 8. Minimum definition of done

A user can: upload a dataset → select models/providers → run a real evaluation → see meaningful metrics → inspect results → compare models/experiments → analyse failures → receive a transparent recommendation → generate an AI diagnosis → create a follow-up experiment → compare before/after → generate a report.

## 9. Constraints and assumptions

- Roughly 27 days for the original MVP.
- Free-tier provider quotas apply and can change at any time.
- Real providers were not exercised live during development; verification used the mock provider.
- Single-user local use; no authentication yet.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Provider rate limits or retired models | Typed errors, retries, planned model availability audit |
| LLM-judge bias and noise | Label metric kinds; planned judge calibration |
| Differences within noise reported as wins | Planned significance testing |
| Lexical default metrics are weak | Configure an LLM judge; planned neural embeddings |
| Public deployment without auth | Planned production hardening; do not expose publicly until then |

## 11. Roadmap pointers

See `Phases.md` for the completed build order and the planned upgrades: significance testing, judge calibration, counterfactual failure attribution, production hardening, model availability audit.

## 12. Open questions

- Which hosted platform to use for a public demo.
- Whether to add cost tracking and cost-aware recommendation.
- Whether to add human-label import for calibration.

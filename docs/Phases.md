# LLM-EvalHub: Phases

The build order for the MVP (about 27 days) followed by planned upgrades. Each phase has a goal, deliverables and a definition of done (DoD). Do not start a phase before the previous DoD is met.

Status legend: ✅ done · 🔜 planned

---

## Part A: MVP build (completed)

| # | Phase | Status |
|---|---|---|
| 1 | Repository and architecture foundation | ✅ |
| 2 | Frontend and backend skeleton | ✅ |
| 3 | Database and dataset management | ✅ |
| 4 | Provider abstraction and hosted LLM integrations | ✅ |
| 5 | Model execution | ✅ |
| 6 | Evaluation engine | ✅ |
| 7 | LangGraph orchestration | ✅ |
| 8 | RAG pipeline | ✅ |
| 9 | Experiment tracking | ✅ |
| 10 | Dashboards and comparison | ✅ |
| 11 | Failure analysis | ✅ |
| 12 | AI diagnosis | ✅ |
| 13 | Recommendation engine | ✅ |
| 14 | Benchmark packs | ✅ |
| 15 | Improvement loop | ✅ |
| 16 | Reporting | ✅ |
| 17 | Security | ✅ |
| 18 | Testing | ✅ |
| 19 | Performance optimisation | ✅ |
| 20 | Documentation | ✅ |
| 21 | Deployment readiness (Docker, CI files) | ✅ files written, not run on hosted infrastructure |

### Phase details

**Phase 1: Foundation.** Repo layout, `.env.example`, `.gitignore`, MIT license, ADR log. *DoD:* clean structure, documented layers.

**Phase 2: Skeleton.** FastAPI app with health route; Vite + React + Tailwind shell with router. *DoD:* both run locally and talk to each other.

**Phase 3: Datasets.** Models, CSV/JSON import, validation, preview, edit, delete. *DoD:* accepted/rejected row reporting works.

**Phase 4: Providers.** `LLMProvider` ABC, OpenAI-compatible adapter, Gemini adapter, mock provider, typed errors, retries. *DoD:* all adapters share one interface; errors map correctly.

**Phase 5: Execution.** Bounded-concurrency runner capturing answer, latency, errors, usage. *DoD:* one dataset runs across several models.

**Phase 6: Evaluation.** Metrics with kinds and availability, judge, failure detector. *DoD:* unavailable metrics are never zero.

**Phase 7: Orchestration.** LangGraph workflow per work unit. *DoD:* RAG branch and persistence work.

**Phase 8: RAG.** Ingestion, chunking, hashing embedder, FAISS/NumPy, hybrid retrieval. *DoD:* retrieval metrics agree with retriever behaviour (shared tokenizer).

**Phase 9: Experiments.** Config snapshot per run, history, retry. *DoD:* any run reproducible.

**Phase 10: Dashboards and comparison.** KPI cards and five chart types. *DoD:* real data only.

**Phase 11: Failures.** Ten categories, filters, detail page. *DoD:* all evidence visible per case.

**Phase 12: Diagnosis.** Heuristic catalogue plus optional LLM engine. *DoD:* structured diagnosis with confidence.

**Phase 13: Recommendation.** Profiles, constraints, magnitude-preserving ranking. *DoD:* evidence and caveats shown.

**Phase 14: Benchmarks.** Six packs, 131 cases. *DoD:* one-click dataset creation from a pack.

**Phase 15: Improvement loop.** `clone_with_overrides` and before/after comparison. *DoD:* accept, rerun, compare works end to end.

**Phase 16: Reporting.** Web reports with JSON/CSV export. *DoD:* all required sections present.

**Phases 17 to 21.** Security hygiene, 77 tests, chunk splitting and polling optimisation, documentation, Docker and CI files.

### MVP verification summary

77 tests passing; ruff clean; frontend build clean; seed script and live loop verified with the mock provider; ZIP verified by extraction and test run. **Not verified:** real-provider behaviour, Docker and CI on hosted environments.

---

## Part B: Planned upgrades

Recommended order. Each is independent enough to ship alone.

### Phase 22 🔜 Model availability audit
- **Goal:** list only models that answer a real probe; remove dead catalog entries and validate default models.
- **Deliverables:** `discover_models()`, live probes with status classification, availability table and cache, filtered model APIs and pickers, generated audit report.
- **DoD:** nothing is shown as available without a successful probe; probe caps protect free-tier quotas; tests cover every status.

### Phase 23 🔜 Significance testing
- **Goal:** report whether differences between models or experiments exceed noise.
- **Deliverables:** paired bootstrap and permutation tests, confidence intervals, effect sizes, "not significant" labelling in compare and report pages.
- **DoD:** comparison and report show intervals; small-sample warnings appear.

### Phase 24 🔜 Judge calibration
- **Goal:** measure how far LLM-judge scores agree with human labels.
- **Deliverables:** human-label import and labelling UI, Cohen's kappa with Landis–Koch bands, bias probes (position, length), judge reliability badge.
- **DoD:** each judge-based metric shows an agreement figure or "uncalibrated".

### Phase 25 🔜 Counterfactual failure attribution
- **Goal:** determine empirically whether a failure is retrieval-caused or generation-caused.
- **Deliverables:** oracle-context and no-context re-runs, attribution rules, attribution workflow, API, UI panel, diagnosis integration.
- **DoD:** verdicts only from conditions that actually ran; dry-run estimates and case caps in place.

### Phase 26 🔜 Production hardening
- **Goal:** make a public deployment safe and runs durable.
- **Deliverables:** users, workspaces and roles, encrypted per-workspace keys, durable job queue with resume and cancel, Alembic migrations, security headers, audit log, production compose, CI on PostgreSQL.
- **DoD:** cross-workspace access returns 404; runs survive restarts without double-billing providers; migrations tested on an empty database.
- **Suggested split:** migrations → auth → jobs.

### Phase 27 🔜 Cloud deployment
- **Goal:** a public demo.
- **Deliverables:** deploy to one managed platform, managed PostgreSQL, object storage for documents, deployment guide with a tested / not tested list.
- **DoD:** deployment actually performed and documented; never claim it before then.

### Backlog (unscheduled)
Neural embeddings and rerankers; cost tracking and cost-aware recommendation; PDF report export; formal star-schema warehouse with scheduled ETL; WebSocket progress; Prometheus metrics.

---

## Suggested timeline for the remaining work

| Week | Focus |
|---|---|
| 1 | Phase 22 (availability audit), Phase 23 (significance testing) |
| 2 | Phase 24 (judge calibration), Phase 25 (attribution) |
| 3 | Phase 26 (migrations, auth, jobs) |
| 4 | Phase 27 (deployment), documentation polish |

Adjust to your submission deadlines. If time is short, do Phases 22 and 23 first; they give the largest credibility gain for the least effort.

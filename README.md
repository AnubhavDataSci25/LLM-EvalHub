# LLM-EvalHub

**An evaluation-first platform for benchmarking LLM and RAG applications — and for proving that a change actually improved them.**

Most evaluation tools stop at a leaderboard. The useful part starts after: *why* did it fail, *what* should change, and *did that change help?* LLM-EvalHub closes that loop.

```
Evaluate → Compare → Diagnose → Recommend → Improve → Re-evaluate
```

Run one dataset against several providers at once, score the answers with deterministic and judge-based metrics, classify every failure from measured evidence, get a transparent model recommendation, apply a suggested fix as a follow-up experiment, and get a before/after verdict.

---

## Contents

- [Why this exists](#why-this-exists)
- [Evaluation integrity rules](#evaluation-integrity-rules)
- [Feature overview](#feature-overview)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Configuring providers](#configuring-providers)
- [The product loop, end to end](#the-product-loop-end-to-end)
- [Metrics](#metrics)
- [Failure taxonomy](#failure-taxonomy)
- [Counterfactual failure attribution](#counterfactual-failure-attribution)
- [Benchmark packs](#benchmark-packs)
- [RAG pipeline](#rag-pipeline)
- [API](#api)
- [Testing](#testing)
- [Project layout](#project-layout)
- [Deployment](#deployment)
- [Design decisions](#design-decisions)
- [Limitations](#limitations)

---

## Why this exists

Choosing a model for a real product is an empirical question, but the evidence is usually anecdotal: someone tried three prompts in a playground and formed an impression. That does not survive contact with a design review, and it does not tell you whether last week's prompt change helped or hurt.

This platform makes the question answerable:

- **Identical inputs.** Every selected model answers exactly the same test cases through the same prompt template, so a difference in scores is attributable to the model rather than to how it was asked.
- **Recorded configuration.** An experiment freezes the dataset version, prompt, parameters, models, retrieval settings and metric selection. Two runs differing in one field give a clean A/B.
- **Evidence-linked failures.** Every failure stores the question, the answer, the retrieved context, the scores and the configuration. Nothing is asserted that cannot be traced back to a stored row.

---

## Evaluation integrity rules

These five rules are enforced in code, not just documented. They are what make the output worth acting on.

**1. A metric that cannot be computed is reported as unavailable, never as zero.**
If a dataset has no expected answers, correctness returns `available: false` with a reason. A zero and an unknown mean very different things when you are ranking models, and conflating them silently is how evaluation tools mislead people.

**2. Deterministic and judge-based scores are labelled.**
Lexical evaluators are reproducible; LLM judges are not. Every stored score carries its `kind` and, where relevant, the judge model that produced it. Recommendations surface this as a caveat rather than burying it.

**3. Provider keys never reach the browser.**
All model calls are proxied through the FastAPI backend. The frontend learns only whether a provider is configured. A logging filter redacts credential patterns from application logs.

**4. Failures are classified from evidence, in a fixed order.**
The detector runs a cascade: infrastructure errors first, then retrieval, then grounding, then answer quality, then latency. If retrieval recall is low, the failure is reported as a retrieval problem — the model could not have answered correctly regardless of its capability, and blaming it would send you off to tune the wrong thing.

**5. Every metric delta ships with its uncertainty.**
A metric movement is counted as an improvement or regression only if it is statistically significant under a paired sign-flip permutation test and a 95% bootstrap confidence interval. Non-significant differences count as unchanged, and underpowered samples (where $N < 8$ or the required sample size for the observed effect exceeds the sample) are explicitly flagged rather than treated as conclusive. Paired analyses drop unavailable scores on either side and report the drop count.

**6. Judge scores carry measured reliability.**
Every judge-scored metric is traceable to a measured reliability figure (Cohen's kappa) against blind human labels on the user's data. If fewer than 10 labelled cases exist, reliability is reported as `insufficient_labels` rather than fabricating agreement. When a judge is uncalibrated or displays poor agreement ($\kappa < 0.40$), recommendations and reports explicitly flag judge scores as weak evidence. Bias probes empirically test for order bias, verbosity inflation, and self-preference.

---

## Feature overview

| Area | What it does |
|---|---|
| **Datasets** | CSV/JSON import with flexible column mapping, validation with per-row errors and warnings, automatic versioning, inline editing |
| **Providers** | Gemini, Groq, Hugging Face, NVIDIA NIM, OpenRouter, optional Ollama, plus a deterministic test provider — all behind one interface |
| **Model runner** | Bounded-concurrency execution with retries, progressive persistence, per-unit error isolation |
| **Evaluation** | Correctness, answer relevance, faithfulness, context precision/recall, latency, retrieval hit rate, response length |
| **RAG** | PDF/TXT/Markdown ingestion, chunking with page citations, vector / BM25 / hybrid retrieval, retrieval preview |
| **Experiments** | Reproducible configuration records with parent/child lineage and a configuration diff |
| **Comparison** | Model-vs-model within a run; run-vs-run with metric deltas, sample sizes and a low-confidence flag |
| **Judge calibration** | Human-in-the-loop blind labelling, Cohen's kappa ($\kappa$) and quadratic-weighted $\kappa_w$, paired bootstrap confidence intervals, and three bias probes (order swap, verbosity padding, self-preference) |
| **Failure analysis** | Ten-category taxonomy, severity, confidence, evidence, filterable explorer |
| **AI diagnosis** | Heuristic and LLM engines returning the same schema, merged so every suggestion stays machine-applicable |
| **Improvement loop** | Accept a suggestion → follow-up experiment created → re-run → before/after verdict |
| **Recommendations** | Weighted ranking with score breakdown, hard constraints, evidence and caveats |
| **Benchmark packs** | Six ready-made scenarios, installable in one click |
| **Reports** | Frozen web reports with JSON and CSV export |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  React + Vite + Tailwind + Recharts          (no credentials)    │
└───────────────────────────┬──────────────────────────────────────┘
                            │ REST /api
┌───────────────────────────▼──────────────────────────────────────┐
│  FastAPI                                                          │
│  ├─ api/routes      thin HTTP layer, Pydantic in and out          │
│  ├─ services        business logic, one module per capability     │
│  ├─ workflows       LangGraph evaluation graph                    │
│  ├─ evaluation      metrics, judge, failure detector, aggregators │
│  ├─ rag             ingestion, chunking, embeddings, retrieval    │
│  ├─ providers       one adapter per provider, one interface       │
│  └─ models / db     SQLAlchemy, SQLite (dev) / PostgreSQL (prod)  │
└──────────────────────────────────────────────────────────────────┘
```

The layering rule: **routes never contain business logic, services never contain HTTP concerns, and provider specifics never leak past the adapter.** Adding a seventh provider means writing one adapter and registering it — the evaluation engine does not change.

### The evaluation graph

Orchestration uses LangGraph, with one graph invocation per *work unit* (one test case × one model):

```
START → prepare ──(rag enabled?)──→ retrieve ──┐
                 └──────────────────────────────┴→ generate → evaluate
                                                     → detect_failure → persist → END
```

Running per unit rather than per run keeps the control flow honest — there is exactly one conditional branch, because the pipeline has exactly one decision — and means a single provider failure is recorded as an errored result instead of aborting the experiment. Database writes are serialised behind an `asyncio.Lock` because a SQLAlchemy `Session` is not safe for concurrent use.

---

## Quick start

**Requirements:** Python 3.11+, Node 18+. No GPU, no local model, no paid API key required to try it.

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env                              # then add any provider keys
uvicorn app.main:app --reload --port 8000
```

```bash
# frontend (second terminal)
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The API docs are at <http://localhost:8000/docs>.

**First run in two minutes:** go to *Benchmark packs* → install **RAG QA** (creates a 32-case dataset and indexes its source document) → *New evaluation* → pick the dataset, select two models, run.

With no provider keys configured, the deterministic test provider is available. Its behaviours (`mock-extractive`, `mock-hallucinate`, `mock-empty`, `mock-error`, `mock-timeout`, `mock-verbose`) exercise the whole loop offline. **Its output is mechanical, not model generation — never read it as a benchmark result.**

---

## Configuring providers

Copy `.env.example` to `backend/.env` and set whichever keys you have. Every provider is optional; the platform reports which are configured and degrades honestly.

| Provider | Variable | Notes |
|---|---|---|
| Google Gemini | `GEMINI_API_KEY` | Native `generateContent` API, with usage metadata and block reasons |
| Groq | `GROQ_API_KEY` | OpenAI-compatible; very low latency |
| Hugging Face | `HF_API_KEY` | Routes through the Inference Providers router |
| OpenRouter | `OPENROUTER_API_KEY` | Gateway; records the upstream provider that served each request |
| NVIDIA NIM | `NVIDIA_NIM_API_KEY` | Hosted, or self-hosted via `NVIDIA_NIM_BASE_URL` (no key needed) |
| Ollama | `OLLAMA_ENABLED=true` | **Optional.** Local inference is never required |

All base URLs are configurable, so a proxy or self-hosted endpoint can be substituted without code changes.

---

## The product loop, end to end

**1. Evaluate.** Select a dataset, one or more models, metrics, prompt and retrieval settings. The run executes in the background with bounded concurrency; the UI polls with backoff and shows partial results as they land.

**2. Compare.** Within a run, models are scored on identical inputs. Across runs, you get per-metric deltas with the sample size behind each side — a delta computed from three cases is labelled low-confidence rather than presented as a finding.

**3. Diagnose.** Every failure carries its evidence. Running diagnosis produces a root cause, a confidence, the evidence used, and remediation actions. Without a judge model the heuristic engine runs; with one, the LLM's reasoning is merged with the heuristic's applicable actions, so suggestions always map to a real configuration change.

**4. Recommend.** Candidates are grouped by provider/model, aggregated, constrained, weighted and ranked. The score breakdown is shown metric by metric: measured value, normalised value, weight, contribution. Under-sampled candidates are excluded and the exclusion is reported.

**5. Improve.** Accept a suggestion and a follow-up experiment is created that differs from its parent in exactly the accepted fields. That diff is stored on the experiment — which is what makes the improvement attributable.

**6. Re-evaluate.** Re-run (optionally only the failed cases) and read the before/after verdict.

---

## Metrics

| Metric | Kind | Requires | Measures |
|---|---|---|---|
| `correctness` | Deterministic or judge | Expected answer | Agreement with the reference |
| `answer_relevance` | Deterministic or judge | — | Whether the response addresses the question |
| `faithfulness` | Deterministic or judge | Context | Whether claims are supported by the context |
| `context_precision` | Deterministic | Context | Rank-weighted usefulness of retrieved chunks |
| `context_recall` | Deterministic | Context + expected answer | Whether the answer was retrievable at all |
| `retrieval_hit_rate` | Deterministic | Context + expected sources | Whether expected sources appeared |
| `latency` | Measured | — | Response time against a budget |
| `response_length` | Measured | — | Informational; catches length-instruction drift |

Deterministic evaluators share a single tokenizer with the retriever (see [Design decisions](#design-decisions)). RAGAS is supported as an optional extra and degrades to the deterministic path when absent.

**Composite score** renormalises weights over the metrics that were actually measured, so a missing metric does not silently halve a model's score.

---

## Failure taxonomy

| Category | Meaning |
|---|---|
| `provider_error` | The request failed before any answer existed |
| `timeout` | No response within the configured timeout |
| `empty_response` | A successful response containing no text |
| `poor_retrieval` | The supporting passage was never retrieved |
| `hallucination` | Specific content absent from context *and* inconsistent with the reference |
| `unsupported_claim` | Partially grounded — some claims lack support |
| `incorrect_answer` | Confident and well-formed, but wrong |
| `missing_information` | Directionally right, omits part of the expected answer |
| `low_relevance` | Did not address the question asked |
| `high_latency` | Quality acceptable, exceeded the latency budget |

The distinction between `poor_retrieval` and `hallucination` matters: the first sends you to the retriever, the second to the prompt or the model. Confidence scales with distance from the threshold and is capped at 0.95 — the detector never claims certainty.

---

## Counterfactual failure attribution

Observational metrics tell you that a test case failed; they do not prove *why*. A low retrieval score might coincide with an answer failure, but if the model still fails when provided with the reference passage, the true bottleneck is the model or prompt, not the retriever.

Counterfactual Failure Attribution intervenes directly by re-running the failed work unit under controlled counterfactual conditions (preserving identical model, prompt template, temperature, and parameters) and comparing results against the stored `ORIGINAL`:

1. **`ORIGINAL`**: The stored evaluation result. Never re-run.
2. **`ORACLE_CONTEXT`**: The retrieved context is replaced with the case's reference gold context (`expected_sources` or `context`). Tests whether the model succeeds when retrieval is perfect.
3. **`NO_CONTEXT`**: Context is completely removed. Tests whether the model answers strictly from parametric memory.
4. **`DISTRACTOR_ONLY`** *(optional)*: Replaces retrieved context with distractor chunks excluding any overlap with the gold passage.

### Attribution rules

| Verdict | Condition Evidence | Root Cause & Actionable Recommendation |
|---|---|---|
| `RETRIEVAL_CAUSED` | `ORIGINAL` fails $\land$ `ORACLE_CONTEXT` passes | **Retrieval bottleneck.** The model produces correct answers when supporting passages are surfaced. Fix retrieval: increase `top_k`, enlarge chunk overlap, or add hybrid/reranking. |
| `GENERATION_CAUSED` | `ORIGINAL` fails $\land$ `ORACLE_CONTEXT` fails $\land$ `NO_CONTEXT` fails | **Generation bottleneck.** The model failed even with gold context. Refine prompt instructions, system instructions, few-shot examples, or upgrade the model. |
| `PARAMETRIC_KNOWLEDGE` | `ORIGINAL` fails $\land$ `ORACLE_CONTEXT` fails $\land$ `NO_CONTEXT` passes | **Context-ignoring behaviour.** The model answered correctly without context, but was distracted or misled when context was present. Strengthen grounding constraints (e.g. quote exact supporting text). |
| `NOT_CONTEXT_DEPENDENT` | `ORIGINAL` passes $\land$ `NO_CONTEXT` passes | **Non-context-dependent.** The test case does not test RAG; the model answers from pre-training memory alone. Reported transparently so it is not mistaken for a RAG retrieval success. |
| `NOT_ATTRIBUTABLE` | Missing gold context or provider error in counterfactual trials | **Not attributable.** Cannot establish causality without gold reference passages or clean trial execution. The reason is explicitly reported; results are never inferred or fabricated. |

### Replication and quota safety

- **Trial repeats ($N=1\dots 5$):** LLMs are stochastic. Single-run attribution ($N=1$) carries a noise warning. Running $N=3$ or $N=5$ repeats computes empirical pass rates across trials.
- **Confidence cap:** Confidence scales with clean condition trials and is hard-capped at 0.95 (never claiming certainty).
- **Free-tier quota protection:** Batch attribution supports a `dry_run=true` estimation of exact provider API calls ($2 \times N$ or $3 \times N$) and caps cases at 10 by default (50 maximum).
- **Idempotent persistence:** Re-running attribution replaces previous `attribution_runs` and `attribution_conditions` records cleanly.

---

## Benchmark packs

Six packs ship with the repository, all synthetic and redistributable:

| Pack | Cases | Focus |
|---|---|---|
| `rag_qa` | 32 | Retrieval-grounded QA over a product handbook |
| `customer_support` | 24 | Policy answers where precision about conditions matters |
| `document_qa` | 25 | Extraction from an HR handbook |
| `citation_grounding` | 20 | Half deliberately unanswerable — rewards declining over guessing |
| `structured_extraction` | 18 | Field extraction from unstructured text |
| `summarization` | 12 | Decisions and owners from operational transcripts |

Each pack carries recommended metrics, baseline settings, and notes explaining *why* those metrics fit the use case. Installing a pack creates a real dataset and, where relevant, indexes its documents.

Adding your own pack is a directory drop: `benchmarks/<key>/pack.json` plus a dataset file. No code change.

---

## RAG pipeline

```
upload → validate → parse (PDF/TXT/MD) → chunk (with page citations)
       → embed → store → retrieve (vector | BM25 | hybrid RRF) → evaluate
```

The default embedder is a **deterministic lexical hasher**: pure NumPy, no model download, works on any hardware, and reproducible. Semantic embedders (Gemini, sentence-transformers) are available when configured. FAISS is used when installed, with a NumPy brute-force index as the fallback.

The **retrieval preview** on the Documents page lets you see what a question actually retrieves before committing to a run — which saves a great deal of confused debugging later.

---

## API

Interactive docs at `/docs`, OpenAPI schema at `/openapi.json`.

```
GET    /api/health                              service + provider status
GET    /api/meta/metrics|failure-types|profiles catalogues
GET    /api/dashboard                           aggregates

POST   /api/datasets/upload|import              CSV / JSON ingestion
GET    /api/datasets/{id}                       detail with validation report
GET    /api/benchmarks                          packs
POST   /api/benchmarks/{key}/install            materialise a pack

POST   /api/experiments                         create a configuration
POST   /api/evaluations/run                     start a run (202, background)
GET    /api/evaluations/{id}                    poll status and summary
GET    /api/evaluations/{id}/results            per-case results, filterable
POST   /api/evaluations/{id}/retry              re-run errored cases

GET    /api/compare/models/{run_id}             model comparison
POST   /api/compare                             run comparison with deltas
GET    /api/compare/improvement                 before/after

GET    /api/failures                            filterable explorer
POST   /api/failures/{id}/diagnose              AI diagnosis
POST   /api/experiments/{id}/improve            follow-up experiment
GET    /api/experiments/{id}/outcome            before/after verdict

POST   /api/recommendations                     weighted ranking
POST   /api/reports                             generate a report
GET    /api/reports/{id}/export?format=json|csv export

POST   /api/documents/upload|index|preview      RAG pipeline
GET    /api/providers?with_models=true          provider status (no secrets)
```

Errors are consistent: `{"error": {"code", "message", "details"}}`.

---

## Testing

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests -q
```

**77 tests, entirely offline.** No API key, no network, no paid call. The deterministic test provider makes the suite reproducible, which is the same property that makes the platform usable for regression testing at all — and there is a test asserting exactly that.

Coverage: provider adapters (including HTTP error mapping and a credential-leak assertion), dataset validation, deterministic metrics, failure classification, recommendation scoring, the RAG pipeline, the full API loop, and pipeline reproducibility.

```
tests/test_providers.py            adapter contract, error mapping, no secret leakage
tests/test_dataset_validation.py   import, aliases, duplicates, warnings
tests/test_metrics.py              determinism, unavailability, discrimination
tests/test_statistics.py           bootstrap CI, permutation test, power, Holm correction
tests/test_failure_detector.py     taxonomy, ordering, confidence scaling
tests/test_recommendation.py       weighting, constraints, caveats, tie detection
tests/test_rag.py                  ingestion, chunking, embedding, retrieval
tests/test_evaluation_pipeline.py  reproducibility, composite scoring
tests/test_api_flow.py             the entire product loop over HTTP
```

---

## Project layout

```
llm-evalhub/
├── backend/
│   ├── app/
│   │   ├── api/routes/        HTTP layer
│   │   ├── core/              config, logging, exceptions, concurrency, text
│   │   ├── db/                session, base, init
│   │   ├── models/            SQLAlchemy models (16 tables)
│   │   ├── schemas/           Pydantic request/response models
│   │   ├── providers/         one adapter per provider + registry
│   │   ├── evaluation/        metrics, judge, detector, aggregators, RAGAS
│   │   ├── rag/               ingestion, chunking, embeddings, retrieval
│   │   ├── workflows/         LangGraph graph and state
│   │   ├── services/          business logic
│   │   └── main.py
│   └── tests/
├── frontend/
│   └── src/
│       ├── components/ui/     design-system primitives
│       ├── components/charts/ Recharts wrappers, theme-aware
│       ├── components/layout/ app shell
│       ├── hooks/             useApi, useRunPolling, useTheme
│       ├── pages/             17 routes
│       └── lib/               API client, formatters
├── benchmarks/                six packs
├── docs/                      architecture, API, decisions
└── scripts/                   dev bootstrap, seeding
```

---

## Deployment

**Development:** SQLite with WAL, foreign keys enforced.
**Production:** set `DATABASE_URL` to a PostgreSQL DSN — no code change; the session layer already handles both.

```bash
docker compose up --build      # API on 8000, frontend on 5173, Postgres on 5432
```

Build the frontend with `npm run build` and serve `dist/` from any static host, pointing `VITE_API_BASE_URL` at the API.

Operational notes: `MAX_CONCURRENT_REQUESTS` bounds provider load, `RETRY_ATTEMPTS` bounds retries (honouring `Retry-After`), `REQUEST_TIMEOUT_SECONDS` bounds a single call. Uploads are size- and type-validated; filenames are sanitised against path traversal.

---

## Design decisions

Recorded in full in [`docs/decisions.md`](docs/decisions.md). Two worth surfacing here, because both were found by tests rather than by reading:

**One tokenizer for metrics and retrieval.** Originally the deterministic metrics stemmed tokens while the lexical embedder did not, so the retriever and the retrieval *metrics* disagreed about what counted as a match. Extracting `app/core/text.py` as the single shared implementation moved `context_recall` on the `rag_qa` pack from **0.53 to 0.91**, and dropped `poor_retrieval` failures from **12 to 2**. A measurement tool whose components disagree about word identity is measuring its own inconsistency.

**Magnitude-preserving normalisation in the recommendation engine.** The first implementation min-max normalised each metric across candidates. With two candidates that collapses every metric to 0 or 1, so a 0.90-vs-0.88 gap scored identically to 0.90-vs-0.30, and the ranking reduced to a comparison of weight sums. Quality metrics are already on a 0–1 scale and are now used directly; latency, being unbounded, is scored as a ratio against the fastest candidate. A test asserts the magnitude is preserved.

---

## Limitations

Stated plainly, because an evaluation tool that oversells itself is self-defeating:

- **Deterministic metrics are lexical.** They reward wording overlap and under-credit correct paraphrase. Configure a judge model for semantic scoring — and then accept judge variance and bias, which the platform labels rather than hides.
- **LLM judges are not reproducible.** Two runs can differ. Sample sizes and judge identity are recorded so you can weigh this. Repeated judge runs (measuring judge scoring variance across multiple evaluations of the exact same output) are not yet modelled.
- **Judge calibration & annotator agreement.** When calibrated against a single human annotator, Cohen's kappa measures agreement with that individual annotator, not absolute ground truth. Small label counts ($N < 10$) return `insufficient_labels` without fabricating kappa, and small counts widen the bootstrap confidence interval. Bias probes cover three specific failure modes (positional order swap, verbosity inflation, and self-preference), not all conceivable judge biases.
- **Landis-Koch conventional boundaries.** Qualitative interpretation of kappa uses conventional Landis-Koch bands (<0 poor, 0–0.20 slight, 0.21–0.40 fair, 0.41–0.60 moderate, 0.61–0.80 substantial, 0.81–1.00 almost perfect). These bands are conventional heuristic boundaries, not universal ground truth.
- **Statistical uncertainty assumptions.** The paired bootstrap confidence intervals and permutation tests assume that the test case set is representative of the production distribution.
- **Small samples and power.** Deltas with insufficient paired test cases ($N < 8$ or where the required sample size for the observed effect size exceeds available cases) are flagged as underpowered. The underpowered label is an explicit warning that the test lacks statistical power to distinguish true effect from chance.
- **Counterfactual failure attribution limitations.** Attribution relies on the presence of high-quality reference gold passages in test cases; without reference context, it safely yields `NOT_ATTRIBUTABLE` and defers to heuristic diagnosis. LLM outputs are stochastic; single trials ($N=1$) are subject to generation noise, so multi-trial repeats ($N=3\dots 5$) are recommended. Re-running conditions incurs extra provider calls ($2 \times N$ or $3 \times N$), which is why batch executions are quota-capped and offer dry-run call estimations. Attribution establishes causality on individual test cases, not cross-case generalizations.
- **Recommendations are scoped.** They describe measured behaviour on your dataset under your weights. A different dataset can reorder the ranking, and the caveats say so on every recommendation. When top models have non-significant differences, a tied-candidate caveat is attached.
- **The test provider is not a model.** It produces mechanical extractive output to exercise the pipeline offline.
- **No authentication.** This is a single-tenant developer tool. Do not expose it to an untrusted network without adding an auth layer.
- **PDF parsing is text-layer only.** Scanned documents need OCR first.

---

## References

- Cohen, J. (1960). "A Coefficient of Agreement for Nominal Scales." *Educational and Psychological Measurement*, 20(1), 37–46.
- Landis, J. R., & Koch, G. G. (1977). "The Measurement of Observer Agreement for Categorical Data." *Biometrics*, 33(1), 159–174.
- Zheng, L., Chiang, W.-L., Sheng, Y., et al. (2023). "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena." *NeurIPS 2023*.
- Wang, P., Li, L., Chen, L., et al. (2023). "Large Language Models are not Fair Evaluators." *arXiv:2305.17926*.
- Panickssery, A., Bowman, S. R., & Shi, F. (2024). "LLM Evaluators Recognize and Favor Their Own Generations." *arXiv:2404.13076*.

---

## License

MIT — see [`LICENSE`](LICENSE).

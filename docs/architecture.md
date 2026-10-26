# Architecture

## Layering

The codebase enforces one rule above all others: **each layer knows only about the layer beneath it.**

| Layer | Directory | Responsibility | Must not |
|---|---|---|---|
| Presentation | `frontend/src` | Rendering, local UI state | Hold credentials, contain evaluation logic |
| HTTP | `backend/app/api` | Routing, validation, serialisation | Contain business logic |
| Business | `backend/app/services` | Orchestration, policy, aggregation | Know about HTTP or providers' wire formats |
| Orchestration | `backend/app/workflows` | Multi-step evaluation flow | Perform database transactions directly |
| Domain | `backend/app/evaluation`, `rag` | Metrics, classification, retrieval | Depend on services |
| Integration | `backend/app/providers` | Provider-specific HTTP and error mapping | Leak provider types upward |
| Persistence | `backend/app/models`, `db` | Schema and sessions | Contain logic |

The practical test: adding a seventh provider must touch exactly two files — the new adapter and the registry. It does. The evaluation engine, the services and the API are all unaware of which provider produced a response.

## Provider abstraction

Every adapter implements `LLMProvider`:

```python
async def generate(prompt, model, *, temperature, max_tokens, system_prompt, timeout) -> LLMResponse
async def list_models() -> list[ModelInfo]
async def health() -> ProviderHealth
def describe() -> dict          # never includes the credential
```

`LLMResponse` normalises text, latency, usage, finish reason and the resolved model id. Provider errors are mapped into a single typed hierarchy with a `kind` and a `retryable` flag:

| HTTP | kind | retryable |
|---|---|---|
| 429 | `rate_limited` | yes, honouring `Retry-After` |
| 401 / 403 | `invalid_credentials` | no |
| 404 | `model_unavailable` | no |
| 5xx | `upstream_error` | yes |
| timeout | `timeout` | yes |

Five of the six hosted providers speak an OpenAI-compatible protocol, so they share `OpenAICompatibleProvider` and differ only in base URL, headers and model discovery. Gemini has its own adapter because its native API differs enough that pretending otherwise would lose information — specifically `usageMetadata` and `blockReason`, both of which matter for evaluation.

## Execution model

```
POST /api/evaluations/run
  → create EvaluationRun (queued), return 202 immediately
  → BackgroundTask opens its own Session
  → build work units: cases × models
  → run_bounded(units, worker, limit=MAX_CONCURRENT_REQUESTS)
      each unit → LangGraph → persist (serialised by asyncio.Lock)
  → commit every 5 units so polling clients see progress
  → aggregate summary, mark completed
```

Three properties this buys:

1. **Failure isolation.** A provider error becomes an errored result row, not an exception that kills the run.
2. **Bounded load.** Free tiers rate-limit aggressively; concurrency and retries are both capped.
3. **Observable progress.** Progressive commits mean the UI shows real partial results rather than a spinner.

## Data model

22 tables. The spine:

```
Dataset ─< DatasetVersion ─< TestCase
                  │
Experiment ───────┘  ─< ExperimentModel
    │
    └─< EvaluationRun ─< EvaluationResult ─< MetricResult
                                  └──────── Failure ─→ diagnosis (JSON)
                                               └────── AttributionRun (1:1)
                                                            └─< AttributionCondition (1:N)

Document ─< DocumentChunk        Recommendation      Report
HumanLabel ─< CalibrationRun     AuditRun ─< ModelAvailability
```

`Experiment.parent_experiment_id` gives improvement lineage. `EvaluationRun.config_snapshot` freezes everything needed to reproduce a run at submission time, so later edits to an experiment never retroactively change what a past run claims to have tested.

## Model Availability Audit

To prevent silent evaluation failures from retired checkpoints, unentitled tiers, or exhausted quotas, model selection is grounded in empirical verification rather than static catalogs:

```
Provider discovery (/models or /tags)
  │
  ├─ Data-driven non-chat filtering (embeddings, moderation, speech, image, rerankers, guard models)
  │
  └─ Cheap live probe (8 tokens, temperature 0, fixed prompt)
       │
       ├─ AVAILABLE           → Cached with latency_ms and TTL (6h)
       ├─ RATE_LIMITED        → Cached with retry_after (opt-in toggle in UI)
       ├─ NOT_ENTITLED / 404  → Cached with reason; auto-rejects experiment creation (422)
       └─ INVALID_CREDENTIALS → Immediately stops further probes for this provider
```

Selection screens read from `ModelAvailability` cache without network overhead on page load. Evaluation runs automatically invalidate cached models upon runtime provider errors (`NOT_FOUND`, `NOT_ENTITLED`), preventing future dead runs. Default evaluator configuration is validated at startup and via `/ready`.

## Counterfactual Attribution Workflow

When a RAG failure case is investigated, `AttributionGraph` executes an empirical multi-stage intervention pipeline via LangGraph:

```
START ─→ build_inputs ─→ generate ─→ evaluate ─→ attribute ─→ persist ─→ END
```

1. **build_inputs**: Extracts the failed work unit's original input, test question, and gold reference passage (`expected_sources` or `context`). Formulates 3 controlled conditions: `ORIGINAL` (cached result), `ORACLE_CONTEXT` (context replaced with gold reference), and `NO_CONTEXT` (context completely cleared), with optional `DISTRACTOR_ONLY`. Expands trials across $N$ repeats ($N=1\dots 5$).
2. **generate**: Executes generation under identical model, temperature, system prompt, and parameters using the typed provider layer. Captures latency, provider error kinds, and generated answers.
3. **evaluate**: Evaluates generated trial responses against ground truth using lexical or LLM evaluators to calculate correctness and faithfulness metrics.
4. **attribute**: Pure decision engine (`compute_attribution`) computes pass rates, checks thresholds from configuration, compares condition success, assigns attribution verdict (`RETRIEVAL_CAUSED`, `GENERATION_CAUSED`, `PARAMETRIC_KNOWLEDGE`, `NOT_CONTEXT_DEPENDENT`, `NOT_ATTRIBUTABLE`), caps confidence at 0.95, and compiles actionable recommendations.
5. **persist**: Persists `AttributionRun` and individual trial records `AttributionCondition` with transaction safety, linking them directly to the `Failure` entity.

## Frontend

- **State:** local, with three hooks (`useApi`, `useRunPolling`, `useTheme`). A server-state library would be more machinery than seventeen pages of read-mostly data justify.
- **Polling:** backs off 1s → 4s while a run is active, stops at a terminal state.
- **Theme:** CSS variables swapped by a `dark` class on `<html>`, applied pre-paint by an inline script so there is no flash.
- **Charts:** Recharts wrappers that read theme variables at render time, so one definition serves both themes.

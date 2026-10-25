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

16 tables. The spine:

```
Dataset ─< DatasetVersion ─< TestCase
                  │
Experiment ───────┘  ─< ExperimentModel
    │
    └─< EvaluationRun ─< EvaluationResult ─< MetricResult
                                  └──────── Failure ─→ diagnosis (JSON)

Document ─< DocumentChunk        Recommendation      Report
```

`Experiment.parent_experiment_id` gives improvement lineage. `EvaluationRun.config_snapshot` freezes everything needed to reproduce a run at submission time, so later edits to an experiment never retroactively change what a past run claims to have tested.

## Frontend

- **State:** local, with three hooks (`useApi`, `useRunPolling`, `useTheme`). A server-state library would be more machinery than seventeen pages of read-mostly data justify.
- **Polling:** backs off 1s → 4s while a run is active, stops at a terminal state.
- **Theme:** CSS variables swapped by a `dark` class on `<html>`, applied pre-paint by an inline script so there is no flash.
- **Charts:** Recharts wrappers that read theme variables at render time, so one definition serves both themes.

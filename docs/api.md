# API reference

Base path `/api`. Interactive docs at `/docs`; schema at `/openapi.json`.

## Conventions

**Errors** are uniform:

```json
{ "error": { "code": "validation_failed", "message": "…", "details": {} } }
```

| Code | Status | Meaning |
|---|---|---|
| `validation_failed` | 422 | Payload or semantic validation failed |
| `not_found` | 404 | Resource does not exist |
| `conflict` | 409 | Operation conflicts with current state |
| `provider_not_configured` | 422 | Provider selected without a credential |
| `rate_limited` | 429 | Upstream rate limit; retry later |
| `internal_error` | 500 | Unexpected — check server logs |

**Pagination:** `limit` (1–200, default 50) and `offset`. List responses return `{items, total, limit, offset}`.

**Long operations:** `POST /evaluations/run` returns `202` with a run id. Poll `GET /evaluations/{id}`; `progress` runs 0→1 and `status` reaches `completed` or `failed`.

---

## Metadata

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Status, database kind, configured provider count, optional features |
| GET | `/meta/metrics` | Metric catalogue with `default_kind`, `requires`, `judge_capable` |
| GET | `/meta/failure-types` | Taxonomy and default thresholds |
| GET | `/meta/profiles` | Recommendation weighting profiles |
| GET | `/dashboard` | Aggregates for the dashboard |

## Providers

| Method | Path | Notes |
|---|---|---|
| GET | `/providers?with_models=true` | Status and models. **Never returns credentials.** |
| GET | `/providers/{key}/models` | Model discovery |
| GET | `/providers/{key}/health` | Connectivity check |

## Datasets

| Method | Path | Notes |
|---|---|---|
| GET/POST | `/datasets` | List / create |
| POST | `/datasets/upload` | Multipart CSV or JSON |
| POST | `/datasets/import` | JSON rows in the body |
| POST | `/datasets/validate` | Dry-run validation, no persistence |
| GET/PUT/DELETE | `/datasets/{id}` | Detail with validation report and versions |
| GET/POST | `/datasets/{id}/cases` | Test cases; adding creates a new version |
| PUT/DELETE | `/datasets/cases/{id}` | Edit or remove a case |

Column aliases are matched case-insensitively: `question`/`query`/`prompt`/`input`, `ground_truth`/`answer`/`expected`, `context`/`passage`/`documents`.

## Benchmarks

| Method | Path | Notes |
|---|---|---|
| GET | `/benchmarks` | Packs with install status |
| GET | `/benchmarks/{key}` | Detail with sample cases and metric notes |
| POST | `/benchmarks/{key}/install` | Creates a dataset; indexes documents when present |

## Experiments and runs

| Method | Path | Notes |
|---|---|---|
| GET/POST | `/experiments` | List / create |
| GET/DELETE | `/experiments/{id}` | Detail / remove |
| GET | `/experiments/{id}/runs` | Run history |
| POST | `/experiments/{id}/improve` | Follow-up experiment from accepted changes |
| GET | `/experiments/{id}/outcome` | Before/after verdict |
| POST | `/evaluations/run` | Start a run (202) |
| GET | `/evaluations/{id}` | Poll status and summary |
| GET | `/evaluations/{id}/results` | Filter by `failed_only`, `model`, `provider`, `search` |
| POST | `/evaluations/{id}/retry` | New run over errored cases only |
| GET | `/evaluations/{id}/improvement-suggestions` | Aggregated, ranked by support |

`POST /evaluations/run` accepts either `experiment_id` (re-run) or an inline `experiment` object (create and run).

## Comparison, failures, recommendations, reports

| Method | Path | Notes |
|---|---|---|
| GET | `/compare/models/{run_id}` | Models on identical inputs |
| GET | `/compare/models/{run_id}/significance?metric=...` | Pairwise significance tests across models with Holm-Bonferroni correction |
| POST | `/compare` | Runs vs a baseline with config diff, paired bootstrap CI, permutation p-values and verdicts |
| GET | `/compare/improvement` | Two-run before/after with statistical significance testing |
| GET | `/failures` | Filter by run, type, severity, provider, model, diagnosed |
| GET | `/failures/{id}` | Full evidence including the result |
| POST | `/failures/{id}/diagnose` | AI diagnosis; `force` re-runs |
| POST | `/failures/{id}/attribution` | Run empirical counterfactual attribution (repeats 1-5, optional distractor) |
| GET | `/failures/{id}/attribution` | Retrieve stored counterfactual attribution run and condition trials |
| POST | `/experiments/{id}/attribution` | Batch failure attribution with dry-run estimation, max_cases capping |
| GET | `/experiments/{id}/attribution/summary` | Aggregate attribution distribution and bottleneck summary |
| POST | `/recommendations` | Weighted ranking with constraints; flags statistically tied top models |
| POST | `/reports` | Generate a frozen report |
| GET | `/reports/{id}/export?format=json\|csv` | Export |

### Comparison metric delta fields

Each item in `metric_deltas` and `latency_analysis` includes:
* `ci_low`, `ci_high`: 95% bootstrap confidence interval (percentile method)
* `p_value`: two-sided paired sign-flip permutation test p-value
* `effect_size_dz`: Cohen's $d_z$ for paired differences
* `n_pairs`: number of test cases with valid measurements on both sides
* `n_dropped`: number of test cases dropped due to missing or unavailable metric data
* `required_n`: estimated sample size needed to detect effect size at 80% power ($\alpha = 0.05$)
* `significance`: verdict (`"significant"`, `"not_significant"`, `"underpowered"`, or `"not_comparable"`)
* `significance_reason`: single-sentence explanation of the statistical verdict

## RAG

| Method | Path | Notes |
|---|---|---|
| GET | `/documents` | Documents and collection summaries |
| POST | `/documents/upload` | Multipart PDF, TXT or Markdown |
| POST | `/documents/index` | Chunk, embed and store |
| POST | `/documents/preview` | Retrieval preview without running an evaluation |
| DELETE | `/documents/{id}` | Remove document and chunks |

## Judge calibration

| Method | Path | Notes |
|---|---|---|
| GET | `/calibration/queue` | Blind human labelling queue; stratified sample across models & score bands (masks judge scores) |
| POST | `/calibration/labels` | Idempotently record or update a human label (0=incorrect, 1=partial, 2=correct) |
| GET | `/calibration/labels` | List stored human labels filtered by `run_id`, `metric`, or `annotator` |
| POST | `/calibration/run` | Execute calibration run computing unweighted & quadratic-weighted $\kappa$, intervals, and bias probes |
| GET | `/calibration/runs` | List historical calibration runs |
| GET | `/calibration/runs/{id}` | Full calibration report with agreement matrix, bias summary, and probe results |
| GET | `/calibration/reliability` | Latest reliability summary for `provider`, `model`, and `metric` |


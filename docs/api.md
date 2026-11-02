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

**Authentication & Multi-Tenancy:**
- In `AUTH_MODE=enabled`, all endpoints except `/health`, `/ready`, `/auth/mode`, `/auth/register`, `/auth/login`, and `/auth/refresh` require an `Authorization: Bearer <access_token>` header.
- Multi-tenant endpoints accept an optional `X-Workspace-Id` header (or `?workspace_id=...` parameter) to scope operations to a specific workspace. In `AUTH_MODE=local`, requests default to the pre-seeded `wks_default` workspace.
- Cross-tenant resource queries return HTTP 404 (Not Found) rather than HTTP 403 (Forbidden) to prevent resource existence enumeration.

---

## Authentication

| Method | Path | Notes |
|---|---|---|
| GET | `/auth/mode` | Public. Returns `{mode: "local"\|"enabled", is_auth_enabled: bool}` |
| POST | `/auth/register` | Rate-limited. Registers user with email, password (min 8 chars), full name |
| POST | `/auth/login` | Rate-limited. Returns JWT access token (15m) and rotating refresh token (7d) |
| POST | `/auth/refresh` | Rotates refresh token. Detects token replay and revokes compromised sessions |
| POST | `/auth/logout` | Revokes the provided refresh token session |
| GET | `/auth/me` | Current user profile, associated workspaces, and active workspace ID |

## Workspaces & RBAC

| Method | Path | Notes |
|---|---|---|
| GET | `/workspaces` | List all workspaces where the current user has membership |
| POST | `/workspaces` | Create a new workspace; creator is assigned `owner` role |
| GET | `/workspaces/{id}` | Workspace detail and current user's role (requires `viewer`+) |
| PUT | `/workspaces/{id}` | Update workspace name/description (requires `owner`) |
| DELETE | `/workspaces/{id}` | Delete workspace and all scoped resources (requires `owner`) |
| GET | `/workspaces/{id}/members` | List members and their assigned roles (requires `viewer`+) |
| POST | `/workspaces/{id}/members` | Add/invite member by email with `owner`, `editor`, or `viewer` role (requires `owner`) |
| PUT | `/workspaces/{id}/members/{user_id}` | Change member role (requires `owner`) |
| DELETE | `/workspaces/{id}/members/{user_id}` | Remove member from workspace (requires `owner`) |
| GET | `/workspaces/{id}/providers` | List provider key status (`configured`, masked suffix `...1a2b`, source) (requires `viewer`+) |
| PUT | `/workspaces/{id}/providers/{provider}` | Store provider API key encrypted at rest with Fernet (requires `owner`) |
| DELETE | `/workspaces/{id}/providers/{provider}` | Remove workspace-level encrypted provider key (requires `owner`) |
| GET | `/workspaces/{id}/audit-logs` | List security audit logs with action/resource filters, pagination (requires `owner`) |

---

## Metadata & Operations

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Service liveness health check (available at `/health` and `/api/health`) |
| GET | `/ready` | Readiness probe; tests database connectivity (`SELECT 1`), Redis connectivity (if configured), and default evaluator status. Returns HTTP 503 if infrastructure is unreachable (available at `/ready` and `/api/ready`) |
| GET | `/metrics` | Prometheus text exposition format (controlled by `ENABLE_METRICS=true`; available at `/metrics` and `/api/metrics`) |
| GET | `/meta/metrics` | Metric catalogue with `default_kind`, `requires`, `judge_capable` |
| GET | `/meta/failure-types` | Taxonomy and default thresholds |
| GET | `/meta/profiles` | Recommendation weighting profiles |
| GET | `/dashboard` | Aggregates for the dashboard |

## Providers

| Method | Path | Notes |
|---|---|---|
| GET | `/providers?with_models=true` | Status and models. **Never returns credentials.** |
| GET | `/providers/status` | Provider status summary: counts per availability status, last audit timestamp |
| GET | `/providers/models` | List verified `AVAILABLE` models grouped by provider (`include_limited`, `include_unavailable`) |
| POST | `/providers/audit` | Run model availability audit with bounded concurrency (`dry_run=true` for call estimation) |
| GET | `/providers/audit/{audit_id}` | Retrieve audit run progress, overall summary, and per-model diagnostic items |
| POST | `/providers/{key}/models/{model_id}/recheck` | On-demand probe re-check of a single model |
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
| POST | `/evaluations/{id}/cancel` | Cooperatively cancels an in-flight evaluation run |
| POST | `/evaluations/{id}/resume` | Resumes an interrupted, cancelled, or failed run without re-billing completed units |
| GET | `/evaluations/{id}/results` | Filter by `failed_only`, `model`, `provider`, `search` |
| POST | `/evaluations/{id}/retry` | New run over errored cases only |
| GET | `/evaluations/{id}/improvement-suggestions` | Aggregated, ranked by support |

`POST /evaluations/run` accepts either `experiment_id` (re-run) or an inline `experiment` object (create and run).

## Background jobs

| Method | Path | Notes |
|---|---|---|
| GET | `/jobs` | List background execution jobs for the active workspace (`status`, `job_type`, pagination) |
| GET | `/jobs/{id}` | Job details, progress units, error logs, and timestamps |
| POST | `/jobs/{id}/cancel` | Cancel an in-flight background job cooperatively |
| POST | `/jobs/{id}/resume` | Resume an interrupted or failed background job |

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


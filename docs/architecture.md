# Architecture

## Layering

The codebase enforces one rule above all others: **each layer knows only about the layer beneath it.**

| Layer | Directory | Responsibility | Must not |
|---|---|---|---|
| Presentation | `frontend/src` | Rendering, local UI state, in-app documentation | Hold credentials, contain evaluation logic |
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

29 tables. The multi-tenant spine:

```
Workspace ──┬──< WorkspaceMember ─> User ──< RefreshToken
            ├──< WorkspaceProviderKey (Fernet encrypted)
            ├──< Job (durable background queue execution)
            ├──< AuditLog (immutable security & operational trail)
            │
            ├──< Dataset ─< DatasetVersion ─< TestCase
            │                 │
            ├──< Experiment ──┘  ─< ExperimentModel
            │      │
            │      └─< EvaluationRun ─< EvaluationResult ─< MetricResult
            │                                    └──────── Failure ─→ diagnosis (JSON)
            │                                                 └────── AttributionRun (1:1)
            │                                                              └─< AttributionCondition (1:N)
            │
            ├──< Document ─< DocumentChunk
            ├──< Recommendation
            └──< Report

HumanLabel ─< CalibrationRun     AuditRun ─< ModelAvailability
```

`Experiment.parent_experiment_id` gives improvement lineage. `EvaluationRun.config_snapshot` freezes everything needed to reproduce a run at submission time, so later edits to an experiment never retroactively change what a past run claims to have tested.

## Database Migrations and Schema Evolution

Schema changes are managed through Alembic (`backend/alembic/`), replacing manual table creation with deterministic, reversible migrations.

1. **Dual Engine Support (SQLite & PostgreSQL):**
   - SQLite migrations run with `render_as_batch=True`, enabling non-destructive table alterations, column drops, and index updates without hitting SQLite's native `ALTER TABLE` limits.
   - PostgreSQL uses native DDL transactions in production.
2. **Startup Auto-Migration (`AUTO_MIGRATE=true|false`):**
   - In local development mode (`AUTO_MIGRATE=true`), `init_db()` executes `alembic upgrade head` on FastAPI startup, ensuring the database is always current without manual CLI steps.
   - In production or container orchestration, setting `AUTO_MIGRATE=false` allows running migrations as a dedicated release phase step (`alembic upgrade head`) before application traffic is routed.
3. **Handling Existing Pre-Alembic Databases:**
   - When `run_migrations()` boots against an existing database that has domain tables (`datasets`, `experiments`, `workspaces`, etc.) but lacks `alembic_version`, it automatically executes `command.stamp(cfg, "head")`. Existing data is preserved without table collision errors.
4. **Schema Verification:**
   - An automated migration test suite verifies that upgrading an empty database to `head` matches SQLAlchemy `Base.metadata` with zero diffs (`compare_metadata`).

## Durable Background Jobs and Queue Abstraction

Long-running evaluation workloads run asynchronously through a unified `JobBackend` abstraction (`backend/app/services/jobs.py`) backed by persistent `Job` records.

### Architecture and Execution Modes

```
POST /evaluations/run
  │
  ├─ Enforce Workspace Quotas (concurrency limit, daily call limit)
  ├─ Create EvaluationRun (queued) & Job (queued)
  └─ Dispatch to JobBackend:
       ├─ AsyncioJobBackend: In-process asyncio.create_task (zero external services, local SQLite mode)
       └─ ArqJobBackend: Distributed Redis queue (arq) with dedicated worker pool (python -m app.worker)
```

1. **Job Lifecycle States:**
   - `queued`: Job submitted, awaiting execution.
   - `running`: Worker has claimed job and is processing work units.
   - `succeeded`: All work units processed, summaries aggregated.
   - `failed`: Job encountered an unhandled fatal error.
   - `cancelled`: Cooperatively cancelled mid-flight by user.
   - `interrupted`: Job was running when server/worker crashed or restarted.

2. **Restart Safety & Orphan Recovery:**
   On FastAPI application boot (`lifespan` in `app/main.py`), `JobService.recover_interrupted_jobs()` automatically scans for orphaned jobs with status `queued` or `running` and marks them (and their linked `EvaluationRun`) as `interrupted`. This prevents stale runs from hanging indefinitely.

3. **Idempotent Resumption (`POST /evaluations/{id}/resume` and `POST /jobs/{id}/resume`):**
   When resuming an `interrupted`, `cancelled`, or `failed` run, the runner queries existing `EvaluationResult` records with `status == "completed"`. It filters the required work units to submit only incomplete cases:
   $$\text{units\_to\_run} = \{u \in \text{all\_units} \mid u \notin \text{completed\_units}\}$$
   Already completed units and scores are preserved, ensuring zero duplicate LLM provider calls and zero duplicate billing.

4. **Cooperative Mid-Flight Cancellation (`POST /evaluations/{id}/cancel` and `POST /jobs/{id}/cancel`):**
   Cancellation sets a flag in the job backend (`register_cancellation`). The worker loop checks `backend.is_cancelled(job_id)` between work units. When cancellation is detected, pending units are aborted and the job/run state is committed as `cancelled`. All units completed prior to cancellation remain intact and queryable.

5. **Workspace Quota & Rate Guardrails:**
   - `WORKSPACE_MAX_CONCURRENT_JOBS` (default: 2): Rejects new submissions with HTTP 429 (`RateLimitExceededError`) if active running jobs in the workspace equal or exceed the limit.
   - `WORKSPACE_DAILY_CALL_LIMIT` (default: 1000): Sums units submitted in the trailing 24 hours and rejects runs that would exceed the daily call budget, preventing accidental API key quota drain.


## Multi-Tenancy and Workspace Isolation

Every domain entity (`Dataset`, `Document`, `Experiment`, `EvaluationRun`, `Recommendation`, `Report`) contains a `workspace_id` foreign key. Query isolation is enforced by the reusable `WorkspaceContext` dependency in `backend/app/api/deps.py`:

```
Request (Bearer token + X-Workspace-Id)
  │
  ├─ Authenticate CurrentUser (or usr_default in local mode)
  ├─ Resolve WorkspaceContext & verify membership
  │    ├─ Check role (viewer: read-only, editor: read/write, owner: admin)
  │    └─ Invariant: cross-workspace ID lookup raises NotFoundError (404)
  │
  └─ Execute scoped service method (ctx.get_or_404, ctx.scope_query)
```

Key guarantees:
1. **Zero-Knowledge Existence Privacy:** If a user queries an ID belonging to another workspace, the server returns HTTP 404 (Not Found), never 403 (Forbidden). An attacker cannot determine whether an entity ID exists.
2. **Role-Based Access Control (RBAC):**
   - `viewer`: Read-only access to datasets, experiments, runs, reports, and masked provider key statuses.
   - `editor`: Can create, edit, run, and delete evaluation runs, datasets, and experiments. Cannot alter workspace membership or provider keys.
   - `owner`: Full administrative control, including member invitations, role promotions, and workspace provider key configuration.
3. **Dual Auth Modes (`AUTH_MODE=local|enabled`):**
   - In `local` mode, a pre-seeded `wks_default` and `usr_default` are injected seamlessly without requiring login or bearer headers.
   - In `enabled` mode, all resource routes enforce strict JWT bearer verification, and the application refuses to boot if `SECRET_KEY` is missing or default.

## Authentication and Session Lifecycle

```
User Registration (email + password)
  │
  ├─ Validate password strength (min 8 chars)
  ├─ Hash password via bcrypt (salt rounds = 12)
  └─ Seed personal default workspace
       │
User Login (/auth/login)
  │
  ├─ In-memory sliding-window rate limit (5 attempts/60s per IP)
  ├─ Constant-time bcrypt check (with precomputed dummy hash for non-existent users)
  └─ Issue dual tokens:
       ├─ Access Token (JWT, 15m, payload: sub=user_id, email, exp)
       └─ Refresh Token (Opaque 32-byte hex, 7d, stored as SHA-256 in DB)
            │
Token Refresh (/auth/refresh)
  │
  ├─ SHA-256 hash lookup of incoming token
  ├─ Replay detection: if token is already revoked, REVOKE ALL SESSIONS for that user
  └─ Atomically revoke old token, record replaced_by_hash, and issue fresh pair
```

## Threat Model

LLM-EvalHub implements defense-in-depth across the application boundary:

| Threat | Attack Vector | Mitigation & Technical Implementation |
|---|---|---|
| **Resource Existence Leakage** | ID enumeration across tenants (`/datasets/{id}`, `/experiments/{id}`) | `WorkspaceContext.get_or_404` returns `HTTP 404` (Not Found) for any record in a foreign workspace, matching the behavior of non-existent IDs. |
| **Credential Brute-Force** | Password guessing on `/auth/login` or `/auth/register` | Sliding-window `InMemoryRateLimiter` (5 requests / 60 seconds per IP, HTTP 429) + Redis fallback when `REDIS_URL` is configured. |
| **User Enumeration / Timing Side-Channels** | Probing `/auth/login` with known vs unknown emails | Bcrypt verification executes constant-time comparisons against a precomputed 60-character dummy pad (`DUMMY_BCRYPT_HASH`) when user is not found. Error message is identical: *"Invalid email or password"*. |
| **Token Theft & Replay Attacks** | Intercepted refresh tokens used to maintain persistence | Refresh tokens rotate on every use. Stored as SHA-256 hashes in DB. If an already-rotated token is submitted, the backend detects reuse and revokes **all** refresh tokens for that user account immediately. |
| **Provider Credential Exposure** | Database leaks or inadvertent logs revealing LLM provider keys | Provider keys are stored encrypted at rest using Fernet (`AES-128-CBC` with `HMAC-SHA256`). Responses mask keys to the last 4 characters (`...1a2b`). Regex filters redact keys, Bearer tokens, and passwords from application logs. |
| **Privilege Escalation** | Viewers modifying experiments or accessing secrets | Role hierarchy (`viewer` < `editor` < `owner`) is strictly enforced at API route dependencies. Viewers cannot mutate data; editors cannot manage workspace keys or members. |
| **Clickjacking & MIME-Sniffing** | Embedding API in malicious iframes or content-type confusion | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` on all API responses. |
| **Denial of Service via Payload Flooding** | Submitting gigabyte uploads to exhaust memory | Middleware enforces `MAX_UPLOAD_BYTES` rejection (`HTTP 413 Payload Too Large`) before parsing body. |

### Known Risks & Non-Goals (Out of Scope for Core Platform)
- **Email Verification & Self-Service Password Reset:** Requires external SMTP/Transactional Email infrastructure. In enterprise deployments, passwords are administrator-managed or provisioned via directory sync.
- **Multi-Factor Authentication (MFA / TOTP):** Native authenticator app / hardware token MFA is not built-in; perimeter zero-trust or reverse proxy auth should enforce 2FA.
- **Enterprise SSO / SAML / OIDC:** Single Sign-On federation is delegated to edge reverse proxies or API gateways.
- **Distributed DDoS Defense:** Volumetric Layer 7 DDoS mitigation must be handled by Cloudflare, AWS CloudFront, or upstream reverse proxies.

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
- **In-App Documentation:** Mounted at `/documentation` (and `/documentation/:sectionId`), fully bundled and static under `frontend/src/content/docs/`. Features a 3-column responsive layout (`DocsLayout`), client-side fuzzy search with keyboard shortcut `/` (`DocsSearch`), scroll-spy outline (`DocsOutline`), heading anchor copy buttons, step lists with expected results, theme-aware inline SVG diagrams, and dedicated print stylesheet (`@media print`). Cross-checked by `test_docs_integrity.py` and `npm run test:docs`.

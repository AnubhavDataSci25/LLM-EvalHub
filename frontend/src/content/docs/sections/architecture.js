export const architectureSection = {
  id: 'architecture',
  title: 'Architecture & Technical Design',
  group: 'Technical reference',
  summary: 'In-depth guide to the multi-tier system architecture, LangGraph execution state machines, provider abstraction interfaces, and typed error handling.',
  blocks: [
    {
      type: 'paragraph',
      text: 'LLM-EvalHub enforces strict unidirectional architectural layering: **each tier knows only about the tier beneath it.** High-level presentation components never interact directly with database models or raw provider payloads.',
    },
    {
      type: 'heading',
      id: 'layered-architecture',
      level: 2,
      text: 'Layered System Architecture',
    },
    {
      type: 'diagram',
      name: 'architecture',
      caption: 'Layered technical stack of LLM-EvalHub across Presentation, API, Services, Orchestration, Evaluation/RAG, and Persistence.',
    },
    {
      type: 'table',
      caption: 'Architectural Layer Responsibilities',
      headers: ['Layer', 'Directory', 'Primary Responsibility', 'Architectural Invariant (Must Not)'],
      rows: [
        ['Presentation', '`frontend/src`', 'User interface rendering, local state management, interactive charts, documentation.', 'Must not hold API credentials or execute evaluation scoring directly.'],
        ['HTTP / API', '`backend/app/api`', 'FastAPI request routing, Pydantic validation, CORS, request ID tracing, security headers.', 'Must not execute direct database transactions or business logic.'],
        ['Business Services', '`backend/app/services`', 'Workspace isolation policy, job coordination, comparison math, recommendation algorithms.', 'Must not know about provider wire protocols or HTTP status codes.'],
        ['Orchestration', '`backend/app/workflows`', 'LangGraph state machines for work unit execution and counterfactual attribution.', 'Must not bypass service validation layers.'],
        ['Domain & Evaluation', '`backend/app/evaluation`, `rag`', 'Deterministic metrics, LLM judges, RAG embedding/indexing, failure cascades.', 'Must not depend on database models or persistence.'],
        ['Integration', '`backend/app/providers`', 'Provider-specific HTTP adapters, streaming, model discovery, and typed error mapping.', 'Must not leak provider-specific exceptions or types upward.'],
        ['Persistence', '`backend/app/models`, `db`', 'SQLAlchemy 2.0 ORM models (29 tables) and Alembic schema migrations.', 'Must not contain business evaluation policy.'],
      ],
    },
    {
      type: 'heading',
      id: 'langgraph-workflow',
      level: 2,
      text: 'LangGraph Work-Unit Workflow',
    },
    {
      type: 'paragraph',
      text: 'Every individual work unit (the execution of one test case against one model) is coordinated through a stateful LangGraph workflow (`backend/app/workflows/evaluation_graph.py`):',
    },
    {
      type: 'diagram',
      name: 'workflow',
      caption: 'LangGraph state machine executed per work unit: prepare -> retrieve? -> generate -> evaluate -> detect_failure -> persist.',
    },
    {
      type: 'list',
      items: [
        '1. prepare: Resolves provider adapter, retrieves model parameters, and renders the prompt template with `{question}` and `{context}`.',
        '2. retrieve (conditional): If RAG is enabled for the experiment, executes vector, keyword, or hybrid retrieval over the document index and binds passages into context.',
        '3. generate: Dispatches the completion request through the bounded-concurrency provider adapter with retries and timeout tracking.',
        '4. evaluate: Executes the configured suite of deterministic and LLM-as-a-judge evaluators, recording raw and normalized scores.',
        '5. detect_failure: Passes all metric evidence and latency measurements through the ordered failure cascade to assign classification and confidence.',
        '6. persist: Atomically commits the EvaluationResult, MetricResults, and Failure record through an injected thread-safe callback.',
      ],
    },
    {
      type: 'heading',
      id: 'provider-abstraction',
      level: 2,
      text: 'Provider Abstraction & Typed Error Mapping',
    },
    {
      type: 'paragraph',
      text: 'All upstream model providers implement the `LLMProvider` abstract base class (`generate`, `list_models`, `health`, `describe`). Upstream HTTP errors are mapped into a unified typed hierarchy with explicit retry semantics:',
    },
    {
      type: 'table',
      caption: 'Provider Error Mapping Matrix',
      headers: ['HTTP Code', 'Error Kind', 'Retryable', 'Engine Behavior'],
      rows: [
        ['429', '`rate_limited`', 'Yes', 'Extracts Retry-After header or applies exponential backoff up to RETRY_ATTEMPTS.'],
        ['401 / 403', '`invalid_credentials`', 'No', 'Fails immediately; marks provider as misconfigured to prevent futile retries.'],
        ['404', '`model_unavailable`', 'No', 'Model checkpoint is retired, renamed, or unentitled. Evicts from availability cache.'],
        ['5xx', '`upstream_error`', 'Yes', 'Upstream server fault. Retries with backoff before isolating as a failed unit.'],
        ['Timeout', '`timeout`', 'Yes', 'Call exceeded REQUEST_TIMEOUT_SECONDS (60s). Aborts call and marks unit failed.'],
      ],
    },
  ],
}

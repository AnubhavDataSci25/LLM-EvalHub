export const installationSection = {
  id: 'installation',
  title: 'Installation & Configuration',
  group: 'Getting started',
  summary: 'Complete reference for system prerequisites, environment variables, database backends (SQLite vs PostgreSQL), LLM judge settings, CORS, and vector store options.',
  blocks: [
    {
      type: 'paragraph',
      text: 'LLM-EvalHub is designed with a strict zero-dependency local mode for rapid iteration, while offering seamless transition to enterprise infrastructure (PostgreSQL, Redis, Arq background workers, multi-tenant authentication) via standard environment variables.',
    },
    {
      type: 'callout',
      tone: 'honesty',
      title: 'Browser Isolation Guarantee',
      body: 'API keys live exclusively in backend environment variables or encrypted database fields. They are never entered in, stored in, or transmitted to the client browser.',
    },
    {
      type: 'heading',
      id: 'prerequisites',
      level: 2,
      text: 'System Prerequisites',
    },
    {
      type: 'list',
      items: [
        'Python: version 3.10, 3.11, or 3.12 (standard virtualenv recommended)',
        'Node.js: version 18.0.0 or higher with npm 9+',
        'Database: SQLite 3 (built into Python, zero setup) or PostgreSQL 15+ with psycopg driver',
        'Optional Queue: Redis 7.0+ (required only if JOB_BACKEND is set to arq for distributed worker queues)',
        'Optional Containers: Docker Engine 24+ and Docker Compose v2 for containerized deployment',
      ],
    },
    {
      type: 'heading',
      id: 'environment-variables',
      level: 2,
      text: 'Environment Variables Reference',
    },
    {
      type: 'paragraph',
      text: 'All settings are loaded at startup from `backend/.env` or system environment variables. The table below lists every supported variable, verified against `backend/app/core/config.py` and `.env.example`:',
    },
    {
      type: 'table',
      caption: 'Application Configuration Reference',
      headers: ['Variable Name', 'Purpose', 'Required', 'Example', 'Default'],
      rows: [
        ['`APP_ENV`', 'Runtime environment (development | production)', 'No', '`development`', '`development`'],
        ['`APP_DEBUG`', 'Enables verbose error traces in responses', 'No', '`true`', '`true`'],
        ['`API_PREFIX`', 'Prefix for all REST endpoints', 'No', '`/api`', '`/api`'],
        ['`CORS_ORIGINS`', 'Allowed frontend origins for CORS', 'No', '`http://localhost:5173`', '`http://localhost:5173,http://127.0.0.1:5173`'],
        ['`LOG_FORMAT`', 'Structured logging format (text | json)', 'No', '`json`', '`text`'],
        ['`ENABLE_METRICS`', 'Exposes Prometheus metrics on /metrics', 'No', '`true`', '`false`'],
        ['`AUTH_MODE`', 'Auth system mode: local (single-user) or enabled (multi-tenant)', 'No', '`local`', '`local`'],
        ['`SECRET_KEY`', 'HMAC key for JWT signing (required if auth enabled)', 'Conditional', '`random-32-byte-hex`', '`dev-insecure-...`'],
        ['`ENCRYPTION_KEY`', 'Fernet key for encrypting provider keys at rest', 'No', '`base64-32-bytes`', 'Derived from secret_key'],
        ['`ACCESS_TOKEN_EXPIRE_MINUTES`', 'Access JWT lifetime in minutes', 'No', '`15`', '`15`'],
        ['`REFRESH_TOKEN_EXPIRE_DAYS`', 'Refresh token lifetime in days', 'No', '`7`', '`7`'],
        ['`DATABASE_URL`', 'SQLAlchemy database connection string', 'No', '`sqlite:///./evalhub.db`', '`sqlite:///./llm_evalhub.db`'],
        ['`AUTO_MIGRATE`', 'Automatically runs alembic upgrade head on boot', 'No', '`true`', '`true`'],
        ['`REDIS_URL`', 'Redis connection string for distributed queues', 'No', '`redis://localhost:6379/0`', '`None` (in-memory)'],
        ['`JOB_BACKEND`', 'Job queue mode: auto | asyncio | arq', 'No', '`auto`', '`auto`'],
        ['`WORKSPACE_MAX_CONCURRENT_JOBS`', 'Max concurrent evaluation jobs per workspace', 'No', '`2`', '`2`'],
        ['`WORKSPACE_DAILY_CALL_LIMIT`', 'Maximum LLM calls per workspace per day', 'No', '`1000`', '`1000`'],
        ['`ENABLE_MOCK_PROVIDER`', 'Enables deterministic mock provider for tests', 'No', '`true`', '`true`'],
        ['`DEFAULT_EVALUATOR_PROVIDER`', 'Provider for LLM-as-a-judge metrics', 'No', '`gemini`', '`None`'],
        ['`DEFAULT_EVALUATOR_MODEL`', 'Model ID for LLM-as-a-judge metrics', 'No', '`gemini-2.5-flash`', '`None`'],
        ['`ENABLE_LLM_JUDGE`', 'Enables LLM-judge scored metrics in evaluations', 'No', '`true`', '`true`'],
        ['`ENABLE_RAGAS`', 'Enables RAGAS composite metrics library', 'No', '`false`', '`false`'],
        ['`MAX_CONCURRENT_REQUESTS`', 'Max outgoing concurrent provider requests', 'No', '`3`', '`3`'],
        ['`REQUEST_TIMEOUT_SECONDS`', 'Timeout for single LLM request in seconds', 'No', '`60`', '`60`'],
        ['`RETRY_ATTEMPTS`', 'Number of retries on 429 or 5xx provider errors', 'No', '`2`', '`2`'],
        ['`MAX_DATASET_ROWS`', 'Maximum allowed rows in uploaded dataset', 'No', '`5000`', '`2000`'],
        ['`MAX_UPLOAD_BYTES`', 'Maximum file upload size in bytes (25MB)', 'No', '`26214400`', '`26214400`'],
        ['`EMBEDDING_BACKEND`', 'RAG embedding backend: hashing | gemini | sentence-transformers', 'No', '`hashing`', '`hashing`'],
        ['`VECTOR_STORE_BACKEND`', 'Vector store backend: auto | faiss | numpy', 'No', '`auto`', '`auto`'],
        ['`DEFAULT_CHUNK_SIZE`', 'Default document chunk size in characters', 'No', '`800`', '`800`'],
        ['`DEFAULT_CHUNK_OVERLAP`', 'Default character overlap between chunks', 'No', '`120`', '`120`'],
        ['`DEFAULT_TOP_K`', 'Default number of context chunks retrieved', 'No', '`4`', '`4`'],
        ['`STORAGE_DIR`', 'Local filesystem path for document storage', 'No', '`./storage`', '`./storage`'],
      ],
    },
    {
      type: 'heading',
      id: 'database-configuration',
      level: 2,
      text: 'Database Configuration: SQLite vs PostgreSQL',
    },
    {
      type: 'paragraph',
      text: 'LLM-EvalHub uses SQLAlchemy 2.0 and Alembic migrations. Switching databases requires changing only the `DATABASE_URL` string:',
    },
    {
      type: 'code',
      language: 'bash',
      filename: 'backend/.env',
      code: `# SQLite (Default for zero-dependency local development)
DATABASE_URL=sqlite:///./llm_evalhub.db

# PostgreSQL (Recommended for production and team environments)
DATABASE_URL=postgresql+psycopg://evalhub:evalhub@localhost:5432/evalhub`,
    },
    {
      type: 'callout',
      tone: 'info',
      title: 'Automated Migration Execution',
      body: 'With `AUTO_MIGRATE=true` (the default), LLM-EvalHub automatically runs `alembic upgrade head` on application startup, creating or migrating all 29 tables seamlessly.',
    },
    {
      type: 'heading',
      id: 'judge-settings',
      level: 2,
      text: 'LLM-as-a-Judge Configuration',
    },
    {
      type: 'paragraph',
      text: 'When computing metrics such as `faithfulness` or `answer_relevance` without pre-computed embeddings, an LLM judge evaluates the outputs. You can configure the judge model via environment variables:',
    },
    {
      type: 'code',
      language: 'bash',
      filename: 'backend/.env',
      code: `# Configure Gemini as the automated judge
DEFAULT_EVALUATOR_PROVIDER=gemini
DEFAULT_EVALUATOR_MODEL=gemini-2.5-flash

# Or configure Groq with an open-weights model
# DEFAULT_EVALUATOR_PROVIDER=groq
# DEFAULT_EVALUATOR_MODEL=llama-3.3-70b-versatile`,
    },
    {
      type: 'paragraph',
      text: 'If `DEFAULT_EVALUATOR_PROVIDER` is left empty, LLM-EvalHub automatically falls back to deterministic lexical evaluators (character F1, ROUGE-L, BLEU-4), ensuring reproducible execution with zero token expenditure.',
    },
    {
      type: 'heading',
      id: 'rag-vector-options',
      level: 2,
      text: 'RAG & Vector Store Options',
    },
    {
      type: 'paragraph',
      text: 'The RAG subsystem provides three embedding algorithms and two vector store backends:',
    },
    {
      type: 'list',
      items: [
        'hashing (default): Deterministic locality-sensitive feature hashing. Requires no downloads, works offline everywhere, and uses zero GPU memory.',
        'gemini: High-fidelity semantic embeddings via Google Generative AI (text-embedding-004, requires GEMINI_API_KEY).',
        'sentence-transformers: Local semantic embeddings running locally (requires optional PyTorch extras).',
        'vector_store_backend=auto: Uses FAISS if installed; otherwise falls back automatically to a vectorized NumPy cosine-similarity matrix.',
      ],
    },
  ],
}

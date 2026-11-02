export const apiReferenceSection = {
  id: 'api-reference',
  title: 'REST API Reference',
  group: 'Technical reference',
  summary: 'Complete endpoint index organized by domain group with HTTP methods, paths, parameter specifications, and copy-able curl examples.',
  blocks: [
    {
      type: 'paragraph',
      text: 'LLM-EvalHub exposes a clean, versioned REST API mounted under `/api`. All endpoints enforce workspace tenant isolation and return standardized JSON error bodies.',
    },
    {
      type: 'callout',
      tone: 'info',
      title: 'Interactive API Documentation',
      body: 'You can explore and test every API endpoint live using the built-in [Interactive Swagger UI](/docs) or view the full OpenAPI 3.1 specification on [ReDoc](/redoc).',
    },
    {
      type: 'heading',
      id: 'endpoint-directory',
      level: 2,
      text: 'Endpoint Directory by Domain Group',
    },
    {
      type: 'table',
      caption: 'Core API Endpoints Reference',
      headers: ['Method', 'Path', 'Domain Group', 'Purpose'],
      rows: [
        ['GET', '`/api/health`', 'Health & Ops', 'Liveness probe returning HTTP 200.'],
        ['GET', '`/api/ready`', 'Health & Ops', 'Deep readiness probe verifying DB connectivity and Redis.'],
        ['GET', '`/api/metrics`', 'Health & Ops', 'Prometheus-compatible metrics exposition (when enabled).'],
        ['GET', '`/api/dashboard`', 'Dashboard', 'Retrieves workspace aggregated KPIs, charts, and activity.'],
        ['GET', '`/api/datasets`', 'Datasets', 'Lists datasets in the active workspace.'],
        ['POST', '`/api/datasets/upload`', 'Datasets', 'Uploads and validates a CSV or JSON dataset.'],
        ['GET', '`/api/datasets/:id`', 'Datasets', 'Retrieves dataset metadata and test case preview.'],
        ['GET', '`/api/benchmarks`', 'Benchmarks', 'Lists all 6 available curated benchmark packs.'],
        ['POST', '`/api/benchmarks/:key/install`', 'Benchmarks', 'Installs a benchmark pack and indexes its documents.'],
        ['GET', '`/api/documents`', 'RAG & Documents', 'Lists ingested knowledge base documents.'],
        ['POST', '`/api/documents/upload`', 'RAG & Documents', 'Uploads and chunks a PDF, Markdown, or TXT file.'],
        ['POST', '`/api/documents/preview`', 'RAG & Documents', 'Tests retrieval query and returns top-k chunks without full eval.'],
        ['GET', '`/api/experiments`', 'Experiments', 'Lists historical experiments and lineage chains.'],
        ['POST', '`/api/experiments/:id/improve`', 'Experiments', 'Creates a child experiment with whitelisted parameter overrides.'],
        ['POST', '`/api/evaluations/run`', 'Evaluations', 'Submits a new evaluation run to the background queue.'],
        ['GET', '`/api/evaluations/:id`', 'Evaluations', 'Polls real-time progress and completed work units.'],
        ['POST', '`/api/evaluations/:id/cancel`', 'Evaluations', 'Cooperatively cancels an active evaluation run.'],
        ['POST', '`/api/evaluations/:id/resume`', 'Evaluations', 'Idempotently resumes an interrupted or cancelled run.'],
        ['POST', '`/api/compare`', 'Comparison', 'Executes paired statistical analysis between two runs.'],
        ['GET', '`/api/failures`', 'Failures & Diagnosis', 'Lists classified failure records with category filters.'],
        ['POST', '`/api/failures/:id/diagnose`', 'Failures & Diagnosis', 'Runs heuristic and LLM root cause diagnosis.'],
        ['GET', '`/api/recommendations`', 'Recommendations', 'Computes model utility rankings under priority profiles.'],
        ['GET', '`/api/reports`', 'Reports', 'Lists frozen evaluation summary reports.'],
        ['GET', '`/api/reports/:id/export`', 'Reports', 'Exports report data in JSON or CSV format.'],
        ['GET', '`/api/providers`', 'Providers', 'Lists provider integration status and audited models.'],
        ['GET', '`/workspaces/:id/audit-logs`', 'Security & Audit', 'Owner-only retrieval of immutable workspace audit logs.'],
      ],
    },
    {
      type: 'heading',
      id: 'curl-examples',
      level: 2,
      text: 'Copy-able API Examples',
    },
    {
      type: 'paragraph',
      text: 'The following examples demonstrate standard API interactions. When authentication is enabled (`AUTH_MODE=enabled`), pass `Authorization: Bearer <token>` and `X-Workspace-Id: <id>` in request headers.',
    },
    {
      type: 'code',
      language: 'bash',
      filename: '1. Check System Readiness',
      code: `curl -s -X GET http://localhost:8000/api/ready`,
    },
    {
      type: 'code',
      language: 'json',
      filename: 'Sample Readiness Response (Illustrative)',
      code: `{
  "status": "ready",
  "database": "connected",
  "redis": "connected",
  "default_evaluator": {
    "configured": true,
    "provider": "gemini",
    "model_id": "gemini-2.5-flash"
  }
}`,
    },
    {
      type: 'code',
      language: 'bash',
      filename: '2. Dispatch an Evaluation Run',
      code: `curl -s -X POST http://localhost:8000/api/evaluations/run \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "Quickstart RAG Evaluation",
    "dataset_id": "ds_demo123",
    "models": [
      {"provider": "mock", "model": "mock-extractive"},
      {"provider": "mock", "model": "mock-hallucinate"}
    ],
    "metrics": ["correctness", "faithfulness", "latency"],
    "parameters": {"temperature": 0.0, "max_tokens": 300}
  }'`,
    },
    {
      type: 'code',
      language: 'json',
      filename: 'Sample Evaluation Run Response (Illustrative)',
      code: `{
  "run_id": "run_9f2a81bc",
  "job_id": "job_01h8a9bc",
  "status": "queued",
  "total_units": 60,
  "completed_units": 0,
  "created_at": "2026-11-02T12:00:00Z"
}`,
    },
  ],
}

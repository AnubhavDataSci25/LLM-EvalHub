export const dataModelSection = {
  id: 'data-model',
  title: 'Data Model & Database Schema',
  group: 'Technical reference',
  summary: 'Complete architectural reference for the 29 database tables, entity relationships, tenant isolation boundaries, and Alembic versioning.',
  blocks: [
    {
      type: 'paragraph',
      text: 'LLM-EvalHub uses SQLAlchemy 2.0 ORM with 29 database tables managed through Alembic schema migrations. The data model is anchored around multi-tenant Workspace boundaries: every operational asset belongs to exactly one workspace.',
    },
    {
      type: 'heading',
      id: 'entity-relationship-graph',
      level: 2,
      text: 'Core Entity Relationship Graph',
    },
    {
      type: 'code',
      language: 'text',
      filename: 'Multi-Tenant Schema Spine',
      code: `Workspace ──┬──< WorkspaceMember ─> User ──< RefreshToken
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

HumanLabel ─< CalibrationRun     AuditRun ─< ModelAvailability`,
    },
    {
      type: 'heading',
      id: 'table-directory',
      level: 2,
      text: 'Database Tables Grouped by Purpose',
    },
    {
      type: 'table',
      caption: '29 Tables Schema Reference',
      headers: ['Table Name', 'Domain Purpose', 'Primary Relationship / Foreign Keys'],
      rows: [
        ['`workspaces`', 'Tenant container establishing data boundary', 'Root entity for all datasets, experiments, and documents.'],
        ['`users`', 'User accounts and argon2/bcrypt password credentials', 'Belongs to workspaces via workspace_members.'],
        ['`workspace_members`', 'Membership table with RBAC roles (owner, editor, viewer)', 'workspace_id -> workspaces.id, user_id -> users.id.'],
        ['`refresh_tokens`', 'Rotating hashed JWT refresh tokens with replay detection', 'user_id -> users.id.'],
        ['`workspace_provider_keys`', 'Fernet-encrypted provider API credentials stored at rest', 'workspace_id -> workspaces.id.'],
        ['`datasets`', 'Test suite container with schema validation status', 'workspace_id -> workspaces.id.'],
        ['`dataset_versions`', 'Immutable snapshot version of a dataset', 'dataset_id -> datasets.id.'],
        ['`test_cases`', 'Atomic question, ground truth reference, and context', 'dataset_version_id -> dataset_versions.id.'],
        ['`documents`', 'Ingested knowledge base files (PDF, Markdown, TXT)', 'workspace_id -> workspaces.id.'],
        ['`document_chunks`', 'Partitioned text segments with character offsets and citations', 'document_id -> documents.id.'],
        ['`experiments`', 'Frozen evaluation specification and prompt configuration', 'workspace_id -> workspaces.id, parent_experiment_id -> experiments.id.'],
        ['`experiment_models`', 'Candidate model identifiers selected for an experiment', 'experiment_id -> experiments.id.'],
        ['`evaluation_runs`', 'Execution session tracking progress, status, and duration', 'experiment_id -> experiments.id.'],
        ['`evaluation_results`', 'Per-case model generation, latency, and pass/fail outcome', 'run_id -> evaluation_runs.id, test_case_id -> test_cases.id.'],
        ['`metric_results`', 'Scored dimension (Correctness, Faithfulness) with kind and evidence', 'result_id -> evaluation_results.id.'],
        ['`failures`', 'Classified failure instance with category and confidence', 'result_id -> evaluation_results.id.'],
        ['`attribution_runs`', 'Counterfactual failure attribution execution session', 'failure_id -> failures.id.'],
        ['`attribution_conditions`', 'Trial results under counterfactual conditions (oracle vs no-context)', 'attribution_run_id -> attribution_runs.id.'],
        ['`recommendations`', 'Weighted profile ranking with score breakdown and caveats', 'workspace_id -> workspaces.id, experiment_id -> experiments.id.'],
        ['`reports`', 'Frozen audit report snapshot with JSON/CSV export', 'workspace_id -> workspaces.id.'],
        ['`jobs`', 'Durable background job record for Asyncio/Arq state machines', 'workspace_id -> workspaces.id.'],
        ['`audit_logs`', 'Immutable record of security and administrative actions', 'workspace_id -> workspaces.id, user_id -> users.id.'],
        ['`human_labels`', 'Blind human annotations for judge calibration', 'workspace_id -> workspaces.id, result_id -> evaluation_results.id.'],
        ['`calibration_runs`', 'Inter-rater agreement session calculating Cohen\'s kappa', 'workspace_id -> workspaces.id.'],
        ['`audit_runs`', 'Model availability probing execution session', 'Records provider scan duration and probe counts.'],
        ['`model_availabilities`', 'Cached model verification probe result with TTL', 'provider, model_id, status (available, rate_limited).'],
      ],
    },
    {
      type: 'callout',
      tone: 'info',
      title: 'Alembic Schema Evolution',
      body: 'All 29 tables are versioned through Alembic migrations (`backend/alembic/versions/`). SQLite operates with `render_as_batch=True` to guarantee complete migration parity with PostgreSQL in production.',
    },
  ],
}

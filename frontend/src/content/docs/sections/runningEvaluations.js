export const runningEvaluationsSection = {
  id: 'running-evaluations',
  title: 'Running & Monitoring Evaluations',
  group: 'Using the platform',
  summary: 'Real-time job execution lifecycle, progressive persistence, bounded provider concurrency, rate-limit backoff, mid-flight cancellation, and crash-resilient resumption.',
  blocks: [
    {
      type: 'paragraph',
      text: 'When an evaluation is dispatched, it executes asynchronously under the Job Service (`JobBackend`). The Evaluation Detail page (`/evaluations/:id`) provides real-time streaming progress, work unit completion counters, live failure detection, and control actions.',
    },
    {
      type: 'heading',
      id: 'job-statuses',
      level: 2,
      text: 'Evaluation Lifecycle Statuses',
    },
    {
      type: 'table',
      caption: 'Evaluation State Machine',
      headers: ['Status', 'Badge Tone', 'Description', 'Allowed Next States'],
      rows: [
        ['`queued`', 'Neutral', 'Job submitted, waiting for worker slot in workspace pool.', 'running, cancelled'],
        ['`running`', 'Info (Pulse)', 'Worker is processing work units concurrently.', 'completed, failed, cancelled, interrupted'],
        ['`completed`', 'Good (Green)', 'All work units processed, summaries aggregated and committed.', 'Terminal'],
        ['`failed`', 'Bad (Red)', 'Fatal unhandled failure (e.g. database disconnect).', 'Terminal'],
        ['`cancelled`', 'Neutral (Gray)', 'Cooperatively halted by user mid-flight.', 'Terminal (resumable)'],
        ['`interrupted`', 'Warn (Yellow)', 'Worker crashed or restarted while run was active.', 'Terminal (resumable)'],
      ],
    },
    {
      type: 'heading',
      id: 'polling-and-persistence',
      level: 2,
      text: 'Progressive Commits and Polling Backoff',
    },
    {
      type: 'paragraph',
      text: 'LLM-EvalHub uses progressive persistence rather than holding results in memory until the end of a run:',
    },
    {
      type: 'list',
      items: [
        'Progressive Commits: Work units are committed to the database in batches of 5 units. If a browser disconnects or refreshes, completed results remain intact.',
        'Adaptive Polling: The UI polls `/api/evaluations/:id` with backoff: 1s while active, scaling to 4s under load, and disconnecting automatically once terminal status is reached.',
      ],
    },
    {
      type: 'heading',
      id: 'concurrency-and-rate-limits',
      level: 2,
      text: 'Concurrency, Timeouts, and 429 Rate Limits',
    },
    {
      type: 'paragraph',
      text: 'Provider requests are strictly throttled to prevent API account bans:',
    },
    {
      type: 'list',
      items: [
        'Bounded Concurrency (`MAX_CONCURRENT_REQUESTS=3`): Bounds simultaneous HTTP requests dispatched to upstream provider endpoints.',
        'Request Timeout (`REQUEST_TIMEOUT_SECONDS=60`): Any call exceeding 60 seconds is aborted and marked as a timeout failure.',
        'Rate-Limit Backoff: If an upstream provider returns HTTP 429 Too Many Requests, the adapter extracts the `Retry-After` header (or applies exponential backoff) and retries up to `RETRY_ATTEMPTS=2` times.',
      ],
    },
    {
      type: 'heading',
      id: 'failure-isolation',
      level: 2,
      text: 'Per-Unit Failure Isolation',
    },
    {
      type: 'callout',
      tone: 'honesty',
      title: 'A Provider Error Never Kills the Entire Run',
      body: 'If model X crashes or exhausts quota mid-run on case #15, only that individual work unit records an error status. The engine continues evaluating the remaining test cases for all other models.',
    },
    {
      type: 'heading',
      id: 'cancellation-and-resume',
      level: 2,
      text: 'Cooperative Cancellation and Resumption',
    },
    {
      type: 'paragraph',
      text: 'You can halt a running evaluation by clicking "Cancel Run". The engine cooperatively terminates between work units, preserving all results processed up to that point. Clicking "Resume Run" triggers an idempotent recovery: the service detects already-scored test cases and executes only the remaining units without re-billing provider tokens.',
    },
  ],
}

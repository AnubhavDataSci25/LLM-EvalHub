export const dashboardSection = {
  id: 'dashboard',
  title: 'Dashboard',
  group: 'Using the platform',
  summary: 'The operational nerve center of LLM-EvalHub, presenting workspace KPIs, metric distribution charts, failure taxonomy, latency trends, and recent experiment deltas.',
  blocks: [
    {
      type: 'paragraph',
      text: 'The Dashboard (`/dashboard`) provides an aggregated overview of all evaluation activity across the active workspace. Every number and chart on this page is computed directly from stored evaluation results in the database; no figures are simulated or guessed.',
    },
    {
      type: 'heading',
      id: 'kpi-cards',
      level: 2,
      text: 'KPI Metric Cards',
    },
    {
      type: 'paragraph',
      text: 'The top row surfaces high-level workspace health indicators:',
    },
    {
      type: 'table',
      caption: 'Dashboard KPI Reference',
      headers: ['KPI Card', 'What It Shows', 'How It Is Computed', 'How to Read It'],
      rows: [
        ['Total Test Cases', 'Volume of test items available in active workspace', 'Count of records in the test_cases table across all datasets', 'Higher numbers indicate broader test coverage across domains and intents.'],
        ['Evaluations Run', 'Total evaluation runs executed', 'Count of records in the evaluation_runs table', 'Shows overall experimental velocity in the workspace.'],
        ['Avg Correctness', 'Mean factual correctness of evaluated answers', 'Mean of available correctness scores across completed units', 'Scale 0.0 to 1.0. A drop indicates regression against reference answers.'],
        ['Avg Faithfulness', 'Mean grounding score against retrieved context', 'Mean of available faithfulness scores', 'Measures context adherence. Values below 0.70 indicate hallucination risk.'],
        ['Avg Answer Relevance', 'Mean relevance to the user query', 'Mean of available answer_relevance scores', 'Detects evasive, overly generic, or tangential model responses.'],
        ['Avg Latency', 'Mean end-to-end response duration', 'Mean of latency_ms across completed work units (in milliseconds)', 'Surfaces infrastructure slowdowns or verbose generation bottlenecks.'],
        ['Failure Rate', 'Proportion of work units failing thresholds', 'Failed units divided by total evaluated units', 'Percentage of outputs triggering the diagnostic cascade.'],
      ],
    },
    {
      type: 'callout',
      tone: 'honesty',
      title: 'Missing Scores Are Never Zero',
      body: 'If a dataset lacks reference answers or retrieved context, correctness and faithfulness return as unavailable. They are excluded from headline averages rather than dragging the score down to zero.',
    },
    {
      type: 'heading',
      id: 'dashboard-charts',
      level: 2,
      text: 'Visualization Charts',
    },
    {
      type: 'paragraph',
      text: 'The dashboard renders five interactive charts built with Recharts, adapting dynamically to light and dark theme tokens:',
    },
    {
      type: 'list',
      items: [
        'Model Comparison Chart: Grouped bar chart comparing candidate models across headline metrics (Correctness, Faithfulness, Relevance, Latency). Allows quick identification of Pareto-optimal models.',
        'Metric Trend Chart: Multi-line timeline tracking metric movements across completed runs over time, showing whether quality is improving as configurations change.',
        'Failure Distribution Chart: Horizontal bar or donut chart breaking down diagnosed failures across the 10 failure categories (e.g. ungrounded_hallucination, retrieval_miss).',
        'Latency Distribution Chart: Histogram displaying request latencies binned across response-time buckets (e.g. <500ms, 1-2s, >5s).',
        'Experiment Deltas: Compact delta cards displaying before-vs-after differences from recent follow-up runs with statistical verdicts.',
      ],
    },
    {
      type: 'heading',
      id: 'empty-state',
      level: 2,
      text: 'Empty-State Behaviour',
    },
    {
      type: 'paragraph',
      text: 'When a new workspace has no evaluation data, the dashboard displays a clean orientation state with quick links to install a Benchmark Pack or create a New Evaluation, instead of blank or broken charts.',
    },
  ],
}

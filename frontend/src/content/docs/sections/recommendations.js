export const recommendationsSection = {
  id: 'recommendations',
  title: 'Recommendations Engine',
  group: 'Using the platform',
  summary: 'Transparent multi-attribute utility ranking of evaluated models under configurable priority profiles with explicit evidence, score breakdowns, and empirical caveats.',
  blocks: [
    {
      type: 'paragraph',
      text: 'The Recommendations page (`/recommendations`) helps you select the right model for deployment based on your application priorities. The engine evaluates candidate models evaluated in your workspace against multi-criteria utility functions and hard constraints.',
    },
    {
      type: 'callout',
      tone: 'honesty',
      title: 'The Honesty Rule: Never "The Best Model"',
      body: 'LLM-EvalHub never claims a model is universally "the best". A recommendation is strictly conditional on the specific dataset tested, the priority profile chosen, and the constraints applied. The caveats section explicitly notes any edge cases where the top-ranked model underperformed.',
    },
    {
      type: 'heading',
      id: 'priority-profiles',
      level: 2,
      text: 'Priority Profiles & Weightings',
    },
    {
      type: 'table',
      caption: 'Built-in Profile Weightings',
      headers: ['Profile', 'Description', 'Correctness', 'Faithfulness', 'Relevance', 'Latency'],
      rows: [
        ['`balanced`', 'Even compromise between accuracy, grounding, and response time.', '0.35', '0.30', '0.20', '0.15'],
        ['`quality`', 'Prioritizes factual correctness; tolerates slower response times.', '0.45', '0.30', '0.20', '0.05'],
        ['`faithfulness`', 'Prioritizes context grounding for compliance-sensitive RAG.', '0.25', '0.50', '0.10', '0.00 (Recall: 0.15)'],
        ['`latency`', 'Prioritizes speed for interactive consumer-facing applications.', '0.25', '0.20', '0.10', '0.45'],
        ['`custom`', 'Fully user-configurable weights and hard quality/latency thresholds.', 'Custom', 'Custom', 'Custom', 'Custom'],
      ],
    },
    {
      type: 'heading',
      id: 'scoring-mechanics',
      level: 2,
      text: 'Magnitude-Preserving Scoring Mechanics',
    },
    {
      type: 'paragraph',
      text: 'Many ranking tools use min-max normalization across candidates, which distorts subtle differences. LLM-EvalHub uses magnitude-preserving scoring:',
    },
    {
      type: 'list',
      items: [
        'Quality Metrics: Correctness, Faithfulness, and Relevance are already naturally bounded on a [0.0, 1.0] scale and are used directly.',
        'Latency Scoring: Latency is unbounded and lower is better. It is scored as a ratio against the fastest candidate model in the run: `score = fastest_latency_ms / this_model_latency_ms`.',
        'Composite Utility: Weighted sum of all available normalized dimensions, re-normalized if any individual metric is unavailable.',
      ],
    },
    {
      type: 'heading',
      id: 'constraints-and-caveats',
      level: 2,
      text: 'Hard Constraints and Caveats',
    },
    {
      type: 'paragraph',
      text: 'You can enforce hard constraints (e.g. `latency_ms <= 1500` or `faithfulness >= 0.80`). Any model failing a hard constraint is filtered out with an explanation. If no candidate passes, the system states so plainly rather than relaxing the constraints.',
    },
  ],
}

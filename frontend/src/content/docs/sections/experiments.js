export const experimentsSection = {
  id: 'experiments',
  title: 'Results & Experiments',
  group: 'Using the platform',
  summary: 'Explore reproducible experiment records, lineage parent-child chains, per-case result matrices, and configuration cloning.',
  blocks: [
    {
      type: 'paragraph',
      text: 'The Experiments page (`/experiments`) and Experiment Detail (`/experiments/:id`) maintain the historical record of every evaluation configuration. An experiment freezes all parameters (dataset, prompt, temperature, chunk size, top-k, models) into an immutable record so results remain reproducible over time.',
    },
    {
      type: 'heading',
      id: 'frozen-configuration',
      level: 2,
      text: 'Frozen Configuration Records',
    },
    {
      type: 'paragraph',
      text: 'Each experiment records the exact state of the system when the evaluation was created:',
    },
    {
      type: 'list',
      items: [
        'Dataset Version: Links to the exact snapshot ID of the test suite evaluated.',
        'Model Catalog: Exact provider and model IDs evaluated (e.g. groq/llama-3.3-70b-versatile).',
        'Generation Parameters: Temperature, max output tokens, prompt template, and system prompt.',
        'RAG Parameters: Knowledge base ID, embedding backend, retriever strategy, chunk size, chunk overlap, and top-k.',
        'Lineage Tracking: Records `parent_experiment_id` when created through the Improvement Loop, creating a verifiable tree of iterations.',
      ],
    },
    {
      type: 'heading',
      id: 'per-case-matrix',
      level: 2,
      text: 'Per-Case Result Exploration',
    },
    {
      type: 'paragraph',
      text: 'The Experiment Detail view provides a comprehensive tabular matrix of all evaluated test cases:',
    },
    {
      type: 'list',
      items: [
        'Interactive Filtering: Filter by candidate model, pass/fail status, failure category, or specific score thresholds.',
        'Side-by-Side Outputs: Inspect model answers, reference ground truth, and retrieved context passages for any test case.',
        'Metric Breakdowns: Review individual scores for Correctness, Faithfulness, Relevance, and Latency.',
      ],
    },
    {
      type: 'heading',
      id: 'cloning-and-reproducing',
      level: 2,
      text: 'Cloning and Reproducing Experiments',
    },
    {
      type: 'paragraph',
      text: 'To test a slight variation without re-entering all settings:',
    },
    {
      type: 'steps',
      steps: [
        {
          title: '1. Open the Experiment Detail page',
          body: 'Navigate to "/experiments/:id" for the baseline run you wish to reproduce.',
          expected: 'Experiment overview displays parameters, metric averages, and past runs.',
        },
        {
          title: '2. Click "Clone Experiment"',
          body: 'Clicking clone opens the New Evaluation form pre-filled with all identical parameters, prompts, models, and retrieval settings.',
          expected: 'The evaluation setup form is populated with the frozen baseline configuration.',
        },
        {
          title: '3. Adjust the target variable and launch',
          body: 'Modify exactly the single variable under test (e.g., lower temperature from 0.7 to 0.0) and submit.',
          expected: 'A linked experiment is initialized, preserving clean A/B comparability.',
        },
      ],
    },
  ],
}

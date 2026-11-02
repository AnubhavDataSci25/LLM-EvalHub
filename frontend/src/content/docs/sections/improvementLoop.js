export const improvementLoopSection = {
  id: 'improvement-loop',
  title: 'Improvement Loop',
  group: 'Using the platform',
  summary: 'Turn diagnostic recommendations into targeted follow-up experiments that modify whitelisted parameters, re-run test cases, and prove whether changes helped.',
  blocks: [
    {
      type: 'paragraph',
      text: 'The Improvement Loop bridges evaluation and remediation. Instead of leaving you to manually recreate configurations after diagnosing a failure, LLM-EvalHub lets you accept a recommendation with one click to spawn an exact follow-up experiment linked by parent lineage.',
    },
    {
      type: 'heading',
      id: 'applicable-fields',
      level: 2,
      text: 'Whitelisted Parameter Overrides',
    },
    {
      type: 'paragraph',
      text: 'To prevent diagnoses from arbitrarily rewriting experiments, the backend enforces a strict whitelist (`APPLICABLE_FIELDS` in `backend/app/services/improvement_service.py`). Only the following parameters can be modified in an improvement experiment:',
    },
    {
      type: 'list',
      items: [
        'Retrieval Tuning: `top_k`, `chunk_size`, `chunk_overlap`, `retriever` (vector, keyword, hybrid), `rag_enabled`, `rag_collection`, `embedding_backend`.',
        'Prompt Optimization: `system_prompt`, `prompt_template`.',
        'Model Parameters: `temperature`, `max_tokens`, `models`.',
        'Evaluation Configuration: `metrics`, `metric_weights`, `judge_provider`, `judge_model`.',
      ],
    },
    {
      type: 'callout',
      tone: 'tip',
      title: 'Isolated Variable Principle',
      body: 'Best practice: change exactly one parameter at a time (e.g. increase top_k from 3 to 5 while keeping chunk_size and prompt identical). This ensures that any observed metric delta is attributable solely to that change.',
    },
    {
      type: 'heading',
      id: 'workflow-steps',
      level: 2,
      text: 'Step-by-Step Improvement Flow',
    },
    {
      type: 'steps',
      steps: [
        {
          title: '1. Review Recommendation or Failure Diagnosis',
          body: 'On the Recommendations or Failure Detail page, inspect the suggested change (e.g. "Switch retriever from vector to hybrid to resolve terminology misses").',
          expected: 'Action card displays exact suggested override with predicted score impact.',
        },
        {
          title: '2. Click "Accept & Create Follow-up Experiment"',
          body: 'The engine calls `POST /experiments/:id/improve`, creating a cloned child experiment linked to the parent via parent_experiment_id.',
          expected: 'A new experiment is created with all parameters frozen from the baseline except the single accepted override.',
        },
        {
          title: '3. Re-evaluate the Follow-up Experiment',
          body: 'Run the newly created experiment against the same dataset.',
          expected: 'The background worker processes work units under the updated configuration.',
        },
        {
          title: '4. Read the Before-vs-After Improvement Verdict',
          body: 'Navigate to Compare to view the paired before/after delta analysis, effect size, and statistical verdict.',
          expected: 'Definitive badge ("improved", "regressed", or "no_change") confirming whether the remediation solved the issue.',
        },
      ],
    },
  ],
}

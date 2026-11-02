export const newEvaluationSection = {
  id: 'new-evaluation',
  title: 'New Evaluation',
  group: 'Using the platform',
  summary: 'Configure and dispatch reproducible evaluation runs across datasets, candidate models, metrics with kind labels, prompts, generation parameters, and RAG retrievers.',
  blocks: [
    {
      type: 'paragraph',
      text: 'The New Evaluation page (`/evaluations/new`) is the primary configuration interface for launching experiments. Rather than hiding settings in multi-step wizard modals, the entire configuration is visible on one page because an experiment is a frozen, reproducible record of all parameters.',
    },
    {
      type: 'heading',
      id: 'form-fields',
      level: 2,
      text: 'Configuration Fields Step-by-Step',
    },
    {
      type: 'table',
      caption: 'Evaluation Setup Fields',
      headers: ['Field', 'Default Value', 'Description', 'Options / Syntax'],
      rows: [
        ['Experiment Name', 'Auto-generated', 'Human-readable label for the experiment and its subsequent runs.', 'E.g., "Customer Support - Llama vs Gemini"'],
        ['Dataset', 'First available', 'The test suite containing questions, references, and contexts.', 'Select from datasets in the active workspace.'],
        ['Candidate Models', 'Mock models (or active keys)', 'One or more provider/model pairs evaluated on identical test cases.', 'Select provider and verified model identifier.'],
        ['Metrics', 'Correctness, Relevance, Latency', 'The quality and performance dimensions to evaluate.', 'Categorized by kind: deterministic, llm_judge, performance.'],
        ['System Prompt', 'Factual assistant prompt', 'System-level instructions prepended to model context.', 'Editable multiline text.'],
        ['Prompt Template', '{context} ... {question}', 'Template used to assemble the user turn.', 'Must contain {question} and optionally {context}.'],
        ['Temperature', '0.0', 'Sampling temperature for candidate models.', 'Range 0.0 to 1.0. Lower values yield reproducible results.'],
        ['Max Output Tokens', '500', 'Maximum response tokens per generation.', 'Bounded by provider limits.'],
        ['Enable RAG', 'False (or pack default)', 'When toggled, retrieves external documents before generation.', 'Requires selecting a Document knowledge base.'],
        ['Retriever Strategy', 'vector', 'Search mode for document retrieval.', '`vector`, `keyword` (BM25), or `hybrid` (RRF).'],
        ['Top-k Chunks', '4', 'Number of chunks injected into prompt context.', 'Range 1 to 10.'],
      ],
    },
    {
      type: 'heading',
      id: 'provider-availability',
      level: 2,
      text: 'Model Availability & Status Badges',
    },
    {
      type: 'paragraph',
      text: 'LLM-EvalHub does not show static catalogs of unverified models. The model selector displays live audit statuses:',
    },
    {
      type: 'list',
      items: [
        'Configured / Available (Green): The provider key is present and a live verification probe confirmed the model can generate completions.',
        'Rate Limited (Yellow): The model is valid but currently quota-throttled by the upstream provider. A toggle allows opt-in inclusion if desired.',
        'Not Entitled / Missing Key (Gray): The provider is unconfigured or the user plan cannot access this gated checkpoint.',
      ],
    },
    {
      type: 'heading',
      id: 'work-unit-estimation',
      level: 2,
      text: 'Work Unit & Quota Impact Estimation',
    },
    {
      type: 'paragraph',
      text: 'Before submitting, the bottom summary bar displays the exact execution footprint:',
    },
    {
      type: 'callout',
      tone: 'info',
      title: 'Work Unit Calculation',
      body: '`Total Work Units = Dataset Test Cases × Selected Candidate Models`. For example, evaluating 30 test cases against 3 models produces exactly 90 work units. If an LLM judge is enabled, up to 90 additional scoring requests are scheduled.',
    },
    {
      type: 'heading',
      id: 'starting-run',
      level: 2,
      text: 'Starting the Evaluation',
    },
    {
      type: 'paragraph',
      text: 'Clicking "Run Evaluation" creates the immutable Experiment record, registers an active EvaluationRun, and dispatches the job to the background worker (`JobBackend`). The browser automatically redirects to the live Evaluation Detail monitor.',
    },
  ],
}

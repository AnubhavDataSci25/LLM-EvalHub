export const overviewSection = {
  id: 'overview',
  title: 'Platform Overview',
  group: 'Getting started',
  summary: 'LLM-EvalHub is an evaluation-first GenAI platform that measures model and RAG performance, diagnoses root causes of failure, and proves whether changes actually improve quality.',
  blocks: [
    {
      type: 'paragraph',
      text: 'LLM-EvalHub is an evaluation-first engineering platform designed specifically for benchmarking large language models (LLMs) and retrieval-augmented generation (RAG) pipelines. It is not a conversational chatbot or a toy prompt playground: it is a measurement and diagnostics environment built to provide reproducible, evidence-based answers to critical engineering decisions.',
    },
    {
      type: 'callout',
      tone: 'honesty',
      title: 'Evaluation Integrity Rule',
      body: 'In LLM-EvalHub, a metric that cannot be evaluated due to missing inputs is reported as unavailable, never as zero. Scores are never fabricated, and recommendations are strictly scoped to the test cases evaluated.',
    },
    {
      type: 'heading',
      id: 'what-it-is',
      level: 2,
      text: 'What it is and who it is for',
    },
    {
      type: 'paragraph',
      text: 'LLM-EvalHub replaces subjective "vibe checks" with deterministic and LLM-judged metrics, automated failure classification, and closed-loop recommendations. It is built for:',
    },
    {
      type: 'list',
      items: [
        'AI Engineers deciding which foundation model offers the best quality-latency-cost trade-off for their specific domain dataset.',
        'RAG Developers tuning retrieval parameters (top-k, chunk size, vector vs hybrid search) and verifying whether context precision and faithfulness improve.',
        'Product & QA Teams needing empirical before-and-after verification when swapping prompts, system instructions, or upstream providers.',
        'Researchers requiring structured, repeatable evaluations across multi-provider catalogs with offline deterministic test execution.',
      ],
    },
    {
      type: 'heading',
      id: 'the-core-loop',
      level: 2,
      text: 'The Core Platform Loop',
    },
    {
      type: 'paragraph',
      text: 'Most evaluation tools end at a leaderboard table. LLM-EvalHub treats evaluation as the beginning of a continuous improvement loop where diagnostics directly feed into targeted follow-up experiments.',
    },
    {
      type: 'diagram',
      name: 'evaluation-loop',
      caption: 'The six stages of the LLM-EvalHub lifecycle. Every stage produces verifiable artifacts stored in the workspace database.',
    },
    {
      type: 'paragraph',
      text: 'The loop consists of six distinct, reproducible stages:',
    },
    {
      type: 'list',
      items: [
        '1. Evaluate: Run identical test cases against multiple providers (Gemini, Groq, Hugging Face, NVIDIA NIM, OpenRouter) or deterministic mocks simultaneously.',
        '2. Compare: Inspect side-by-side metric deltas, paired statistical confidence, and latency distributions across models.',
        '3. Diagnose: Automatically classify every failure through an ordered detection cascade into 10 deterministic failure categories, backed by counterfactual attribution.',
        '4. Recommend: Compute weighted utility scores based on configurable profiles (Balanced, Quality, Faithfulness, Latency) with full score transparency.',
        '5. Improve: One-click generation of follow-up experiments modifying exactly one whitelisted parameter (e.g. chunk size, top-k, system prompt).',
        '6. Re-evaluate: Re-run the follow-up experiment and obtain a definitive before-vs-after delta verdict confirming whether the fix solved the diagnosed problem.',
      ],
    },
    {
      type: 'heading',
      id: 'end-to-end-path',
      level: 2,
      text: 'The Minimum End-to-End Path',
    },
    {
      type: 'paragraph',
      text: 'To get from a new dataset to a verified model recommendation, follow this step-by-step workflow:',
    },
    {
      type: 'steps',
      steps: [
        {
          title: '1. Ingest Data or Benchmark Pack',
          body: 'Navigate to "Datasets" and upload your domain Q&A pairs (CSV or JSON), or head to "Benchmark packs" and install one of the pre-built starter packs (e.g., RAG QA, Customer Support).',
          expected: 'Dataset appears in your workspace with verified schema validation, token counts, and difficulty breakdown.',
        },
        {
          title: '2. Configure an Evaluation Run',
          body: 'Open "New evaluation". Select your dataset, pick two or more candidate models (or offline mock models), choose your evaluation metrics (Correctness, Faithfulness, Relevance, Latency), and configure prompt parameters.',
          expected: 'An evaluation job is queued in the background state machine and starts processing work units concurrently.',
        },
        {
          title: '3. Inspect and Compare Results',
          body: 'View real-time progress on the Evaluation Detail page. When complete, navigate to "Compare" to inspect side-by-side metric distributions and identify which model outperformed baselines.',
          expected: 'Per-case score matrix rendered with color-coded quality bands and paired delta analysis.',
        },
        {
          title: '4. Diagnose Failures & Root Causes',
          body: 'Open the "Failures" page to review cases that fell below thresholds. The automated cascade flags specific root causes such as retrieval_miss, ungrounded_hallucination, or answer_relevance_low.',
          expected: 'Detailed diagnosis drawer displays question, retrieved context chunks, generated output, and actionable remedy.',
        },
        {
          title: '5. Launch Follow-Up Improvement',
          body: 'Review "Recommendations" for your data profile. Accept a recommended remediation to automatically create a linked follow-up experiment.',
          expected: 'A new experiment is initialized with identical baseline parameters except for the single improved variable.',
        },
        {
          title: '6. Export Verified Report',
          body: 'Go to "Reports" to generate an executive evaluation summary, or export raw evaluation results in CSV and JSON formats.',
          expected: 'Comprehensive audit report generated with model rankings, failure distributions, and methodology notes.',
        },
      ],
    },
    {
      type: 'callout',
      tone: 'tip',
      title: 'Zero-Credential Offline Exploration',
      body: 'You do not need paid API keys or cloud infrastructure to test the complete loop. LLM-EvalHub ships with a deterministic mock provider enabled by default (`ENABLE_MOCK_PROVIDER=true`), allowing full offline evaluation, diagnosis, and reporting.',
    },
  ],
}

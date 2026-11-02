export const scoreLimitationsSection = {
  id: 'score-limitations',
  title: 'How Scores Can Mislead: Honest Limitations',
  group: 'Evaluation reference',
  summary: 'A critical guide to the empirical failure modes of evaluation: lexical proxy traps, LLM-judge biases, sample size risks, statistical significance testing, and judge calibration.',
  blocks: [
    {
      type: 'paragraph',
      text: 'An evaluation platform that oversells its precision is worse than useless: it gives dangerous confidence to flawed engineering decisions. Every automated measurement system carries inherent failure modes. Understanding these limitations is required to properly interpret your results.',
    },
    {
      type: 'heading',
      id: 'lexical-metric-traps',
      level: 2,
      text: '1. Lexical Fallback Metrics Reward Repetition',
    },
    {
      type: 'paragraph',
      text: 'When no LLM judge is configured (`DEFAULT_EVALUATOR_PROVIDER=None`), LLM-EvalHub uses deterministic lexical algorithms (token-F1, bag-of-words cosine, content word coverage). These metrics are fast, free, and 100% reproducible, but they carry severe semantic blind spots:',
    },
    {
      type: 'list',
      items: [
        'Paraphrase Penalization: An answer that expresses the exact ground-truth meaning using different vocabulary or sentence structure receives a poor lexical score.',
        'Length and Keyword Exploitation: A verbose answer that repeats keywords without answering the prompt can score artificially high on unigram overlap.',
        'Negation Blindness: Sentences like "The service is available" and "The service is not available" share high unigram overlap despite having opposite meanings.',
      ],
    },
    {
      type: 'callout',
      tone: 'warning',
      title: 'Always Label Metric Kinds',
      body: 'Never present lexical scores as semantic comprehension. In LLM-EvalHub, lexical metrics are always explicitly labelled `kind: deterministic` and `kind: lexical proxy`.',
    },
    {
      type: 'heading',
      id: 'llm-judge-biases',
      level: 2,
      text: '2. LLM-as-a-Judge Biases & Calibration',
    },
    {
      type: 'paragraph',
      text: 'LLM judges understand semantic nuance, but introduce stochasticity and systematic cognitive biases. To measure and bound this risk, LLM-EvalHub implements an end-to-end Judge Calibration system (`/calibration`):',
    },
    {
      type: 'list',
      items: [
        'Inter-Rater Agreement: Compares judge scores against blind human labels on your own data using Cohen\'s kappa (κ) and quadratic-weighted kappa (κ_w).',
        'Landis-Koch Conventional Bands: Kappa is qualitatively interpreted using standard bands (<0 poor, 0-0.20 slight, 0.21-0.40 fair, 0.41-0.60 moderate, 0.61-0.80 substantial, 0.81-1.00 almost perfect). Caveat: with a single human rater, kappa measures agreement with that specific individual, not universal ground truth.',
        'Positional Order Bias Probe: Empirically tests whether swapping the order of candidate answers in pairwise evaluation alters the judge\'s preference.',
        'Verbosity Inflation Probe: Tests whether padding answers with non-substantive introductory or summary prose increases the judge score.',
        'Self-Preference Bias Probe: Checks whether a foundation model judge systematically scores generations from its own model family higher than competitors.',
      ],
    },
    {
      type: 'heading',
      id: 'sample-size-and-significance',
      level: 2,
      text: '3. Small Test Sets & Statistical Significance',
    },
    {
      type: 'paragraph',
      text: 'Running evaluations on 5 to 10 test cases is useful for smoke testing, but drawing architectural conclusions from small samples is invalid. To prevent premature optimization, LLM-EvalHub enforces Statistical Significance Testing across all model and run comparisons:',
    },
    {
      type: 'list',
      items: [
        'Bootstrap Confidence Intervals: 10,000 non-parametric resamples generate 95% confidence intervals for every metric delta.',
        'Permutation Tests: Paired sign-flip permutation tests ensure p < 0.05 before declaring an improvement.',
        'Underpowered Warnings: Any comparison with fewer than 8 paired cases (N < 8) is explicitly flagged with an "underpowered" warning.',
      ],
    },
    {
      type: 'heading',
      id: 'mock-provider-warning',
      level: 2,
      text: '4. Mock Provider Output is Mechanical',
    },
    {
      type: 'callout',
      tone: 'honesty',
      title: 'Mock Models Verify Pipelines, Not Quality',
      body: 'The mock provider (`mock-extractive`, `mock-hallucinate`, `mock-timeout`) produces mechanical, deterministic string transformations designed to exercise evaluation and failure detection pipelines offline. They are synthetic test fixtures and must never be cited as real model benchmarks.',
    },
    {
      type: 'heading',
      id: 'free-tier-limits',
      level: 2,
      text: '5. Provider Rate Limits and Concurrency Ceilings',
    },
    {
      type: 'paragraph',
      text: 'Free tier API keys from Groq, Gemini, or OpenRouter impose strict requests-per-minute (RPM) and tokens-per-minute (TPM) limits. Running large datasets (e.g. 500 cases) across multiple models simultaneously on free tiers will trigger HTTP 429 throttling. Keep `MAX_CONCURRENT_REQUESTS=2` or `3` when operating on free accounts.',
    },
  ],
}

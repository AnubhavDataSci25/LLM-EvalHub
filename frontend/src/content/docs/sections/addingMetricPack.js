export const addingMetricPackSection = {
  id: 'adding-metric-pack',
  title: 'Developer Guide: Adding Metrics & Packs',
  group: 'Technical reference',
  summary: 'How to implement a custom deterministic or judged metric and author a new benchmark pack for offline evaluation.',
  blocks: [
    {
      type: 'paragraph',
      text: 'LLM-EvalHub is designed to be easily extensible. This guide explains how to add a custom evaluation metric to the scoring registry and how to author a new benchmark pack.',
    },
    {
      type: 'heading',
      id: 'adding-metric',
      level: 2,
      text: 'Part 1: Adding a Custom Metric',
    },
    {
      type: 'paragraph',
      text: 'Adding a new evaluation metric requires two steps: writing the evaluation function and declaring its metadata specification.',
    },
    {
      type: 'steps',
      steps: [
        {
          title: '1. Implement the scoring function in metrics.py',
          body: 'Open `backend/app/evaluation/metrics.py` and write your function. It must return a `MetricOutcome` object and handle missing inputs gracefully:',
          code: `def code_syntax_validity(answer: str | None) -> MetricOutcome:
    if not (answer or "").strip():
        return MetricOutcome.unavailable("code_syntax", "Answer is empty.")
    try:
        compile(answer, "<string>", "exec")
        score = 1.0
        evidence = "Code compiled successfully without syntax errors."
    except SyntaxError as err:
        score = 0.0
        evidence = f"Syntax error detected: {err.msg} at line {err.lineno}."
    return MetricOutcome(metric="code_syntax", raw_score=score, normalized_score=score, evidence=evidence)`,
          expected: 'Function returns MetricOutcome with score between 0.0 and 1.0, or MetricOutcome.unavailable().',
        },
        {
          title: '2. Register the MetricSpec in registry.py',
          body: 'Open `backend/app/evaluation/registry.py` and add your metric to `METRIC_SPECS`:',
          code: `METRIC_SPECS["code_syntax"] = MetricSpec(
    key="code_syntax",
    label="Code Syntax Validity",
    description="Verifies whether generated code compiles without syntax errors.",
    default_kind=DETERMINISTIC,
    requires=[],
    higher_is_better=True,
    group="quality",
)`,
          expected: 'The new metric immediately surfaces in the UI evaluation setup form with its kind badge.',
        },
      ],
    },
    {
      type: 'heading',
      id: 'adding-benchmark-pack',
      level: 2,
      text: 'Part 2: Authoring a Benchmark Pack',
    },
    {
      type: 'paragraph',
      text: 'A benchmark pack is a self-contained directory under `benchmarks/<pack_key>/` containing two JSON files and optional markdown documents:',
    },
    {
      type: 'list',
      items: [
        'pack.json: Defines the pack title, description, recommended metrics, default generation configuration, and metric rationale.',
        'dataset.json: Contains the array of `test_cases`, each specifying `question`, `ground_truth`, `category`, and `difficulty`.',
        'Optional docs/: Any Markdown or TXT documents bundled for RAG retrieval.',
      ],
    },
    {
      type: 'code',
      language: 'json',
      filename: 'benchmarks/sql_generation/pack.json',
      code: `{
  "key": "sql_generation",
  "name": "Text-to-SQL Benchmark",
  "description": "Tests relational SQL query generation from natural language prompts against a schema.",
  "use_case": "code_generation",
  "metrics": ["correctness", "latency"],
  "dataset": "dataset.json",
  "default_config": {
    "temperature": 0.0,
    "max_tokens": 400,
    "system_prompt": "You are a database engineer. Return only valid PostgreSQL SQL queries without markdown formatting."
  }
}`,
    },
    {
      type: 'callout',
      tone: 'tip',
      title: 'Automatic Pack Discovery',
      body: 'The backend benchmark service automatically scans the `benchmarks/` directory at startup. Any valid directory containing `pack.json` and `dataset.json` appears instantly in the Benchmark Packs catalog.',
    },
  ],
}

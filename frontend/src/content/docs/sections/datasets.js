export const datasetsSection = {
  id: 'datasets',
  title: 'Datasets',
  group: 'Using the platform',
  summary: 'Manage test datasets with automated schema validation, forgiving column alias mapping, per-row error reporting, and support for reference answers, context passages, and expected citations.',
  blocks: [
    {
      type: 'paragraph',
      text: 'The Datasets page (`/datasets`) manages test suites used for model evaluations. A dataset is an immutable, versioned collection of test cases. Every import undergoes strict validation to ensure data integrity before execution.',
    },
    {
      type: 'heading',
      id: 'import-formats',
      level: 2,
      text: 'Import Formats & Schema Aliases',
    },
    {
      type: 'paragraph',
      text: 'You can import datasets via CSV or JSON. LLM-EvalHub is intentionally forgiving about column naming, recognizing common aliases from third-party tools while strictly requiring the `question` field.',
    },
    {
      type: 'table',
      caption: 'Supported Canonical Columns & Aliases',
      headers: ['Canonical Field', 'Required', 'Accepted Aliases', 'Description'],
      rows: [
        ['`question`', 'Yes', 'query, input, prompt, userinput, q', 'The input prompt or question evaluated by candidate models.'],
        ['`ground_truth`', 'Optional', 'groundtruth, answer, expectedanswer, reference, expected, truth, label', 'The gold-standard reference answer used for correctness scoring.'],
        ['`context`', 'Optional', 'reference_context, retrievedcontext, passage, document, evidence', 'Pre-retrieved or reference passage required for faithfulness metrics.'],
        ['`category`', 'Optional', 'topic, type, intent, domain', 'Domain or intent classification for grouped metric analysis.'],
        ['`difficulty`', 'Optional', 'level, complexity', 'Difficulty rating (easy, medium, hard).'],
        ['`expected_sources`', 'Optional', 'expectedsources, sources, citations, expectedcitations', 'List of document chunk IDs or source filenames expected to be cited.'],
        ['`metadata`', 'Optional', 'meta, extra', 'Arbitrary JSON key-value pairs stored with the case.'],
      ],
    },
    {
      type: 'heading',
      id: 'copyable-samples',
      level: 2,
      text: 'Copy-able Import Samples',
    },
    {
      type: 'code',
      language: 'csv',
      filename: 'sample_dataset.csv',
      code: `question,ground_truth,category,difficulty
"What is the maximum upload limit?","The maximum upload limit is 25MB.","limits","easy"
"How do I configure PostgreSQL?","Set DATABASE_URL in backend/.env with a valid postgresql+psycopg DSN.","configuration","medium"
"What causes ungrounded_hallucination?","When the model asserts facts not present in retrieved context.","diagnostics","hard"`,
    },
    {
      type: 'code',
      language: 'json',
      filename: 'sample_dataset.json',
      code: `[
  {
    "question": "What is the maximum upload limit?",
    "ground_truth": "The maximum upload limit is 25MB.",
    "category": "limits",
    "difficulty": "easy"
  },
  {
    "question": "How do I configure PostgreSQL?",
    "ground_truth": "Set DATABASE_URL in backend/.env with a valid postgresql+psycopg DSN.",
    "category": "configuration",
    "difficulty": "medium"
  }
]`,
    },
    {
      type: 'heading',
      id: 'validation-rules',
      level: 2,
      text: 'Validation Rules & Row Rejection',
    },
    {
      type: 'paragraph',
      text: 'When a file is uploaded, the backend runs a comprehensive validation pass:',
    },
    {
      type: 'list',
      items: [
        'Mandatory Question: Any row missing a non-empty `question` field is rejected immediately with an error.',
        'File Size Limit: Uploads exceeding `MAX_UPLOAD_BYTES` (26,214,400 bytes / 25MB) return HTTP 413 Payload Too Large.',
        'Row Count Limit: Datasets with more than `MAX_DATASET_ROWS` (default 2,000, configurable up to 5,000) are rejected to prevent worker starvation.',
        'Duplicate Detection: Duplicate questions within the same file generate non-fatal warnings in the validation report.',
        'Length Bounds: Questions exceeding 8,000 characters are flagged as invalid.',
      ],
    },
    {
      type: 'callout',
      tone: 'tip',
      title: 'Validation Reports',
      body: 'Every import produces a persistent DatasetValidationReport showing accepted rows, rejected rows, and specific per-line error messages. You can inspect the report before confirming the import.',
    },
    {
      type: 'heading',
      id: 'management-actions',
      level: 2,
      text: 'Preview, Edit, and Deletion',
    },
    {
      type: 'paragraph',
      text: 'From the Dataset Detail page (`/datasets/:id`), you can preview all test cases, inline-edit individual prompts or expected answers, filter by category or difficulty, and trigger immediate single-case evaluation tests.',
    },
  ],
}

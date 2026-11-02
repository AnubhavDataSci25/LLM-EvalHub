export const conceptsSection = {
  id: 'core-concepts',
  title: 'Core Concepts & Glossary',
  group: 'Getting started',
  summary: 'A complete reference glossary of foundational terms and abstractions used across LLM-EvalHub, from work units to failure cascades and improvement loops.',
  blocks: [
    {
      type: 'paragraph',
      text: 'To make rigorous engineering decisions, terminology must be exact. This glossary establishes the definitive definitions for every core abstraction, data entity, and measurement category used throughout the platform.',
    },
    {
      type: 'heading',
      id: 'platform-entities',
      level: 2,
      text: 'Evaluation Entities & Data Model',
    },
    {
      type: 'definition-list',
      items: [
        {
          term: 'Dataset',
          category: 'Data Entity',
          definition: 'A versioned collection of structured test cases used as inputs for model evaluations. A dataset belongs to a specific workspace and has a schema validation state (valid, invalid, partial).',
          example: 'customer_support_q3 with 250 validated cases.',
        },
        {
          term: 'Test Case',
          category: 'Data Entity',
          definition: 'A single atomic evaluation item consisting of a user query/prompt, an optional expected reference answer, optional metadata, and optional ground-truth context passages or expected sources.',
          example: 'Query: "What is our enterprise refund policy?", Expected: "30-day full refund with receipt".',
        },
        {
          term: 'Provider',
          category: 'Inference',
          definition: 'An upstream LLM hosting platform integrated into LLM-EvalHub (Gemini, Groq, Hugging Face, NVIDIA NIM, OpenRouter, Ollama, or Mock). Each provider adapter normalizes error codes, streaming, and model discovery.',
          example: 'Groq (LPUs), Gemini (Google AI Studio), Mock (offline deterministic test provider).',
        },
        {
          term: 'Model',
          category: 'Inference',
          definition: 'A specific language model identifier served by a provider. In LLM-EvalHub, only models verified via the Model Availability Audit are presented as selectable.',
          example: 'gemini-2.5-flash, llama-3.3-70b-versatile, openai/gpt-oss-120b.',
        },
        {
          term: 'Experiment',
          category: 'Configuration',
          definition: 'The immutable specification of an evaluation setup, recording the dataset, selected candidate models, system prompt template, generation parameters (temperature, max_tokens), and RAG retriever configuration.',
          example: 'RAG Chunking Benchmark v2 — compares top_k=3 vs top_k=6.',
        },
        {
          term: 'Run (Evaluation Run)',
          category: 'Execution',
          definition: 'An execution instance of an Experiment. A run tracks real-time progress across work units, records overall duration and latency, and yields aggregated metrics and failure distributions.',
          example: 'run_9f2a81bc with status: completed, 500 total units.',
        },
        {
          term: 'Work Unit',
          category: 'Execution',
          definition: 'The atomic unit of execution in the evaluation engine, defined as the Cartesian product of exactly one Test Case and one candidate Model (test_case x model). Each work unit produces an EvaluationResult.',
          example: 'Case #42 executed against Gemini 2.5 Flash produces one work unit.',
        },
      ],
    },
    {
      type: 'heading',
      id: 'metrics-and-evaluation',
      level: 2,
      text: 'Metrics, Judges & Kinds',
    },
    {
      type: 'definition-list',
      items: [
        {
          term: 'Metric',
          category: 'Scoring',
          definition: 'A quantitative or categorical score between 0.0 and 1.0 (or raw milliseconds for latency) assessing a specific quality dimension of a model generation.',
          example: 'correctness, answer_relevance, faithfulness, context_precision, latency.',
        },
        {
          term: 'Metric Kind',
          category: 'Scoring',
          definition: 'The operational classification of how a metric is computed. LLM-EvalHub distinguishes four kinds: deterministic (pure code, lexical algorithms), llm_judge (scored by an LLM against a rubric), ragas (composite library score), and performance (hardware/network measured, like latency).',
          example: 'correctness can be deterministic (F1) or llm_judge; latency is performance.',
        },
        {
          term: 'Evaluator / Judge',
          category: 'Scoring',
          definition: 'A scoring agent (either deterministic code or a foundation LLM configured with an evaluation prompt and scoring schema) that compares model output against expected answers or retrieved context.',
          example: 'LLMJudge using Gemini 2.5 Flash with temperature=0.0 and strict JSON schema output.',
        },
        {
          term: 'Unavailable Metric',
          category: 'Integrity',
          definition: 'A metric state where evaluation could not be executed because a mandatory dependency was missing (e.g., faithfulness requires retrieved context; correctness requires an expected answer). In LLM-EvalHub, an unavailable metric is never assigned a score of zero.',
          example: 'Status "unavailable" with reason "missing_expected_answer".',
        },
      ],
    },
    {
      type: 'heading',
      id: 'rag-and-retrieval',
      level: 2,
      text: 'RAG & Retrieval Architecture',
    },
    {
      type: 'definition-list',
      items: [
        {
          term: 'RAG (Retrieval-Augmented Generation)',
          category: 'Architecture',
          definition: 'An architecture where a query first retrieves relevant external context passages from a document knowledge base before prompt assembly and generation by the LLM.',
          example: 'Extracting clauses from PDF contracts before generating legal answers.',
        },
        {
          term: 'Chunk',
          category: 'RAG',
          definition: 'A partitioned segment of an ingested document text, determined by chunk size (character or token length) and overlap.',
          example: '800-character chunks with 120-character sliding overlap.',
        },
        {
          term: 'Top-k',
          category: 'RAG',
          definition: 'The maximum number of highest-scoring context chunks retrieved by the search engine and inserted into the model prompt context.',
          example: 'top_k=4 supplies the 4 most relevant passages to the LLM.',
        },
        {
          term: 'Retrieval Mode',
          category: 'RAG',
          definition: 'The algorithmic strategy used to find passages: vector (dense semantic similarity), bm25 (sparse keyword frequency), or hybrid (combining dense and sparse using Reciprocal Rank Fusion).',
          example: 'Hybrid search balancing domain acronyms with semantic questions.',
        },
      ],
    },
    {
      type: 'heading',
      id: 'failures-and-improvement',
      level: 2,
      text: 'Diagnostics, Recommendations & Improvement',
    },
    {
      type: 'definition-list',
      items: [
        {
          term: 'Failure Category',
          category: 'Diagnostics',
          definition: 'One of ten deterministic classifications assigned to a failed work unit by the ordered diagnostic cascade: timeout, rate_limit, context_length, model_error, retrieval_miss, retrieval_noise, ungrounded_hallucination, incomplete_answer, answer_relevance_low, or semantic_drift.',
          example: 'ungrounded_hallucination indicates generation contradicts the retrieved context.',
        },
        {
          term: 'Diagnosis',
          category: 'Diagnostics',
          definition: 'An automated forensic report generated for an evaluation failure, combining deterministic cascade checks, counterfactual failure attribution (oracle vs no-context tests), and actionable remedy recommendations.',
          example: 'Identifies whether retrieval or parametric generation was the root cause of a failure.',
        },
        {
          term: 'Recommendation',
          category: 'Optimization',
          definition: 'A multi-attribute ranking of evaluated models under a specific user profile (Balanced, Quality-First, Cost-Sensitive, Latency-First) with explicit score breakdowns and empirical caveats.',
          example: 'Recommends Groq Llama-3.3-70b for latency constraints, noting lower recall on code cases.',
        },
        {
          term: 'Improvement Loop',
          category: 'Optimization',
          definition: 'The workflow of taking a diagnosed failure recommendation, spawning an identical follow-up experiment that modifies exactly one whitelisted parameter, and comparing before-vs-after delta scores.',
          example: 'Increasing chunk_size from 500 to 800 and verifying that retrieval_miss dropped by 45%.',
        },
        {
          term: 'Benchmark Pack',
          category: 'Benchmarking',
          definition: 'A curated starter package containing a domain dataset, recommended metrics, and baseline configuration ready for immediate evaluation.',
          example: 'The RAG QA pack includes 30 synthetic questions and 4 reference docs.',
        },
        {
          term: 'Report',
          category: 'Export',
          definition: 'A persistent snapshot of an evaluation run including executive summaries, score distribution charts, failure taxonomy, and raw data exportable in JSON and CSV formats.',
          example: 'Quarterly compliance evaluation report exported for engineering audit.',
        },
      ],
    },
  ],
}

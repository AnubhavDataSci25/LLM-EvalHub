export const failuresDiagnosisSection = {
  id: 'failures-diagnosis',
  title: 'Failures & Diagnosis',
  group: 'Using the platform',
  summary: 'Automated failure classification across 10 deterministic categories, ordered detection cascades, counterfactual attribution, and actionable AI root cause diagnosis.',
  blocks: [
    {
      type: 'paragraph',
      text: 'The Failures page (`/failures`) and Failure Detail view (`/failures/:id`) provide forensic inspection of outputs that did not meet quality thresholds. Rather than labelling all errors as "hallucination", LLM-EvalHub classifies issues through an ordered cascade grounded in empirical evidence.',
    },
    {
      type: 'heading',
      id: 'ordered-cascade',
      level: 2,
      text: 'The Ordered Detection Cascade',
    },
    {
      type: 'paragraph',
      text: 'Failure detection runs in a strict deterministic order from most certain to least certain:',
    },
    {
      type: 'list',
      items: [
        '1. Infrastructure Signals: Checks for provider exceptions, HTTP errors, timeouts, or empty outputs.',
        '2. Retrieval Signals: Checks context precision (<0.3) and context recall (<0.5). If retrieval failed to find evidence, the problem is classified as a retrieval failure, not an LLM hallucination.',
        '3. Grounding Signals: Checks faithfulness (<0.6). Identifies unsupported claims that contradict or exceed the retrieved context.',
        '4. Answer-Quality Signals: Checks factual correctness (<0.5) against reference ground truth and answer relevance (<0.5) against the prompt.',
        '5. Latency Signals: Checks whether end-to-end duration exceeded the configured latency threshold (default 15,000ms).',
      ],
    },
    {
      type: 'callout',
      tone: 'honesty',
      title: 'Confidence is Capped at 0.95',
      body: 'Detection confidence is calculated from the normalized distance between a metric score and its threshold: `confidence = min(0.95, floor + gap * 0.4)`. It is never reported as 1.0 (100%), acknowledging natural evaluator variance.',
    },
    {
      type: 'heading',
      id: 'ten-failure-categories',
      level: 2,
      text: 'The 10 Failure Categories Reference',
    },
    {
      type: 'table',
      caption: 'LLM-EvalHub Failure Taxonomy',
      headers: ['Category Key', 'Definition', 'Concrete Example', 'Typical Remedy'],
      rows: [
        ['`provider_error`', 'The upstream model provider rejected or failed the request.', 'HTTP 500 internal server error or 401 invalid key.', 'Check credentials, base URLs, or provider status.'],
        ['`timeout`', 'Model response did not finish within the timeout budget.', 'Request timed out after 60.0s.', 'Increase timeout, reduce max_tokens, or pick a faster provider.'],
        ['`empty_response`', 'The model returned a blank or whitespace-only completion.', 'Model generated "" with finish_reason: stop.', 'Review system prompt formatting or safety filters.'],
        ['`poor_retrieval`', 'The retriever failed to surface necessary source passages.', 'Context recall=0.10 on a specific handbook query.', 'Increase top_k, enlarge chunk_size, or enable hybrid search.'],
        ['`missing_information`', 'Answer is truthful but omits critical components from ground truth.', 'Answer lists 2 of 4 required refund conditions.', 'Adjust prompt to explicitly request complete enumerations.'],
        ['`unsupported_claim`', 'Answer makes claims not found in the retrieved context.', 'Generated response states warranty is 2 years when text says 1.', 'Strengthen prompt instruction to answer only from context.'],
        ['`hallucination`', 'Answer asserts specific falsehoods or fabricated entities.', 'Model cites non-existent Article 14.b.', 'Switch to an LLM with higher grounding benchmarks.'],
        ['`incorrect_answer`', 'Answer directly contradicts reference ground truth.', 'Model answers "Yes" when ground truth answer is "No".', 'Refine prompt context or evaluate larger parameter models.'],
        ['`low_relevance`', 'Answer fails to address the user question asked.', 'Model summarizes handbook history instead of answering policy question.', 'Sharpen prompt template and penalize evasive preamble.'],
        ['`high_latency`', 'Answer was correct but exceeded the latency ceiling.', 'Generation took 18,500ms on interactive chat.', 'Lower max_tokens, switch to Groq LPUs or Flash tier.'],
      ],
    },
    {
      type: 'heading',
      id: 'ai-diagnosis',
      level: 2,
      text: 'AI Diagnosis Engine',
    },
    {
      type: 'paragraph',
      text: 'From any failure record, you can trigger an AI Diagnosis. The diagnostic engine combines a deterministic rule catalog with an optional LLM reasoning pass to generate a structured remediation object:',
    },
    {
      type: 'list',
      items: [
        'Diagnosis: A plain-English forensic explanation of the failure mode.',
        'Likely Root Cause: Whether the failure originated in retrieval, model capability, or prompt ambiguity.',
        'Recommended Change: Specific whitelisted parameter override (e.g. `{"chunk_size": 800, "top_k": 5}`).',
        'Expected Improvement: Predicted metric trajectory (e.g. "increases context_recall without degrading latency").',
      ],
    },
  ],
}

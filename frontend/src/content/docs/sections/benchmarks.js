export const benchmarksSection = {
  id: 'benchmarks',
  title: 'Benchmark Packs',
  group: 'Using the platform',
  summary: 'Ready-to-use starter packages for six real-world evaluation scenarios, complete with synthetic datasets, recommended metrics, and baseline configurations.',
  blocks: [
    {
      type: 'paragraph',
      text: 'The Benchmark Packs page (`/benchmarks`) provides one-click installations for common enterprise LLM scenarios. Each pack bundles a curated test dataset, recommended evaluation metrics, reference documents (where relevant), and tuned default prompts and parameters.',
    },
    {
      type: 'callout',
      tone: 'honesty',
      title: 'Packs Are Starter Sets, Not Authoritative Baselines',
      body: 'Benchmark packs contain between 12 and 32 focused test cases (131 cases total across all 6 packs). They are designed for quick orientation, pipeline smoke testing, and regression sanity checks. They are not authoritative industry benchmarks and do not substitute for a representative sample of your own domain data.',
    },
    {
      type: 'heading',
      id: 'the-six-packs',
      level: 2,
      text: 'The Six Benchmark Packs',
    },
    {
      type: 'table',
      caption: 'Curated Benchmark Pack Specifications',
      headers: ['Pack Key', 'Name', 'Cases', 'What It Tests', 'Recommended Metrics', 'Baseline Settings'],
      rows: [
        ['`rag_qa`', 'RAG QA Starter', '32', 'Question answering over an ingested product knowledge base (Orbit Platform Handbook). Evaluates whether context retrieval succeeded before scoring answer quality.', '`correctness`, `faithfulness`, `answer_relevance`, `context_precision`, `context_recall`, `latency`', 'top_k=4, chunk_size=700, chunk_overlap=120, retriever=vector, temp=0.0'],
        ['`customer_support`', 'Customer Support', '24', 'E-commerce and SaaS support inquiries, refund policies, billing, and order lookup under strict brand and tone constraints.', '`correctness`, `answer_relevance`, `faithfulness`, `latency`', 'temp=0.1, max_tokens=350, system prompt enforcing policy compliance'],
        ['`document_qa`', 'Document QA', '25', 'Technical documentation comprehension, specifications, API contracts, and troubleshooting procedures.', '`correctness`, `faithfulness`, `context_precision`, `latency`', 'top_k=3, chunk_size=800, retriever=hybrid, temp=0.0'],
        ['`citation_grounding`', 'Citation Grounding', '20', 'Evaluates whether citations and source tags provided by the LLM accurately match the retrieved evidence chunks.', '`faithfulness`, `context_precision`, `correctness`', 'temp=0.0, strict citation prompt requiring [source:id] syntax'],
        ['`structured_extraction`', 'Structured Extraction', '18', 'Extracting structured JSON entities (invoices, dates, line items, monetary amounts) from unstructured plain text.', '`correctness`, `answer_relevance`, `latency`', 'temp=0.0, strict JSON schema output instruction'],
        ['`summarization`', 'Summarization', '12', 'Condensing long multi-paragraph documents into concise summaries while retaining critical facts.', '`answer_relevance`, `faithfulness`, `completeness`, `latency`', 'temp=0.2, max_tokens=300'],
      ],
    },
    {
      type: 'heading',
      id: 'installing-and-running',
      level: 2,
      text: 'How to Install and Evaluate a Pack',
    },
    {
      type: 'steps',
      steps: [
        {
          title: '1. Select a pack on the Benchmarks page',
          body: 'Navigate to "/benchmarks" and choose the scenario matching your use case (e.g. "RAG QA Starter"). Review the case count, bundled documents, and metric rationale.',
          expected: 'The benchmark detail drawer opens displaying pack metadata, sample test cases, and recommended models.',
        },
        {
          title: '2. Click "Install Benchmark Pack"',
          body: 'Clicking install imports the dataset into your active workspace and automatically parses and indexes any bundled reference documents into the vector store.',
          expected: 'A new dataset (e.g. "RAG QA Starter Dataset") and indexed document collection appear in your workspace.',
        },
        {
          title: '3. Launch the pre-configured evaluation',
          body: 'Click "Run evaluation from pack". The evaluation form pre-fills with the recommended metrics, prompts, retrieval parameters, and candidate models.',
          expected: 'An evaluation run is immediately dispatched to the background job queue.',
        },
      ],
    },
  ],
}

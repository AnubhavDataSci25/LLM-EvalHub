export const documentsSection = {
  id: 'documents-rag',
  title: 'Documents & RAG',
  group: 'Using the platform',
  summary: 'Knowledge base document ingestion, character chunking, embedding algorithms, vector indexing, and vector/BM25/hybrid retrieval modes.',
  blocks: [
    {
      type: 'paragraph',
      text: 'The Documents page (`/documents`) manages the knowledge bases used in Retrieval-Augmented Generation (RAG) experiments. When an evaluation runs with RAG enabled, questions first query the document index to retrieve relevant context passages, which are then injected into the prompt context for the LLM.',
    },
    {
      type: 'heading',
      id: 'supported-formats',
      level: 2,
      text: 'Supported File Formats & Ingestion',
    },
    {
      type: 'list',
      items: [
        'PDF (.pdf): Text layer is extracted using pypdf. Note: scanned image-only PDFs require OCR preprocessing before upload.',
        'Markdown (.md): Structured markdown files parsed with heading and section boundary awareness.',
        'Plain Text (.txt): Raw text ingested with whitespace normalization.',
      ],
    },
    {
      type: 'heading',
      id: 'chunking-strategy',
      level: 2,
      text: 'Chunking Strategy: Size and Overlap',
    },
    {
      type: 'paragraph',
      text: 'Ingested documents are partitioned into overlapping text segments called chunks:',
    },
    {
      type: 'list',
      items: [
        'Chunk Size (`DEFAULT_CHUNK_SIZE=800`): The target character length of each chunk. Smaller chunks (e.g. 400 chars) provide high context precision but risk splitting sentences; larger chunks (e.g. 1200 chars) provide rich context but increase prompt token costs.',
        'Chunk Overlap (`DEFAULT_CHUNK_OVERLAP=120`): The sliding character overlap shared between consecutive chunks. Prevents critical facts from being split across chunk boundaries.',
      ],
    },
    {
      type: 'heading',
      id: 'embedding-backends',
      level: 2,
      text: 'Embedding Backends: Hashing vs Semantic',
    },
    {
      type: 'paragraph',
      text: 'LLM-EvalHub supports three embedding implementations configured via `EMBEDDING_BACKEND`:',
    },
    {
      type: 'list',
      items: [
        'hashing (Default): A deterministic lexical feature hash (512-dimension vector) based on token n-grams. It requires no model downloads, uses zero GPU memory, and runs completely offline. Limitation: It captures lexical and morphological similarity, but does not capture high-level semantic synonyms (e.g., "physician" and "doctor").',
        'gemini: High-dimensional semantic embeddings using Google AI text-embedding-004. Requires a valid GEMINI_API_KEY.',
        'sentence-transformers: Local dense neural embeddings running locally via PyTorch (requires optional dependencies).',
      ],
    },
    {
      type: 'callout',
      tone: 'honesty',
      title: 'Why Lexical Hashing is Default',
      body: 'Hashing ensures that anyone cloning LLM-EvalHub can run RAG evaluations immediately without waiting for a 1.5GB embedding model download or spending API tokens. For production accuracy comparisons, switch to `gemini` embeddings.',
    },
    {
      type: 'heading',
      id: 'retrieval-modes',
      level: 2,
      text: 'Retrieval Modes: Vector, Keyword, and Hybrid',
    },
    {
      type: 'table',
      caption: 'Retriever Strategy Comparison',
      headers: ['Mode', 'Algorithm', 'Best Used For', 'How It Works'],
      rows: [
        ['`vector`', 'Dense similarity (cosine)', 'Natural language questions, semantic paraphrase', 'Queries are embedded into vector space and matched against nearest chunk embeddings.'],
        ['`keyword`', 'BM25-style term frequency', 'Acronyms, error codes, part numbers, exact quotes', 'Scores chunks using token frequencies and inverse document frequencies.'],
        ['`hybrid`', 'Reciprocal Rank Fusion (RRF)', 'Production search balancing keywords and concepts', 'Runs both vector and keyword queries in parallel, combining rankings using formula: RRF_score = 1 / (60 + rank).'],
      ],
    },
    {
      type: 'heading',
      id: 'retrieval-preview',
      level: 2,
      text: 'Top-k and Retrieval Preview',
    },
    {
      type: 'paragraph',
      text: 'The `top_k` parameter (default 4) specifies how many chunks are retrieved and passed into the prompt. You can test your retrieval settings without running an entire evaluation by using the "Preview Retrieval" tool on the Documents page.',
    },
  ],
}

export const quickstartSection = {
  id: 'quick-start',
  title: 'Quick Start (5 Minutes)',
  group: 'Getting started',
  summary: 'Spin up LLM-EvalHub locally in 5 minutes with zero external dependencies using the mock provider, run the end-to-end seed workflow, and connect real LLM providers.',
  blocks: [
    {
      type: 'paragraph',
      text: 'This guide gets you from cloning the repository to running a full evaluation, failure diagnosis, and recommendation cycle in five minutes. No third-party API keys or external services (no Redis, no external PostgreSQL) are required to get started.',
    },
    {
      type: 'callout',
      tone: 'tip',
      title: 'Offline Mock Provider Included',
      body: 'By default, `ENABLE_MOCK_PROVIDER=true` is enabled. You can evaluate synthetic models (mock-extractive, mock-hallucinate, mock-timeout) to test the entire pipeline without spending API quota.',
    },
    {
      type: 'heading',
      id: 'local-setup',
      level: 2,
      text: 'Step-by-Step Local Setup',
    },
    {
      type: 'steps',
      steps: [
        {
          title: '1. Clone the repository and configure environment',
          body: 'Create a local configuration file from the template. The default settings use SQLite and in-process background task execution.',
          code: 'cp .env.example backend/.env',
          expected: 'A configured backend/.env file ready for local development with AUTH_MODE=local and JOB_BACKEND=auto.',
        },
        {
          title: '2. Setup and launch the Python backend',
          body: 'Create a Python virtual environment (Python 3.10+), install dependencies, and start the FastAPI server with uvicorn.',
          code: `cd backend
python -m venv venv
# Windows: .\\venv\\Scripts\\activate | Unix: source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000`,
          expected: 'FastAPI server boots on http://localhost:8000 with log line "LLM-EvalHub starting (env=development, db=sqlite, job_backend=asyncio)".',
        },
        {
          title: '3. Setup and launch the React frontend',
          body: 'In a separate terminal window, navigate to the frontend directory, install npm packages, and start the Vite development server.',
          code: `cd frontend
npm install
npm run dev`,
          expected: 'Vite dev server starts on http://localhost:5173 with proxy configured to route /api and /docs to port 8000.',
        },
        {
          title: '4. Run the offline seed script',
          body: 'Execute the seed script to automatically install the RAG QA benchmark pack, execute baseline mock evaluations, diagnose simulated failures, and generate a report.',
          code: 'python scripts/seed.py --pack rag_qa',
          expected: 'Console logs display "Installing benchmark pack", "Running baseline evaluation", "Diagnosing failures", and "Report generated successfully".',
        },
        {
          title: '5. Explore the populated UI',
          body: 'Open http://localhost:5173 in your browser. Navigate to Dashboard to see populated KPIs, Compare to review side-by-side models, and Failures to inspect diagnosed hallucinations.',
          expected: 'Dashboard displays active evaluation runs, metric scores, failure distribution charts, and recommendation rankings.',
        },
      ],
    },
    {
      type: 'heading',
      id: 'docker-setup',
      level: 2,
      text: 'Running with Docker Compose',
    },
    {
      type: 'paragraph',
      text: 'If you prefer a containerized multi-service setup (PostgreSQL 16, Redis 7, FastAPI API, Arq worker, and Vite frontend), launch the entire stack with Docker Compose:',
    },
    {
      type: 'code',
      language: 'bash',
      filename: 'Terminal',
      code: `cp .env.example backend/.env
docker compose up --build`,
    },
    {
      type: 'paragraph',
      text: 'Docker starts all five services with automated health checks, shared database volumes, and containerized networking.',
    },
    {
      type: 'heading',
      id: 'urls-and-ports',
      level: 2,
      text: 'Service URLs and Default Ports',
    },
    {
      type: 'table',
      caption: 'Service Port Mappings',
      headers: ['Service', 'URL', 'Default Port', 'Description'],
      rows: [
        ['Frontend Web UI', 'http://localhost:5173', '5173', 'React 19 single-page application and interactive dashboards'],
        ['Backend REST API', 'http://localhost:8000/api', '8000', 'FastAPI application endpoints with tenant isolation'],
        ['Interactive Swagger UI', 'http://localhost:8000/docs', '8000', 'Live OpenAPI 3.1 documentation and schema test runner'],
        ['ReDoc API Reference', 'http://localhost:8000/redoc', '8000', 'Standalone technical OpenAPI specification reference'],
        ['OpenAPI Schema JSON', 'http://localhost:8000/openapi.json', '8000', 'Raw JSON OpenAPI schema for client generation'],
        ['PostgreSQL Database', 'localhost:5432', '5432', 'Relational database (Docker or production mode)'],
        ['Redis Cache & Queue', 'localhost:6379', '6379', 'Job queue and rate limiter (when REDIS_URL is configured)'],
      ],
    },
    {
      type: 'heading',
      id: 'adding-real-providers',
      level: 2,
      text: 'Adding Real Provider API Keys',
    },
    {
      type: 'paragraph',
      text: 'Once you are ready to evaluate real foundation models, add your provider credentials to `backend/.env` (or via the Settings page when logged in):',
    },
    {
      type: 'code',
      language: 'bash',
      filename: 'backend/.env',
      code: `# Google Gemini — https://aistudio.google.com/apikey
GEMINI_API_KEY=AIzaSy...

# Groq — https://console.groq.com/keys
GROQ_API_KEY=gsk_...

# Hugging Face — https://huggingface.co/settings/tokens
HF_API_KEY=hf_...

# OpenRouter — https://openrouter.ai/keys
OPENROUTER_API_KEY=sk-or-v1-...

# NVIDIA NIM — https://build.nvidia.com
NVIDIA_NIM_API_KEY=nvapi-...`,
    },
    {
      type: 'callout',
      tone: 'honesty',
      title: 'Provider Security Guarantee',
      body: 'Provider API keys are read strictly server-side by the backend process. Keys are never transmitted to the browser, never baked into container images, and are automatically redacted with `***redacted***` in all structured application logs.',
    },
  ],
}

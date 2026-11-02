export const settingsProvidersSection = {
  id: 'settings-providers',
  title: 'Settings & Providers',
  group: 'Using the platform',
  summary: 'Manage provider API credentials, inspect model availability audit probes, configure automated LLM judges, and manage workspace members.',
  blocks: [
    {
      type: 'paragraph',
      text: 'The Settings page (`/settings`) allows workspace owners and editors to inspect provider integration health, configure API keys, view model availability audit results, and set the default LLM judge model.',
    },
    {
      type: 'heading',
      id: 'supported-providers',
      level: 2,
      text: 'Supported Providers & Key Provisioning',
    },
    {
      type: 'table',
      caption: 'Provider Integration Directory',
      headers: ['Provider', 'Adapter Type', 'Where to Get API Key', 'Key Environment Variable'],
      rows: [
        ['Google Gemini', 'Native SDK / REST', 'https://aistudio.google.com/apikey', '`GEMINI_API_KEY`'],
        ['Groq', 'OpenAI-Compatible', 'https://console.groq.com/keys', '`GROQ_API_KEY`'],
        ['Hugging Face', 'Inference Providers', 'https://huggingface.co/settings/tokens', '`HF_API_KEY`'],
        ['OpenRouter', 'OpenAI-Compatible', 'https://openrouter.ai/keys', '`OPENROUTER_API_KEY`'],
        ['NVIDIA NIM', 'OpenAI-Compatible', 'https://build.nvidia.com', '`NVIDIA_NIM_API_KEY`'],
        ['Ollama', 'Local OpenAI-Compatible', 'Local server (http://localhost:11434)', '`OLLAMA_ENABLED=true`'],
        ['Mock Provider', 'Deterministic Test', 'Built-in (offline development)', '`ENABLE_MOCK_PROVIDER=true`'],
      ],
    },
    {
      type: 'heading',
      id: 'provider-status-meanings',
      level: 2,
      text: 'What "Configured" vs "Unavailable" Means',
    },
    {
      type: 'list',
      items: [
        'Configured (Green): An API credential is present in the backend environment or encrypted workspace database, and the service endpoint responded successfully to a health check.',
        'Not Configured (Neutral): No API key has been supplied. The platform degrades gracefully and hides live models for this provider while keeping the rest of the application functional.',
        'Model Availability Probed: Beyond checking the provider key, the Model Availability Audit sends a lightweight 8-token probe to verify whether your specific account tier is permitted to invoke each individual model.',
      ],
    },
    {
      type: 'callout',
      tone: 'honesty',
      title: 'Model Availability Reality',
      body: 'Foundation models are frequently retired, renamed, or gated behind enterprise pricing tiers. A provider being "configured" does not guarantee every model in its catalog is accessible. LLM-EvalHub tests each checkpoint with live verification probes so you only select models that can actually run.',
    },
    {
      type: 'heading',
      id: 'judge-model-configuration',
      level: 2,
      text: 'Default LLM Judge Configuration',
    },
    {
      type: 'paragraph',
      text: 'On the Settings page, workspace owners can set the default evaluator provider and model (e.g. Gemini 2.5 Flash or Groq Llama 3.3 70B). The judge model is automatically validated against availability before being saved.',
    },
  ],
}

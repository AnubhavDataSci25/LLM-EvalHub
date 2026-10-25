/**
 * New evaluation — the main configuration surface.
 *
 * Deliberately shows the whole configuration on one page rather than a wizard:
 * an experiment is a reproducible record, and the person setting it up needs to
 * see every field that will be frozen into that record.
 */
import {
  AlertTriangle,
  Cpu,
  Database,
  FileText,
  Gauge,
  Info,
  Play,
  Scale,
  Search,
  Settings2,
  Sparkles,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import {
  Badge,
  Button,
  Card,
  Checkbox,
  ErrorState,
  Field,
  InlineNote,
  Input,
  LoadingState,
  PageHeader,
  Reveal,
  SectionHeader,
  Select,
  Textarea,
  Toggle,
  useToast,
} from '../components/ui'
import { useApi } from '../hooks'
import { api } from '../lib/api'
import { metricKindLabel, num, titleCase } from '../lib/format'

const DEFAULT_SYSTEM_PROMPT =
  'You are a precise assistant being evaluated for factual accuracy. Answer from the supplied context. If the context does not contain the answer, say so plainly rather than guessing. Keep answers concise.'

const DEFAULT_PROMPT_TEMPLATE =
  'Answer the question using the context when it is provided.\n\nContext:\n{context}\n\nQuestion: {question}\n\nAnswer:'

export default function NewEvaluation() {
  const navigate = useNavigate()
  const toast = useToast()
  const [params] = useSearchParams()

  const { data: datasetsPayload, loading: datasetsLoading } = useApi(() => api.datasets({ limit: 100 }), [])
  const { data: providersPayload, loading: providersLoading, error: providersError } = useApi(
    () => api.providers(true),
    [],
  )
  const { data: metricsPayload } = useApi(() => api.metricCatalogue(), [])
  const { data: documentsPayload } = useApi(() => api.documents(), [])

  const datasets = datasetsPayload?.items || []
  const providers = providersPayload?.providers || []
  const configured = providers.filter((p) => p.configured)
  const metricSpecs = metricsPayload?.metrics || []
  const collections = documentsPayload?.collections || []

  const [form, setForm] = useState({
    name: '',
    datasetId: params.get('dataset') || '',
    models: [],
    metrics: [],
    systemPrompt: DEFAULT_SYSTEM_PROMPT,
    promptTemplate: DEFAULT_PROMPT_TEMPLATE,
    temperature: 0,
    maxTokens: 512,
    ragEnabled: Boolean(params.get('collection')),
    collection: params.get('collection') || '',
    retriever: 'hybrid',
    topK: 4,
    chunkSize: 800,
    chunkOverlap: 120,
    judgeProvider: '',
    judgeModel: '',
    latencyBudget: 4000,
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }))

  // default metric selection once the catalogue loads
  useEffect(() => {
    if (metricsPayload?.defaults && form.metrics.length === 0) {
      set('metrics', metricsPayload.defaults)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metricsPayload])

  // name the experiment after the dataset unless the user typed one
  const selectedDataset = datasets.find((d) => d.id === form.datasetId)
  useEffect(() => {
    if (selectedDataset && !form.name) set('name', `${selectedDataset.name} — baseline`)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDataset])

  const modelOptions = useMemo(
    () =>
      configured.flatMap((provider) =>
        (provider.models || []).map((model) => ({
          key: `${provider.key}/${model.id}`,
          provider: provider.key,
          providerName: provider.display_name,
          model: model.id,
          label: model.name || model.id,
          context: model.context_window,
          note: model.note,
        })),
      ),
    [configured],
  )

  const toggleModel = (option) => {
    const exists = form.models.some((m) => m.provider === option.provider && m.model === option.model)
    set(
      'models',
      exists
        ? form.models.filter((m) => !(m.provider === option.provider && m.model === option.model))
        : [...form.models, { provider: option.provider, model: option.model, label: option.label }],
    )
  }

  const toggleMetric = (key) =>
    set('metrics', form.metrics.includes(key) ? form.metrics.filter((m) => m !== key) : [...form.metrics, key])

  const ragMetricsSelected = form.metrics.some((m) =>
    ['context_precision', 'context_recall', 'retrieval_hit_rate'].includes(m),
  )
  const needsGroundTruth = form.metrics.some((m) => ['correctness'].includes(m))

  const submit = async () => {
    setError(null)
    if (!form.datasetId) return setError({ message: 'Choose a dataset first.' })
    if (form.models.length === 0) return setError({ message: 'Select at least one model.' })
    if (form.ragEnabled && !form.collection)
      return setError({ message: 'RAG is on but no document collection is selected.' })

    setSubmitting(true)
    try {
      const payload = {
        experiment: {
          name: form.name.trim() || 'Untitled experiment',
          dataset_id: form.datasetId,
          models: form.models,
          metrics: form.metrics,
          system_prompt: form.systemPrompt,
          prompt_template: form.promptTemplate,
          temperature: Number(form.temperature),
          max_tokens: Number(form.maxTokens),
          rag: {
            enabled: form.ragEnabled,
            collection: form.ragEnabled ? form.collection : null,
            retriever: form.retriever,
            top_k: Number(form.topK),
            chunk_size: Number(form.chunkSize),
            chunk_overlap: Number(form.chunkOverlap),
          },
          judge: form.judgeProvider
            ? { provider: form.judgeProvider, model: form.judgeModel }
            : { provider: null, model: null },
        },
        latency_budget_ms: Number(form.latencyBudget),
      }
      const run = await api.runEvaluation(payload)
      toast.success(`${run.total_units} unit(s) queued.`, 'Evaluation started')
      navigate(`/evaluations/${run.id}`)
    } catch (err) {
      setError(err)
    } finally {
      setSubmitting(false)
    }
  }

  const judgeModels =
    providers.find((p) => p.key === form.judgeProvider)?.models?.map((m) => ({
      value: m.id,
      label: m.name || m.id,
    })) || []

  const estimatedUnits = (selectedDataset?.row_count || 0) * form.models.length

  if (datasetsLoading || providersLoading) return <LoadingState label="Loading configuration…" rows={4} />

  return (
    <>
      <PageHeader
        eyebrow="Evaluate"
        title="New evaluation"
        description="Every field here is frozen into the experiment record, so a later comparison can attribute a change in results to a specific change in configuration."
        actions={
          <Button variant="primary" icon={Play} loading={submitting} onClick={submit}>
            Run evaluation
          </Button>
        }
      />

      {providersError ? <ErrorState error={providersError} /> : null}

      {configured.length <= 1 ? (
        <div className="mb-6">
          <InlineNote tone="warn" icon={AlertTriangle}>
            Only the deterministic test provider is configured. Add a real provider key
            (Gemini, Groq, Hugging Face, OpenRouter or NVIDIA NIM) in the backend <span className="mono">.env</span>{' '}
            to benchmark actual models — the test provider produces mechanical output and must not be
            read as a benchmark result.
          </InlineNote>
        </div>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="space-y-5">
          {/* ---------------------------------------------------- dataset */}
          <Reveal>
            <Card className="p-5">
              <SectionHeader icon={Database} title="Dataset" description="The test cases every selected model will answer." />
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Dataset" required>
                  <Select
                    value={form.datasetId}
                    onChange={(e) => set('datasetId', e.target.value)}
                    placeholder="Choose a dataset…"
                    options={datasets.map((d) => ({
                      value: d.id,
                      label: `${d.name} (${d.row_count} cases)`,
                    }))}
                  />
                </Field>
                <Field label="Experiment name" hint="Used everywhere this run is referenced.">
                  <Input value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="Baseline" />
                </Field>
              </div>

              {selectedDataset && !selectedDataset.has_ground_truth && needsGroundTruth ? (
                <div className="mt-4">
                  <InlineNote tone="warn" icon={AlertTriangle}>
                    This dataset has no expected answers, so correctness will report as unavailable
                    rather than scoring zero. Remove it from the metric selection, or use a dataset
                    with references.
                  </InlineNote>
                </div>
              ) : null}
            </Card>
          </Reveal>

          {/* ---------------------------------------------------- models */}
          <Reveal delay={0.05}>
            <Card className="p-5">
              <SectionHeader
                icon={Cpu}
                title="Models"
                description="Selected models receive identical inputs, so any difference in results is attributable to the model."
                actions={<Badge tone={form.models.length ? 'accent' : 'neutral'}>{form.models.length} selected</Badge>}
              />
              {modelOptions.length === 0 ? (
                <InlineNote tone="warn">
                  No models are available. Configure a provider key and reload.
                </InlineNote>
              ) : (
                <div className="space-y-4">
                  {configured.map((provider) => {
                    const options = modelOptions.filter((m) => m.provider === provider.key)
                    if (!options.length) return null
                    return (
                      <div key={provider.key}>
                        <div className="mb-2 flex items-center gap-2">
                          <p className="label">{provider.display_name}</p>
                          <Badge tone={provider.key === 'mock' ? 'fair' : 'good'}>
                            {provider.key === 'mock' ? 'test fixture' : provider.kind}
                          </Badge>
                        </div>
                        <div className="grid gap-2 sm:grid-cols-2">
                          {options.map((option) => (
                            <Checkbox
                              key={option.key}
                              checked={form.models.some(
                                (m) => m.provider === option.provider && m.model === option.model,
                              )}
                              onChange={() => toggleModel(option)}
                              label={option.label}
                              description={
                                option.context
                                  ? `${num(option.context)} token context`
                                  : option.note || option.model
                              }
                            />
                          ))}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </Card>
          </Reveal>

          {/* ---------------------------------------------------- metrics */}
          <Reveal delay={0.1}>
            <Card className="p-5">
              <SectionHeader
                icon={Scale}
                title="Metrics"
                description="Deterministic metrics are reproducible; judge-based metrics are more semantically accurate but vary between runs."
              />
              <div className="grid gap-2 sm:grid-cols-2">
                {metricSpecs.map((spec) => (
                  <Checkbox
                    key={spec.key}
                    checked={form.metrics.includes(spec.key)}
                    onChange={() => toggleMetric(spec.key)}
                    label={`${spec.label} · ${metricKindLabel(
                      spec.judge_capable && form.judgeProvider ? 'llm_judge' : spec.default_kind,
                    )}`}
                    description={spec.description}
                  />
                ))}
              </div>
              {ragMetricsSelected && !form.ragEnabled ? (
                <div className="mt-4">
                  <InlineNote tone="warn" icon={AlertTriangle}>
                    Retrieval metrics are selected but RAG is off. They will only be computed for
                    cases that carry inline context in the dataset; otherwise they report as
                    unavailable.
                  </InlineNote>
                </div>
              ) : null}
            </Card>
          </Reveal>

          {/* ---------------------------------------------------- prompt */}
          <Reveal delay={0.15}>
            <Card className="p-5">
              <SectionHeader
                icon={FileText}
                title="Prompt"
                description="Both fields are versioned with the experiment. Changing the prompt and re-running is the cleanest A/B this platform supports."
              />
              <div className="space-y-4">
                <Field label="System prompt">
                  <Textarea rows={3} value={form.systemPrompt} onChange={(e) => set('systemPrompt', e.target.value)} />
                </Field>
                <Field
                  label="Prompt template"
                  hint="Placeholders: {question} and {context}. Context comes from retrieval, or from the dataset's inline context when RAG is off."
                >
                  <Textarea rows={6} value={form.promptTemplate} onChange={(e) => set('promptTemplate', e.target.value)} className="mono" />
                </Field>
              </div>
            </Card>
          </Reveal>

          {/* ---------------------------------------------------- RAG */}
          <Reveal delay={0.2}>
            <Card className="p-5">
              <SectionHeader icon={Search} title="Retrieval" description="Optional. Turn this on to evaluate a RAG pipeline end to end rather than the model alone." />
              <Toggle
                checked={form.ragEnabled}
                onChange={(value) => set('ragEnabled', value)}
                label="Enable RAG retrieval"
                description="Retrieved chunks replace the dataset's inline context."
              />
              {form.ragEnabled ? (
                <div className="mt-5 grid gap-4 sm:grid-cols-2">
                  <Field label="Collection" required>
                    <Select
                      value={form.collection}
                      onChange={(e) => set('collection', e.target.value)}
                      placeholder="Choose a collection…"
                      options={collections.map((c) => ({
                        value: c.name,
                        label: `${c.name} (${c.chunks} chunks)`,
                      }))}
                    />
                  </Field>
                  <Field label="Retriever" hint="Hybrid fuses BM25 and vector ranking.">
                    <Select
                      value={form.retriever}
                      onChange={(e) => set('retriever', e.target.value)}
                      options={[
                        { value: 'vector', label: 'Vector similarity' },
                        { value: 'keyword', label: 'Keyword (BM25)' },
                        { value: 'hybrid', label: 'Hybrid (RRF)' },
                      ]}
                    />
                  </Field>
                  <Field label="Top K" hint="Chunks passed to the model.">
                    <Input type="number" min={1} max={20} value={form.topK} onChange={(e) => set('topK', e.target.value)} />
                  </Field>
                  <Field label="Chunk size" hint="Recorded for reproducibility; re-index to change the stored chunks.">
                    <Input type="number" min={200} max={4000} step={100} value={form.chunkSize} onChange={(e) => set('chunkSize', e.target.value)} />
                  </Field>
                </div>
              ) : (
                <p className="prose-note mt-4 text-[0.82rem]">
                  With retrieval off, the model sees whatever context the dataset supplies. That is the
                  right setting for measuring a model in isolation.
                </p>
              )}
            </Card>
          </Reveal>
        </div>

        {/* ------------------------------------------------------ sidebar */}
        <div className="space-y-5">
          <Reveal>
            <Card className="sticky top-20 p-5">
              <SectionHeader icon={Settings2} title="Run parameters" />
              <div className="space-y-4">
                <Field label="Temperature" hint="0 gives the most reproducible evaluation.">
                  <Input type="number" min={0} max={2} step={0.1} value={form.temperature} onChange={(e) => set('temperature', e.target.value)} />
                </Field>
                <Field label="Max tokens">
                  <Input type="number" min={32} max={4096} step={32} value={form.maxTokens} onChange={(e) => set('maxTokens', e.target.value)} />
                </Field>
                <Field label="Latency budget (ms)" hint="Responses slower than this are flagged as high latency.">
                  <Input type="number" min={500} step={500} value={form.latencyBudget} onChange={(e) => set('latencyBudget', e.target.value)} />
                </Field>

                <div className="border-t border-line pt-4">
                  <p className="label mb-3">LLM judge (optional)</p>
                  <div className="space-y-3">
                    <Select
                      value={form.judgeProvider}
                      onChange={(e) => {
                        set('judgeProvider', e.target.value)
                        set('judgeModel', '')
                      }}
                      placeholder="Deterministic only"
                      options={configured
                        .filter((p) => p.key !== 'mock')
                        .map((p) => ({ value: p.key, label: p.display_name }))}
                    />
                    {form.judgeProvider ? (
                      <Select
                        value={form.judgeModel}
                        onChange={(e) => set('judgeModel', e.target.value)}
                        placeholder="Choose a judge model…"
                        options={judgeModels}
                      />
                    ) : null}
                    <p className="prose-note text-[0.75rem] leading-snug">
                      A judge scores correctness, relevance and faithfulness semantically. It costs
                      extra calls and introduces run-to-run variance — both are recorded against
                      every score it produces.
                    </p>
                  </div>
                </div>

                <div className="rounded-xl border border-line bg-overlay/60 p-4">
                  <div className="flex items-center justify-between">
                    <span className="label">Work units</span>
                    <span className="mono text-lg font-semibold text-ink">{num(estimatedUnits)}</span>
                  </div>
                  <p className="prose-note mt-1 text-[0.75rem]">
                    {selectedDataset?.row_count || 0} case(s) × {form.models.length} model(s)
                  </p>
                </div>

                {error ? <ErrorState compact error={error} /> : null}

                <Button variant="primary" icon={Play} className="w-full" loading={submitting} onClick={submit}>
                  Run evaluation
                </Button>
              </div>
            </Card>
          </Reveal>
        </div>
      </div>
    </>
  )
}

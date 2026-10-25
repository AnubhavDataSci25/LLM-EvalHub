/** Benchmark packs — preconfigured evaluation scenarios, installable in one click. */
import { BookOpen, CheckCircle2, Download, Layers, Play, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  InlineNote,
  LoadingState,
  Modal,
  PageHeader,
  Reveal,
  useToast,
} from '../components/ui'
import { useApi } from '../hooks'
import { api } from '../lib/api'
import { num, titleCase, truncate } from '../lib/format'

const DIFFICULTY_TONES = { easy: 'good', medium: 'fair', hard: 'poor', adversarial: 'bad' }

function PackModal({ packKey, onClose, onInstalled }) {
  const toast = useToast()
  const [installing, setInstalling] = useState(false)
  const { data: pack, loading, error } = useApi(() => api.benchmark(packKey), [packKey], {
    enabled: Boolean(packKey),
  })

  const install = async () => {
    setInstalling(true)
    try {
      const result = await api.installBenchmark(packKey)
      toast.success(
        result.collection
          ? `Dataset created and ${result.documents.length} document(s) indexed into "${result.collection}".`
          : 'Dataset created.',
        pack.name,
      )
      onInstalled(result)
    } catch (err) {
      toast.error(err.message, 'Install failed')
    } finally {
      setInstalling(false)
    }
  }

  return (
    <Modal
      open={Boolean(packKey)}
      onClose={onClose}
      title={pack?.name || 'Benchmark pack'}
      description={pack?.description}
      size="lg"
      footer={
        <>
          <Button onClick={onClose}>Close</Button>
          <Button variant="primary" icon={Download} loading={installing} onClick={install}>
            Install pack
          </Button>
        </>
      }
    >
      {loading ? (
        <LoadingState label="Loading pack…" rows={2} />
      ) : error ? (
        <ErrorState error={error} />
      ) : pack ? (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-3">
            {[
              ['Test cases', num(pack.case_count)],
              ['Categories', pack.categories?.length || 0],
              ['RAG', pack.rag_recommended ? 'Recommended' : 'Not needed'],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl bg-overlay/60 px-4 py-3">
                <p className="label">{label}</p>
                <p className="mono mt-1 text-base font-semibold text-ink">{value}</p>
              </div>
            ))}
          </div>

          <div>
            <p className="label mb-2">Recommended metrics</p>
            <div className="flex flex-wrap gap-1.5">
              {pack.metrics?.map((metric) => (
                <Badge key={metric} tone="accent">{titleCase(metric)}</Badge>
              ))}
            </div>
          </div>

          {Object.keys(pack.metric_notes || {}).length ? (
            <div>
              <p className="label mb-2">Why these metrics</p>
              <div className="space-y-2">
                {Object.entries(pack.metric_notes).map(([metric, note]) => (
                  <div key={metric} className="rounded-xl border border-line bg-surface p-3">
                    <p className="text-xs font-semibold text-ink">{titleCase(metric)}</p>
                    <p className="prose-note mt-1 text-xs leading-relaxed">{note}</p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div>
            <p className="label mb-2">Difficulty mix</p>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(pack.difficulty_mix || {}).map(([level, count]) => (
                <Badge key={level} tone={DIFFICULTY_TONES[level] || 'neutral'}>
                  {titleCase(level)} · {count}
                </Badge>
              ))}
            </div>
          </div>

          {pack.sample_cases?.length ? (
            <div>
              <p className="label mb-2">Sample cases</p>
              <div className="space-y-2">
                {pack.sample_cases.slice(0, 3).map((sample, index) => (
                  <div key={index} className="rounded-xl border border-line bg-surface p-3">
                    <p className="text-sm font-medium text-ink">{sample.question}</p>
                    {sample.ground_truth ? (
                      <p className="prose-note mt-1.5 text-xs">
                        <span className="font-semibold">Expected: </span>
                        {truncate(sample.ground_truth, 180)}
                      </p>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {pack.installed_dataset_id ? (
            <InlineNote tone="accent" icon={CheckCircle2}>
              This pack is already installed. Installing again creates a second, independent dataset.
            </InlineNote>
          ) : null}
        </div>
      ) : null}
    </Modal>
  )
}

export default function Benchmarks() {
  const navigate = useNavigate()
  const [selected, setSelected] = useState(null)
  const { data, loading, error, refetch } = useApi(() => api.benchmarks(), [])

  const packs = data || []

  return (
    <>
      <PageHeader
        eyebrow="Inputs"
        title="Benchmark packs"
        description="Preconfigured evaluation scenarios. Each pack ships a dataset, the metrics that actually matter for that use case, baseline settings, and — where retrieval is part of the task — source documents that are chunked and indexed on install."
      />

      <InlineNote tone="accent" icon={Sparkles}>
        Every pack is synthetic and redistributable. They are designed to discriminate between models
        rather than to be easy: several include deliberately unanswerable questions so that a model
        that guesses is penalised against one that declines.
      </InlineNote>

      <div className="mt-6">
        {loading ? (
          <LoadingState label="Loading packs…" />
        ) : error ? (
          <ErrorState error={error} onRetry={refetch} />
        ) : packs.length === 0 ? (
          <EmptyState
            icon={BookOpen}
            title="No benchmark packs found"
            description="The benchmarks directory could not be read on the server."
          />
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {packs.map((pack, index) => (
              <Reveal key={pack.key} delay={Math.min(index * 0.05, 0.3)}>
                <Card hover className="flex h-full flex-col p-5">
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <h3 className="text-[1.02rem] font-semibold">{pack.name}</h3>
                    {pack.installed_dataset_id ? (
                      <Badge tone="good" icon={CheckCircle2}>Installed</Badge>
                    ) : null}
                  </div>

                  <p className="prose-note mb-4 line-clamp-3 text-[0.84rem]">{pack.description}</p>

                  <div className="mb-4 flex flex-wrap gap-1.5">
                    <Badge tone="neutral" icon={Layers}>{num(pack.case_count)} cases</Badge>
                    {pack.rag_recommended ? <Badge tone="info">RAG</Badge> : null}
                    <Badge>{titleCase(pack.use_case)}</Badge>
                  </div>

                  <div className="mb-4 flex flex-wrap gap-1">
                    {pack.metrics?.slice(0, 4).map((metric) => (
                      <span key={metric} className="mono rounded bg-overlay px-1.5 py-0.5 text-[0.68rem] text-muted">
                        {metric}
                      </span>
                    ))}
                  </div>

                  <div className="mt-auto flex gap-2 border-t border-line pt-3">
                    <Button className="flex-1" onClick={() => setSelected(pack.key)}>
                      Details
                    </Button>
                    {pack.installed_dataset_id ? (
                      <Link
                        to={`/evaluations/new?dataset=${pack.installed_dataset_id}`}
                        className="btn-primary flex-1"
                      >
                        <Play className="h-4 w-4" />
                        Evaluate
                      </Link>
                    ) : (
                      <Button variant="primary" className="flex-1" onClick={() => setSelected(pack.key)}>
                        <Download className="h-4 w-4" />
                        Install
                      </Button>
                    )}
                  </div>
                </Card>
              </Reveal>
            ))}
          </div>
        )}
      </div>

      <PackModal
        packKey={selected}
        onClose={() => setSelected(null)}
        onInstalled={(result) => {
          setSelected(null)
          refetch()
          navigate(`/evaluations/new?dataset=${result.dataset.id}${result.collection ? `&collection=${result.collection}` : ''}`)
        }}
      />
    </>
  )
}

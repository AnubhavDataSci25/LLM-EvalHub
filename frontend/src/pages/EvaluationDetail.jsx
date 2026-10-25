/** Evaluation run detail — live progress, per-model comparison and the result table. */
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Clock,
  FileText,
  Filter,
  Layers,
  RefreshCw,
  Search,
  Stethoscope,
  XCircle,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { LatencyChart, MetricRadarChart, ModelComparisonChart } from '../components/charts'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  InlineNote,
  KeyValue,
  LoadingState,
  Modal,
  PageHeader,
  ProgressBar,
  Reveal,
  ScoreBar,
  SectionHeader,
  StatusBadge,
  Tabs,
  useToast,
} from '../components/ui'
import { useApi, useDebounced, useRunPolling } from '../hooks'
import { api } from '../lib/api'
import { NA, formatKappa, ms, num, pct, score, scoreTone, seconds, titleCase, truncate } from '../lib/format'

function ResultModal({ result, onClose }) {
  if (!result) return null
  return (
    <Modal open onClose={onClose} title="Result detail" size="lg" description={`${result.provider} / ${result.model}`}>
      <div className="space-y-5">
        <div>
          <p className="label mb-1.5">Question</p>
          <p className="text-sm text-ink">{result.question}</p>
        </div>

        {result.ground_truth ? (
          <div>
            <p className="label mb-1.5">Expected answer</p>
            <p className="rounded-xl border border-line bg-overlay/50 p-3 text-sm text-muted">
              {result.ground_truth}
            </p>
          </div>
        ) : null}

        <div>
          <p className="label mb-1.5">Generated answer</p>
          {result.generated_answer ? (
            <p className="whitespace-pre-wrap rounded-xl border border-line bg-surface p-3 text-sm text-ink">
              {result.generated_answer}
            </p>
          ) : (
            <p className="rounded-xl border border-[rgb(var(--bad))]/25 bg-[rgb(var(--bad))]/8 p-3 text-sm">
              {result.error_message || 'The model returned no text.'}
            </p>
          )}
        </div>

        {result.retrieved_context?.length ? (
          <div>
            <p className="label mb-1.5">Retrieved context ({result.retrieved_context.length} chunk(s))</p>
            <div className="space-y-2">
              {result.retrieved_context.map((chunk, index) => (
                <div key={index} className="rounded-xl border border-line bg-overlay/40 p-3">
                  <p className="mono mb-1 text-[0.68rem] text-faint">chunk {index + 1}</p>
                  <p className="text-xs leading-relaxed text-muted">{chunk}</p>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <div>
          <p className="label mb-2">Scores</p>
          <div className="space-y-2">
            {(result.metrics || []).map((metric) => {
              let relInfo = null
              if (metric.evidence) {
                try {
                  const p = typeof metric.evidence === 'string' ? JSON.parse(metric.evidence) : metric.evidence
                  relInfo = p?.judge_reliability
                } catch {
                  relInfo = null
                }
              }
              const isJudged = metric.kind === 'llm_judge'
              const isCalibrated = relInfo?.status === 'calibrated' && relInfo?.kappa !== null && relInfo?.kappa !== undefined

              return (
                <div key={metric.metric} className="flex items-center justify-between gap-3 rounded-lg bg-overlay/50 px-3 py-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-ink">{titleCase(metric.metric)}</p>
                      {isJudged ? (
                        <Link to="/calibration" className="inline-flex outline-none" title="View judge calibration">
                          {isCalibrated ? (
                            <Badge tone="good" className="text-[0.65rem]">
                              Judge reliability: κ {formatKappa(relInfo.kappa)}
                            </Badge>
                          ) : (
                            <Badge tone="neutral" className="text-[0.65rem]">
                              uncalibrated
                            </Badge>
                          )}
                        </Link>
                      ) : null}
                    </div>
                    <p className="text-[0.7rem] text-faint">
                      {metric.available
                        ? `${titleCase(metric.kind)}${metric.judge_model ? ` · ${metric.judge_model}` : ''}`
                        : metric.unavailable_reason}
                    </p>
                  </div>
                  {metric.available ? (
                    <ScoreBar value={metric.normalized_score} tone={scoreTone(metric.normalized_score)} />
                  ) : (
                    <Badge tone="neutral">unavailable</Badge>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        <KeyValue
          items={[
            { label: 'Latency', value: ms(result.latency_ms) },
            { label: 'Composite', value: score(result.composite_score) },
            { label: 'Status', value: titleCase(result.status) },
            { label: 'Tokens', value: result.usage?.total_tokens ? num(result.usage.total_tokens) : NA },
          ]}
        />
      </div>
    </Modal>
  )
}

export default function EvaluationDetail() {
  const { id } = useParams()
  const toast = useToast()
  const [tab, setTab] = useState('overview')
  const [failedOnly, setFailedOnly] = useState(false)
  const [modelFilter, setModelFilter] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(null)
  const debouncedSearch = useDebounced(search)

  const { run, loading, error } = useRunPolling(id, {
    onComplete: (payload) =>
      payload.status === 'completed'
        ? toast.success('Evaluation finished.', payload.experiment_name)
        : toast.error(payload.error || 'The run failed.', 'Evaluation failed'),
  })

  const finished = run?.status === 'completed' || run?.status === 'failed'

  const { data: comparison } = useApi(() => api.compareModels(id), [id, finished], { enabled: finished })
  const { data: results, refetch: refetchResults } = useApi(
    () =>
      api.runResults(id, {
        limit: 200,
        failed_only: failedOnly || undefined,
        model: modelFilter || undefined,
        search: debouncedSearch || undefined,
      }),
    [id, finished, failedOnly, modelFilter, debouncedSearch],
    { enabled: Boolean(run) },
  )

  if (loading && !run) return <LoadingState label="Loading run…" rows={4} />
  if (error) return <ErrorState error={error} />
  if (!run) return null

  const summary = run.summary || {}
  const rows = comparison?.rows || []
  const metrics = comparison?.metrics || []
  const resultItems = results?.items || []

  const retry = async () => {
    try {
      const newRun = await api.retryRun(id)
      toast.success('Errored cases queued in a new run.')
      window.location.href = `/evaluations/${newRun.id}`
    } catch (err) {
      toast.error(err.message)
    }
  }

  return (
    <>
      <Link to="/experiments" className="btn-ghost mb-4 -ml-2 px-2 text-sm">
        <ArrowLeft className="h-4 w-4" />
        Experiments
      </Link>

      <PageHeader
        eyebrow="Evaluation run"
        title={run.experiment_name || run.id}
        description={run.dataset_name ? `Dataset: ${run.dataset_name}` : undefined}
        actions={
          <>
            {summary.error_cases ? (
              <Button icon={RefreshCw} onClick={retry}>
                Retry {summary.error_cases} errored
              </Button>
            ) : null}
            {finished ? (
              <>
                <Link to={`/compare?run=${id}`} className="btn-secondary">
                  <BarChart3 className="h-4 w-4" />
                  Compare
                </Link>
                <Link to={`/reports?run=${id}`} className="btn-primary">
                  <FileText className="h-4 w-4" />
                  Generate report
                </Link>
              </>
            ) : null}
          </>
        }
      >
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <StatusBadge status={run.status} />
          <span className="text-xs text-muted">
            {num(run.completed_units)} / {num(run.total_units)} units
          </span>
          {run.duration_seconds ? (
            <span className="text-xs text-muted">{seconds(run.duration_seconds)}</span>
          ) : null}
          {run.experiment_id ? (
            <Link
              to={`/experiments/${run.experiment_id}`}
              className="text-xs text-accent underline-offset-2 hover:underline"
            >
              View experiment configuration
            </Link>
          ) : null}
        </div>

        {!finished ? (
          <div className="mt-4 max-w-md">
            <ProgressBar value={run.progress || 0} label={titleCase(run.stage || 'running')} />
          </div>
        ) : null}
      </PageHeader>

      {run.status === 'failed' ? (
        <div className="mb-6">
          <ErrorState error={{ message: run.error || 'The run failed.' }} />
        </div>
      ) : null}

      {run.warnings?.length ? (
        <div className="mb-6 space-y-2">
          {run.warnings.map((warning, index) => (
            <InlineNote key={index} tone="warn">{warning}</InlineNote>
          ))}
        </div>
      ) : null}

      {/* headline metrics */}
      <div className="mb-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: 'Quality score', value: score(summary.avg_quality_score), icon: CheckCircle2, hint: 'Mean of the quality metrics' },
          { label: 'Failure rate', value: pct(summary.failure_rate), icon: XCircle, hint: `${num(summary.failed_cases)} of ${num(summary.total_cases)} cases` },
          { label: 'Average latency', value: ms(summary.avg_latency_ms), icon: Clock, hint: `p95 ${ms(summary.p95_latency_ms)}` },
          { label: 'Provider errors', value: num(summary.error_cases ?? 0), icon: Layers, hint: `Error rate ${pct(summary.error_rate)}` },
        ].map((kpi, index) => (
          <Reveal key={kpi.label} delay={index * 0.05}>
            <Card className="p-5">
              <div className="mb-3 flex items-start justify-between">
                <span className="label">{kpi.label}</span>
                <kpi.icon className="h-4 w-4 text-faint" />
              </div>
              <p className="metric-value">{kpi.value}</p>
              <p className="prose-note mt-1.5 text-xs">{kpi.hint}</p>
            </Card>
          </Reveal>
        ))}
      </div>

      <Tabs
        className="mb-5 w-fit"
        active={tab}
        onChange={setTab}
        tabs={[
          { value: 'overview', label: 'Overview' },
          { value: 'models', label: 'Per model', count: rows.length },
          { value: 'results', label: 'Results', count: results?.total },
        ]}
      />

      {tab === 'overview' ? (
        <div className="grid gap-5 xl:grid-cols-2">
          <Card className="p-5">
            <SectionHeader title="Model comparison" description="Identical inputs across every model in this run." />
            <ModelComparisonChart rows={rows} metrics={metrics.filter((m) => m !== 'latency')} />
          </Card>
          <Card className="p-5">
            <SectionHeader title="Latency" description="Average and p95 response time per model." />
            <LatencyChart rows={rows} />
          </Card>
          <Card className="p-5">
            <SectionHeader title="Metric profile" description="Shape of each model's strengths across metrics." />
            <MetricRadarChart rows={rows} metrics={metrics.filter((m) => m !== 'latency')} />
          </Card>
          <Card className="p-5">
            <SectionHeader title="Metric detail" description="Sample size tells you how much weight a mean deserves." />
            <div className="space-y-2.5">
              {Object.entries(summary.metrics || {}).map(([metric, block]) => {
                const isJudged = block.kinds?.includes('llm_judge')
                return (
                  <div key={metric} className="flex items-center justify-between gap-3 rounded-lg bg-overlay/50 px-3 py-2.5">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-ink">{titleCase(metric)}</p>
                        {isJudged ? (
                          <Link to="/calibration" className="inline-flex outline-none" title="View judge calibration">
                            <Badge tone="neutral" className="text-[0.65rem] hover:opacity-80">
                              Judge reliability
                            </Badge>
                          </Link>
                        ) : null}
                      </div>
                      <p className="text-[0.7rem] text-faint">
                        {block.sample_size ? `${block.sample_size} scored case(s)` : 'Never measured'}
                        {block.kinds?.length ? ` · ${block.kinds.map(titleCase).join(', ')}` : ''}
                      </p>
                    </div>
                    {block.mean !== null && block.mean !== undefined ? (
                      <ScoreBar value={block.mean} tone={scoreTone(block.mean)} />
                    ) : (
                      <Badge tone="neutral">unavailable</Badge>
                    )}
                  </div>
                )
              })}
            </div>
          </Card>
        </div>
      ) : null}

      {tab === 'models' ? (
        rows.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Cases</th>
                  {metrics.filter((m) => m !== 'latency').map((m) => (
                    <th key={m}>{titleCase(m)}</th>
                  ))}
                  <th>Latency</th>
                  <th>Failure rate</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key}>
                    <td>
                      <p className="font-semibold text-ink">{row.label}</p>
                      <p className="mono text-xs text-faint">{row.provider}</p>
                    </td>
                    <td className="mono">{row.cases}</td>
                    {metrics.filter((m) => m !== 'latency').map((m) => (
                      <td key={m}>
                        {row.metrics?.[m]?.mean !== null && row.metrics?.[m]?.mean !== undefined ? (
                          <ScoreBar value={row.metrics[m].mean} tone={scoreTone(row.metrics[m].mean)} />
                        ) : (
                          <span className="text-faint">{NA}</span>
                        )}
                      </td>
                    ))}
                    <td className="mono">{ms(row.avg_latency_ms)}</td>
                    <td className="mono">{pct(row.failure_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon={Layers} title="No completed results yet" description="Per-model figures appear once the run finishes." />
        )
      ) : null}

      {tab === 'results' ? (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <div className="relative min-w-[14rem] flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
              <input
                className="input pl-9"
                placeholder="Search questions…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <select className="input w-auto" value={modelFilter} onChange={(e) => setModelFilter(e.target.value)}>
              <option value="">All models</option>
              {rows.map((row) => (
                <option key={row.key} value={row.model}>{row.label}</option>
              ))}
            </select>
            <Button
              icon={Filter}
              onClick={() => setFailedOnly(!failedOnly)}
              className={failedOnly ? 'border-accent text-accent' : ''}
            >
              {failedOnly ? 'Showing failures' : 'All results'}
            </Button>
            <Button icon={RefreshCw} onClick={refetchResults}>Refresh</Button>
          </div>

          {resultItems.length ? (
            <div className="table-wrap max-h-[70vh] overflow-y-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>Question</th>
                    <th>Model</th>
                    <th>Answer</th>
                    <th>Composite</th>
                    <th>Latency</th>
                    <th>Outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {resultItems.map((result) => (
                    <tr
                      key={result.id}
                      onClick={() => setSelected(result)}
                      className="cursor-pointer"
                    >
                      <td className="max-w-xs text-sm">{truncate(result.question, 90)}</td>
                      <td className="mono whitespace-nowrap text-xs">{result.model}</td>
                      <td className="max-w-sm text-xs text-muted">
                        {result.generated_answer ? (
                          truncate(result.generated_answer, 110)
                        ) : (
                          <span className="text-[rgb(var(--bad))]">{result.error_kind || 'empty'}</span>
                        )}
                      </td>
                      <td>
                        {result.composite_score !== null && result.composite_score !== undefined ? (
                          <ScoreBar value={result.composite_score} tone={scoreTone(result.composite_score)} />
                        ) : (
                          <span className="text-faint">{NA}</span>
                        )}
                      </td>
                      <td className="mono whitespace-nowrap">{ms(result.latency_ms)}</td>
                      <td>
                        {result.status === 'error' ? (
                          <Badge tone="bad">error</Badge>
                        ) : result.passed ? (
                          <Badge tone="good">passed</Badge>
                        ) : (
                          <Badge tone="poor">{result.failure?.failure_type?.replace(/_/g, ' ') || 'failed'}</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              icon={Stethoscope}
              title={failedOnly ? 'No failures match these filters' : 'No results yet'}
              description={failedOnly ? 'Clear the filter to see every result.' : 'Results appear as the run progresses.'}
            />
          )}

          <div className="mt-4 flex items-center justify-between">
            <p className="prose-note text-xs">
              Showing {resultItems.length} of {num(results?.total ?? 0)} result(s).
            </p>
            <Link to={`/failures?run=${id}`} className="btn-ghost text-xs">
              Diagnose failures
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </>
      ) : null}

      <ResultModal result={selected} onClose={() => setSelected(null)} />
    </>
  )
}

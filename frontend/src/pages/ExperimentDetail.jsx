/** Experiment detail — configuration, run history, before/after outcome, and counterfactual attribution. */
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  FlaskConical,
  GitBranch,
  GitCompare,
  Play,
  Settings2,
  TrendingUp,
  XCircle,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { DeltaChart } from '../components/charts'
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
  Reveal,
  SectionHeader,
  StatusBadge,
  useToast,
} from '../components/ui'
import { useApi } from '../hooks'
import { api } from '../lib/api'
import {
  NA,
  attributionLabel,
  attributionTone,
  dateTime,
  formatCI,
  formatP,
  ms,
  num,
  pct,
  score,
  seconds,
  titleCase,
} from '../lib/format'

const VERDICT_CHART_CONFIG = {
  RETRIEVAL_CAUSED: { label: 'Retrieval', fill: '#7C8C46' },
  GENERATION_CAUSED: { label: 'Generation', fill: '#B4633F' },
  PARAMETRIC_KNOWLEDGE: { label: 'Parametric', fill: '#9C8862' },
  NOT_CONTEXT_DEPENDENT: { label: 'Not context-dep.', fill: '#5C7A8C' },
  NOT_ATTRIBUTABLE: { label: 'Not attributable', fill: '#8C8C8C' },
}

function VerdictDistributionChart({ counts }) {
  const data = Object.entries(VERDICT_CHART_CONFIG).map(([key, cfg]) => ({
    key,
    name: cfg.label,
    count: counts?.[key] || 0,
    fill: cfg.fill,
  }))

  const total = data.reduce((sum, d) => sum + d.count, 0)
  if (total === 0) {
    return (
      <div className="flex h-48 items-center justify-center rounded-xl border border-dashed border-line text-xs text-faint">
        No attributed cases yet.
      </div>
    )
  }

  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
          <XAxis dataKey="name" fontSize={11} stroke="rgb(var(--faint))" tickLine={false} />
          <YAxis allowDecimals={false} fontSize={11} stroke="rgb(var(--faint))" tickLine={false} />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const entry = payload[0].payload
              return (
                <div className="rounded-xl border border-line bg-elevated px-3 py-2 text-xs shadow-lift">
                  <p className="font-semibold text-ink">{entry.name}</p>
                  <p className="mt-0.5 text-muted">
                    Count: <span className="mono font-bold text-ink">{entry.count}</span>{' '}
                    ({total > 0 ? `${((entry.count / total) * 100).toFixed(0)}%` : '0%'})
                  </p>
                </div>
              )
            }}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={48}>
            {data.map((entry) => (
              <Cell key={entry.key} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function BatchAttributionModal({ experimentId, totalFailures, onClose, onCompleted }) {
  const [maxCases, setMaxCases] = useState(Math.min(10, Math.max(1, totalFailures || 10)))
  const [repeats, setRepeats] = useState(1)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const { data: estimate, loading: estimating } = useApi(
    () =>
      api.runExperimentAttribution(experimentId, {
        dry_run: true,
        max_cases: maxCases,
        repeats,
      }),
    [experimentId, maxCases, repeats],
  )

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await api.runExperimentAttribution(experimentId, {
        dry_run: false,
        max_cases: maxCases,
        repeats,
      })
      onCompleted(res)
      onClose()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  const estimatedCalls = estimate?.estimated_provider_calls ?? maxCases * 2 * repeats
  const targetCases = estimate?.target_cases ?? maxCases

  return (
    <Modal
      open
      onClose={onClose}
      title="Counterfactual attribution on failed cases"
      description="Run empirical counterfactual tests on failed cases in this experiment to isolate retrieval vs generation bottlenecks."
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" icon={FlaskConical} loading={busy} onClick={run}>
            {busy ? 'Attributing cases…' : `Run attribution (${estimatedCalls} call${estimatedCalls > 1 ? 's' : ''})`}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div>
          <label className="label mb-1.5 block">Max cases to attribute (quota protection)</label>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min="1"
              max={Math.min(50, Math.max(1, totalFailures || 10))}
              value={maxCases}
              onChange={(e) => setMaxCases(Number(e.target.value))}
              className="flex-1 accent-[rgb(var(--accent))]"
            />
            <span className="mono w-16 text-right text-xs font-semibold text-ink">
              {maxCases} case{maxCases > 1 ? 's' : ''}
            </span>
          </div>
          <p className="prose-note mt-1 text-[0.72rem]">
            Targets up to {maxCases} failed cases. Capped at 50 to protect free-tier quotas.
          </p>
        </div>

        <div>
          <label className="label mb-1.5 block">Repeats per condition</label>
          <div className="flex gap-2">
            {[1, 3, 5].map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => setRepeats(n)}
                className={`flex-1 rounded-lg border px-3 py-2 text-xs font-medium transition ${
                  repeats === n
                    ? 'border-accent bg-accent-soft font-semibold text-ink'
                    : 'border-line bg-surface text-muted hover:border-ink/20'
                }`}
              >
                {n} {n === 1 ? 'trial (fastest)' : 'trials (robust)'}
              </button>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-line bg-overlay/50 p-3.5 text-xs">
          <div className="flex items-center justify-between font-semibold text-ink">
            <span>Estimated provider calls:</span>
            <span className="mono text-sm font-bold text-accent">
              {estimating ? '…' : estimatedCalls}
            </span>
          </div>
          <p className="mt-1 text-[0.72rem] text-faint">
            {targetCases} target case(s) × 2 conditions × {repeats} trial(s).
          </p>
        </div>

        {error ? <ErrorState compact error={error} /> : null}
      </div>
    </Modal>
  )
}

export default function ExperimentDetail() {
  const { id } = useParams()
  const toast = useToast()
  const [tab, setTab] = useState('overview')
  const [showBatchModal, setShowBatchModal] = useState(false)
  const { data: experiment, loading, error, refetch } = useApi(() => api.experiment(id), [id])
  const { data: runsPayload } = useApi(() => api.experimentRuns(id), [id])
  const { data: outcome } = useApi(() => api.experimentOutcome(id), [id], {
    enabled: Boolean(experiment?.parent_experiment_id),
  })
  const { data: attributionSummary, refetch: refetchAttribution } = useApi(
    () => api.experimentAttributionSummary(id),
    [id],
  )

  if (loading) return <LoadingState label="Loading experiment…" />
  if (error) return <ErrorState error={error} onRetry={refetch} />
  if (!experiment) return null

  const runs = runsPayload?.items || []

  const handleBatchCompleted = (res) => {
    refetchAttribution()
    toast.success(
      `Attributed ${res.completed_cases} failed case(s) under counterfactual conditions.`,
      'Attribution complete',
    )
  }

  const rerun = async () => {
    try {
      const run = await api.runEvaluation({ experiment_id: experiment.id })
      toast.success('Re-run queued.')
      window.location.href = `/evaluations/${run.id}`
    } catch (err) {
      toast.error(err.message)
    }
  }

  return (
    <>
      <Link to="/experiments" className="btn-ghost mb-4 -ml-2 px-2 text-sm">
        <ArrowLeft className="h-4 w-4" />
        All experiments
      </Link>

      <PageHeader
        eyebrow={experiment.parent_experiment_id ? 'Follow-up experiment' : 'Experiment'}
        title={experiment.name}
        description={experiment.description}
        actions={
          <>
            {experiment.parent_experiment_id ? (
              <Link to={`/experiments/${experiment.parent_experiment_id}`} className="btn-secondary">
                <GitBranch className="h-4 w-4" />
                Baseline
              </Link>
            ) : null}
            <Button variant="primary" icon={Play} onClick={rerun}>
              Run again
            </Button>
          </>
        }
      />

      {experiment.change_summary ? (
        <div className="mb-6">
          <InlineNote tone="accent" icon={GitBranch}>
            <span className="font-semibold text-ink">What changed from the baseline: </span>
            {experiment.change_summary}
          </InlineNote>
        </div>
      ) : null}

      {/* Tabs */}
      <div className="mb-6 flex border-b border-line">
        <button
          type="button"
          onClick={() => setTab('overview')}
          className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition ${
            tab === 'overview'
              ? 'border-accent font-semibold text-accent'
              : 'border-transparent text-muted hover:text-ink'
          }`}
        >
          <Settings2 className="h-4 w-4" />
          Overview
        </button>
        <button
          type="button"
          onClick={() => setTab('attribution')}
          className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition ${
            tab === 'attribution'
              ? 'border-accent font-semibold text-accent'
              : 'border-transparent text-muted hover:text-ink'
          }`}
        >
          <FlaskConical className="h-4 w-4" />
          Attribution
          {attributionSummary?.total_attributed ? (
            <Badge tone="accent">{attributionSummary.total_attributed}</Badge>
          ) : null}
        </button>
      </div>

      {tab === 'attribution' ? (
        <div className="space-y-6">
          {/* Summary KPIs */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card className="p-4">
              <p className="label">Total failures</p>
              <p className="mono mt-1 text-2xl font-bold text-ink">
                {num(attributionSummary?.total_failures ?? 0)}
              </p>
              <p className="mt-1 text-[0.7rem] text-faint">Failed cases across runs</p>
            </Card>
            <Card className="p-4">
              <p className="label">Attributed cases</p>
              <p className="mono mt-1 text-2xl font-bold text-ink">
                {num(attributionSummary?.total_attributed ?? 0)}
              </p>
              <p className="mt-1 text-[0.7rem] text-faint">Empirically counterfactual tested</p>
            </Card>
            <Card className="p-4">
              <p className="label">Retrieval-caused</p>
              <p className="mono mt-1 text-2xl font-bold text-[rgb(var(--good))]">
                {pct(attributionSummary?.retrieval_share ?? 0)}
              </p>
              <p className="mt-1 text-[0.7rem] text-faint">Passed with gold context</p>
            </Card>
            <Card className="p-4">
              <p className="label">Generation-caused</p>
              <p className="mono mt-1 text-2xl font-bold text-[rgb(var(--bad))]">
                {pct(attributionSummary?.generation_share ?? 0)}
              </p>
              <p className="mt-1 text-[0.7rem] text-faint">Failed even with gold context</p>
            </Card>
          </div>

          <Reveal>
            <Card className="p-5">
              <SectionHeader
                icon={FlaskConical}
                title="Counterfactual verdict distribution"
                description="Distribution of failure root causes isolated by oracle and no-context trials."
                actions={
                  <Button
                    variant="primary"
                    icon={FlaskConical}
                    onClick={() => setShowBatchModal(true)}
                  >
                    Run on failed cases
                  </Button>
                }
              />
              <div className="mt-2">
                <VerdictDistributionChart counts={attributionSummary?.verdict_counts} />
              </div>
            </Card>
          </Reveal>

          {/* Cases Table */}
          <Reveal delay={0.06}>
            <Card className="p-5">
              <SectionHeader
                title="Attributed cases"
                description="All failure cases in this experiment that have undergone counterfactual attribution."
              />
              {attributionSummary?.items?.length ? (
                <div className="table-wrap mt-3">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Verdict</th>
                        <th>Confidence</th>
                        <th>Repeats</th>
                        <th>Reason</th>
                        <th>When</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {attributionSummary.items.map((item) => (
                        <tr key={item.id}>
                          <td>
                            <Badge tone={attributionTone(item.verdict)}>
                              {attributionLabel(item.verdict)}
                            </Badge>
                          </td>
                          <td className="mono text-xs">{score(item.confidence)}</td>
                          <td className="mono text-xs">{item.repeats}</td>
                          <td className="text-xs text-muted max-w-md truncate">
                            {item.reason}
                          </td>
                          <td className="whitespace-nowrap text-xs text-faint">
                            {dateTime(item.created_at)}
                          </td>
                          <td>
                            <Link
                              to={`/failures/${item.failure_id}`}
                              className="btn-ghost px-2 py-1 text-xs"
                            >
                              View
                              <ArrowRight className="h-3 w-3" />
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyState
                  compact
                  icon={FlaskConical}
                  title="No attributed cases yet"
                  description="Click 'Run on failed cases' to test failed work units under controlled counterfactual conditions."
                />
              )}
            </Card>
          </Reveal>
        </div>
      ) : (
        /* Overview tab contents */
        <div>

      {/* before/after */}
      {outcome?.ready ? (
        <Reveal>
          <Card className="mb-6 p-5">
            <SectionHeader
              icon={TrendingUp}
              title="Before / after"
              description={`Compared against ${outcome.baseline_experiment_name || 'the baseline experiment'}.`}
              actions={
                <Badge
                  tone={
                    { improvement: 'good', regression: 'bad', mixed: 'fair' }[outcome.verdict?.label] ||
                    'neutral'
                  }
                >
                  {outcome.verdict?.label}
                </Badge>
              }
            />
            <p className="prose-note mb-5 text-sm">{outcome.verdict?.detail}</p>
            <DeltaChart deltas={outcome.metric_deltas} />
            <div className="mt-5 table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Before</th>
                    <th>After</th>
                    <th>Delta</th>
                    <th>95% CI</th>
                    <th>p</th>
                    <th>Significance</th>
                  </tr>
                </thead>
                <tbody>
                  {outcome.metric_deltas?.map((delta) => (
                    <tr key={delta.metric}>
                      <td className="font-medium">{delta.label}</td>
                      <td className="mono">{score(delta.before)}</td>
                      <td className="mono">{score(delta.after)}</td>
                      <td>
                        {delta.delta === null ? (
                          <span className="text-faint">{NA}</span>
                        ) : (
                          <span
                            className={`mono font-semibold ${
                              delta.direction === 'improved'
                                ? 'text-[rgb(var(--ok))]'
                                : delta.direction === 'regressed'
                                  ? 'text-[rgb(var(--bad))]'
                                  : 'text-faint'
                            }`}
                          >
                            {delta.delta > 0 ? '+' : ''}{delta.delta_pp} pp
                          </span>
                        )}
                      </td>
                      <td className="mono text-xs">
                        {delta.ci_low !== null && delta.ci_high !== null
                          ? formatCI(delta.ci_low, delta.ci_high, 2)
                          : NA}
                      </td>
                      <td className="mono text-xs">{formatP(delta.p_value)}</td>
                      <td>
                        {delta.significance === 'significant' ? (
                          <Badge tone="good">significant</Badge>
                        ) : delta.significance === 'underpowered' ? (
                          <div className="flex flex-col items-start gap-0.5">
                            <Badge tone="warn">underpowered</Badge>
                            {delta.required_n ? (
                              <span className="text-[0.68rem] text-[rgb(var(--warn))]">
                                needs ~{delta.required_n} cases
                              </span>
                            ) : null}
                          </div>
                        ) : delta.significance === 'not_significant' ? (
                          <Badge tone="neutral">not significant</Badge>
                        ) : (
                          <span className="text-faint">{NA}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </Reveal>
      ) : outcome && !outcome.ready ? (
        <div className="mb-6">
          <InlineNote tone="warn">{outcome.message}</InlineNote>
        </div>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-2">
        <Reveal>
          <Card className="p-5">
            <SectionHeader icon={Settings2} title="Configuration" description="Frozen at creation — this is what makes the experiment reproducible." />
            <KeyValue
              items={[
                { label: 'Dataset', value: experiment.dataset_name },
                { label: 'Prompt version', value: experiment.prompt_label || NA },
                { label: 'Temperature', value: experiment.temperature },
                { label: 'Max tokens', value: experiment.max_tokens },
                { label: 'RAG', value: experiment.rag_enabled ? `On — ${experiment.rag_collection}` : 'Off' },
                { label: 'Retriever', value: experiment.rag_enabled ? titleCase(experiment.retriever) : NA },
                { label: 'Top K', value: experiment.rag_enabled ? experiment.top_k : NA },
                { label: 'Chunk size / overlap', value: experiment.rag_enabled ? `${experiment.chunk_size} / ${experiment.chunk_overlap}` : NA },
                { label: 'Judge', value: experiment.judge_model ? `${experiment.judge_provider} / ${experiment.judge_model}` : 'Deterministic only' },
                { label: 'Created', value: dateTime(experiment.created_at) },
              ]}
            />
            <div className="mt-5">
              <p className="label mb-2">Models</p>
              <div className="flex flex-wrap gap-1.5">
                {experiment.models?.map((model) => (
                  <Badge key={model.id} tone="accent">{model.provider} / {model.model}</Badge>
                ))}
              </div>
            </div>
            <div className="mt-4">
              <p className="label mb-2">Metrics</p>
              <div className="flex flex-wrap gap-1.5">
                {experiment.metrics?.map((metric) => (
                  <Badge key={metric}>{titleCase(metric)}</Badge>
                ))}
              </div>
            </div>
          </Card>
        </Reveal>

        <Reveal delay={0.06}>
          <Card className="p-5">
            <SectionHeader title="Prompt" />
            <div className="space-y-4">
              <div>
                <p className="label mb-1.5">System prompt</p>
                <p className="whitespace-pre-wrap rounded-xl border border-line bg-overlay/40 p-3 text-xs leading-relaxed text-muted">
                  {experiment.system_prompt}
                </p>
              </div>
              <div>
                <p className="label mb-1.5">Prompt template</p>
                <p className="mono whitespace-pre-wrap rounded-xl border border-line bg-overlay/40 p-3 text-xs leading-relaxed text-muted">
                  {experiment.prompt_template}
                </p>
              </div>
            </div>
          </Card>
        </Reveal>
      </div>

      <div className="mt-6">
        <SectionHeader
          title="Run history"
          actions={
            runs.length > 1 ? (
              <Link to={`/compare?experiment=${experiment.id}`} className="btn-ghost text-xs">
                <GitCompare className="h-3.5 w-3.5" />
                Compare runs
              </Link>
            ) : null
          }
        />
        {runs.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Run</th><th>Status</th><th>Quality</th><th>Failure rate</th><th>Latency</th><th>Duration</th><th>When</th></tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <Link to={`/evaluations/${run.id}`} className="mono text-xs text-accent hover:underline">
                        {run.id}
                      </Link>
                    </td>
                    <td><StatusBadge status={run.status} /></td>
                    <td className="mono">{score(run.summary?.avg_quality_score)}</td>
                    <td className="mono">{pct(run.summary?.failure_rate)}</td>
                    <td className="mono">{ms(run.summary?.avg_latency_ms)}</td>
                    <td className="mono">{run.duration_seconds ? seconds(run.duration_seconds) : NA}</td>
                    <td className="whitespace-nowrap text-xs text-muted">{dateTime(run.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState compact icon={Play} title="This experiment has never been run" />
        )}
      </div>
      </div>
      )}

      {showBatchModal ? (
        <BatchAttributionModal
          experimentId={experiment.id}
          totalFailures={attributionSummary?.total_failures ?? 0}
          onClose={() => setShowBatchModal(false)}
          onCompleted={handleBatchCompleted}
        />
      ) : null}
    </>
  )
}

/** Experiment detail — configuration, run history and before/after outcome. */
import { ArrowLeft, GitBranch, GitCompare, Play, Settings2, TrendingUp } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

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

export default function ExperimentDetail() {
  const { id } = useParams()
  const toast = useToast()
  const { data: experiment, loading, error, refetch } = useApi(() => api.experiment(id), [id])
  const { data: runsPayload } = useApi(() => api.experimentRuns(id), [id])
  const { data: outcome } = useApi(() => api.experimentOutcome(id), [id], {
    enabled: Boolean(experiment?.parent_experiment_id),
  })

  if (loading) return <LoadingState label="Loading experiment…" />
  if (error) return <ErrorState error={error} onRetry={refetch} />
  if (!experiment) return null

  const runs = runsPayload?.items || []

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
    </>
  )
}

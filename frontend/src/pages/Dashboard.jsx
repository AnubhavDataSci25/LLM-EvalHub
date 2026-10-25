/** Dashboard — headline health of every evaluation in the workspace. */
import {
  Activity,
  ArrowRight,
  BookOpen,
  Clock,
  Database,
  FlaskConical,
  Gauge,
  LayoutDashboard,
  Play,
  ShieldAlert,
  Target,
  TrendingUp,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import {
  DistributionChart,
  FailureDistributionChart,
  MetricTrendChart,
  ModelComparisonChart,
} from '../components/charts'
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Reveal,
  ScoreBar,
  SectionHeader,
  StatusBadge,
} from '../components/ui'
import { useApi } from '../hooks'
import { api } from '../lib/api'
import { NA, ms, num, pct, relativeTime, score, scoreTone, seconds } from '../lib/format'

function Kpi({ label, value, hint, icon: Icon, tone = 'neutral', to }) {
  const body = (
    <Card hover={Boolean(to)} className="h-full p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <span className="label">{label}</span>
        {Icon ? <Icon className="h-4 w-4 shrink-0 text-faint" /> : null}
      </div>
      <p className="metric-value">{value}</p>
      {hint ? <p className="prose-note mt-1.5 text-xs">{hint}</p> : null}
    </Card>
  )
  return to ? (
    <Link to={to} className="block h-full outline-none">
      {body}
    </Link>
  ) : (
    body
  )
}

export default function Dashboard() {
  const { data, loading, error, refetch } = useApi(() => api.dashboard(), [])

  if (loading) return <LoadingState label="Loading dashboard…" rows={4} />
  if (error) return <ErrorState error={error} onRetry={refetch} />

  const {
    kpis,
    model_comparison: models = [],
    metric_trend: trend = [],
    failure_distribution: failures = [],
    latency_distribution: latency = [],
    score_distribution: scores = [],
    recent_runs: runs = [],
    experiment_deltas: deltas = [],
    empty,
  } = data || {}

  if (empty) {
    return (
      <>
        <PageHeader
          eyebrow="Overview"
          title="Dashboard"
          description="Nothing has been evaluated yet. Install a benchmark pack or upload a dataset, then run your first evaluation."
        />
        <EmptyState
          icon={LayoutDashboard}
          title="No evaluation data yet"
          description="The fastest path is a benchmark pack: it installs a dataset, indexes its documents for RAG, and gives you recommended metrics and baseline settings."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Link to="/benchmarks" className="btn-primary">
                <BookOpen className="h-4 w-4" />
                Browse benchmark packs
              </Link>
              <Link to="/datasets" className="btn-secondary">
                <Database className="h-4 w-4" />
                Upload a dataset
              </Link>
            </div>
          }
        />
      </>
    )
  }

  const metricsToPlot = ['correctness', 'faithfulness', 'answer_relevance'].filter((m) =>
    models.some((row) => row[m] !== undefined),
  )

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Dashboard"
        description="Every figure here is aggregated from stored evaluation results. Metrics that were never measured show an em dash rather than a zero."
        actions={
          <>
            <Link to="/evaluations/new" className="btn-primary">
              <Play className="h-4 w-4" />
              New evaluation
            </Link>
            <Link to="/compare" className="btn-secondary">
              Compare runs
            </Link>
          </>
        }
      />

      {/* KPIs */}
      <div className="mb-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Reveal>
          <Kpi
            label="Overall quality"
            value={score(kpis.avg_quality_score)}
            hint="Mean of correctness, faithfulness and relevance"
            icon={Target}
          />
        </Reveal>
        <Reveal delay={0.05}>
          <Kpi
            label="Faithfulness"
            value={score(kpis.avg_faithfulness)}
            hint="Share of claims supported by context"
            icon={ShieldAlert}
          />
        </Reveal>
        <Reveal delay={0.1}>
          <Kpi
            label="Average latency"
            value={ms(kpis.avg_latency_ms)}
            hint="Across all completed results"
            icon={Clock}
          />
        </Reveal>
        <Reveal delay={0.15}>
          <Kpi
            label="Failure rate"
            value={pct(kpis.failure_rate)}
            hint={`${num(kpis.failures)} failure(s) · ${num(kpis.diagnosed_failures)} diagnosed`}
            icon={Activity}
            to="/failures"
          />
        </Reveal>
      </div>

      <div className="mb-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Datasets" value={num(kpis.datasets)} hint={`${num(kpis.test_cases)} test cases`} icon={Database} to="/datasets" />
        <Kpi label="Experiments" value={num(kpis.experiments)} hint={`${num(kpis.completed_runs)} completed run(s)`} icon={FlaskConical} to="/experiments" />
        <Kpi label="Results scored" value={num(kpis.results)} hint={`Error rate ${pct(kpis.error_rate)}`} icon={Gauge} />
        <Kpi label="RAG documents" value={num(kpis.documents)} hint="Indexed for retrieval" icon={BookOpen} to="/documents" />
      </div>

      {/* charts */}
      <div className="mb-8 grid gap-5 xl:grid-cols-2">
        <Reveal>
          <Card className="p-5">
            <SectionHeader
              icon={Target}
              title="Model comparison"
              description="Mean scores per model across every evaluated case."
            />
            <ModelComparisonChart rows={models} metrics={metricsToPlot} />
          </Card>
        </Reveal>

        <Reveal delay={0.06}>
          <Card className="p-5">
            <SectionHeader
              icon={TrendingUp}
              title="Metric trend"
              description="How quality has moved across successive runs."
            />
            <MetricTrendChart points={trend} metrics={['correctness', 'faithfulness', 'answer_relevance']} />
          </Card>
        </Reveal>

        <Reveal>
          <Card className="p-5">
            <SectionHeader
              icon={Activity}
              title="Failure distribution"
              description="What actually goes wrong, by category."
              actions={
                <Link to="/failures" className="btn-ghost text-xs">
                  Inspect
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              }
            />
            <FailureDistributionChart items={failures} />
          </Card>
        </Reveal>

        <Reveal delay={0.06}>
          <Card className="p-5">
            <SectionHeader icon={Clock} title="Latency distribution" description="Response-time spread across all results." />
            <DistributionChart data={latency} height={130} />
            <div className="mt-4">
              <p className="label mb-2">Composite score distribution</p>
              <DistributionChart data={scores} height={130} colour="#4A562C" />
            </div>
          </Card>
        </Reveal>
      </div>

      {/* improvement deltas */}
      {deltas.length ? (
        <Reveal>
          <Card className="mb-8 p-5">
            <SectionHeader
              icon={TrendingUp}
              title="Recent improvement attempts"
              description="Follow-up experiments compared against the baseline they branched from."
            />
            <div className="space-y-3">
              {deltas.map((delta) => (
                <Link
                  key={delta.experiment_id}
                  to={`/experiments/${delta.experiment_id}`}
                  className="block rounded-xl border border-line bg-surface p-4 transition-all duration-200
                             ease-spring hover:border-accent/40 hover:shadow-card"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-ink">{delta.experiment_name}</p>
                      {delta.change_summary ? (
                        <p className="prose-note mt-1 text-xs">{delta.change_summary}</p>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Badge
                        tone={
                          { improvement: 'good', regression: 'bad', mixed: 'fair' }[
                            delta.verdict?.label
                          ] || 'neutral'
                        }
                      >
                        {delta.verdict?.label || 'unknown'}
                      </Badge>
                      {!delta.metric_deltas?.some((d) => d.significance === 'significant') ? (
                        <Badge tone="neutral">inconclusive</Badge>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
                    {delta.metric_deltas
                      ?.filter((d) => d.delta !== null)
                      .slice(0, 4)
                      .map((d) => (
                        <span key={d.metric} className="text-xs text-muted">
                          {d.label}{' '}
                          <span
                            className={`mono font-semibold ${
                              d.direction === 'improved'
                                ? 'text-[rgb(var(--ok))]'
                                : d.direction === 'regressed'
                                  ? 'text-[rgb(var(--bad))]'
                                  : 'text-faint'
                            }`}
                          >
                            {d.delta > 0 ? '+' : ''}
                            {d.delta_pp} pp
                          </span>
                        </span>
                      ))}
                  </div>
                </Link>
              ))}
            </div>
          </Card>
        </Reveal>
      ) : null}

      {/* recent runs */}
      <Reveal>
        <SectionHeader
          icon={FlaskConical}
          title="Recent runs"
          actions={
            <Link to="/experiments" className="btn-ghost text-xs">
              All experiments
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          }
        />
        {runs.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Experiment</th>
                  <th>Status</th>
                  <th>Quality</th>
                  <th>Failure rate</th>
                  <th>Latency</th>
                  <th>Duration</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <Link
                        to={`/evaluations/${run.id}`}
                        className="font-semibold text-ink hover:text-accent"
                      >
                        {run.experiment_name || run.id}
                      </Link>
                      <p className="mono mt-0.5 text-xs text-faint">
                        {run.models?.length ? run.models.join(', ') : `${run.total_units} unit(s)`}
                      </p>
                    </td>
                    <td>
                      <StatusBadge status={run.status} />
                    </td>
                    <td>
                      <ScoreBar value={run.quality} tone={scoreTone(run.quality)} />
                    </td>
                    <td className="mono">{pct(run.failure_rate)}</td>
                    <td className="mono">{ms(run.avg_latency_ms)}</td>
                    <td className="mono">{run.duration_seconds ? seconds(run.duration_seconds) : NA}</td>
                    <td className="whitespace-nowrap text-xs text-muted">
                      {relativeTime(run.created_at)}
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
            title="No runs yet"
            description="Start an evaluation to populate this table."
          />
        )}
      </Reveal>
    </>
  )
}

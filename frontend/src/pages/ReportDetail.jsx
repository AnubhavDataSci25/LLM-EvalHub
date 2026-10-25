/** Report detail — the full web report, section by section. */
import { ArrowLeft, Download, FileText, Lightbulb, ListChecks, Search } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { LatencyChart, ModelComparisonChart } from '../components/charts'
import {
  Badge,
  Card,
  ErrorState,
  KeyValue,
  LoadingState,
  PageHeader,
  Reveal,
  ScoreBar,
  SectionHeader,
} from '../components/ui'
import { useApi } from '../hooks'
import { api } from '../lib/api'
import { NA, dateTime, ms, num, pct, score, scoreTone, seconds, titleCase, truncate } from '../lib/format'

export default function ReportDetail() {
  const { id } = useParams()
  const { data: report, loading, error, refetch } = useApi(() => api.report(id), [id])

  if (loading) return <LoadingState label="Loading report…" />
  if (error) return <ErrorState error={error} onRetry={refetch} />
  if (!report) return null

  const c = report.content || {}
  const metrics = c.metrics?.per_metric || {}
  const models = c.models_tested || []
  const metricKeys = c.experiment?.metrics?.filter((m) => m !== 'latency') || []

  return (
    <>
      <Link to="/reports" className="btn-ghost mb-4 -ml-2 px-2 text-sm">
        <ArrowLeft className="h-4 w-4" />
        All reports
      </Link>

      <PageHeader
        eyebrow={titleCase(report.kind)}
        title={report.title}
        description={`Generated ${dateTime(report.created_at)} from stored results — no provider was re-called.`}
        actions={
          <>
            <a href={api.exportUrl(report.id, 'csv')} className="btn-secondary" download>
              <Download className="h-4 w-4" />CSV
            </a>
            <a href={api.exportUrl(report.id, 'json')} className="btn-primary" download>
              <Download className="h-4 w-4" />JSON
            </a>
          </>
        }
      />

      {/* findings */}
      {c.findings?.length ? (
        <Reveal>
          <Card className="mb-6 p-5">
            <SectionHeader icon={Search} title="Key findings" description="Derived from the measured results in this run." />
            <ul className="space-y-2.5">
              {c.findings.map((finding, index) => (
                <li key={index} className="flex gap-3 text-sm leading-relaxed text-ink">
                  <span className="mono mt-0.5 text-xs text-accent">{String(index + 1).padStart(2, '0')}</span>
                  {finding}
                </li>
              ))}
            </ul>
          </Card>
        </Reveal>
      ) : null}

      {/* summary numbers */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ['Quality score', score(c.metrics?.overall?.avg_quality_score)],
          ['Failure rate', pct(c.metrics?.overall?.failure_rate)],
          ['Average latency', ms(c.latency?.avg_ms)],
          ['Duration', c.run?.duration_seconds ? seconds(c.run.duration_seconds) : NA],
        ].map(([label, value]) => (
          <Card key={label} className="p-5">
            <p className="label">{label}</p>
            <p className="metric-value mt-2">{value}</p>
          </Card>
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Reveal>
          <Card className="p-5">
            <SectionHeader title="Experiment" />
            <KeyValue
              items={[
                { label: 'Name', value: c.experiment?.name },
                { label: 'Prompt version', value: c.experiment?.prompt_label || NA },
                { label: 'Temperature', value: c.experiment?.temperature },
                { label: 'Max tokens', value: c.experiment?.max_tokens },
                { label: 'RAG', value: c.rag?.enabled ? `On — ${c.rag.retriever}, top_k ${c.rag.top_k}` : 'Off' },
                { label: 'Judge', value: c.experiment?.judge?.model || 'Deterministic only' },
              ]}
            />
          </Card>
        </Reveal>

        <Reveal delay={0.06}>
          <Card className="p-5">
            <SectionHeader title="Dataset" />
            <KeyValue
              items={[
                { label: 'Name', value: c.dataset?.name },
                { label: 'Test cases', value: num(c.dataset?.case_count) },
                { label: 'With expected answers', value: num(c.dataset?.with_ground_truth) },
                { label: 'With inline context', value: num(c.dataset?.with_context) },
                { label: 'Domain', value: c.dataset?.domain ? titleCase(c.dataset.domain) : NA },
                { label: 'Benchmark pack', value: c.dataset?.benchmark_pack_key || NA },
              ]}
            />
          </Card>
        </Reveal>
      </div>

      {/* models */}
      <Reveal>
        <Card className="mt-5 p-5">
          <SectionHeader title="Models tested" description="Identical inputs across every model." />
          <ModelComparisonChart rows={models} metrics={metricKeys} />
          <div className="mt-5 table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Model</th><th>Cases</th>
                  {metricKeys.map((m) => <th key={m}>{titleCase(m)}</th>)}
                  <th>Latency</th><th>Failure rate</th>
                </tr>
              </thead>
              <tbody>
                {models.map((row) => (
                  <tr key={row.key}>
                    <td>
                      <p className="font-semibold text-ink">{row.label}</p>
                      <p className="mono text-xs text-faint">{row.provider}</p>
                    </td>
                    <td className="mono">{row.cases}</td>
                    {metricKeys.map((m) => (
                      <td key={m}>
                        {row.metrics?.[m]?.mean != null ? (
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
        </Card>
      </Reveal>

      <Reveal>
        <Card className="mt-5 p-5">
          <SectionHeader title="Latency" />
          <LatencyChart rows={models} />
        </Card>
      </Reveal>

      {/* metric detail */}
      <Reveal>
        <Card className="mt-5 p-5">
          <SectionHeader title="Metric detail" description="Sample size and evaluator kind for every metric." />
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Metric</th><th>Mean</th><th>Min</th><th>Max</th><th>Sample</th><th>Kind</th></tr>
              </thead>
              <tbody>
                {Object.entries(metrics).map(([metric, block]) => (
                  <tr key={metric}>
                    <td className="font-medium">{titleCase(metric)}</td>
                    <td>
                      {block.mean != null ? (
                        <ScoreBar value={block.mean} tone={scoreTone(block.mean)} />
                      ) : (
                        <Badge tone="neutral">unavailable</Badge>
                      )}
                    </td>
                    <td className="mono">{score(block.min)}</td>
                    <td className="mono">{score(block.max)}</td>
                    <td className="mono">{block.sample_size ?? 0}</td>
                    <td className="text-xs text-muted">
                      {block.kinds?.length ? block.kinds.map(titleCase).join(', ') : NA}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </Reveal>

      {/* RAG */}
      {c.rag?.enabled ? (
        <Reveal>
          <Card className="mt-5 p-5">
            <SectionHeader title="RAG performance" />
            <KeyValue
              items={[
                { label: 'Collection', value: c.rag.collection },
                { label: 'Retriever', value: titleCase(c.rag.retriever) },
                { label: 'Top K', value: c.rag.top_k },
                { label: 'Chunk size / overlap', value: `${c.rag.chunk_size} / ${c.rag.chunk_overlap}` },
                { label: 'Context precision', value: score(c.rag.context_precision) },
                { label: 'Context recall', value: score(c.rag.context_recall) },
                { label: 'Avg chunks retrieved', value: c.rag.avg_chunks_retrieved },
                { label: 'Empty retrievals', value: num(c.rag.empty_retrievals) },
              ]}
            />
          </Card>
        </Reveal>
      ) : null}

      {/* recommendation */}
      {c.recommendation && !c.recommendation.unavailable_reason ? (
        <Reveal>
          <Card className="mt-5 p-5">
            <SectionHeader
              icon={Lightbulb}
              title={`Recommendation: ${c.recommendation.recommended_provider} / ${c.recommendation.recommended_model}`}
              description={c.recommendation.rationale}
            />
            <div className="grid gap-5 lg:grid-cols-2">
              <div>
                <p className="label mb-2">Evidence</p>
                <ul className="space-y-1.5">
                  {c.recommendation.evidence?.map((item, index) => (
                    <li key={index} className="text-xs leading-relaxed text-muted">• {item}</li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="label mb-2">Caveats</p>
                <ul className="space-y-1.5">
                  {c.recommendation.caveats?.map((item, index) => (
                    <li key={index} className="text-xs leading-relaxed text-muted">• {item}</li>
                  ))}
                </ul>
              </div>
            </div>
          </Card>
        </Reveal>
      ) : null}

      {/* failures */}
      {c.failures?.cases?.length ? (
        <Reveal>
          <Card className="mt-5 p-5">
            <SectionHeader
              title={`Failed cases (${c.failures.total})`}
              description={`Failure rate ${pct(c.failures.rate)}. Breakdown: ${Object.entries(c.failures.breakdown || {})
                .map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`)
                .join(', ')}`}
            />
            <div className="table-wrap max-h-[50vh] overflow-y-auto">
              <table className="table">
                <thead>
                  <tr><th>Type</th><th>Model</th><th>Question</th><th>Generated</th><th>Diagnosis</th></tr>
                </thead>
                <tbody>
                  {c.failures.cases.map((failure) => (
                    <tr key={failure.failure_id}>
                      <td><Badge tone="poor">{failure.failure_type?.replace(/_/g, ' ')}</Badge></td>
                      <td className="mono text-xs">{failure.model}</td>
                      <td className="max-w-xs text-xs">{truncate(failure.question, 80)}</td>
                      <td className="max-w-xs text-xs text-muted">{truncate(failure.generated || '—', 80)}</td>
                      <td className="max-w-xs text-xs text-muted">
                        {failure.diagnosis ? truncate(failure.diagnosis.root_cause, 90) : <span className="text-faint">not diagnosed</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </Reveal>
      ) : null}

      {/* next steps */}
      {c.next_steps?.length ? (
        <Reveal>
          <Card className="mt-5 p-5">
            <SectionHeader icon={ListChecks} title="Next steps" description="Derived from the failure pattern in this run." />
            <ul className="space-y-2.5">
              {c.next_steps.map((step, index) => (
                <li key={index} className="flex gap-3 text-sm leading-relaxed text-ink">
                  <span className="mono mt-0.5 text-xs text-accent">→</span>
                  {step}
                </li>
              ))}
            </ul>
          </Card>
        </Reveal>
      ) : null}
    </>
  )
}

/** Compare — pick runs, see metric deltas and the configuration diff that caused them. */
import { GitCompare, Scale } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { DeltaChart, ModelComparisonChart } from '../components/charts'
import {
  Badge,
  Button,
  Card,
  Checkbox,
  EmptyState,
  ErrorState,
  InlineNote,
  LoadingState,
  PageHeader,
  Reveal,
  SectionHeader,
  Select,
} from '../components/ui'
import { useApi } from '../hooks'
import { api } from '../lib/api'
import { NA, dateTime, formatCI, formatP, ms, num, pct, score, seconds } from '../lib/format'

export default function Compare() {
  const [params] = useSearchParams()
  const [selectedRuns, setSelectedRuns] = useState([])
  const [baseline, setBaseline] = useState('')
  const [comparison, setComparison] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const { data: runsPayload, loading } = useApi(
    () => api.runs({ status: 'completed', limit: 50 }),
    [],
  )
  const runs = runsPayload?.items || []

  // preselect from the query string
  useEffect(() => {
    const runParam = params.get('run')
    if (runParam && !selectedRuns.includes(runParam)) {
      setSelectedRuns((current) => [...new Set([runParam, ...current])])
      setBaseline((current) => current || runParam)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params])

  const toggle = (runId) =>
    setSelectedRuns((current) =>
      current.includes(runId) ? current.filter((r) => r !== runId) : [...current, runId],
    )

  const compare = async () => {
    if (selectedRuns.length < 2) {
      setError({ message: 'Select at least two completed runs.' })
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = await api.compareRuns({
        run_ids: selectedRuns,
        baseline_run_id: baseline || selectedRuns[0],
      })
      setComparison(result)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Analysis"
        title="Compare runs"
        description="Pick a baseline and one or more runs to compare against it. Deltas are shown per metric with the sample size behind each side, and the configuration diff shows which change could account for the movement."
        actions={
          <Button variant="primary" icon={GitCompare} loading={busy} onClick={compare}>
            Compare {selectedRuns.length} run(s)
          </Button>
        }
      />

      {loading ? (
        <LoadingState label="Loading runs…" />
      ) : runs.length < 2 ? (
        <EmptyState
          icon={GitCompare}
          title="At least two completed runs are needed"
          description="Run the same dataset with a changed prompt, model or retrieval setting, then come back to see whether it helped."
        />
      ) : (
        <>
          <Card className="mb-6 p-5">
            <SectionHeader title="Select runs" description="Completed runs only — partial results would make a comparison misleading." />
            <div className="mb-4 max-w-sm">
              <p className="label mb-1.5">Baseline</p>
              <Select
                value={baseline}
                onChange={(e) => setBaseline(e.target.value)}
                placeholder="First selected run"
                options={runs
                  .filter((r) => selectedRuns.includes(r.id))
                  .map((r) => ({ value: r.id, label: `${r.experiment_name} — ${dateTime(r.created_at)}` }))}
              />
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              {runs.map((run) => (
                <Checkbox
                  key={run.id}
                  checked={selectedRuns.includes(run.id)}
                  onChange={() => toggle(run.id)}
                  label={run.experiment_name || run.id}
                  description={`${run.dataset_name || 'dataset'} · quality ${score(run.summary?.avg_quality_score)} · ${dateTime(run.created_at)}`}
                />
              ))}
            </div>
            {error ? <div className="mt-4"><ErrorState compact error={error} /></div> : null}
          </Card>

          {comparison ? (
            <>
              {comparison.warnings?.map((warning, index) => (
                <div key={index} className="mb-4">
                  <InlineNote tone="warn">{warning}</InlineNote>
                </div>
              ))}

              <div className="mb-5">
                <InlineNote tone="info">
                  <p className="font-semibold text-ink">How to read statistical uncertainty</p>
                  <p className="mt-0.5 text-xs text-muted">
                    Every metric delta is evaluated using paired bootstrap resampling (<span className="font-medium text-ink">95% CI</span>) and a paired sign-flip permutation test (<span className="font-medium text-ink">p-value</span>).
                    A movement is marked <Badge tone="good" className="mx-1">significant</Badge> only if the CI excludes 0 and p &lt; 0.05. Small samples or low-power comparisons are marked <Badge tone="warn" className="mx-1">underpowered</Badge> with estimated cases needed to detect the observed effect size.
                  </p>
                </InlineNote>
              </div>

              <Reveal>
                <Card className="mb-6 p-5">
                  <SectionHeader icon={Scale} title="Run summary" />
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Run</th><th>Quality</th><th>Failure rate</th><th>Latency</th>
                          <th>Cases</th><th>Duration</th><th>When</th>
                        </tr>
                      </thead>
                      <tbody>
                        {comparison.runs.map((run) => (
                          <tr key={run.run_id} className={run.run_id === comparison.baseline_run_id ? 'bg-accent-soft/40' : ''}>
                            <td>
                              <p className="font-semibold text-ink">{run.experiment_name}</p>
                              {run.run_id === comparison.baseline_run_id ? (
                                <Badge tone="accent" className="mt-1">baseline</Badge>
                              ) : null}
                            </td>
                            <td className="mono">{score(run.summary?.avg_quality_score)}</td>
                            <td className="mono">{pct(run.summary?.failure_rate)}</td>
                            <td className="mono">{ms(run.summary?.avg_latency_ms)}</td>
                            <td className="mono">{num(run.case_count)}</td>
                            <td className="mono">{run.duration_seconds ? seconds(run.duration_seconds) : NA}</td>
                            <td className="whitespace-nowrap text-xs text-muted">{dateTime(run.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              </Reveal>

              {comparison.comparisons.map((block, index) => (
                <Reveal key={block.run_id} delay={index * 0.06}>
                  <Card className="mb-5 p-5">
                    <SectionHeader
                      title={block.experiment_name || block.run_id}
                      description={block.verdict?.detail}
                      actions={
                        <Badge
                          tone={
                            { improvement: 'good', regression: 'bad', mixed: 'fair' }[block.verdict?.label] ||
                            'neutral'
                          }
                        >
                          {block.verdict?.label}
                        </Badge>
                      }
                    />

                    <DeltaChart deltas={block.metric_deltas} />

                    <div className="mt-5 grid gap-5 lg:grid-cols-2">
                      <div className="table-wrap">
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
                            {block.metric_deltas.map((delta) => (
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

                      <div>
                        <p className="label mb-2">Configuration differences</p>
                        {block.config_diff?.length ? (
                          <div className="space-y-2">
                            {block.config_diff.map((diff) => (
                              <div key={diff.field} className="rounded-xl border border-line bg-overlay/50 p-3">
                                <p className="text-xs font-semibold text-ink">{diff.label}</p>
                                <div className="mt-1.5 grid gap-1 text-[0.7rem]">
                                  <p className="text-muted">
                                    <span className="text-faint">before: </span>
                                    {String(diff.before)}
                                  </p>
                                  <p className="text-accent">
                                    <span className="text-faint">after: </span>
                                    {String(diff.after)}
                                  </p>
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="prose-note text-xs">
                            These runs share the same experiment configuration, so any difference comes
                            from provider non-determinism rather than a change you made.
                          </p>
                        )}
                      </div>
                    </div>
                  </Card>
                </Reveal>
              ))}
            </>
          ) : null}
        </>
      )}
    </>
  )
}

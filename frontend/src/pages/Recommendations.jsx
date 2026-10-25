/** Model recommendation — transparent, weighted, constrained, and scoped to real data. */
import { AlertTriangle, Info, Lightbulb, Scale, Sparkles } from 'lucide-react'
import { useState } from 'react'

import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  InlineNote,
  Input,
  LoadingState,
  PageHeader,
  Reveal,
  ScoreBar,
  SectionHeader,
  Select,
  useToast,
} from '../components/ui'
import { useApi } from '../hooks'
import { api } from '../lib/api'
import { NA, ms, num, pct, score, scoreTone, titleCase } from '../lib/format'

function RecommendationCard({ recommendation }) {
  const ranked = (recommendation.candidates || []).filter((c) => c.rank)
  const excluded = (recommendation.candidates || []).filter((c) => c.excluded_reason)
  const winner = ranked[0]

  return (
    <Card className="p-5">
      <SectionHeader
        icon={Sparkles}
        title={
          recommendation.recommended_model
            ? `Recommended: ${recommendation.recommended_provider} / ${recommendation.recommended_model}`
            : 'No model satisfied the constraints'
        }
        description={recommendation.rationale}
        actions={
          recommendation.recommended_score ? (
            <Badge tone="accent">score {score(recommendation.recommended_score)}</Badge>
          ) : null
        }
      />

      {recommendation.scope?.top_two_tied ? (
        <div className="mb-5">
          <InlineNote tone="warn">
            <span className="font-semibold text-ink">Statistically Tied:</span>{' '}
            {recommendation.caveats?.find((c) => c.includes('statistically indistinguishable')) ||
              'The top two models are statistically indistinguishable on this evaluated data.'}
          </InlineNote>
        </div>
      ) : null}

      {/* judge calibration caveat */}
      {(() => {
        const calCaveat = recommendation.caveats?.find(
          (c) =>
            c.toLowerCase().includes('judge calibration') ||
            c.toLowerCase().includes('uncalibrated') ||
            c.toLowerCase().includes('weak evidence'),
        )
        if (!calCaveat) return null
        const isWarn = calCaveat.includes('uncalibrated') || calCaveat.includes('weak')
        return (
          <div className="mb-5">
            <InlineNote tone={isWarn ? 'warn' : 'info'}>
              <span className="font-semibold text-ink">Judge Reliability:</span> {calCaveat}
            </InlineNote>
          </div>
        )
      })()}

      {/* weights */}
      <div className="mb-5">
        <p className="label mb-2">Weighting ({recommendation.profile})</p>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(recommendation.weights || {}).map(([metric, weight]) => (
            <Badge key={metric}>
              {titleCase(metric)} · {(weight * 100).toFixed(0)}%
            </Badge>
          ))}
        </div>
      </div>

      {/* score breakdown */}
      {winner?.score_breakdown ? (
        <div className="mb-5">
          <p className="label mb-2">How the winning score was built</p>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Metric</th><th>Measured</th><th>Normalised</th><th>Weight</th><th>Contribution</th></tr>
              </thead>
              <tbody>
                {Object.entries(winner.score_breakdown).map(([metric, entry]) => (
                  <tr key={metric}>
                    <td className="font-medium">{titleCase(metric)}</td>
                    <td className="mono">{metric === 'latency' ? ms(entry.raw) : score(entry.raw)}</td>
                    <td className="mono">{score(entry.normalized)}</td>
                    <td className="mono">{(entry.weight * 100).toFixed(0)}%</td>
                    <td className="mono">{score(entry.contribution, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {/* candidates */}
      {ranked.length ? (
        <div className="mb-5">
          <p className="label mb-2">Ranked candidates</p>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>#</th><th>Model</th><th>Weighted score</th><th>Latency</th><th>Failure rate</th><th>Sample</th></tr>
              </thead>
              <tbody>
                {ranked.map((candidate) => (
                  <tr key={candidate.key}>
                    <td className="mono">{candidate.rank}</td>
                    <td>
                      <p className="font-semibold text-ink">{candidate.label}</p>
                      <p className="mono text-xs text-faint">{candidate.provider}</p>
                    </td>
                    <td><ScoreBar value={candidate.weighted_score} tone={scoreTone(candidate.weighted_score)} /></td>
                    <td className="mono">{ms(candidate.avg_latency_ms)}</td>
                    <td className="mono">{pct(candidate.failure_rate)}</td>
                    <td className="mono text-xs">{candidate.sample_size}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {excluded.length ? (
        <div className="mb-5">
          <p className="label mb-2">Excluded candidates</p>
          <div className="space-y-1.5">
            {excluded.map((candidate) => (
              <div key={candidate.key} className="rounded-lg bg-overlay/50 px-3 py-2">
                <p className="text-xs font-semibold text-ink">{candidate.label}</p>
                <p className="prose-note text-[0.7rem]">{candidate.excluded_reason}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-2">
        <div>
          <p className="label mb-2">Evidence</p>
          <ul className="space-y-1.5">
            {recommendation.evidence?.map((item, index) => (
              <li key={index} className="flex gap-2 text-xs leading-relaxed text-muted">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                {item}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="label mb-2">Caveats</p>
          <ul className="space-y-1.5">
            {recommendation.caveats?.map((item, index) => (
              <li key={index} className="flex gap-2 text-xs leading-relaxed text-muted">
                <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-[rgb(var(--warn))]" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  )
}

export default function Recommendations() {
  const toast = useToast()
  const [form, setForm] = useState({
    useCase: 'general',
    profile: 'balanced',
    runId: '',
    maxLatency: '',
    minFaithfulness: '',
    minSampleSize: 5,
  })
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const { data: profilesPayload } = useApi(() => api.profiles(), [])
  const { data: runsPayload, loading } = useApi(() => api.runs({ status: 'completed', limit: 50 }), [])
  const { data: history, refetch: refetchHistory } = useApi(() => api.recommendations(), [])

  const runs = runsPayload?.items || []
  const profiles = profilesPayload?.profiles || []
  const activeProfile = profiles.find((p) => p.key === form.profile)

  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }))

  const generate = async () => {
    setBusy(true)
    setError(null)
    try {
      const payload = {
        use_case: form.useCase,
        profile: form.profile,
        run_ids: form.runId ? [form.runId] : [],
        min_sample_size: Number(form.minSampleSize) || 1,
      }
      if (form.maxLatency) payload.max_latency_ms = Number(form.maxLatency)
      if (form.minFaithfulness) payload.min_faithfulness = Number(form.minFaithfulness)
      const recommendation = await api.createRecommendation(payload)
      setResult(recommendation)
      refetchHistory()
      toast.success('Recommendation generated from measured results.')
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
        title="Model recommendation"
        description="A weighted ranking built only from results measured in this workspace. Every score is decomposed into its contributions, and the caveats are part of the output rather than a footnote."
      />

      <InlineNote tone="info" icon={Info}>
        This is decision support scoped to your dataset, metrics and constraints. It is not a general
        claim that one model is better than another — a different dataset can and often does reorder
        the ranking.
      </InlineNote>

      <div className="mt-6 grid gap-5 lg:grid-cols-[20rem_minmax(0,1fr)]">
        <Card className="h-fit p-5">
          <SectionHeader icon={Scale} title="Criteria" />
          <div className="space-y-4">
            <Field label="Use case" hint="Recorded with the recommendation for context.">
              <Input value={form.useCase} onChange={(e) => set('useCase', e.target.value)} placeholder="rag_qa" />
            </Field>

            <Field label="Priority profile">
              <Select
                value={form.profile}
                onChange={(e) => set('profile', e.target.value)}
                options={profiles.map((p) => ({ value: p.key, label: titleCase(p.key) }))}
              />
            </Field>
            {activeProfile ? (
              <p className="prose-note -mt-2 text-xs">{activeProfile.description}</p>
            ) : null}

            <Field label="Scope" hint="Leave empty to use the most recent completed runs.">
              <Select
                value={form.runId}
                onChange={(e) => set('runId', e.target.value)}
                placeholder="All recent runs"
                options={runs.map((r) => ({ value: r.id, label: r.experiment_name || r.id }))}
              />
            </Field>

            <div className="border-t border-line pt-4">
              <p className="label mb-3">Hard constraints</p>
              <div className="space-y-3">
                <Field label="Max average latency (ms)">
                  <Input
                    type="number"
                    value={form.maxLatency}
                    onChange={(e) => set('maxLatency', e.target.value)}
                    placeholder="no ceiling"
                  />
                </Field>
                <Field label="Min faithfulness">
                  <Input
                    type="number"
                    step={0.05}
                    min={0}
                    max={1}
                    value={form.minFaithfulness}
                    onChange={(e) => set('minFaithfulness', e.target.value)}
                    placeholder="no floor"
                  />
                </Field>
                <Field label="Min scored cases" hint="Candidates below this are excluded and reported.">
                  <Input
                    type="number"
                    min={1}
                    value={form.minSampleSize}
                    onChange={(e) => set('minSampleSize', e.target.value)}
                  />
                </Field>
              </div>
            </div>

            {error ? <ErrorState compact error={error} /> : null}

            <Button variant="primary" icon={Lightbulb} className="w-full" loading={busy} onClick={generate}>
              Generate recommendation
            </Button>
          </div>
        </Card>

        <div className="space-y-5">
          {loading ? (
            <LoadingState label="Loading runs…" />
          ) : runs.length === 0 ? (
            <EmptyState
              icon={Lightbulb}
              title="No completed runs to analyse"
              description="Recommendations are only made from measured results. Run an evaluation with at least two models first."
            />
          ) : result ? (
            <Reveal><RecommendationCard recommendation={result} /></Reveal>
          ) : (
            <EmptyState
              compact
              icon={Sparkles}
              title="Set your criteria and generate"
              description="Choose a priority profile and any hard constraints, then generate a ranking from the evaluation evidence."
            />
          )}

          {history?.items?.length ? (
            <Card className="p-5">
              <SectionHeader title="Earlier recommendations" />
              <div className="space-y-2">
                {history.items.slice(0, 6).map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setResult(item)}
                    className="flex w-full items-center justify-between gap-3 rounded-xl border border-line
                               bg-surface px-4 py-3 text-left transition-colors hover:border-accent/40"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-ink">
                        {item.recommended_model || 'No candidate met the constraints'}
                      </p>
                      <p className="prose-note text-xs">
                        {titleCase(item.profile)} · {item.use_case} · {item.sample_size} case(s)
                      </p>
                    </div>
                    {item.recommended_score ? (
                      <Badge tone="accent">{score(item.recommended_score)}</Badge>
                    ) : null}
                  </button>
                ))}
              </div>
            </Card>
          ) : null}
        </div>
      </div>
    </>
  )
}

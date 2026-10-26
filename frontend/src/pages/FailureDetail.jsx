/**
 * Failure detail — full evidence, AI diagnosis and the improvement loop entry point.
 *
 * This is the page the whole product is built around: it shows what was asked,
 * what came back, what was retrieved, what the scores were, why it failed, and
 * what to change — then creates the follow-up experiment that tests the change.
 */
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  FlaskConical,
  HelpCircle,
  Lightbulb,
  Sparkles,
  Split,
  Stethoscope,
  XCircle,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  Badge,
  Button,
  Card,
  ErrorState,
  InlineNote,
  KeyValue,
  LoadingState,
  Modal,
  PageHeader,
  Reveal,
  ScoreBar,
  SectionHeader,
  useToast,
} from '../components/ui'
import { useApi } from '../hooks'
import { api } from '../lib/api'
import {
  NA,
  attributionLabel,
  attributionTone,
  ms,
  pct,
  score,
  scoreTone,
  titleCase,
} from '../lib/format'

const SEVERITY_TONES = { critical: 'bad', high: 'bad', medium: 'poor', low: 'fair' }

function AttributionModal({ failure, onClose, onAttributed }) {
  const [repeats, setRepeats] = useState(1)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const estimatedCalls = repeats * 2

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      const att = await api.runFailureAttribution(failure.id, { repeats })
      onAttributed(att)
      onClose()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Run counterfactual failure attribution"
      description="Determine empirically whether this failure was caused by retrieval or by generation by testing under controlled counterfactual conditions."
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" icon={FlaskConical} loading={busy} onClick={run}>
            {busy ? 'Running trials…' : `Confirm and run (${estimatedCalls} call${estimatedCalls > 1 ? 's' : ''})`}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="rounded-xl border border-line bg-overlay/50 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink">Controlled conditions</p>
          <ul className="mt-2 space-y-1.5 text-xs text-muted">
            <li className="flex items-start gap-2">
              <span className="mono font-semibold text-ink">ORACLE_CONTEXT:</span>
              Replaces retrieved context with gold passage (from test case). If the model passes, retrieval was the bottleneck.
            </li>
            <li className="flex items-start gap-2">
              <span className="mono font-semibold text-ink">NO_CONTEXT:</span>
              Removes context completely. Tests whether the model answers from parametric memory or ignores context.
            </li>
          </ul>
        </div>

        <div>
          <label className="label mb-1.5 block">Repeats per condition (trial count)</label>
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
          <p className="prose-note mt-1.5 text-[0.75rem]">
            {repeats === 1
              ? 'Single trial gives instant results; repeats recommended if output is stochastic.'
              : `Runs ${repeats} trials per condition to measure pass rates across generation variance.`}
          </p>
        </div>

        <div className="rounded-lg border border-line bg-surface p-3 text-xs">
          <div className="flex items-center justify-between font-medium text-ink">
            <span>Estimated provider calls:</span>
            <span className="mono text-sm font-bold text-accent">{estimatedCalls}</span>
          </div>
          <p className="mt-1 text-[0.7rem] text-faint">
            2 conditions × {repeats} trial(s). The original stored answer is reused and does not consume provider calls.
          </p>
        </div>

        {error ? <ErrorState compact error={error} /> : null}
      </div>
    </Modal>
  )
}

function ConditionCard({ title, subtitle, answer, scores, passed, error }) {
  return (
    <div
      className={`flex flex-col justify-between rounded-xl border p-4 ${
        passed ? 'border-[rgb(var(--good))]/40 bg-[rgb(var(--good))]/5' : 'border-line bg-surface'
      }`}
    >
      <div>
        <div className="mb-2 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-ink">{title}</p>
            <p className="text-[0.7rem] text-faint">{subtitle}</p>
          </div>
          {error ? (
            <Badge tone="bad">error</Badge>
          ) : passed ? (
            <Badge tone="good" icon={CheckCircle2}>
              Pass
            </Badge>
          ) : (
            <Badge tone="bad" icon={XCircle}>
              Fail
            </Badge>
          )}
        </div>
        <div className="mt-2 text-xs">
          <p className="label mb-1 text-[0.68rem]">Generated answer</p>
          {error ? (
            <p className="rounded bg-bad/10 p-2 font-mono text-xs text-bad">{error}</p>
          ) : answer ? (
            <p className="max-h-36 overflow-y-auto whitespace-pre-wrap rounded-lg border border-line bg-overlay/40 p-2.5 leading-relaxed text-ink">
              {answer}
            </p>
          ) : (
            <p className="italic text-faint">No text generated</p>
          )}
        </div>
      </div>
      {scores && Object.keys(scores).length > 0 ? (
        <div className="mt-3 space-y-1 border-t border-line pt-2.5">
          {Object.entries(scores).map(([metric, val]) => (
            <div key={metric} className="flex items-center justify-between text-[0.72rem]">
              <span className="text-faint">{titleCase(metric)}</span>
              <span className="mono font-medium text-ink">{score(val)}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function ApplyModal({ suggestion, failure, onClose }) {
  const navigate = useNavigate()
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [rerunFailedOnly, setRerunFailedOnly] = useState(true)
  const [error, setError] = useState(null)

  if (!suggestion) return null

  const apply = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await api.improveExperiment(failure.experiment_id, {
        apply: suggestion.apply,
        run_id: failure.run_id,
        rerun_failed_only: rerunFailedOnly,
        auto_run: true,
        change_summary: suggestion.detail,
      })
      toast.success('Follow-up experiment created and queued.', 'Improvement loop')
      navigate(result.run_id ? `/evaluations/${result.run_id}` : `/experiments/${result.experiment.id}`)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Create a follow-up experiment"
      description="The follow-up is identical to the baseline except for this one change, so any difference in results is attributable to it."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" icon={FlaskConical} loading={busy} onClick={apply}>
            Create and run
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="rounded-xl border border-accent/30 bg-accent-soft/60 p-4">
          <p className="text-sm font-semibold text-ink">{titleCase(suggestion.action)}</p>
          <p className="prose-note mt-1.5 text-xs leading-relaxed">
            {suggestion.llm_detail || suggestion.detail}
          </p>
        </div>

        <div>
          <p className="label mb-2">Configuration change</p>
          <div className="space-y-1.5">
            {Object.entries(suggestion.apply || {}).map(([field, value]) => (
              <div key={field} className="rounded-lg bg-overlay/60 px-3 py-2">
                <p className="mono text-xs text-faint">{field}</p>
                <p className="mt-0.5 break-words text-sm text-ink">
                  {typeof value === 'string' && value.length > 120 ? `${value.slice(0, 120)}…` : String(value)}
                </p>
              </div>
            ))}
          </div>
        </div>

        {suggestion.expected_improvement ? (
          <InlineNote tone="info">
            <span className="font-semibold text-ink">Expected effect: </span>
            {suggestion.expected_improvement}
          </InlineNote>
        ) : null}

        <label className="flex items-start gap-3 rounded-xl border border-line p-3">
          <input
            type="checkbox"
            checked={rerunFailedOnly}
            onChange={(e) => setRerunFailedOnly(e.target.checked)}
            className="mt-1 accent-[rgb(var(--accent))]"
          />
          <span>
            <span className="block text-sm font-semibold text-ink">Re-run only the failed cases</span>
            <span className="prose-note block text-xs">
              Faster and cheaper. Turn this off to re-run the whole dataset, which gives a comparison
              across identical case sets.
            </span>
          </span>
        </label>

        {error ? <ErrorState compact error={error} /> : null}
      </div>
    </Modal>
  )
}

export default function FailureDetail() {
  const { id } = useParams()
  const toast = useToast()
  const [diagnosing, setDiagnosing] = useState(false)
  const [selected, setSelected] = useState(null)
  const [showAttributionModal, setShowAttributionModal] = useState(false)
  const { data: failure, loading, error, refetch, setData } = useApi(() => api.failure(id), [id])
  const { data: attribution, refetch: refetchAttribution, setData: setAttribution } = useApi(
    () => api.failureAttribution(id),
    [id],
  )

  if (loading) return <LoadingState label="Loading failure…" />
  if (error) return <ErrorState error={error} onRetry={refetch} />
  if (!failure) return null

  const result = failure.result || {}
  const diagnosis = failure.diagnosis

  const handleAttributed = (newAtt) => {
    setAttribution(newAtt)
    refetch()
    toast.success(
      `Attributed as ${attributionLabel(newAtt.verdict)} (confidence ${score(newAtt.confidence)}).`,
      'Counterfactual test complete',
    )
  }

  const diagnose = async () => {
    setDiagnosing(true)
    try {
      const updated = await api.diagnose(id, { force: Boolean(diagnosis) })
      setData(updated)
      toast.success(
        updated.diagnosis_source === 'llm'
          ? 'Diagnosis produced by the configured judge model.'
          : 'Heuristic diagnosis produced from the stored evidence.',
        'Diagnosis complete',
      )
    } catch (err) {
      toast.error(err.message, 'Diagnosis failed')
    } finally {
      setDiagnosing(false)
    }
  }

  return (
    <>
      <Link to="/failures" className="btn-ghost mb-4 -ml-2 px-2 text-sm">
        <ArrowLeft className="h-4 w-4" />
        All failures
      </Link>

      <PageHeader
        eyebrow="Failure analysis"
        title={titleCase(failure.failure_type)}
        description={failure.evidence?.[0]}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              icon={FlaskConical}
              onClick={() => setShowAttributionModal(true)}
            >
              {attribution ? 'Re-run attribution' : 'Counterfactual test'}
            </Button>
            <Button variant="primary" icon={Stethoscope} loading={diagnosing} onClick={diagnose}>
              {diagnosis ? 'Re-run diagnosis' : 'Run AI diagnosis'}
            </Button>
          </div>
        }
      >
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Badge tone={SEVERITY_TONES[failure.severity] || 'neutral'}>{failure.severity}</Badge>
          <Badge tone={failure.detector === 'counterfactual' ? 'accent' : 'neutral'}>
            detector: {failure.detector}
          </Badge>
          <Badge tone="neutral">confidence {score(failure.confidence)}</Badge>
          <span className="mono text-xs text-faint">{failure.provider} / {failure.model}</span>
          {failure.run_id ? (
            <Link to={`/evaluations/${failure.run_id}`} className="text-xs text-accent hover:underline">
              View the run
            </Link>
          ) : null}
        </div>
      </PageHeader>

      {/* ---------------------------------------------------------- counterfactual attribution */}
      {attribution ? (
        <Reveal>
          <Card className="mb-6 border-accent/40 bg-surface p-5">
            <SectionHeader
              icon={FlaskConical}
              title="Counterfactual failure attribution"
              description={`Tested under controlled counterfactual conditions with N=${attribution.repeats} trial(s).`}
              actions={
                <div className="flex items-center gap-2">
                  <Badge tone={attributionTone(attribution.verdict)}>
                    {attributionLabel(attribution.verdict)}
                  </Badge>
                  {attribution.verdict !== 'NOT_ATTRIBUTABLE' ? (
                    <Badge tone="neutral">confidence {score(attribution.confidence)}</Badge>
                  ) : null}
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={FlaskConical}
                    onClick={() => setShowAttributionModal(true)}
                  >
                    Re-test
                  </Button>
                </div>
              }
            />

            {attribution.verdict === 'NOT_ATTRIBUTABLE' ? (
              <div className="mb-4">
                <InlineNote tone="bad" icon={AlertTriangle}>
                  <span className="font-semibold text-ink">Cannot attribute: </span>
                  {attribution.reason}
                </InlineNote>
              </div>
            ) : (
              <div className="mb-5 rounded-xl border border-line bg-overlay/50 p-4">
                <p className="label mb-1.5">Attributed root cause</p>
                <p className="text-sm font-medium leading-relaxed text-ink">{attribution.reason}</p>
                {attribution.recommendation ? (
                  <p className="mt-2 text-xs leading-relaxed text-muted">
                    <span className="font-semibold text-ink">Remediation: </span>
                    {attribution.recommendation}
                  </p>
                ) : null}
              </div>
            )}

            {/* Condition side-by-side comparison */}
            <div>
              <p className="label mb-2.5">Controlled condition comparison</p>
              <div className="grid gap-4 md:grid-cols-3">
                <ConditionCard
                  title="1. Original"
                  subtitle="Stored evaluation result"
                  answer={result.generated_answer}
                  scores={result.metric_map}
                  passed={attribution.condition_passes?.original ?? result.passed}
                  error={result.error_kind ? `${result.error_kind}: ${result.error_message || ''}` : null}
                />
                <ConditionCard
                  title="2. Oracle context"
                  subtitle="Gold context from test case"
                  answer={
                    attribution.conditions?.find((c) => c.condition === 'oracle_context')?.generated_answer
                  }
                  scores={
                    attribution.conditions_summary?.oracle_context?.avg_scores ||
                    attribution.conditions?.find((c) => c.condition === 'oracle_context')?.scores
                  }
                  passed={attribution.condition_passes?.oracle_context}
                  error={
                    attribution.conditions_summary?.oracle_context?.error ||
                    attribution.conditions?.find((c) => c.condition === 'oracle_context')?.error_message
                  }
                />
                <ConditionCard
                  title="3. No context"
                  subtitle="Empty context (parametric)"
                  answer={
                    attribution.conditions?.find((c) => c.condition === 'no_context')?.generated_answer
                  }
                  scores={
                    attribution.conditions_summary?.no_context?.avg_scores ||
                    attribution.conditions?.find((c) => c.condition === 'no_context')?.scores
                  }
                  passed={attribution.condition_passes?.no_context}
                  error={
                    attribution.conditions_summary?.no_context?.error ||
                    attribution.conditions?.find((c) => c.condition === 'no_context')?.error_message
                  }
                />
              </div>
            </div>

            {attribution.evidence?.length ? (
              <div className="mt-4 border-t border-line pt-3">
                <p className="label mb-1.5">Empirical evidence</p>
                <ul className="space-y-1">
                  {attribution.evidence.map((item, idx) => (
                    <li key={idx} className="flex gap-2 text-xs text-muted">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </Card>
        </Reveal>
      ) : (
        <div className="mb-6">
          <Card className="flex flex-wrap items-center justify-between gap-4 border-dashed border-accent/40 bg-accent-soft/30 p-4">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <FlaskConical className="h-4 w-4 text-accent" />
                <p className="text-sm font-semibold text-ink">Empirical failure attribution</p>
              </div>
              <p className="mt-1 text-xs text-muted leading-relaxed">
                Empirically isolate whether this failure was caused by retrieval or generation by re-running
                the test case with the gold context and with empty context.
              </p>
            </div>
            <Button
              variant="secondary"
              icon={FlaskConical}
              onClick={() => setShowAttributionModal(true)}
            >
              Run counterfactual test
            </Button>
          </Card>
        </div>
      )}

      {/* ---------------------------------------------------------- diagnosis */}
      {diagnosis ? (
        <Reveal>
          <Card className="mb-6 border-accent/30 p-5">
            <SectionHeader
              icon={Sparkles}
              title="AI diagnosis"
              description={
                diagnosis.engine === 'heuristic'
                  ? 'Produced by the deterministic rule engine from stored evidence. No LLM judge was configured.'
                  : `Produced by ${diagnosis.judge_model || 'the configured judge'}, with machine-applicable actions from the rule engine.`
              }
              actions={<Badge tone="accent">confidence {score(diagnosis.confidence)}</Badge>}
            />

            <div className="mb-5 rounded-xl border border-line bg-overlay/50 p-4">
              <p className="label mb-1.5">Likely root cause</p>
              <p className="text-sm leading-relaxed text-ink">{diagnosis.root_cause}</p>
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
              <div>
                <p className="label mb-2">Evidence used</p>
                <ul className="space-y-1.5">
                  {diagnosis.evidence?.map((item, index) => (
                    <li key={index} className="flex gap-2 text-xs leading-relaxed text-muted">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="label mb-2">Expected improvement</p>
                <p className="prose-note text-xs leading-relaxed">{diagnosis.expected_improvement}</p>
              </div>
            </div>

            {diagnosis.suggestions?.length ? (
              <div className="mt-6">
                <p className="label mb-3">Recommended changes</p>
                <div className="space-y-2.5">
                  {diagnosis.suggestions.map((suggestion, index) => {
                    const applicable = Object.keys(suggestion.apply || {}).length > 0
                    return (
                      <div
                        key={index}
                        className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-line bg-surface p-4"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="mb-1.5 flex items-center gap-2">
                            <Lightbulb className="h-3.5 w-3.5 text-accent" />
                            <p className="text-sm font-semibold text-ink">{titleCase(suggestion.action)}</p>
                            {!applicable ? <Badge tone="neutral">manual</Badge> : null}
                          </div>
                          <p className="prose-note text-xs leading-relaxed">
                            {suggestion.llm_detail || suggestion.detail}
                          </p>
                          {applicable ? (
                            <p className="mono mt-2 text-[0.7rem] text-faint">
                              {Object.entries(suggestion.apply)
                                .map(([k, v]) => `${k} = ${typeof v === 'string' && v.length > 40 ? `${v.slice(0, 40)}…` : v}`)
                                .join(', ')}
                            </p>
                          ) : null}
                        </div>
                        {applicable && failure.experiment_id ? (
                          <Button onClick={() => setSelected(suggestion)}>
                            Apply
                            <ArrowRight className="h-3.5 w-3.5" />
                          </Button>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              </div>
            ) : null}
          </Card>
        </Reveal>
      ) : (
        <div className="mb-6">
          <InlineNote tone="accent" icon={Stethoscope}>
            No diagnosis has been run for this failure yet. The diagnosis engine reads only the stored
            evidence below — the question, the answer, the retrieved context, the measured scores and
            the experiment configuration — and returns a root cause with applicable changes.
          </InlineNote>
        </div>
      )}

      {/* ---------------------------------------------------------- evidence */}
      <div className="grid gap-5 lg:grid-cols-2">
        <Reveal>
          <Card className="p-5">
            <SectionHeader title="What was asked and answered" />
            <div className="space-y-4">
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
                    {result.error_message || 'The model produced no text.'}
                  </p>
                )}
              </div>
            </div>
          </Card>
        </Reveal>

        <Reveal delay={0.06}>
          <Card className="p-5">
            <SectionHeader title="Measured scores" description="Only these numbers feed the classification." />
            <div className="space-y-2">
              {(result.metrics || []).map((metric) => (
                <div key={metric.metric} className="flex items-center justify-between gap-3 rounded-lg bg-overlay/50 px-3 py-2.5">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-ink">{titleCase(metric.metric)}</p>
                    <p className="text-[0.7rem] text-faint">
                      {metric.available ? titleCase(metric.kind) : metric.unavailable_reason}
                    </p>
                  </div>
                  {metric.available ? (
                    <ScoreBar value={metric.normalized_score} tone={scoreTone(metric.normalized_score)} />
                  ) : (
                    <Badge tone="neutral">unavailable</Badge>
                  )}
                </div>
              ))}
            </div>
            <div className="mt-5 border-t border-line pt-4">
              <KeyValue
                items={[
                  { label: 'Latency', value: ms(result.latency_ms) },
                  { label: 'Composite', value: score(result.composite_score) },
                  { label: 'Status', value: titleCase(result.status || '') },
                  { label: 'Error kind', value: result.error_kind || NA },
                ]}
              />
            </div>
          </Card>
        </Reveal>
      </div>

      {result.retrieved_context?.length ? (
        <Reveal>
          <Card className="mt-5 p-5">
            <SectionHeader
              title={`Retrieved context (${result.retrieved_context.length} chunk(s))`}
              description="What the model actually had available. If the answer is not here, the failure is a retrieval problem, not a model problem."
            />
            <div className="space-y-2.5">
              {result.retrieved_context.map((chunk, index) => (
                <div key={index} className="rounded-xl border border-line bg-overlay/40 p-3.5">
                  <p className="mono mb-1.5 text-[0.68rem] text-faint">chunk {index + 1}</p>
                  <p className="text-xs leading-relaxed text-muted">{chunk}</p>
                </div>
              ))}
            </div>
          </Card>
        </Reveal>
      ) : null}

      <ApplyModal suggestion={selected} failure={failure} onClose={() => setSelected(null)} />
      {showAttributionModal ? (
        <AttributionModal
          failure={failure}
          onClose={() => setShowAttributionModal(false)}
          onAttributed={handleAttributed}
        />
      ) : null}
    </>
  )
}

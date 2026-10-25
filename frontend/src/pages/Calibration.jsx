/**
 * Judge calibration — human labels, agreement scoring (Cohen's kappa) and bias probes.
 */
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CheckSquare,
  HelpCircle,
  Play,
  RotateCcw,
  Scale,
  ShieldAlert,
  ShieldCheck,
  SkipForward,
  Sparkles,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

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
  ProgressBar,
  Reveal,
  ScoreBar,
  SectionHeader,
  Select,
  Tabs,
  Toggle,
  useToast,
} from '../components/ui'
import { useApi } from '../hooks'
import { api } from '../lib/api'
import {
  NA,
  formatCI,
  formatKappa,
  kappaTone,
  pct,
  relativeTime,
  score,
  titleCase,
} from '../lib/format'

const METRIC_OPTIONS = [
  { value: 'correctness', label: 'Correctness' },
  { value: 'faithfulness', label: 'Faithfulness' },
  { value: 'answer_relevance', label: 'Answer relevance' },
]

export default function Calibration() {
  const [searchParams] = useSearchParams()
  const toast = useToast()

  const [activeTab, setActiveTab] = useState('label')
  const [selectedRunId, setSelectedRunId] = useState(searchParams.get('run') || '')
  const [selectedMetric, setSelectedMetric] = useState(searchParams.get('metric') || 'correctness')

  // Queue state
  const [currentIndex, setCurrentIndex] = useState(0)
  const [labelNote, setLabelNote] = useState('')
  const [annotatorName, setAnnotatorName] = useState('default')
  const [runProbes, setRunProbes] = useState(true)
  const [calibrating, setCalibrating] = useState(false)

  // Fetch runs
  const { data: runsData, loading: runsLoading } = useApi(
    () => api.dashboard().then((res) => res.recent_runs || []),
    [],
  )

  // Set default run if none selected
  useEffect(() => {
    if (!selectedRunId && runsData?.length) {
      setSelectedRunId(runsData[0].id)
    }
  }, [selectedRunId, runsData])

  // Fetch unlabelled queue
  const {
    data: queueData,
    loading: queueLoading,
    refetch: refetchQueue,
  } = useApi(
    () =>
      selectedRunId
        ? api.calibrationQueue({ run_id: selectedRunId, metric: selectedMetric, limit: 50 })
        : Promise.resolve([]),
    [selectedRunId, selectedMetric],
    { enabled: Boolean(selectedRunId) },
  )

  // Fetch existing labels for progress
  const { data: labelsData, refetch: refetchLabels } = useApi(
    () =>
      selectedRunId
        ? api.calibrationLabels({ run_id: selectedRunId, metric: selectedMetric })
        : Promise.resolve([]),
    [selectedRunId, selectedMetric],
    { enabled: Boolean(selectedRunId) },
  )

  // Fetch calibration runs history
  const {
    data: calRunsData,
    loading: calRunsLoading,
    refetch: refetchCalRuns,
  } = useApi(() => api.calibrationRuns({ limit: 20 }), [])

  const currentCase = queueData?.[currentIndex]
  const labelledCount = labelsData?.length || 0
  const targetLabels = 30
  const progressRatio = Math.min(1.0, labelledCount / targetLabels)

  // Most recent calibration run for selected scope
  const activeCalibration = calRunsData?.find(
    (r) =>
      r.status === 'completed' &&
      r.metric === selectedMetric &&
      (r.scope?.run_id === selectedRunId || !selectedRunId),
  ) || calRunsData?.[0]

  // Submit label handler
  const handleRate = useCallback(
    async (labelValue) => {
      if (!currentCase) return
      try {
        await api.upsertLabel({
          result_id: currentCase.result_id,
          metric: selectedMetric,
          label: labelValue,
          annotator: annotatorName.trim() || 'default',
          note: labelNote.trim() || undefined,
        })
        toast.success(
          `Rated ${labelValue === 2 ? 'Correct' : labelValue === 1 ? 'Partial' : 'Incorrect'}.`,
        )
        setLabelNote('')
        refetchLabels()
        if (currentIndex < (queueData?.length || 0) - 1) {
          setCurrentIndex((idx) => idx + 1)
        } else {
          refetchQueue()
          setCurrentIndex(0)
        }
      } catch (err) {
        toast.error(err.message || 'Failed to record label.')
      }
    },
    [
      currentCase,
      selectedMetric,
      annotatorName,
      labelNote,
      toast,
      refetchLabels,
      currentIndex,
      queueData?.length,
      refetchQueue,
    ],
  )

  // Keyboard shortcut listener (1, 2, 3)
  useEffect(() => {
    if (activeTab !== 'label' || !currentCase) return

    const handleKeyDown = (e) => {
      // Ignore if user is typing in an input or textarea
      if (['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return
      if (e.key === '1') {
        e.preventDefault()
        handleRate(0)
      } else if (e.key === '2') {
        e.preventDefault()
        handleRate(1)
      } else if (e.key === '3') {
        e.preventDefault()
        handleRate(2)
      } else if (e.key === 's' || e.key === 'S') {
        e.preventDefault()
        setCurrentIndex((idx) => Math.min((queueData?.length || 1) - 1, idx + 1))
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [activeTab, currentCase, handleRate, queueData?.length])

  // Run calibration action
  const handleExecuteCalibration = async () => {
    if (!selectedRunId) return
    setCalibrating(true)
    try {
      const res = await api.runCalibration({
        run_id: selectedRunId,
        metric: selectedMetric,
        run_probes: runProbes,
      })
      if (res.status === 'insufficient_labels') {
        toast.error(
          `Only ${res.n_labels} cases labelled (minimum 10 required for agreement).`,
          'Insufficient labels',
        )
      } else if (res.status === 'no_judge_scores') {
        toast.error(
          'Selected run only contains deterministic scores. Calibration applies to LLM-judge metrics.',
          'No judge scores',
        )
      } else if (res.status === 'judge_unavailable') {
        toast.error(
          res.warnings?.[0] || 'Judge provider is unconfigured.',
          'Judge unavailable',
        )
      } else {
        toast.success(
          `Calibration complete. Cohen's kappa: ${formatKappa(res.agreement?.kappa)}.`,
        )
        refetchCalRuns()
        setActiveTab('results')
      }
    } catch (err) {
      toast.error(err.message || 'Calibration execution failed.')
    } finally {
      setCalibrating(false)
    }
  }

  const runOptions = (runsData || []).map((r) => ({
    value: r.id,
    label: `${r.experiment_name || r.id} (${relativeTime(r.started_at || r.created_at)})`,
  }))

  return (
    <div className="space-y-6">
      <PageHeader
        title="Judge calibration"
        description="Verify how far LLM-as-a-judge scores align with human judgment using blind labelling, Cohen's kappa and automated bias probes."
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <div className="w-56">
              <Select
                value={selectedRunId}
                onChange={setSelectedRunId}
                options={runOptions}
                placeholder="Choose evaluation run"
              />
            </div>
            <div className="w-44">
              <Select
                value={selectedMetric}
                onChange={setSelectedMetric}
                options={METRIC_OPTIONS}
              />
            </div>
            <Button
              variant="primary"
              onClick={handleExecuteCalibration}
              disabled={calibrating || !selectedRunId}
            >
              <Play className="h-4 w-4" />
              {calibrating ? 'Calibrating…' : 'Run calibration'}
            </Button>
          </div>
        }
      />

      <Tabs
        active={activeTab}
        onChange={setActiveTab}
        tabs={[
          {
            value: 'label',
            label: 'Blind labelling queue',
            count: queueData?.length || 0,
          },
          {
            value: 'results',
            label: 'Calibration & Probes',
            count: activeCalibration ? 'Active' : undefined,
          },
          {
            value: 'history',
            label: 'Calibration history',
            count: calRunsData?.length || 0,
          },
        ]}
      />

      {/* ------------------------------------------------ Tab 1: Blind Labelling */}
      {activeTab === 'label' ? (
        <div className="space-y-6">
          {/* Progress bar */}
          <Card className="p-4">
            <div className="mb-2 flex items-center justify-between text-xs">
              <span className="font-medium text-ink">
                Labelling progress ({labelledCount} of target {targetLabels} cases)
              </span>
              <span className="mono text-muted">
                {queueData?.length ? `Case ${currentIndex + 1} of ${queueData.length}` : 'Queue empty'}
              </span>
            </div>
            <ProgressBar value={progressRatio} />
            {labelledCount < 10 ? (
              <p className="mt-2 text-xs text-[rgb(var(--warn))]">
                Minimum 10 labels required before kappa can be calculated. Target 30+ for tight intervals.
              </p>
            ) : null}
          </Card>

          {queueLoading ? (
            <LoadingState message="Loading unlabelled cases…" />
          ) : !queueData?.length ? (
            <Card className="p-8 text-center">
              <CheckCircle2 className="mx-auto mb-3 h-10 w-10 text-[rgb(var(--good))]" />
              <h3 className="text-base font-semibold text-ink">Queue complete</h3>
              <p className="prose-note mx-auto mt-1 max-w-md text-xs">
                All eligible cases for this run and metric have been labelled, or no judge-scored results were found.
              </p>
              <div className="mt-5 flex justify-center gap-3">
                <Button variant="primary" onClick={handleExecuteCalibration} disabled={calibrating}>
                  <Play className="h-4 w-4" />
                  Run calibration now
                </Button>
                <Button variant="outline" onClick={() => refetchQueue()}>
                  <RotateCcw className="h-4 w-4" />
                  Refresh queue
                </Button>
              </div>
            </Card>
          ) : currentCase ? (
            <Card className="p-6">
              <div className="mb-5 flex items-center justify-between border-b border-line pb-4">
                <div>
                  <span className="label">Evaluation test case</span>
                  <p className="text-xs text-faint">
                    Candidate model: <span className="mono text-ink">{currentCase.model}</span> · Metric: <span className="font-semibold text-ink">{titleCase(selectedMetric)}</span>
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone="neutral">Blind review</Badge>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setCurrentIndex((idx) => Math.min(queueData.length - 1, idx + 1))}
                  >
                    <SkipForward className="h-3.5 w-3.5" />
                    Skip
                  </Button>
                </div>
              </div>

              <div className="space-y-4">
                {/* Question */}
                <div>
                  <p className="label mb-1">Question</p>
                  <p className="rounded-xl border border-line bg-surface p-3.5 text-sm text-ink font-medium">
                    {currentCase.question}
                  </p>
                </div>

                {/* Expected Answer */}
                {currentCase.expected_answer ? (
                  <div>
                    <p className="label mb-1">Expected reference answer</p>
                    <p className="rounded-xl border border-line bg-overlay/40 p-3.5 text-xs text-muted">
                      {currentCase.expected_answer}
                    </p>
                  </div>
                ) : null}

                {/* Candidate Generated Answer */}
                <div>
                  <p className="label mb-1">Model answer (to rate)</p>
                  <p className="whitespace-pre-wrap rounded-xl border border-line bg-surface p-4 text-sm text-ink leading-relaxed">
                    {currentCase.generated_answer || '(Model produced no answer text)'}
                  </p>
                </div>

                {/* Retrieved Context Chunks */}
                {currentCase.retrieved_context?.length ? (
                  <div>
                    <p className="label mb-1">
                      Retrieved context ({currentCase.retrieved_context.length} chunk(s))
                    </p>
                    <div className="max-h-40 space-y-2 overflow-y-auto rounded-xl border border-line bg-overlay/30 p-3">
                      {currentCase.retrieved_context.map((c, i) => (
                        <p key={i} className="text-xs text-muted">
                          <span className="mono text-[0.65rem] text-faint font-semibold">[{i + 1}] </span>
                          {c}
                        </p>
                      ))}
                    </div>
                  </div>
                ) : null}

                {/* Optional Note & Annotator */}
                <div className="grid gap-3 sm:grid-cols-2 pt-2">
                  <div>
                    <label className="label mb-1 block">Annotator identity</label>
                    <Input
                      value={annotatorName}
                      onChange={(e) => setAnnotatorName(e.target.value)}
                      placeholder="e.g. reviewer_1"
                    />
                  </div>
                  <div>
                    <label className="label mb-1 block">Optional note / rationale</label>
                    <Input
                      value={labelNote}
                      onChange={(e) => setLabelNote(e.target.value)}
                      placeholder="Add brief note for this rating…"
                    />
                  </div>
                </div>

                {/* Rating Action Buttons */}
                <div className="pt-4 border-t border-line">
                  <p className="label mb-2 text-center text-xs">
                    Assign rating (or press shortcut <span className="mono font-bold">1</span>, <span className="mono font-bold">2</span>, <span className="mono font-bold">3</span>)
                  </p>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <button
                      type="button"
                      onClick={() => handleRate(0)}
                      className="group flex flex-col items-center justify-center gap-1 rounded-2xl border border-[rgb(var(--bad))]/35 bg-[rgb(var(--bad))]/10 p-4 transition-all duration-200 hover:bg-[rgb(var(--bad))]/20 hover:scale-[1.01] active:scale-[0.99]"
                    >
                      <div className="flex items-center gap-1.5 font-semibold text-[rgb(var(--bad))]">
                        <span className="mono text-xs rounded bg-[rgb(var(--bad))]/20 px-1.5 py-0.5">1</span>
                        Incorrect
                      </div>
                      <span className="text-[0.7rem] text-faint">Factual error, contradiction, or evasion</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleRate(1)}
                      className="group flex flex-col items-center justify-center gap-1 rounded-2xl border border-[rgb(var(--warn))]/35 bg-[rgb(var(--warn))]/10 p-4 transition-all duration-200 hover:bg-[rgb(var(--warn))]/20 hover:scale-[1.01] active:scale-[0.99]"
                    >
                      <div className="flex items-center gap-1.5 font-semibold text-[rgb(var(--warn))]">
                        <span className="mono text-xs rounded bg-[rgb(var(--warn))]/20 px-1.5 py-0.5">2</span>
                        Partially correct
                      </div>
                      <span className="text-[0.7rem] text-faint">Minor omission, partial details</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleRate(2)}
                      className="group flex flex-col items-center justify-center gap-1 rounded-2xl border border-[rgb(var(--good))]/35 bg-[rgb(var(--good))]/10 p-4 transition-all duration-200 hover:bg-[rgb(var(--good))]/20 hover:scale-[1.01] active:scale-[0.99]"
                    >
                      <div className="flex items-center gap-1.5 font-semibold text-[rgb(var(--good))]">
                        <span className="mono text-xs rounded bg-[rgb(var(--good))]/20 px-1.5 py-0.5">3</span>
                        Correct
                      </div>
                      <span className="text-[0.7rem] text-faint">Conveys the same key facts</span>
                    </button>
                  </div>
                </div>
              </div>
            </Card>
          ) : null}
        </div>
      ) : null}

      {/* ------------------------------------------------ Tab 2: Calibration & Probes */}
      {activeTab === 'results' ? (
        !activeCalibration ? (
          <EmptyState
            title="No calibration report yet"
            description="Label at least 10 cases in the queue and run calibration to measure judge reliability."
            action={
              <Button variant="primary" onClick={() => setActiveTab('label')}>
                Go to labelling queue
              </Button>
            }
          />
        ) : (
          <div className="space-y-6">
            {/* Warnings and Integrity alerts */}
            {activeCalibration.warnings?.map((warning, index) => (
              <InlineNote key={index} tone={warning.includes('Low') || warning.includes('weak') ? 'bad' : 'warn'}>
                {warning}
              </InlineNote>
            ))}

            {activeCalibration.n_labels < 30 ? (
              <InlineNote tone="warn">
                <span className="font-semibold text-ink">Sample size advisory:</span> Current calibration is based on {activeCalibration.n_labels} labels. At least 30 labelled cases are recommended for tight confidence intervals.
              </InlineNote>
            ) : null}

            {activeCalibration.agreement?.kappa !== null && activeCalibration.agreement?.kappa < 0.4 ? (
              <InlineNote tone="bad">
                <span className="font-semibold text-ink">Low Reliability:</span> Cohen's kappa is below 0.40 ({formatKappa(activeCalibration.agreement?.kappa)}). Scores from this judge should be treated as weak evidence.
              </InlineNote>
            ) : null}

            {/* Headline Stats */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Card className="p-5">
                <span className="label">Unweighted Cohen's κ</span>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="metric-value">{formatKappa(activeCalibration.agreement?.kappa)}</span>
                  <Badge tone={kappaTone(activeCalibration.agreement?.kappa)}>
                    {activeCalibration.agreement?.interpretation || 'uncalibrated'}
                  </Badge>
                </div>
                <p className="prose-note mt-1.5 text-xs">
                  95% CI: {formatCI(activeCalibration.agreement?.interval?.[0], activeCalibration.agreement?.interval?.[1])}
                </p>
              </Card>

              <Card className="p-5">
                <span className="label">Quadratic-weighted κ</span>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="metric-value">{formatKappa(activeCalibration.agreement?.weighted_kappa)}</span>
                  <span className="text-xs text-muted">ordinal penalty</span>
                </div>
                <p className="prose-note mt-1.5 text-xs">
                  95% CI: {formatCI(activeCalibration.agreement?.weighted_interval?.[0], activeCalibration.agreement?.weighted_interval?.[1])}
                </p>
              </Card>

              <Card className="p-5">
                <span className="label">Observed agreement (Po)</span>
                <p className="metric-value mt-2">{pct(activeCalibration.agreement?.observed_agreement)}</p>
                <p className="prose-note mt-1.5 text-xs">
                  Chance agreement (Pe): {pct(activeCalibration.agreement?.expected_agreement)}
                </p>
              </Card>

              <Card className="p-5">
                <span className="label">Labelled sample (N)</span>
                <p className="metric-value mt-2">{activeCalibration.n_labels}</p>
                <p className="prose-note mt-1.5 text-xs">
                  Judge: {activeCalibration.judge_provider} / {activeCalibration.judge_model}
                </p>
              </Card>
            </div>

            {/* 3x3 Confusion Matrix & Bias Summary */}
            <div className="grid gap-6 lg:grid-cols-2">
              {/* Confusion matrix */}
              <Card className="p-5">
                <SectionHeader
                  title="3×3 Agreement Matrix"
                  description="Cross-tabulation of Human ratings (rows) against LLM judge ratings (columns)."
                />
                {activeCalibration.agreement?.confusion_matrix ? (
                  <div className="mt-4 overflow-x-auto">
                    <table className="w-full text-center text-xs">
                      <thead>
                        <tr className="border-b border-line text-faint">
                          <th className="p-2 text-left">Human \ Judge</th>
                          <th className="p-2">Incorrect (0)</th>
                          <th className="p-2">Partial (1)</th>
                          <th className="p-2">Correct (2)</th>
                          <th className="p-2 text-right">Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        {['Incorrect (0)', 'Partial (1)', 'Correct (2)'].map((humanLabel, rIdx) => {
                          const row = activeCalibration.agreement.confusion_matrix[rIdx] || [0, 0, 0]
                          const rowSum = row.reduce((a, b) => a + b, 0)
                          return (
                            <tr key={rIdx} className="border-b border-line/60">
                              <td className="p-2 text-left font-medium text-ink">{humanLabel}</td>
                              {row.map((count, cIdx) => {
                                const isDiag = rIdx === cIdx
                                const intensity = activeCalibration.n_labels > 0 ? count / activeCalibration.n_labels : 0
                                return (
                                  <td
                                    key={cIdx}
                                    className="p-2 mono"
                                    style={{
                                      backgroundColor: isDiag
                                        ? `rgba(var(--good), ${Math.min(0.55, 0.12 + intensity * 0.7)})`
                                        : count > 0
                                        ? `rgba(var(--warn), ${Math.min(0.4, 0.08 + intensity * 0.5)})`
                                        : 'transparent',
                                    }}
                                  >
                                    <span className="font-semibold">{count}</span>
                                  </td>
                                )
                              })}
                              <td className="p-2 text-right mono text-faint font-medium">{rowSum}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-xs text-muted">No matrix available.</p>
                )}
                <p className="prose-note mt-3 text-[0.7rem]">
                  {activeCalibration.agreement?.landis_koch_note}
                </p>
              </Card>

              {/* Bias Summary */}
              <Card className="p-5">
                <SectionHeader
                  title="Directional Bias Summary"
                  description="Systematic tendency to score higher or lower than human ground truth."
                />
                <div className="mt-4 space-y-4">
                  <div>
                    <div className="flex justify-between text-xs">
                      <span className="text-muted">Mean signed error (Judge - Human)</span>
                      <span className="mono font-semibold text-ink">
                        {activeCalibration.agreement?.bias?.mean_signed_error !== undefined
                          ? `${activeCalibration.agreement.bias.mean_signed_error > 0 ? '+' : ''}${score(activeCalibration.agreement.bias.mean_signed_error)}`
                          : NA}
                      </span>
                    </div>
                    <p className="text-[0.7rem] text-faint mt-0.5">
                      Positive indicates systematic over-scoring; negative indicates harsh scoring.
                    </p>
                  </div>

                  <div>
                    <div className="flex justify-between text-xs">
                      <span className="text-muted">Over-scoring share</span>
                      <span className="mono font-semibold text-[rgb(var(--warn))]">
                        {pct(activeCalibration.agreement?.bias?.over_scoring_share)}
                      </span>
                    </div>
                    <ProgressBar
                      value={activeCalibration.agreement?.bias?.over_scoring_share || 0}
                      tone="warn"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between text-xs">
                      <span className="text-muted">Under-scoring share</span>
                      <span className="mono font-semibold text-[rgb(var(--warn))]">
                        {pct(activeCalibration.agreement?.bias?.under_scoring_share)}
                      </span>
                    </div>
                    <ProgressBar
                      value={activeCalibration.agreement?.bias?.under_scoring_share || 0}
                      tone="warn"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between text-xs">
                      <span className="text-muted">Exact classification agreement</span>
                      <span className="mono font-semibold text-[rgb(var(--good))]">
                        {pct(activeCalibration.agreement?.bias?.exact_agreement_share)}
                      </span>
                    </div>
                    <ProgressBar
                      value={activeCalibration.agreement?.bias?.exact_agreement_share || 0}
                      tone="good"
                    />
                  </div>
                </div>
              </Card>
            </div>

            {/* Three Bias Probe Cards */}
            <div>
              <SectionHeader
                title="Bias Probes"
                description="Controlled sensitivity experiments: re-judging cases by mutating one experimental variable at a time."
              />
              <div className="grid gap-5 md:grid-cols-3 mt-3">
                {/* 1. Order swap */}
                <Card className="p-5 flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold text-ink text-sm">Order swap probe</span>
                      <Badge tone={activeCalibration.probes?.order_swap?.flip_rate > 0.2 ? 'warn' : 'good'}>
                        {activeCalibration.probes?.order_swap?.flip_rate > 0.2 ? 'Position sensitive' : 'Position stable'}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted leading-relaxed mb-3">
                      Swaps reference and answer presentation order in prompt.
                    </p>
                    <div className="space-y-1.5 text-xs">
                      <div className="flex justify-between">
                        <span className="text-faint">Flip rate</span>
                        <span className="mono font-medium text-ink">
                          {pct(activeCalibration.probes?.order_swap?.flip_rate)}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-faint">95% Wilson CI</span>
                        <span className="mono text-muted">
                          {formatCI(
                            activeCalibration.probes?.order_swap?.interval?.[0],
                            activeCalibration.probes?.order_swap?.interval?.[1],
                          )}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-faint">Mean verdict shift</span>
                        <span className="mono text-muted">
                          {score(activeCalibration.probes?.order_swap?.mean_shift)}
                        </span>
                      </div>
                    </div>
                  </div>
                  <p className="prose-note mt-4 border-t border-line/60 pt-3 text-[0.7rem]">
                    {activeCalibration.probes?.order_swap?.interpretation || 'Probe executed on sampled pairs.'}
                  </p>
                </Card>

                {/* 2. Verbosity padding */}
                <Card className="p-5 flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold text-ink text-sm">Verbosity padding</span>
                      <Badge
                        tone={
                          activeCalibration.probes?.verbosity_padding?.share_scored_higher > 0.2 ||
                          activeCalibration.probes?.verbosity_padding?.mean_score_change > 0.05
                            ? 'bad'
                            : 'good'
                        }
                      >
                        {activeCalibration.probes?.verbosity_padding?.share_scored_higher > 0.2
                          ? 'Verbosity biased'
                          : 'Length neutral'}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted leading-relaxed mb-3">
                      Appends ~80 words of neutral filler text with no new facts.
                    </p>
                    <div className="space-y-1.5 text-xs">
                      <div className="flex justify-between">
                        <span className="text-faint">Share scored higher</span>
                        <span className="mono font-medium text-ink">
                          {pct(activeCalibration.probes?.verbosity_padding?.share_scored_higher)}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-faint">Mean score change</span>
                        <span className="mono text-muted">
                          {activeCalibration.probes?.verbosity_padding?.mean_score_change !== undefined
                            ? `${activeCalibration.probes.verbosity_padding.mean_score_change > 0 ? '+' : ''}${score(activeCalibration.probes.verbosity_padding.mean_score_change, 3)}`
                            : NA}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-faint">95% Wilson CI</span>
                        <span className="mono text-muted">
                          {formatCI(
                            activeCalibration.probes?.verbosity_padding?.interval?.[0],
                            activeCalibration.probes?.verbosity_padding?.interval?.[1],
                          )}
                        </span>
                      </div>
                    </div>
                  </div>
                  <p className="prose-note mt-4 border-t border-line/60 pt-3 text-[0.7rem]">
                    {activeCalibration.probes?.verbosity_padding?.interpretation || 'Probe executed on sampled pairs.'}
                  </p>
                </Card>

                {/* 3. Self-preference */}
                <Card className="p-5 flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold text-ink text-sm">Self-preference</span>
                      <Badge tone={activeCalibration.probes?.self_preference?.warnings?.length ? 'warn' : 'neutral'}>
                        {activeCalibration.probes?.self_preference?.n_same_family > 0 ? 'Same-family candidate' : 'Family isolated'}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted leading-relaxed mb-3">
                      Compares judge scores on same-family vs other-family candidates.
                    </p>
                    <div className="space-y-1.5 text-xs">
                      <div className="flex justify-between">
                        <span className="text-faint">Same-family mean (N={activeCalibration.probes?.self_preference?.n_same_family || 0})</span>
                        <span className="mono font-medium text-ink">
                          {score(activeCalibration.probes?.self_preference?.mean_same_family)}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-faint">Other-family mean (N={activeCalibration.probes?.self_preference?.n_other_family || 0})</span>
                        <span className="mono text-muted">
                          {score(activeCalibration.probes?.self_preference?.mean_other_family)}
                        </span>
                      </div>
                    </div>
                  </div>
                  <p className="prose-note mt-4 border-t border-line/60 pt-3 text-[0.7rem]">
                    {activeCalibration.probes?.self_preference?.interpretation || 'Inferred without re-calling judge.'}
                  </p>
                </Card>
              </div>
            </div>
          </div>
        )
      ) : null}

      {/* ------------------------------------------------ Tab 3: History */}
      {activeTab === 'history' ? (
        <Card className="p-5">
          <SectionHeader
            title="Calibration Run History"
            description="Stored reliability runs for reproducibility and audit trails."
          />
          {calRunsLoading ? (
            <LoadingState message="Loading calibration runs…" />
          ) : !calRunsData?.length ? (
            <p className="text-xs text-muted mt-3">No calibration runs recorded yet.</p>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="table text-xs">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Judge</th>
                    <th>Metric</th>
                    <th>Labels</th>
                    <th>Status</th>
                    <th>Kappa (95% CI)</th>
                    <th>Interpretation</th>
                  </tr>
                </thead>
                <tbody>
                  {calRunsData.map((run) => (
                    <tr key={run.id}>
                      <td className="text-muted">{relativeTime(run.created_at)}</td>
                      <td>
                        <span className="font-semibold text-ink">{run.judge_provider}</span>
                        <span className="mono text-[0.7rem] text-faint block">{run.judge_model}</span>
                      </td>
                      <td>{titleCase(run.metric)}</td>
                      <td className="mono">{run.n_labels}</td>
                      <td>
                        <Badge tone={run.status === 'completed' ? 'good' : 'warn'}>
                          {run.status}
                        </Badge>
                      </td>
                      <td className="mono">
                        {run.agreement?.kappa !== undefined && run.agreement?.kappa !== null
                          ? `${formatKappa(run.agreement.kappa)} ${formatCI(run.agreement.interval?.[0], run.agreement.interval?.[1])}`
                          : NA}
                      </td>
                      <td>
                        <Badge tone={kappaTone(run.agreement?.kappa)}>
                          {run.agreement?.interpretation || run.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      ) : null}
    </div>
  )
}

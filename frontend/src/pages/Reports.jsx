/** Reports — generate and browse frozen evaluation reports. */
import { Download, FileText, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Modal,
  PageHeader,
  Reveal,
  Select,
  Toggle,
  useToast,
} from '../components/ui'
import { useApi } from '../hooks'
import { api } from '../lib/api'
import { dateTime, titleCase } from '../lib/format'

function GenerateModal({ open, onClose, runs, defaultRun, onDone }) {
  const toast = useToast()
  const [runId, setRunId] = useState(defaultRun || '')
  const [baselineRunId, setBaselineRunId] = useState('')
  const [title, setTitle] = useState('')
  const [includeFailures, setIncludeFailures] = useState(true)
  const [includeRecommendation, setIncludeRecommendation] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async () => {
    if (!runId) return setError({ message: 'Choose a run to report on.' })
    setBusy(true)
    setError(null)
    try {
      const report = await api.createReport({
        run_id: runId,
        baseline_run_id: baselineRunId || null,
        title: title.trim() || null,
        include_failures: includeFailures,
        include_recommendation: includeRecommendation,
      })
      toast.success('Report generated.')
      onDone(report)
      onClose()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Generate a report"
      description="A report is a frozen snapshot assembled from stored results — it never re-calls a provider, so it stays valid and reproducible."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={submit}>Generate</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Run" required>
          <Select
            value={runId}
            onChange={(e) => setRunId(e.target.value)}
            placeholder="Choose a completed run…"
            options={runs.map((r) => ({ value: r.id, label: `${r.experiment_name || r.id} — ${dateTime(r.created_at)}` }))}
          />
        </Field>
        <Field label="Baseline run" hint="Optional. Adds a before/after section comparing the two.">
          <Select
            value={baselineRunId}
            onChange={(e) => setBaselineRunId(e.target.value)}
            placeholder="No baseline comparison"
            options={runs.filter((r) => r.id !== runId).map((r) => ({ value: r.id, label: r.experiment_name || r.id }))}
          />
        </Field>
        <Field label="Title" hint="Defaults to the experiment name.">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Q3 model selection" />
        </Field>
        <Toggle checked={includeFailures} onChange={setIncludeFailures} label="Include failed cases" description="With their evidence and any diagnosis already produced." />
        <Toggle checked={includeRecommendation} onChange={setIncludeRecommendation} label="Include a model recommendation" description="Generated from this run's results only." />
        {error ? <ErrorState compact error={error} /> : null}
      </div>
    </Modal>
  )
}

export default function Reports() {
  const navigate = useNavigate()
  const toast = useToast()
  const [params] = useSearchParams()
  const [open, setOpen] = useState(Boolean(params.get('run')))

  const { data, loading, error, refetch } = useApi(() => api.reports(), [])
  const { data: runsPayload } = useApi(() => api.runs({ status: 'completed', limit: 50 }), [])
  const runs = runsPayload?.items || []
  const reports = data?.items || []

  const remove = async (report) => {
    try {
      await api.deleteReport(report.id)
      toast.success('Report deleted.')
      refetch()
    } catch (err) {
      toast.error(err.message)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Analysis"
        title="Reports"
        description="Shareable summaries of an evaluation: dataset, models tested, metrics, latency, failures, RAG performance, findings and next steps — exportable as JSON or CSV."
        actions={
          <Button variant="primary" icon={Plus} onClick={() => setOpen(true)}>
            Generate report
          </Button>
        }
      />

      {loading ? (
        <LoadingState label="Loading reports…" />
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : reports.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No reports yet"
          description="Generate one from any completed run."
          action={
            <Button variant="primary" icon={Plus} onClick={() => setOpen(true)}>
              Generate report
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {reports.map((report, index) => (
            <Reveal key={report.id} delay={Math.min(index * 0.04, 0.25)}>
              <Card hover className="flex h-full flex-col p-5">
                <div className="mb-3 flex items-start justify-between gap-3">
                  <Link to={`/reports/${report.id}`} className="text-[1.02rem] font-semibold text-ink hover:text-accent">
                    {report.title}
                  </Link>
                  <Badge tone={report.kind === 'improvement' ? 'accent' : 'neutral'}>
                    {titleCase(report.kind)}
                  </Badge>
                </div>
                <p className="prose-note text-xs">{dateTime(report.created_at)}</p>
                <div className="mt-auto flex items-center gap-1.5 border-t border-line pt-3">
                  <Link to={`/reports/${report.id}`} className="btn-ghost flex-1 px-2.5 py-1.5 text-xs">
                    Open
                  </Link>
                  <a href={api.exportUrl(report.id, 'json')} className="btn-ghost px-2.5 py-1.5 text-xs" download>
                    <Download className="h-3.5 w-3.5" />JSON
                  </a>
                  <a href={api.exportUrl(report.id, 'csv')} className="btn-ghost px-2.5 py-1.5 text-xs" download>
                    <Download className="h-3.5 w-3.5" />CSV
                  </a>
                  <button
                    onClick={() => remove(report)}
                    className="rounded-lg p-1.5 text-faint transition-colors hover:bg-[rgb(var(--bad))]/10 hover:text-[rgb(var(--bad))]"
                    aria-label="Delete report"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </Card>
            </Reveal>
          ))}
        </div>
      )}

      <GenerateModal
        open={open}
        onClose={() => setOpen(false)}
        runs={runs}
        defaultRun={params.get('run')}
        onDone={(report) => navigate(`/reports/${report.id}`)}
      />
    </>
  )
}

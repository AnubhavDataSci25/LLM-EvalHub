/** Dataset detail — validation report, versions and the test-case table. */
import { ArrowLeft, CheckCircle2, Database, Play, Plus, Trash2, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Input,
  KeyValue,
  LoadingState,
  Modal,
  PageHeader,
  SectionHeader,
  Tabs,
  Textarea,
  useToast,
} from '../components/ui'
import { useApi } from '../hooks'
import { api } from '../lib/api'
import { NA, dateTime, num, titleCase, truncate } from '../lib/format'

const DIFFICULTY_TONES = { easy: 'good', medium: 'fair', hard: 'poor', adversarial: 'bad' }

function AddCaseModal({ open, onClose, datasetId, onDone }) {
  const toast = useToast()
  const [form, setForm] = useState({ question: '', ground_truth: '', context: '', category: '', difficulty: 'medium' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value })

  const submit = async () => {
    if (!form.question.trim()) {
      setError('A question is required.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await api.addCase(datasetId, {
        question: form.question.trim(),
        ground_truth: form.ground_truth.trim() || null,
        context: form.context.trim() || null,
        category: form.category.trim() || null,
        difficulty: form.difficulty,
      })
      toast.success('Test case added. A new dataset version was created.')
      setForm({ question: '', ground_truth: '', context: '', category: '', difficulty: 'medium' })
      onDone()
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Add a test case"
      description="Adding a case creates a new dataset version, so earlier experiments keep pointing at the data they actually ran on."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={submit}>
            Add case
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Question" required>
          <Textarea rows={2} value={form.question} onChange={set('question')} placeholder="What is the refund window?" />
        </Field>
        <Field label="Expected answer" hint="Without this, correctness cannot be scored and will show as unavailable.">
          <Textarea rows={2} value={form.ground_truth} onChange={set('ground_truth')} />
        </Field>
        <Field label="Context" hint="Optional inline context, used when RAG retrieval is off.">
          <Textarea rows={3} value={form.context} onChange={set('context')} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Category">
            <Input value={form.category} onChange={set('category')} placeholder="policy" />
          </Field>
          <Field label="Difficulty">
            <select className="input" value={form.difficulty} onChange={set('difficulty')}>
              {['easy', 'medium', 'hard', 'adversarial'].map((d) => (
                <option key={d} value={d}>{titleCase(d)}</option>
              ))}
            </select>
          </Field>
        </div>
        {error ? <ErrorState compact error={{ message: error }} /> : null}
      </div>
    </Modal>
  )
}

function ValidationReport({ report }) {
  if (!report) return null
  const issues = [...(report.errors || []), ...(report.warnings || [])]
  return (
    <Card className="mb-6 p-5">
      <SectionHeader
        icon={report.valid ? CheckCircle2 : TriangleAlert}
        title="Validation report"
        description="Produced when the dataset was imported. Errors drop a row; warnings keep it but flag a gap that will affect which metrics can be computed."
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-4">
        {[
          ['Rows', report.total_rows],
          ['Usable', report.accepted_rows],
          ['Errors', report.errors?.length || 0],
          ['Warnings', report.warnings?.length || 0],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl bg-overlay/60 px-4 py-3">
            <p className="label">{label}</p>
            <p className="mono mt-1 text-lg font-semibold text-ink">{num(value)}</p>
          </div>
        ))}
      </div>
      {issues.length ? (
        <div className="max-h-56 overflow-y-auto rounded-xl border border-line">
          <table className="table">
            <thead>
              <tr><th>Row</th><th>Field</th><th>Issue</th></tr>
            </thead>
            <tbody>
              {issues.slice(0, 40).map((issue, index) => (
                <tr key={index}>
                  <td className="mono">{issue.row}</td>
                  <td className="mono text-xs">{issue.field || NA}</td>
                  <td className="text-xs">{issue.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="prose-note text-sm">No issues were found in this dataset.</p>
      )}
    </Card>
  )
}

export default function DatasetDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const [tab, setTab] = useState('cases')
  const [addOpen, setAddOpen] = useState(false)
  const { data, loading, error, refetch } = useApi(() => api.dataset(id, { preview: 500 }), [id])

  if (loading) return <LoadingState label="Loading dataset…" />
  if (error) return <ErrorState error={error} onRetry={refetch} />
  if (!data) return null

  const cases = data.test_cases || []
  const stats = {
    withGroundTruth: cases.filter((c) => c.ground_truth).length,
    withContext: cases.filter((c) => c.context).length,
  }

  const removeCase = async (caseId) => {
    try {
      await api.deleteCase(caseId)
      toast.success('Test case removed.')
      refetch()
    } catch (err) {
      toast.error(err.message)
    }
  }

  return (
    <>
      <Link to="/datasets" className="btn-ghost mb-4 -ml-2 px-2 text-sm">
        <ArrowLeft className="h-4 w-4" />
        All datasets
      </Link>

      <PageHeader
        eyebrow={data.source === 'benchmark' ? 'Benchmark dataset' : 'Dataset'}
        title={data.name}
        description={data.description}
        actions={
          <>
            <Button icon={Plus} onClick={() => setAddOpen(true)}>Add case</Button>
            <Button
              variant="primary"
              icon={Play}
              onClick={() => navigate(`/evaluations/new?dataset=${data.id}`)}
            >
              Run evaluation
            </Button>
          </>
        }
      />

      <Card className="mb-6 p-5">
        <KeyValue
          items={[
            { label: 'Test cases', value: num(data.row_count) },
            { label: 'Versions', value: data.version_count },
            { label: 'Domain', value: data.domain ? titleCase(data.domain) : NA },
            { label: 'Source', value: titleCase(data.source) },
            { label: 'With expected answer', value: `${stats.withGroundTruth} of ${cases.length}` },
            { label: 'With inline context', value: `${stats.withContext} of ${cases.length}` },
            { label: 'Created', value: dateTime(data.created_at) },
            { label: 'Benchmark pack', value: data.benchmark_pack_key ? titleCase(data.benchmark_pack_key) : NA },
          ]}
        />
        {!data.has_ground_truth ? (
          <div className="mt-4 rounded-xl border border-[rgb(var(--warn))]/28 bg-[rgb(var(--warn))]/8 px-4 py-3">
            <p className="prose-note text-[0.82rem]">
              No expected answers are present, so correctness and faithfulness-against-reference
              cannot be computed. Those metrics will report as unavailable rather than scoring zero.
            </p>
          </div>
        ) : null}
      </Card>

      <Tabs
        className="mb-5 w-fit"
        active={tab}
        onChange={setTab}
        tabs={[
          { value: 'cases', label: 'Test cases', count: cases.length },
          { value: 'validation', label: 'Validation' },
          { value: 'versions', label: 'Versions', count: data.versions?.length || 0 },
        ]}
      />

      {tab === 'validation' ? <ValidationReport report={data.validation_report} /> : null}

      {tab === 'versions' ? (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>Version</th><th>Rows</th><th>Notes</th><th>Created</th></tr>
            </thead>
            <tbody>
              {(data.versions || []).map((version) => (
                <tr key={version.id}>
                  <td className="mono font-semibold">v{version.version}</td>
                  <td className="mono">{num(version.row_count)}</td>
                  <td className="text-xs text-muted">{version.notes || NA}</td>
                  <td className="whitespace-nowrap text-xs text-muted">{dateTime(version.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {tab === 'cases' ? (
        cases.length === 0 ? (
          <EmptyState
            icon={Database}
            title="This dataset has no test cases"
            description="Add one manually, or re-import the file."
            action={<Button variant="primary" icon={Plus} onClick={() => setAddOpen(true)}>Add case</Button>}
          />
        ) : (
          <div className="table-wrap max-h-[68vh] overflow-y-auto">
            <table className="table">
              <thead>
                <tr>
                  <th className="w-10">#</th>
                  <th>Question</th>
                  <th>Expected answer</th>
                  <th>Context</th>
                  <th>Category</th>
                  <th>Difficulty</th>
                  <th className="w-10" />
                </tr>
              </thead>
              <tbody>
                {cases.map((testCase, index) => (
                  <tr key={testCase.id}>
                    <td className="mono text-xs text-faint">{index + 1}</td>
                    <td className="min-w-[16rem] max-w-md text-sm">{testCase.question}</td>
                    <td className="min-w-[14rem] max-w-md text-sm text-muted">
                      {testCase.ground_truth || <span className="text-faint">{NA}</span>}
                    </td>
                    <td className="max-w-xs text-xs text-faint">
                      {testCase.context ? truncate(testCase.context, 110) : NA}
                    </td>
                    <td className="text-xs">{testCase.category ? titleCase(testCase.category) : NA}</td>
                    <td>
                      {testCase.difficulty ? (
                        <Badge tone={DIFFICULTY_TONES[testCase.difficulty] || 'neutral'}>
                          {testCase.difficulty}
                        </Badge>
                      ) : NA}
                    </td>
                    <td>
                      <button
                        onClick={() => removeCase(testCase.id)}
                        className="rounded-lg p-1.5 text-faint transition-colors hover:bg-[rgb(var(--bad))]/10 hover:text-[rgb(var(--bad))]"
                        aria-label="Delete case"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : null}

      <AddCaseModal open={addOpen} onClose={() => setAddOpen(false)} datasetId={id} onDone={refetch} />
    </>
  )
}

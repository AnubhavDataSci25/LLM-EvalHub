/** Datasets — list, upload (CSV/JSON), paste-import and delete. */
import { AlertTriangle, Database, FileUp, Plus, Search, Trash2, Upload } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

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
  SectionHeader,
  Textarea,
  useToast,
} from '../components/ui'
import { useApi, useDebounced } from '../hooks'
import { api } from '../lib/api'
import { num, relativeTime, titleCase } from '../lib/format'

const SAMPLE_JSON = `[
  {
    "question": "What is the refund window?",
    "ground_truth": "Refunds are available within 30 days of purchase.",
    "context": "Our policy allows refunds within 30 days.",
    "category": "policy",
    "difficulty": "easy"
  }
]`

function UploadModal({ open, onClose, onDone }) {
  const toast = useToast()
  const [file, setFile] = useState(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async () => {
    if (!file || !name.trim()) {
      setError('Choose a file and give the dataset a name.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('name', name.trim())
      if (description) form.append('description', description)
      const dataset = await api.uploadDataset(form)
      toast.success(`${dataset.row_count} test case(s) imported.`, 'Dataset created')
      onDone(dataset)
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
      title="Upload a dataset"
      description="CSV or JSON. Column names are matched flexibly — question/query/prompt, ground_truth/answer/expected, context/passage."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={submit} icon={Upload}>
            Import
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="File" required hint="Max 25 MB. A `question` column is the only hard requirement.">
          <label
            className="flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed
                       border-line bg-overlay/40 px-6 py-8 text-center transition-colors hover:border-accent/50"
          >
            <FileUp className="mb-2 h-6 w-6 text-accent" />
            <span className="text-sm font-semibold text-ink">
              {file ? file.name : 'Choose a .csv or .json file'}
            </span>
            <span className="prose-note mt-1 text-xs">
              {file ? `${(file.size / 1024).toFixed(1)} KB` : 'Click to browse'}
            </span>
            <input
              type="file"
              accept=".csv,.json,.jsonl"
              className="hidden"
              onChange={(event) => {
                const chosen = event.target.files?.[0]
                setFile(chosen || null)
                if (chosen && !name) setName(chosen.name.replace(/\.[^.]+$/, ''))
              }}
            />
          </label>
        </Field>

        <Field label="Dataset name" required>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Support QA v1" />
        </Field>

        <Field label="Description" hint="Optional — what this dataset is for.">
          <Input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Policy questions from the 2024 support handbook"
          />
        </Field>

        {error ? <ErrorState compact error={{ message: error }} /> : null}
      </div>
    </Modal>
  )
}

function PasteModal({ open, onClose, onDone }) {
  const toast = useToast()
  const [name, setName] = useState('')
  const [raw, setRaw] = useState(SAMPLE_JSON)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [report, setReport] = useState(null)

  const validate = async () => {
    setError(null)
    try {
      const rows = JSON.parse(raw)
      const result = await api.validateRows({ name: name || 'preview', rows })
      setReport(result)
    } catch (err) {
      setError(err.message || 'That is not valid JSON.')
      setReport(null)
    }
  }

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const rows = JSON.parse(raw)
      const dataset = await api.importDataset({ name: name.trim() || 'Pasted dataset', rows })
      toast.success(`${dataset.row_count} test case(s) imported.`, 'Dataset created')
      onDone(dataset)
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
      title="Paste JSON test cases"
      description="An array of objects, or an object with a `test_cases` array."
      size="lg"
      footer={
        <>
          <Button onClick={validate}>Validate</Button>
          <Button variant="primary" loading={busy} onClick={submit}>
            Create dataset
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Dataset name" required>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Manual test cases" />
        </Field>
        <Field label="JSON" hint="Only `question` is required per row.">
          <Textarea rows={12} value={raw} onChange={(e) => setRaw(e.target.value)} className="mono" />
        </Field>

        {report ? (
          <div className="rounded-xl border border-line bg-overlay/40 p-4">
            <div className="mb-2 flex items-center gap-2">
              <Badge tone={report.valid ? 'good' : 'bad'}>
                {report.valid ? 'Valid' : 'Invalid'}
              </Badge>
              <span className="text-sm text-muted">
                {report.accepted_rows} of {report.total_rows} row(s) usable
              </span>
            </div>
            {report.errors?.length ? (
              <ul className="mt-2 space-y-1">
                {report.errors.slice(0, 5).map((issue, index) => (
                  <li key={index} className="text-xs text-[rgb(var(--bad))]">
                    Row {issue.row}: {issue.message}
                  </li>
                ))}
              </ul>
            ) : null}
            {report.warnings?.length ? (
              <ul className="mt-2 space-y-1">
                {report.warnings.slice(0, 5).map((issue, index) => (
                  <li key={index} className="text-xs text-[rgb(var(--warn))]">
                    Row {issue.row}: {issue.message}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        {error ? <ErrorState compact error={{ message: error }} /> : null}
      </div>
    </Modal>
  )
}

export default function Datasets() {
  const navigate = useNavigate()
  const toast = useToast()
  const [search, setSearch] = useState('')
  const debounced = useDebounced(search)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [pasteOpen, setPasteOpen] = useState(false)
  const [deleting, setDeleting] = useState(null)

  const { data, loading, error, refetch } = useApi(
    () => api.datasets({ search: debounced || undefined, limit: 100 }),
    [debounced],
  )

  const remove = async (dataset) => {
    setDeleting(dataset.id)
    try {
      await api.deleteDataset(dataset.id)
      toast.success(`${dataset.name} deleted.`)
      refetch()
    } catch (err) {
      toast.error(err.message, 'Could not delete')
    } finally {
      setDeleting(null)
    }
  }

  const datasets = data?.items || []

  return (
    <>
      <PageHeader
        eyebrow="Inputs"
        title="Datasets"
        description="A dataset is a set of test cases: a question, an optional expected answer, and optional context. Versions are created automatically whenever cases change, so an experiment always points at an exact snapshot."
        actions={
          <>
            <Button icon={Plus} onClick={() => setPasteOpen(true)}>
              Paste JSON
            </Button>
            <Button variant="primary" icon={Upload} onClick={() => setUploadOpen(true)}>
              Upload file
            </Button>
          </>
        }
      />

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="relative min-w-[16rem] flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
          <input
            className="input pl-9"
            placeholder="Search datasets…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Link to="/benchmarks" className="btn-secondary">
          <Database className="h-4 w-4" />
          Install a benchmark pack
        </Link>
      </div>

      {loading ? (
        <LoadingState label="Loading datasets…" />
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : datasets.length === 0 ? (
        <EmptyState
          icon={Database}
          title={debounced ? 'No datasets match that search' : 'No datasets yet'}
          description={
            debounced
              ? 'Try a different term, or clear the search.'
              : 'Upload a CSV or JSON file, paste rows directly, or install one of the six benchmark packs.'
          }
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button variant="primary" icon={Upload} onClick={() => setUploadOpen(true)}>
                Upload a file
              </Button>
              <Link to="/benchmarks" className="btn-secondary">
                Browse benchmark packs
              </Link>
            </div>
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {datasets.map((dataset, index) => (
            <Reveal key={dataset.id} delay={Math.min(index * 0.04, 0.3)}>
              <Card hover className="flex h-full flex-col p-5">
                <div className="mb-3 flex items-start justify-between gap-3">
                  <Link
                    to={`/datasets/${dataset.id}`}
                    className="min-w-0 text-[1.02rem] font-semibold text-ink hover:text-accent"
                  >
                    {dataset.name}
                  </Link>
                  <Badge tone={dataset.source === 'benchmark' ? 'accent' : 'neutral'}>
                    {titleCase(dataset.source)}
                  </Badge>
                </div>

                {dataset.description ? (
                  <p className="prose-note mb-4 line-clamp-2 text-[0.84rem]">{dataset.description}</p>
                ) : null}

                <div className="mb-4 grid grid-cols-3 gap-3 text-center">
                  <div className="rounded-lg bg-overlay/60 py-2">
                    <p className="mono text-base font-semibold text-ink">{num(dataset.row_count)}</p>
                    <p className="label mt-0.5">Cases</p>
                  </div>
                  <div className="rounded-lg bg-overlay/60 py-2">
                    <p className="mono text-base font-semibold text-ink">{dataset.version_count}</p>
                    <p className="label mt-0.5">Versions</p>
                  </div>
                  <div className="rounded-lg bg-overlay/60 py-2">
                    <p className="mono text-base font-semibold text-ink">{dataset.experiment_count ?? 0}</p>
                    <p className="label mt-0.5">Runs</p>
                  </div>
                </div>

                <div className="mb-4 flex flex-wrap gap-1.5">
                  {dataset.has_ground_truth ? (
                    <Badge tone="good">Ground truth</Badge>
                  ) : (
                    <Badge tone="fair" icon={AlertTriangle}>
                      No ground truth
                    </Badge>
                  )}
                  {dataset.has_context ? <Badge tone="info">Inline context</Badge> : null}
                  {dataset.domain ? <Badge>{titleCase(dataset.domain)}</Badge> : null}
                </div>

                <div className="mt-auto flex items-center justify-between gap-2 border-t border-line pt-3">
                  <span className="text-xs text-faint">{relativeTime(dataset.created_at)}</span>
                  <div className="flex items-center gap-1">
                    <Link
                      to={`/evaluations/new?dataset=${dataset.id}`}
                      className="btn-ghost px-2.5 py-1.5 text-xs"
                    >
                      Evaluate
                    </Link>
                    <button
                      onClick={() => remove(dataset)}
                      disabled={deleting === dataset.id}
                      className="rounded-lg p-1.5 text-faint transition-colors hover:bg-[rgb(var(--bad))]/10
                                 hover:text-[rgb(var(--bad))] disabled:opacity-40"
                      aria-label={`Delete ${dataset.name}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </Card>
            </Reveal>
          ))}
        </div>
      )}

      <UploadModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onDone={(dataset) => navigate(`/datasets/${dataset.id}`)}
      />
      <PasteModal
        open={pasteOpen}
        onClose={() => setPasteOpen(false)}
        onDone={(dataset) => navigate(`/datasets/${dataset.id}`)}
      />
    </>
  )
}

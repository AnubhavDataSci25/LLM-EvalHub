/** RAG documents — upload, index and preview retrieval before committing to a run. */
import { FileText, FileUp, Layers, Search, Trash2, Upload } from 'lucide-react'
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
  SectionHeader,
  Select,
  StatusBadge,
  useToast,
} from '../components/ui'
import { useApi } from '../hooks'
import { api } from '../lib/api'
import { NA, num, relativeTime, score, titleCase } from '../lib/format'

export default function Documents() {
  const toast = useToast()
  const [collection, setCollection] = useState('default')
  const [uploading, setUploading] = useState(false)
  const [indexing, setIndexing] = useState(false)
  const [chunkSize, setChunkSize] = useState(800)
  const [chunkOverlap, setChunkOverlap] = useState(120)
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(4)
  const [strategy, setStrategy] = useState('hybrid')
  const [preview, setPreview] = useState(null)
  const [previewing, setPreviewing] = useState(false)

  const { data, loading, error, refetch } = useApi(() => api.documents(), [])
  const documents = data?.items || []
  const collections = data?.collections || []

  const upload = async (file) => {
    if (!file) return
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('collection', collection || 'default')
      await api.uploadDocument(form)
      toast.success(`${file.name} uploaded. Index it to make it searchable.`)
      refetch()
    } catch (err) {
      toast.error(err.message, 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const index = async () => {
    setIndexing(true)
    try {
      const result = await api.indexDocuments({
        document_ids: documents.filter((d) => d.collection === collection).map((d) => d.id),
        collection,
        chunk_size: Number(chunkSize),
        chunk_overlap: Number(chunkOverlap),
      })
      toast.success(
        `${result.chunks} chunk(s) indexed using the ${result.embedding?.name} embedder.`,
        'Indexing complete',
      )
      refetch()
    } catch (err) {
      toast.error(err.message, 'Indexing failed')
    } finally {
      setIndexing(false)
    }
  }

  const runPreview = async () => {
    if (!query.trim()) return
    setPreviewing(true)
    try {
      const result = await api.previewRetrieval({
        query: query.trim(),
        collection,
        top_k: Number(topK),
        strategy,
      })
      setPreview(result)
    } catch (err) {
      toast.error(err.message, 'Preview failed')
    } finally {
      setPreviewing(false)
    }
  }

  const remove = async (document) => {
    try {
      await api.deleteDocument(document.id)
      toast.success('Document removed.')
      refetch()
    } catch (err) {
      toast.error(err.message)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Inputs"
        title="RAG documents"
        description="Upload PDF, TXT or Markdown, chunk and index it, then preview what a question actually retrieves. Inspecting retrieval before running an evaluation saves a great deal of confused debugging afterwards."
      />

      <InlineNote tone="info">
        The default embedder is a deterministic lexical hasher — no model download, works on any
        hardware, and reproducible. It shares the exact tokenizer used by the retrieval metrics, so
        what the retriever considers a match is what the metrics score. Configure a semantic embedder
        in the backend for better paraphrase handling.
      </InlineNote>

      <div className="mt-6 grid gap-5 lg:grid-cols-[20rem_minmax(0,1fr)]">
        <div className="space-y-5">
          <Card className="p-5">
            <SectionHeader icon={Upload} title="Upload" />
            <div className="space-y-4">
              <Field label="Collection" hint="Documents are grouped into collections; an experiment retrieves from one.">
                <Input value={collection} onChange={(e) => setCollection(e.target.value)} placeholder="default" />
              </Field>
              <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed
                                border-line bg-overlay/40 px-5 py-7 text-center transition-colors hover:border-accent/50">
                <FileUp className="mb-2 h-5 w-5 text-accent" />
                <span className="text-sm font-semibold text-ink">
                  {uploading ? 'Uploading…' : 'Choose a file'}
                </span>
                <span className="prose-note mt-1 text-xs">PDF, TXT or Markdown · max 25 MB</span>
                <input
                  type="file"
                  accept=".pdf,.txt,.md,.markdown"
                  className="hidden"
                  disabled={uploading}
                  onChange={(e) => upload(e.target.files?.[0])}
                />
              </label>
            </div>
          </Card>

          <Card className="p-5">
            <SectionHeader icon={Layers} title="Index" description="Re-indexing replaces the stored chunks for this collection." />
            <div className="space-y-4">
              <Field label="Chunk size" hint="Characters per chunk.">
                <Input type="number" min={200} max={4000} step={100} value={chunkSize} onChange={(e) => setChunkSize(e.target.value)} />
              </Field>
              <Field label="Chunk overlap" hint="Stops an answer being split across a boundary.">
                <Input type="number" min={0} max={1000} step={20} value={chunkOverlap} onChange={(e) => setChunkOverlap(e.target.value)} />
              </Field>
              <Button variant="primary" className="w-full" loading={indexing} onClick={index}>
                Index “{collection}”
              </Button>
            </div>
          </Card>

          <Card className="p-5">
            <SectionHeader icon={Search} title="Retrieval preview" />
            <div className="space-y-4">
              <Field label="Question">
                <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="What is the refund window?" />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Top K">
                  <Input type="number" min={1} max={20} value={topK} onChange={(e) => setTopK(e.target.value)} />
                </Field>
                <Field label="Strategy">
                  <Select
                    value={strategy}
                    onChange={(e) => setStrategy(e.target.value)}
                    options={[
                      { value: 'vector', label: 'Vector' },
                      { value: 'keyword', label: 'Keyword' },
                      { value: 'hybrid', label: 'Hybrid' },
                    ]}
                  />
                </Field>
              </div>
              <Button className="w-full" loading={previewing} onClick={runPreview}>
                Preview retrieval
              </Button>
            </div>
          </Card>
        </div>

        <div className="space-y-5">
          {collections.length ? (
            <Card className="p-5">
              <SectionHeader title="Collections" />
              <div className="flex flex-wrap gap-2">
                {collections.map((item) => (
                  <button
                    key={item.name}
                    onClick={() => setCollection(item.name)}
                    className={`rounded-xl border px-3.5 py-2 text-left transition-all duration-200 ${
                      collection === item.name
                        ? 'border-accent/60 bg-accent-soft/60'
                        : 'border-line bg-surface hover:border-accent/35'
                    }`}
                  >
                    <p className="text-sm font-semibold text-ink">{item.name}</p>
                    <p className="prose-note text-[0.7rem]">
                      {item.documents} doc(s) · {num(item.chunks)} chunk(s)
                    </p>
                  </button>
                ))}
              </div>
            </Card>
          ) : null}

          {preview ? (
            <Reveal>
              <Card className="p-5">
                <SectionHeader
                  title={`Retrieved ${preview.chunks?.length || 0} chunk(s)`}
                  description={`Strategy: ${titleCase(preview.strategy || strategy)}${preview.embedding ? ` · embedder: ${preview.embedding}` : ''}`}
                />
                {preview.note ? <InlineNote tone="warn">{preview.note}</InlineNote> : null}
                <div className="mt-3 space-y-2.5">
                  {preview.chunks?.map((chunk, index) => (
                    <div key={index} className="rounded-xl border border-line bg-overlay/40 p-3.5">
                      <div className="mb-1.5 flex items-center justify-between">
                        <span className="mono text-[0.68rem] text-faint">
                          rank {index + 1}
                          {chunk.metadata?.citation ? ` · ${chunk.metadata.citation}` : ''}
                        </span>
                        <Badge tone="neutral">score {score(chunk.score, 3)}</Badge>
                      </div>
                      <p className="text-xs leading-relaxed text-muted">{chunk.content}</p>
                    </div>
                  ))}
                </div>
              </Card>
            </Reveal>
          ) : null}

          {loading ? (
            <LoadingState label="Loading documents…" />
          ) : error ? (
            <ErrorState error={error} onRetry={refetch} />
          ) : documents.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No documents uploaded"
              description="Upload a PDF, TXT or Markdown file, or install a benchmark pack that ships source documents."
            />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr><th>Document</th><th>Collection</th><th>Chunks</th><th>Status</th><th>Uploaded</th><th /></tr>
                </thead>
                <tbody>
                  {documents.map((document) => (
                    <tr key={document.id}>
                      <td>
                        <p className="font-medium text-ink">{document.filename}</p>
                        <p className="mono text-xs text-faint">{(document.byte_size / 1024).toFixed(1)} KB</p>
                      </td>
                      <td className="mono text-xs">{document.collection}</td>
                      <td className="mono">{document.chunk_count || 0}</td>
                      <td>
                        <StatusBadge status={document.status} />
                        {document.error ? (
                          <p className="mt-1 text-[0.68rem] text-[rgb(var(--bad))]">{document.error}</p>
                        ) : null}
                      </td>
                      <td className="whitespace-nowrap text-xs text-muted">{relativeTime(document.created_at)}</td>
                      <td>
                        <button
                          onClick={() => remove(document)}
                          className="rounded-lg p-1.5 text-faint transition-colors hover:bg-[rgb(var(--bad))]/10 hover:text-[rgb(var(--bad))]"
                          aria-label="Delete document"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

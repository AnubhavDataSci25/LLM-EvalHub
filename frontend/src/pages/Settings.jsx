/** Settings — provider configuration status and runtime limits. No secrets are ever shown. */
import { CheckCircle2, Cpu, Info, RefreshCw, Settings2, ShieldCheck, XCircle } from 'lucide-react'
import { useState } from 'react'

import {
  Badge,
  Button,
  Card,
  ErrorState,
  InlineNote,
  KeyValue,
  LoadingState,
  PageHeader,
  Reveal,
  SectionHeader,
  useToast,
} from '../components/ui'
import { useApi } from '../hooks'
import { api } from '../lib/api'
import { NA, num, titleCase } from '../lib/format'

export default function Settings() {
  const toast = useToast()
  const [checking, setChecking] = useState(null)
  const { data, loading, error, refetch } = useApi(() => api.providers(true), [])
  const { data: health } = useApi(() => api.health(), [])

  const providers = data?.providers || []
  const runtime = data?.runtime || {}

  const check = async (key) => {
    setChecking(key)
    try {
      const result = await api.providerHealth(key)
      if (result.reachable) toast.success(result.message || 'Provider reachable.', titleCase(key))
      else toast.error(result.message || 'Provider not reachable.', titleCase(key))
    } catch (err) {
      toast.error(err.message, titleCase(key))
    } finally {
      setChecking(null)
    }
  }

  if (loading) return <LoadingState label="Loading settings…" rows={4} />
  if (error) return <ErrorState error={error} onRetry={refetch} />

  return (
    <>
      <PageHeader
        eyebrow="Configuration"
        title="Settings & providers"
        description="Provider credentials live only in the backend environment. This page reports whether each provider is configured and reachable — it never displays, transmits or stores a key."
        actions={<Button icon={RefreshCw} onClick={refetch}>Refresh</Button>}
      />

      <InlineNote tone="accent" icon={ShieldCheck}>
        To configure a provider, set its variable in <span className="mono">backend/.env</span> and
        restart the API. See <span className="mono">.env.example</span> for the full list. Keys are
        redacted from application logs by a logging filter.
      </InlineNote>

      <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="space-y-4">
          {providers.map((provider, index) => (
            <Reveal key={provider.key} delay={Math.min(index * 0.04, 0.25)}>
              <Card className="p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="mb-1.5 flex flex-wrap items-center gap-2">
                      <h3 className="text-[1.02rem] font-semibold">{provider.display_name}</h3>
                      <Badge tone={provider.configured ? 'good' : 'neutral'} icon={provider.configured ? CheckCircle2 : XCircle}>
                        {provider.configured ? 'configured' : 'not configured'}
                      </Badge>
                      <Badge tone="neutral">{provider.kind}</Badge>
                    </div>
                    <p className="mono text-xs text-faint">{provider.base_url}</p>
                    {provider.note ? (
                      <p className="prose-note mt-2 text-xs leading-relaxed">{provider.note}</p>
                    ) : null}
                    {provider.message ? (
                      <p className="prose-note mt-2 text-xs">{provider.message}</p>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {provider.configured ? (
                      <Button loading={checking === provider.key} onClick={() => check(provider.key)}>
                        Test
                      </Button>
                    ) : null}
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-line pt-3">
                  <span className="text-xs text-muted">
                    <span className="label mr-1.5">Env var</span>
                    <span className="mono">{provider.env_var || NA}</span>
                  </span>
                  <span className="text-xs text-muted">
                    <span className="label mr-1.5">Models</span>
                    {provider.models?.length || 0}
                  </span>
                  {provider.docs_url ? (
                    <a
                      href={provider.docs_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-accent underline-offset-2 hover:underline"
                    >
                      Provider docs
                    </a>
                  ) : null}
                </div>

                {provider.models?.length ? (
                  <div className="mt-3 flex flex-wrap gap-1">
                    {provider.models.slice(0, 8).map((model) => (
                      <span key={model.id} className="mono rounded bg-overlay px-1.5 py-0.5 text-[0.68rem] text-muted">
                        {model.id}
                      </span>
                    ))}
                    {provider.models.length > 8 ? (
                      <span className="text-[0.68rem] text-faint">+{provider.models.length - 8} more</span>
                    ) : null}
                  </div>
                ) : null}
              </Card>
            </Reveal>
          ))}
        </div>

        <div className="space-y-5">
          <Card className="p-5">
            <SectionHeader icon={Settings2} title="Runtime" />
            <KeyValue
              columns={1}
              items={[
                { label: 'Environment', value: titleCase(runtime.environment || '') },
                { label: 'Database', value: titleCase(runtime.database || '') },
                { label: 'Concurrency limit', value: runtime.max_concurrent_requests },
                { label: 'Request timeout', value: `${runtime.request_timeout_seconds}s` },
                { label: 'Retry attempts', value: runtime.retry_attempts },
                { label: 'Max dataset rows', value: num(runtime.max_dataset_rows) },
                { label: 'Max upload', value: `${runtime.max_upload_mb} MB` },
                { label: 'Embedding backend', value: runtime.embedding_backend },
                { label: 'Vector store', value: runtime.vector_store_backend },
                { label: 'Default chunk size', value: runtime.default_chunk_size },
                { label: 'Default top K', value: runtime.default_top_k },
              ]}
            />
          </Card>

          <Card className="p-5">
            <SectionHeader icon={Cpu} title="Optional features" />
            <div className="space-y-2">
              {Object.entries(health?.optional_features || {}).map(([feature, enabled]) => (
                <div key={feature} className="flex items-center justify-between gap-3 rounded-lg bg-overlay/50 px-3 py-2">
                  <span className="text-sm text-ink">{titleCase(feature)}</span>
                  <Badge tone={enabled ? 'good' : 'neutral'}>{enabled ? 'available' : 'off'}</Badge>
                </div>
              ))}
            </div>
            <p className="prose-note mt-4 text-xs leading-relaxed">
              RAGAS and FAISS are optional extras. When they are absent the platform degrades
              honestly: deterministic evaluators and a NumPy vector index are used instead, and the
              substitution is recorded against each score.
            </p>
          </Card>
        </div>
      </div>
    </>
  )
}

/** Settings — provider configuration status, model availability audit, and runtime limits. No secrets are ever shown. */
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Info,
  Play,
  RefreshCw,
  RotateCcw,
  Settings2,
  ShieldCheck,
  XCircle,
  Zap,
} from 'lucide-react'
import { useMemo, useState } from 'react'

import {
  Badge,
  Button,
  Card,
  ErrorState,
  Field,
  InlineNote,
  Input,
  KeyValue,
  LoadingState,
  Modal,
  PageHeader,
  Reveal,
  SectionHeader,
  StatusBadge,
  useToast,
} from '../components/ui'
import { useApi } from '../hooks'
import { api } from '../lib/api'
import { NA, num, relativeTime, titleCase } from '../lib/format'

export default function Settings() {
  const toast = useToast()
  const [checking, setChecking] = useState(null)
  const [rechecking, setRechecking] = useState(null)
  const [viewAllDiagnostics, setViewAllDiagnostics] = useState(false)

  // Audit modal state
  const [auditModalOpen, setAuditModalOpen] = useState(false)
  const [maxProbes, setMaxProbes] = useState(15)
  const [dryRunLoading, setDryRunLoading] = useState(false)
  const [dryRunEstimate, setDryRunEstimate] = useState(null)
  const [auditRunning, setAuditRunning] = useState(false)

  const { data, loading, error, refetch } = useApi(() => api.providers(true), [])
  const { data: health } = useApi(() => api.health(), [])
  const { data: statusPayload, refetch: refetchStatus } = useApi(() => api.providerStatus(), [])
  const { data: allModelsPayload, refetch: refetchAllModels } = useApi(
    () => api.allProviderModels({ include_unavailable: true }),
    [],
  )

  const providers = data?.providers || []
  const runtime = data?.runtime || {}
  const providerStatusList = statusPayload || []

  const allAuditedModels = useMemo(() => {
    if (!allModelsPayload?.models) return []
    return Object.entries(allModelsPayload.models).flatMap(([pKey, list]) =>
      (list || []).map((m) => ({ ...m, provider: pKey })),
    )
  }, [allModelsPayload])

  const diagnosticModels = useMemo(() => {
    if (viewAllDiagnostics) return allAuditedModels
    return allAuditedModels.filter((m) => m.status !== 'AVAILABLE')
  }, [allAuditedModels, viewAllDiagnostics])

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

  const handleRecheck = async (provider, modelId) => {
    const key = `${provider}/${modelId}`
    setRechecking(key)
    try {
      const res = await api.recheckModel(provider, modelId)
      toast.success(`${provider}/${modelId} is now ${res.status}: ${res.reason || ''}`, 'Re-check complete')
      refetchStatus()
      refetchAllModels()
    } catch (err) {
      toast.error(err.message, 'Re-check failed')
    } finally {
      setRechecking(null)
    }
  }

  const openAuditModal = async () => {
    setAuditModalOpen(true)
    setDryRunLoading(true)
    try {
      const est = await api.runProviderAudit({ dry_run: true, max_probes_per_provider: maxProbes })
      setDryRunEstimate(est)
    } catch (err) {
      toast.error(err.message, 'Failed to estimate probes')
    } finally {
      setDryRunLoading(false)
    }
  }

  const handleMaxProbesChange = async (val) => {
    const numVal = Math.max(1, Math.min(50, Number(val) || 15))
    setMaxProbes(numVal)
    setDryRunLoading(true)
    try {
      const est = await api.runProviderAudit({ dry_run: true, max_probes_per_provider: numVal })
      setDryRunEstimate(est)
    } catch {
      // ignore transient error
    } finally {
      setDryRunLoading(false)
    }
  }

  const startAudit = async () => {
    setAuditRunning(true)
    try {
      const res = await api.runProviderAudit({ dry_run: false, max_probes_per_provider: maxProbes })
      toast.success(
        `Audit complete: ${res.summary?.total_probed || 0} models probed.`,
        'Model Availability Audit',
      )
      setAuditModalOpen(false)
      refetchStatus()
      refetchAllModels()
      refetch()
    } catch (err) {
      toast.error(err.message, 'Audit failed')
    } finally {
      setAuditRunning(false)
    }
  }

  const getStatusBadgeTone = (status) => {
    switch (status) {
      case 'AVAILABLE':
        return 'good'
      case 'RATE_LIMITED':
        return 'warn'
      case 'NOT_ENTITLED':
        return 'fair'
      case 'NOT_FOUND':
        return 'neutral'
      case 'INVALID_CREDENTIALS':
        return 'bad'
      case 'TIMEOUT':
      case 'UPSTREAM_ERROR':
      case 'EMPTY_RESPONSE':
        return 'bad'
      default:
        return 'neutral'
    }
  }

  if (loading) return <LoadingState label="Loading settings…" rows={4} />
  if (error) return <ErrorState error={error} onRetry={refetch} />

  return (
    <>
      <PageHeader
        eyebrow="Configuration"
        title="Settings & providers"
        description="Provider credentials live only in the backend environment. This page reports live model availability, provider reachability, and diagnostic evidence — it never displays or transmits a secret."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="primary" icon={Play} onClick={openAuditModal}>
              Run audit
            </Button>
            <Button
              icon={RefreshCw}
              onClick={() => {
                refetch()
                refetchStatus()
                refetchAllModels()
              }}
            >
              Refresh
            </Button>
          </div>
        }
      />

      <InlineNote tone="accent" icon={ShieldCheck}>
        To configure a provider, set its variable in <span className="mono">backend/.env</span> and
        restart the API. See <span className="mono">.env.example</span> for the full list. Keys are
        redacted from application logs by a logging filter.
      </InlineNote>

      {/* ----------------- Model Availability Section ----------------- */}
      <div className="mt-6 space-y-6">
        <Reveal>
          <Card className="p-5">
            <SectionHeader
              icon={Activity}
              title="Model availability audit"
              description="Live minimal probes verify which models are actually usable. Models that are retired, rate-limited, or gated behind unentitled tiers are diagnosed with exact evidence."
              actions={
                <Button variant="secondary" icon={Zap} onClick={openAuditModal}>
                  Audit models now
                </Button>
              }
            />

            {providerStatusList.length > 0 ? (
              <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {providerStatusList.map((p) => {
                  const counts = p.counts || {}
                  return (
                    <div
                      key={p.provider}
                      className="rounded-lg border border-line bg-surface/60 p-4 transition-colors hover:border-line-strong"
                    >
                      <div className="mb-2 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-semibold">{p.display_name}</h4>
                          <Badge tone={p.configured ? 'good' : 'neutral'}>
                            {p.configured ? 'configured' : 'missing key'}
                          </Badge>
                        </div>
                        <span className="text-[0.72rem] text-faint">
                          {p.last_audit_at ? relativeTime(p.last_audit_at) : 'never audited'}
                        </span>
                      </div>
                      <div className="mt-2.5 flex flex-wrap gap-1.5">
                        <Badge tone={counts.AVAILABLE ? 'good' : 'neutral'} className="text-[0.7rem]">
                          {counts.AVAILABLE || 0} available
                        </Badge>
                        {counts.RATE_LIMITED ? (
                          <Badge tone="warn" className="text-[0.7rem]">
                            {counts.RATE_LIMITED} limited
                          </Badge>
                        ) : null}
                        {counts.NOT_ENTITLED ? (
                          <Badge tone="fair" className="text-[0.7rem]">
                            {counts.NOT_ENTITLED} not entitled
                          </Badge>
                        ) : null}
                        {counts.NOT_FOUND ? (
                          <Badge tone="neutral" className="text-[0.7rem]">
                            {counts.NOT_FOUND} not found
                          </Badge>
                        ) : null}
                        {counts.INVALID_CREDENTIALS ? (
                          <Badge tone="bad" className="text-[0.7rem]">
                            {counts.INVALID_CREDENTIALS} auth error
                          </Badge>
                        ) : null}
                        {counts.TIMEOUT ? (
                          <Badge tone="bad" className="text-[0.7rem]">
                            {counts.TIMEOUT} timeout
                          </Badge>
                        ) : null}
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : (
              <InlineNote tone="info" icon={Info}>
                No audit has been run yet. Click &quot;Audit models now&quot; to probe configured providers and discover available models.
              </InlineNote>
            )}

            {/* Diagnostics Table */}
            <div className="mt-6 border-t border-line pt-5">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h4 className="text-sm font-semibold text-ink">
                    {viewAllDiagnostics ? 'All probed models' : 'Model diagnostics & exclusions'}
                  </h4>
                  <p className="prose-note text-xs">
                    {viewAllDiagnostics
                      ? 'Showing all audited models across providers.'
                      : 'Showing models that were rejected or limited during probe verification.'}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setViewAllDiagnostics((v) => !v)}
                >
                  {viewAllDiagnostics
                    ? 'Show excluded only'
                    : `Show all (${allAuditedModels.length})`}
                </Button>
              </div>

              {diagnosticModels.length === 0 ? (
                <div className="rounded-lg border border-line bg-surface/30 p-4 text-center">
                  <p className="prose-note text-xs">
                    {allAuditedModels.length === 0
                      ? 'No audit records in cache. Run an audit to populate diagnostics.'
                      : 'No excluded models — all probed models are confirmed available!'}
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-line">
                  <table className="w-full text-left text-xs">
                    <thead className="border-b border-line bg-surface/75 text-muted">
                      <tr>
                        <th className="px-3.5 py-2.5 font-medium">Provider</th>
                        <th className="px-3.5 py-2.5 font-medium">Model ID</th>
                        <th className="px-3.5 py-2.5 font-medium">Status</th>
                        <th className="px-3.5 py-2.5 font-medium">Diagnostic Reason</th>
                        <th className="px-3.5 py-2.5 font-medium">Latency / Retry</th>
                        <th className="px-3.5 py-2.5 font-medium">Last Checked</th>
                        <th className="px-3.5 py-2.5 text-right font-medium">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/60 bg-surface/30">
                      {diagnosticModels.map((m) => (
                        <tr key={`${m.provider}/${m.id}`} className="hover:bg-overlay/40">
                          <td className="px-3.5 py-2.5 font-medium text-ink">{titleCase(m.provider)}</td>
                          <td className="px-3.5 py-2.5 mono font-medium text-ink">{m.id}</td>
                          <td className="px-3.5 py-2.5">
                            <Badge tone={getStatusBadgeTone(m.status)} className="text-[0.68rem] px-1.5 py-0.5">
                              {m.status}
                            </Badge>
                          </td>
                          <td className="max-w-xs px-3.5 py-2.5 text-muted truncate" title={m.reason}>
                            {m.reason || '—'}
                          </td>
                          <td className="px-3.5 py-2.5 mono text-faint">
                            {m.latency_ms
                              ? `${Math.round(m.latency_ms)}ms`
                              : m.retry_after
                                ? `retry ${m.retry_after}s`
                                : '—'}
                          </td>
                          <td className="px-3.5 py-2.5 text-faint">{relativeTime(m.last_checked_at)}</td>
                          <td className="px-3.5 py-2.5 text-right">
                            <Button
                              size="sm"
                              variant="secondary"
                              icon={RotateCcw}
                              loading={rechecking === `${m.provider}/${m.id}`}
                              onClick={() => handleRecheck(m.provider, m.id)}
                            >
                              Re-check
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </Card>
        </Reveal>

        {/* ----------------- Provider Configuration Details ----------------- */}
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="space-y-4">
            {providers.map((provider, index) => (
              <Reveal key={provider.key} delay={Math.min(index * 0.04, 0.25)}>
                <Card className="p-5">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="mb-1.5 flex flex-wrap items-center gap-2">
                        <h3 className="text-[1.02rem] font-semibold">{provider.display_name}</h3>
                        <Badge
                          tone={provider.configured ? 'good' : 'neutral'}
                          icon={provider.configured ? CheckCircle2 : XCircle}
                        >
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
                        <span
                          key={model.id}
                          className="mono rounded bg-overlay px-1.5 py-0.5 text-[0.68rem] text-muted"
                        >
                          {model.id}
                        </span>
                      ))}
                      {provider.models.length > 8 ? (
                        <span className="text-[0.68rem] text-faint">
                          +{provider.models.length - 8} more
                        </span>
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
                  <div
                    key={feature}
                    className="flex items-center justify-between gap-3 rounded-lg bg-overlay/50 px-3 py-2"
                  >
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
      </div>

      {/* ----------------- Audit Confirmation Modal ----------------- */}
      <Modal
        open={auditModalOpen}
        onClose={() => !auditRunning && setAuditModalOpen(false)}
        title="Run Model Availability Audit"
        description="Verifies discovered models across all configured providers with a minimal 8-token generation probe."
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" disabled={auditRunning} onClick={() => setAuditModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" loading={auditRunning} icon={Play} onClick={startAudit}>
              Confirm & Run Audit
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <Field
            label="Max probes per provider"
            hint="Limits calls to protect rate limits and free quotas (1 - 50)."
          >
            <Input
              type="number"
              min={1}
              max={50}
              value={maxProbes}
              onChange={(e) => handleMaxProbesChange(e.target.value)}
              disabled={auditRunning}
            />
          </Field>

          {dryRunLoading ? (
            <p className="prose-note text-xs">Estimating call volume…</p>
          ) : dryRunEstimate ? (
            <div className="rounded-lg border border-line bg-surface/50 p-3.5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted font-medium">Estimated Cheap Probes:</span>
                <span className="mono font-semibold text-ink text-sm">
                  {dryRunEstimate.estimated_calls} calls
                </span>
              </div>
              <div className="text-[0.75rem] text-muted space-y-1">
                <p>Providers targeted: {dryRunEstimate.providers_targeted?.join(', ') || 'None'}</p>
                {dryRunEstimate.by_provider && (
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {Object.entries(dryRunEstimate.by_provider).map(([p, count]) => (
                      <span key={p} className="mono bg-overlay px-1.5 py-0.5 rounded text-[0.7rem]">
                        {p}: {count}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              {dryRunEstimate.warnings?.length > 0 && (
                <div className="mt-2 space-y-1">
                  {dryRunEstimate.warnings.map((w, idx) => (
                    <p key={idx} className="text-xs text-amber-600 dark:text-amber-400">
                      • {w}
                    </p>
                  ))}
                </div>
              )}
            </div>
          ) : null}

          <InlineNote tone="info" icon={Info}>
            Probes run concurrently with bounded concurrency. If an invalid credential or quota exhaustion is encountered on a provider, further probes for that provider stop immediately.
          </InlineNote>
        </div>
      </Modal>
    </>
  )
}

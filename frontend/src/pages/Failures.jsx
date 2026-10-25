/** Failure explorer — filterable list with the taxonomy distribution. */
import { Activity, Filter, Stethoscope } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { FailureDistributionChart } from '../components/charts'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Reveal,
  SectionHeader,
  Select,
} from '../components/ui'
import { useApi } from '../hooks'
import { api } from '../lib/api'
import { NA, ms, num, relativeTime, score, titleCase, truncate } from '../lib/format'

const SEVERITY_TONES = { critical: 'bad', high: 'bad', medium: 'poor', low: 'fair' }

export default function Failures() {
  const [params, setParams] = useSearchParams()
  const runId = params.get('run') || ''
  const [failureType, setFailureType] = useState('')
  const [severity, setSeverity] = useState('')
  const [diagnosed, setDiagnosed] = useState('')

  const { data: distribution } = useApi(
    () => api.failureDistribution({ run_id: runId || undefined }),
    [runId],
  )
  const { data, loading, error, refetch } = useApi(
    () =>
      api.failures({
        run_id: runId || undefined,
        failure_type: failureType || undefined,
        severity: severity || undefined,
        diagnosed: diagnosed === '' ? undefined : diagnosed === 'yes',
        limit: 100,
      }),
    [runId, failureType, severity, diagnosed],
  )
  const { data: taxonomy } = useApi(() => api.failureTypes(), [])

  const failures = data?.items || []
  const items = distribution?.items || []

  return (
    <>
      <PageHeader
        eyebrow="Analysis"
        title="Failure analysis"
        description="Failures are classified by an ordered cascade over measured signals: infrastructure problems first, then retrieval, then grounding, then answer quality. Low retrieval recall is reported as a retrieval problem rather than blamed on the model."
        actions={
          runId ? (
            <Button onClick={() => setParams({})}>Clear run filter</Button>
          ) : null
        }
      />

      {items.length ? (
        <Reveal>
          <Card className="mb-6 p-5">
            <SectionHeader icon={Activity} title="Distribution" description={runId ? 'Within the selected run.' : 'Across every run in the workspace.'} />
            <FailureDistributionChart items={items} height={Math.max(200, items.length * 42)} />
          </Card>
        </Reveal>
      ) : null}

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="w-52">
          <Select
            value={failureType}
            onChange={(e) => setFailureType(e.target.value)}
            placeholder="All failure types"
            options={(taxonomy?.failure_types || []).map((t) => ({ value: t.key, label: t.label }))}
          />
        </div>
        <div className="w-40">
          <Select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            placeholder="All severities"
            options={['critical', 'high', 'medium', 'low'].map((s) => ({ value: s, label: titleCase(s) }))}
          />
        </div>
        <div className="w-44">
          <Select
            value={diagnosed}
            onChange={(e) => setDiagnosed(e.target.value)}
            placeholder="Any diagnosis state"
            options={[
              { value: 'no', label: 'Not yet diagnosed' },
              { value: 'yes', label: 'Diagnosed' },
            ]}
          />
        </div>
        <span className="ml-auto text-xs text-muted">{num(data?.total ?? 0)} failure(s)</span>
      </div>

      {loading ? (
        <LoadingState label="Loading failures…" />
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : failures.length === 0 ? (
        <EmptyState
          icon={Stethoscope}
          title="No failures match these filters"
          description="Either the filters are too narrow, or the evaluated models handled these cases correctly."
        />
      ) : (
        <div className="space-y-3">
          {failures.map((failure, index) => (
            <Reveal key={failure.id} delay={Math.min(index * 0.03, 0.25)}>
              <Link to={`/failures/${failure.id}`} className="block">
                <Card hover className="p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <Badge tone={SEVERITY_TONES[failure.severity] || 'neutral'}>
                          {failure.failure_type?.replace(/_/g, ' ')}
                        </Badge>
                        <span className="mono text-xs text-faint">{failure.model}</span>
                        {failure.diagnosis ? (
                          <Badge tone="accent" icon={Stethoscope}>
                            diagnosed · {failure.diagnosis_source}
                          </Badge>
                        ) : null}
                      </div>
                      <p className="text-sm font-medium text-ink">{truncate(failure.question, 130)}</p>
                      {failure.evidence?.length ? (
                        <p className="prose-note mt-1.5 text-xs">{failure.evidence[0]}</p>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 gap-5 text-right">
                      <div>
                        <p className="label mb-1">Confidence</p>
                        <p className="mono text-sm">{score(failure.confidence)}</p>
                      </div>
                      <div>
                        <p className="label mb-1">Latency</p>
                        <p className="mono text-sm">{ms(failure.latency_ms)}</p>
                      </div>
                      <div>
                        <p className="label mb-1">Detected</p>
                        <p className="text-xs text-muted">{relativeTime(failure.created_at)}</p>
                      </div>
                    </div>
                  </div>
                </Card>
              </Link>
            </Reveal>
          ))}
        </div>
      )}
    </>
  )
}

/**
 * API client.
 *
 * Every provider call happens on the backend — this client never sees or sends
 * an API key. Errors are normalised into a single shape so the UI can render
 * rate limits, quota exhaustion and validation failures differently.
 */
import axios from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
})

export class ApiError extends Error {
  constructor({ message, code, details, status }) {
    super(message)
    this.name = 'ApiError'
    this.code = code || 'error'
    this.details = details
    this.status = status
  }

  /** True for conditions the user can resolve by waiting and retrying. */
  get isTransient() {
    return ['rate_limited', 'timeout', 'upstream_error', 'network_error'].includes(this.code)
  }

  get isConfiguration() {
    return ['provider_not_configured', 'invalid_credentials', 'quota_exhausted'].includes(this.code)
  }
}

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.code === 'ECONNABORTED') {
      return Promise.reject(
        new ApiError({ message: 'The request timed out.', code: 'timeout', status: 408 }),
      )
    }
    if (!error.response) {
      return Promise.reject(
        new ApiError({
          message: 'Cannot reach the API. Is the backend running on port 8000?',
          code: 'network_error',
          status: 0,
        }),
      )
    }
    const payload = error.response.data?.error
    return Promise.reject(
      new ApiError({
        message: payload?.message || error.response.statusText || 'Request failed.',
        code: payload?.code,
        details: payload?.details,
        status: error.response.status,
      }),
    )
  },
)

const get = (url, config) => client.get(url, config).then((r) => r.data)
const post = (url, body, config) => client.post(url, body, config).then((r) => r.data)
const put = (url, body) => client.put(url, body).then((r) => r.data)
const del = (url) => client.delete(url).then((r) => r.data)

export const api = {
  health: () => get('/health'),
  readyCheck: () => get('/ready'),
  metricCatalogue: () => get('/meta/metrics'),
  failureTypes: () => get('/meta/failure-types'),
  profiles: () => get('/meta/profiles'),
  dashboard: () => get('/dashboard'),

  providers: (withModels = false) => get('/providers', { params: { with_models: withModels } }),
  providerStatus: () => get('/providers/status'),
  allProviderModels: (params) => get('/providers/models', { params }),
  providerModels: (key) => get(`/providers/${key}/models`),
  providerHealth: (key) => get(`/providers/${key}/health`),
  runProviderAudit: (body) => post('/providers/audit', body),
  getProviderAudit: (id) => get(`/providers/audit/${id}`),
  recheckModel: (provider, modelId) =>
    post(`/providers/${encodeURIComponent(provider)}/models/${encodeURIComponent(modelId)}/recheck`),

  datasets: (params) => get('/datasets', { params }),
  dataset: (id, params) => get(`/datasets/${id}`, { params }),
  createDataset: (body) => post('/datasets', body),
  updateDataset: (id, body) => put(`/datasets/${id}`, body),
  deleteDataset: (id) => del(`/datasets/${id}`),
  importDataset: (body) => post('/datasets/import', body),
  validateRows: (body) => post('/datasets/validate', body),
  uploadDataset: (formData) =>
    client
      .post('/datasets/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      .then((r) => r.data),
  datasetCases: (id, params) => get(`/datasets/${id}/cases`, { params }),
  addCase: (id, body) => post(`/datasets/${id}/cases`, body),
  updateCase: (caseId, body) => put(`/datasets/cases/${caseId}`, body),
  deleteCase: (caseId) => del(`/datasets/cases/${caseId}`),

  benchmarks: () => get('/benchmarks'),
  benchmark: (key) => get(`/benchmarks/${key}`),
  installBenchmark: (key, body = {}) => post(`/benchmarks/${key}/install`, body),

  experiments: (params) => get('/experiments', { params }),
  experiment: (id) => get(`/experiments/${id}`),
  createExperiment: (body) => post('/experiments', body),
  deleteExperiment: (id) => del(`/experiments/${id}`),
  experimentRuns: (id) => get(`/experiments/${id}/runs`),
  improveExperiment: (id, body) => post(`/experiments/${id}/improve`, body),
  experimentOutcome: (id) => get(`/experiments/${id}/outcome`),

  runEvaluation: (body) => post('/evaluations/run', body),
  runs: (params) => get('/evaluations', { params }),
  run: (id) => get(`/evaluations/${id}`),
  runResults: (id, params) => get(`/evaluations/${id}/results`, { params }),
  result: (id) => get(`/evaluations/results/${id}`),
  retryRun: (id) => post(`/evaluations/${id}/retry`, {}),
  improvementSuggestions: (id) => get(`/evaluations/${id}/improvement-suggestions`),

  compareRuns: (body) => post('/compare', body),
  compareModels: (runId) => get(`/compare/models/${runId}`),
  improvement: (baselineRunId, followupRunId) =>
    get('/compare/improvement', {
      params: { baseline_run_id: baselineRunId, followup_run_id: followupRunId },
    }),

  failures: (params) => get('/failures', { params }),
  failure: (id) => get(`/failures/${id}`),
  failureDistribution: (params) => get('/failures/distribution', { params }),
  diagnose: (id, body = {}) => post(`/failures/${id}/diagnose`, body),
  failureAttribution: (id) => get(`/failures/${id}/attribution`),
  runFailureAttribution: (id, body = {}) => post(`/failures/${id}/attribution`, body),
  experimentAttributionSummary: (id) => get(`/experiments/${id}/attribution/summary`),
  runExperimentAttribution: (id, body = {}) => post(`/experiments/${id}/attribution`, body),

  recommendations: () => get('/recommendations'),
  recommendation: (id) => get(`/recommendations/${id}`),
  createRecommendation: (body) => post('/recommendations', body),

  reports: () => get('/reports'),
  report: (id) => get(`/reports/${id}`),
  createReport: (body) => post('/reports', body),
  deleteReport: (id) => del(`/reports/${id}`),
  exportUrl: (id, format) =>
    `${import.meta.env.VITE_API_BASE_URL || '/api'}/reports/${id}/export?format=${format}`,

  documents: (params) => get('/documents', { params }),
  uploadDocument: (formData) =>
    client
      .post('/documents/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      .then((r) => r.data),
  indexDocuments: (body) => post('/documents/index', body),
  previewRetrieval: (body) => post('/documents/preview', body),
  deleteDocument: (id) => del(`/documents/${id}`),

  calibrationQueue: (params) => get('/calibration/queue', { params }),
  upsertLabel: (body) => post('/calibration/labels', body),
  calibrationLabels: (params) => get('/calibration/labels', { params }),
  runCalibration: (body) => post('/calibration/run', body),
  calibrationRuns: (params) => get('/calibration/runs', { params }),
  calibrationRun: (id) => get(`/calibration/runs/${id}`),
  judgeReliability: (params) => get('/calibration/reliability', { params }),
}

export default api

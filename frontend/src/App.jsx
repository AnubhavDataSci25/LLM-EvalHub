import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'

import AppLayout from './components/layout/AppLayout'
import { EmptyState, ToastProvider } from './components/ui'
import { AuthProvider, useAuth } from './context/AuthContext'
import Benchmarks from './pages/Benchmarks'
import Calibration from './pages/Calibration'
import Compare from './pages/Compare'
import Dashboard from './pages/Dashboard'
import DatasetDetail from './pages/DatasetDetail'
import Datasets from './pages/Datasets'
import Documents from './pages/Documents'
import EvaluationDetail from './pages/EvaluationDetail'
import ExperimentDetail from './pages/ExperimentDetail'
import Experiments from './pages/Experiments'
import FailureDetail from './pages/FailureDetail'
import Failures from './pages/Failures'
import Landing from './pages/Landing'
import Login from './pages/Login'
import NewEvaluation from './pages/NewEvaluation'
import Recommendations from './pages/Recommendations'
import Register from './pages/Register'
import ReportDetail from './pages/ReportDetail'
import Reports from './pages/Reports'
import Settings from './pages/Settings'

const Documentation = lazy(() => import('./pages/Documentation'))

function DocsLoadingFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface">
      <div className="text-xs text-muted">Loading documentation...</div>
    </div>
  )
}

function ProtectedAppLayout({ children }) {
  const { user, isAuthEnabled, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-base">
        <div className="text-xs text-muted">Loading LLM-EvalHub...</div>
      </div>
    )
  }

  if (isAuthEnabled && !user) {
    return <Navigate to="/login" replace />
  }

  return <AppLayout>{children}</AppLayout>
}

function NotFound() {
  const location = useLocation()
  return (
    <EmptyState
      title="Page not found"
      description={`Nothing is routed at ${location.pathname}.`}
      action={
        <a href="/dashboard" className="btn-primary">
          Back to the dashboard
        </a>
      }
    />
  )
}

/** The landing page and auth pages render outside the app shell; everything else inside it. */
export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/documentation"
            element={
              <Suspense fallback={<DocsLoadingFallback />}>
                <Documentation />
              </Suspense>
            }
          />
          <Route
            path="/documentation/:sectionId"
            element={
              <Suspense fallback={<DocsLoadingFallback />}>
                <Documentation />
              </Suspense>
            }
          />
          <Route
            path="*"
            element={
              <ProtectedAppLayout>
                <Routes>
                  <Route path="/dashboard" element={<Dashboard />} />
                  <Route path="/datasets" element={<Datasets />} />
                  <Route path="/datasets/:id" element={<DatasetDetail />} />
                  <Route path="/benchmarks" element={<Benchmarks />} />
                  <Route path="/documents" element={<Documents />} />
                  <Route path="/evaluations/new" element={<NewEvaluation />} />
                  <Route path="/evaluations/:id" element={<EvaluationDetail />} />
                  <Route path="/experiments" element={<Experiments />} />
                  <Route path="/experiments/:id" element={<ExperimentDetail />} />
                  <Route path="/compare" element={<Compare />} />
                  <Route path="/failures" element={<Failures />} />
                  <Route path="/failures/:id" element={<FailureDetail />} />
                  <Route path="/recommendations" element={<Recommendations />} />
                  <Route path="/calibration" element={<Calibration />} />
                  <Route path="/reports" element={<Reports />} />
                  <Route path="/reports/:id" element={<ReportDetail />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route path="/index.html" element={<Navigate to="/dashboard" replace />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </ProtectedAppLayout>
            }
          />
        </Routes>
      </ToastProvider>
    </AuthProvider>
  )
}

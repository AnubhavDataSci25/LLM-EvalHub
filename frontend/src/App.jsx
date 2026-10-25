import { Navigate, Route, Routes, useLocation } from 'react-router-dom'

import AppLayout from './components/layout/AppLayout'
import { EmptyState, ToastProvider } from './components/ui'
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
import NewEvaluation from './pages/NewEvaluation'
import Recommendations from './pages/Recommendations'
import ReportDetail from './pages/ReportDetail'
import Reports from './pages/Reports'
import Settings from './pages/Settings'

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

/** The landing page renders outside the app shell; everything else inside it. */
export default function App() {
  return (
    <ToastProvider>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route
          path="*"
          element={
            <AppLayout>
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
            </AppLayout>
          }
        />
      </Routes>
    </ToastProvider>
  )
}

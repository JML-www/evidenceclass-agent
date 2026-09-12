import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '../app/AppShell'
import { AuthPage } from '../app/AuthPage'
import { JobsPage } from '../features/jobs/JobsPage'
import { NewAnalysisPage } from '../features/analysis/NewAnalysisPage'
import { RunPage } from '../features/run/RunPage'
import { EvidencePage } from '../features/evidence/EvidencePage'
import { ReviewPage } from '../features/review/ReviewPage'
import { ResultsPage } from '../features/results/ResultsPage'
import { KnowledgePage } from '../features/knowledge/KnowledgePage'
import { EvaluationPage } from '../features/evaluation/EvaluationPage'
import { SettingsPage } from '../features/settings/SettingsPage'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<AuthPage />} />
      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/jobs" replace />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/new" element={<NewAnalysisPage />} />
        <Route path="/runs/:jobId" element={<RunPage />} />
        <Route path="/evidence" element={<EvidencePage />} />
        <Route path="/reviews" element={<ReviewPage />} />
        <Route path="/results" element={<ResultsPage />} />
        <Route path="/knowledge" element={<KnowledgePage />} />
        <Route path="/evaluation" element={<EvaluationPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/jobs" replace />} />
      </Route>
    </Routes>
  )
}

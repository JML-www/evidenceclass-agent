export type JobStatus = 'QUEUED' | 'RUNNING' | 'NEEDS_REVIEW' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED'
export type AnalysisMode = 'IMAGE' | 'VIDEO' | 'STRUCTURED'

export type Job = {
  id: string
  title: string
  mode: AnalysisMode
  status: JobStatus
  progress: number
  createdAt: string
  duration?: string
  error?: string
  evidenceCount: number
}

export type AgentStep = {
  id: string
  name: string
  label: string
  status: 'completed' | 'running' | 'failed' | 'pending'
  duration?: string
  summary: string
  retryCount: number
}

export type Evidence = {
  id: string
  time: string
  source: string
  tag: string
  region: string
  review: '已确认' | '待复核' | '未知'
  observation: string
  deterministic: string
  explanation: string
  confidence: number
}

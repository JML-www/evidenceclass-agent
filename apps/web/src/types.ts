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

export type Citation = {
  evidence_id?: string
  citation_id?: string
  source_ref?: string
  document_id?: string
  chunk_id?: string
  page?: number
  version?: string
  fact?: string
  limitations?: string[]
}

export type ConversationMessage = {
  message_id: string
  conversation_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  citations: Citation[]
  evidence_available: boolean
  source?: string
  limitations: string[]
  boundary: Record<string, unknown>
  created_at?: string
}

export type Answer = {
  conversation_id: string
  user_message: ConversationMessage
  assistant_message: ConversationMessage
  answer: string
  citations: Citation[]
  evidence_available: boolean
  source: string
  limitations: string[]
  boundary: Record<string, unknown>
  summary_version: number
}

export type ReviewItem = {
  review_id: string
  job_id: string
  status: string
  decision?: string | null
  reason: string
  reviewer_id?: string | null
  revision: number
  original_observation: Record<string, unknown>
  revised_observation?: Record<string, unknown> | null
  evidence_ids: string[]
  created_at?: string
  decided_at?: string | null
}

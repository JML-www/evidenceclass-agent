import { mockAnswerCitations, mockEvidence, mockJobs, mockSteps } from './mock'
import type { AgentStep, Answer, Citation, ConversationMessage, Evidence, Job } from '../types'
import type { CreateJobRequest, JobResponse } from './openapi.generated'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
const USE_MOCK = import.meta.env.VITE_USE_MOCK_API !== 'false'
const mockConversationMessages = new Map<string, ConversationMessage[]>()

function authHeaders(init?: RequestInit): Headers {
  const headers = new Headers(init?.headers)
  if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const token = window.localStorage.getItem('evidenceclass.access_token')
  const workspace = window.localStorage.getItem('evidenceclass.workspace_id')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (workspace) headers.set('X-Workspace-ID', workspace)
  return headers
}

async function rawRequest(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${API_BASE}${path}`, { ...init, headers: authHeaders(init) })
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await rawRequest(path, init)
  if (!response.ok) throw new Error(`请求失败（${response.status}）`)
  return response.json() as Promise<T>
}

export async function listJobs(): Promise<Job[]> {
  if (USE_MOCK) return new Promise(resolve => setTimeout(() => resolve(mockJobs), 240))
  const jobs = await request<JobResponse[]>('/jobs')
  return jobs.map(job => ({ id: String(job.job_id), title: String((job as JobResponse & { title?: unknown }).title ?? `分析任务 · ${String(job.job_id).slice(0, 8)}`), mode: String(job.mode ?? 'video').toUpperCase() as Job['mode'], status: String(job.status ?? 'QUEUED').toUpperCase() as Job['status'], progress: Number(job.progress ?? 0), createdAt: formatDate(job.created_at), error: job.error_code ? String(job.error_code) : undefined, evidenceCount: 0 }))
}

function formatDate(value: unknown): string {
  if (!value) return '未知时间'
  const date = new Date(String(value))
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export async function getRun(jobId: string): Promise<{ job: Job; steps: AgentStep[] }> {
  if (USE_MOCK) return new Promise(resolve => setTimeout(() => resolve({ job: mockJobs[0], steps: mockSteps }), 180))
  const rawJob = await request<Record<string, unknown>>(`/jobs/${jobId}`)
  const runs = await request<Array<Record<string, unknown>>>(`/jobs/${jobId}/agent-runs`)
  const runId = runs.at(-1)?.run_id
  const rawSteps = runId ? await request<Array<Record<string, unknown>>>(`/agent-runs/${runId}/steps`) : []
  const job: Job = { id: String(rawJob.job_id), title: String(rawJob.title ?? `分析任务 · ${jobId.slice(0, 8)}`), mode: String(rawJob.mode ?? 'video').toUpperCase() as Job['mode'], status: String(rawJob.status ?? 'QUEUED').toUpperCase() as Job['status'], progress: Number(rawJob.progress ?? 0), createdAt: formatDate(rawJob.created_at), error: rawJob.error_code ? String(rawJob.error_code) : undefined, evidenceCount: 0 }
  const steps: AgentStep[] = rawSteps.map((step, index) => ({ id: String(step.step_id ?? index), name: String(step.node ?? `step_${index + 1}`), label: String(step.node ?? `执行节点 ${index + 1}`), status: normalizeStepStatus(step.status), summary: `结构化执行记录 · ${String(step.output_hash ?? '等待结果')}`, duration: undefined, retryCount: 0 }))
  return { job, steps }
}

function normalizeStepStatus(value: unknown): AgentStep['status'] {
  const status = String(value ?? '').toUpperCase()
  if (status.includes('SUCC') || status.includes('COMPLETE')) return 'completed'
  if (status.includes('FAIL')) return 'failed'
  if (status.includes('RUN')) return 'running'
  return 'pending'
}

export async function listEvidence(jobId = 'job_8f21'): Promise<Evidence[]> {
  if (USE_MOCK) return new Promise(resolve => setTimeout(() => resolve(mockEvidence), 180))
  const items = await request<Array<Record<string, unknown>>>(`/jobs/${jobId}/evidence`)
  return items.map((item, index) => ({ id: String(item.evidence_id ?? `EV-${index + 1}`), time: '未知时间', source: String(item.source_ref ?? 'unknown'), tag: '观察', region: '未标注区域', review: '未知', observation: String(item.fact ?? '未提供原始观察'), deterministic: '后端未返回确定性字段', explanation: String(item.limitations ?? '暂无解释'), confidence: 0 }))
}

export async function listAssets(jobId: string): Promise<Array<Record<string, unknown>>> {
  if (USE_MOCK) return []
  return request<Array<Record<string, unknown>>>(`/jobs/${jobId}/assets`)
}

export async function initUpload(jobId: string, expectedMime: string, maxSizeBytes: number, role = 'source'): Promise<Record<string, unknown>> {
  if (USE_MOCK) return { upload_id: `upload_${Date.now()}`, upload_url: '', expected_mime: expectedMime, max_size_bytes: maxSizeBytes }
  return request<Record<string, unknown>>(`/jobs/${jobId}/assets/uploads`, { method: 'POST', body: JSON.stringify({ expected_mime: expectedMime, max_size_bytes: maxSizeBytes, role }) })
}

export async function completeUpload(jobId: string, uploadId: string, expectedSizeBytes: number, expectedSha256: string): Promise<Record<string, unknown>> {
  if (USE_MOCK) return { asset_id: `asset_${Date.now()}`, size_bytes: expectedSizeBytes, sha256: expectedSha256 }
  return request<Record<string, unknown>>(`/jobs/${jobId}/assets/uploads/${uploadId}/complete`, { method: 'POST', body: JSON.stringify({ expected_size_bytes: expectedSizeBytes, expected_sha256: expectedSha256 }) })
}

export async function uploadToSignedUrl(url: string, file: File, onProgress?: (progress: number) => void): Promise<void> {
  if (!url) return
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', url)
    xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream')
    xhr.upload.onprogress = event => { if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100)) }
    xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`上传失败（${xhr.status}）`))
    xhr.onerror = () => reject(new Error('上传连接失败'))
    xhr.send(file)
  })
}

export async function sha256Hex(file: File): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
}

export async function listArtifacts(jobId: string): Promise<Array<Record<string, unknown>>> {
  if (USE_MOCK) return []
  return request<Array<Record<string, unknown>>>(`/jobs/${jobId}/artifacts`)
}

export type Conversation = {
  conversation_id: string
  workspace_id: string
  job_id?: string
  title: string
  summary_version: number
  summary?: Record<string, unknown> | null
  created_at?: string
  updated_at?: string
}

export async function createConversation(title: string, jobId?: string): Promise<Conversation> {
  if (USE_MOCK) {
    const conversationId = `conversation_${Date.now()}`
    mockConversationMessages.set(conversationId, [])
    return {
      conversation_id: conversationId,
      workspace_id: 'workspace_mock',
      job_id: jobId,
      title,
      summary_version: 0,
    }
  }
  return request<Conversation>('/conversations', {
    method: 'POST',
    body: JSON.stringify({ title, job_id: jobId ?? null }),
  })
}

export async function listConversations(jobId?: string): Promise<Conversation[]> {
  if (USE_MOCK) return []
  const suffix = jobId ? `?job_id=${encodeURIComponent(jobId)}` : ''
  return request<Conversation[]>(`/conversations${suffix}`)
}

export async function listMessages(conversationId: string): Promise<ConversationMessage[]> {
  if (USE_MOCK) return [...(mockConversationMessages.get(conversationId) ?? [])]
  return request<ConversationMessage[]>(`/conversations/${conversationId}/messages`)
}

export async function askReport(conversationId: string, content: string): Promise<Answer> {
  if (USE_MOCK) {
    // The offline adapter exposes both grounded and unavailable paths.  A
    // clearly marked request lets E2E/demo checks exercise the refusal state
    // without pretending that evidence exists.
    const unavailable = /证据不足|无证据|无法判断|猜测/.test(content)
    const citations: Citation[] = unavailable ? [] : mockAnswerCitations
    const answer = citations.length
      ? `基于当前任务证据：${citations.map(item => item.fact).join('；')}。该回答仅描述可见事实。`
      : '证据不足，无法判断。请先完成分析或补充授权材料。'
    const boundary = { conversation_id: conversationId, allowed_sources: ['evidence_items'], limitations: ['仅基于当前任务证据'] }
    const userMessage: ConversationMessage = {
      message_id: `message_${Date.now()}_u`, conversation_id: conversationId, role: 'user', content,
      citations: [], evidence_available: false, source: 'user', limitations: [], boundary,
    }
    const assistantMessage: ConversationMessage = {
      message_id: `message_${Date.now()}_a`, conversation_id: conversationId, role: 'assistant', content: answer,
      citations, evidence_available: citations.length > 0, source: citations.length ? 'deterministic/mock' : 'unavailable_fallback',
      limitations: citations.length ? ['仅基于当前任务证据'] : ['当前任务没有可用证据'], boundary,
    }
    const stored = mockConversationMessages.get(conversationId) ?? []
    mockConversationMessages.set(conversationId, [...stored, userMessage, assistantMessage])
    return { conversation_id: conversationId, user_message: userMessage, assistant_message: assistantMessage,
      answer, citations, evidence_available: citations.length > 0, source: assistantMessage.source ?? 'deterministic/mock',
      limitations: assistantMessage.limitations, boundary, summary_version: 1 }
  }
  return request<Answer>(`/conversations/${conversationId}/ask`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  })
}

export async function getConversationSummary(conversationId: string): Promise<Record<string, unknown>> {
  if (USE_MOCK) {
    const messages = mockConversationMessages.get(conversationId) ?? []
    return {
      conversation_id: conversationId,
      version: Math.ceil(messages.length / 2),
      summary: messages.map(message => `${message.role}: ${message.content}`).join('\n') || '暂无会话摘要。',
    }
  }
  return request<Record<string, unknown>>(`/conversations/${conversationId}/summary`)
}

export type FeedbackPayload = {
  decision: 'APPROVED' | 'REJECTED' | 'MODIFIED' | 'MATERIALS_REQUESTED'
  reason: string
  original_observation?: Record<string, unknown>
  revised_observation?: Record<string, unknown>
  evidence_ids?: string[]
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

export async function submitFeedback(jobId: string, payload: FeedbackPayload): Promise<ReviewItem> {
  if (USE_MOCK) {
    return {
      review_id: `review_${Date.now()}`,
      job_id: jobId,
      status: 'DECIDED',
      decision: payload.decision,
      reason: payload.reason,
      revision: 1,
      original_observation: payload.original_observation ?? {},
      revised_observation: payload.revised_observation,
      evidence_ids: payload.evidence_ids ?? [],
    }
  }
  return request<ReviewItem>(`/jobs/${jobId}/feedback`, { method: 'POST', body: JSON.stringify(payload) })
}

export async function listReviewItems(filters: { jobId?: string; decision?: string; reviewerId?: string } = {}): Promise<ReviewItem[]> {
  if (USE_MOCK) return []
  const query = new URLSearchParams()
  if (filters.jobId) query.set('job_id', filters.jobId)
  if (filters.decision) query.set('decision', filters.decision)
  if (filters.reviewerId) query.set('reviewer_id', filters.reviewerId)
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return request<ReviewItem[]>(`/review-items${suffix}`)
}

export async function getReviewStats(jobId?: string): Promise<Record<string, unknown>> {
  if (USE_MOCK) return { total: 0, pending: 0, decided: 0, by_decision: {} }
  return request<Record<string, unknown>>(`/review-items/stats${jobId ? `?job_id=${encodeURIComponent(jobId)}` : ''}`)
}

export async function getReviewAudit(reviewId: string): Promise<Array<Record<string, unknown>>> {
  if (USE_MOCK) return []
  return request<Array<Record<string, unknown>>>(`/review-items/${reviewId}/audit`)
}

export async function decideReview(reviewId: string, decision: 'APPROVED' | 'REJECTED' | 'MODIFIED' | 'MATERIALS_REQUESTED', note = '', revisedObservation?: Record<string, unknown>): Promise<Record<string, unknown>> {
  if (USE_MOCK) return { review_id: reviewId, status: 'DECIDED', decision }
  return request<Record<string, unknown>>(`/review-items/${reviewId}/decision`, { method: 'POST', body: JSON.stringify({ decision, note, revised_observation: revisedObservation }) })
}

export async function createJob(title: string, mode: Job['mode']): Promise<Job> {
  if (!USE_MOCK) {
    const payload: CreateJobRequest = { mode: mode.toLowerCase() as CreateJobRequest['mode'], goal: title || 'analyze classroom evidence', metadata: { title } }
    const raw = await request<JobResponse>('/jobs', { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify(payload) })
    return { id: String(raw.job_id), title: title || '未命名课堂分析', mode, status: String(raw.status ?? 'QUEUED').toUpperCase() as Job['status'], progress: Number(raw.progress ?? 0), createdAt: formatDate(raw.created_at), evidenceCount: 0 }
  }
  const job: Job = { id: `job_${Math.random().toString(16).slice(2, 8)}`, title, mode, status: 'QUEUED', progress: 0, createdAt: '刚刚', evidenceCount: 0 }
  mockJobs.unshift(job)
  return job
}

export type JobEvent = { eventId: number; type: string; payload: Record<string, unknown> }

/**
 * Fetch-based SSE seam. The UI can attach this in phase ten without changing
 * the API contract; Last-Event-ID is preserved for reconnects.
 */
export async function streamJobEvents(jobId: string, onEvent: (event: JobEvent) => void, signal?: AbortSignal): Promise<void> {
  if (USE_MOCK) return
  const lastEventId = window.localStorage.getItem(`evidenceclass.last_event.${jobId}`) ?? '0'
  const response = await rawRequest(`/jobs/${jobId}/events`, { headers: { Accept: 'text/event-stream', 'Last-Event-ID': lastEventId }, signal })
  if (!response.ok) throw new Error(`SSE 请求失败（${response.status}）`)
  if (!response.body) throw new Error('SSE 响应没有 body')
  const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''
  while (true) {
    const chunk = await reader.read(); if (chunk.done) break
    buffer += decoder.decode(chunk.value, { stream: true })
    const blocks = buffer.split('\n\n'); buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const id = block.match(/^id:\s*(\d+)/m)?.[1]; const type = block.match(/^event:\s*(.+)$/m)?.[1] ?? 'message'; const data = block.match(/^data:\s*(.+)$/m)?.[1]
      if (!id || !data) continue
      window.localStorage.setItem(`evidenceclass.last_event.${jobId}`, id)
      onEvent({ eventId: Number(id), type, payload: JSON.parse(data) as Record<string, unknown> })
    }
  }
}

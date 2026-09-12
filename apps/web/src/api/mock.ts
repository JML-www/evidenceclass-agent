import type { AgentStep, Citation, Evidence, Job, ReviewItem } from '../types'

export const mockJobs: Job[] = [
  { id: 'job_8f21', title: '高一数学 · 函数单调性', mode: 'VIDEO', status: 'NEEDS_REVIEW', progress: 82, createdAt: '今天 09:42', duration: '18:32', evidenceCount: 14 },
  { id: 'job_7a90', title: '高二物理 · 电磁感应', mode: 'IMAGE', status: 'SUCCEEDED', progress: 100, createdAt: '昨天 16:18', duration: '00:12', evidenceCount: 8 },
  { id: 'job_6cc4', title: '课堂板书快照', mode: 'STRUCTURED', status: 'RUNNING', progress: 54, createdAt: '昨天 15:03', evidenceCount: 3 },
  { id: 'job_5d17', title: '初一英语 · 口语互动', mode: 'VIDEO', status: 'FAILED', progress: 36, createdAt: '08-21 11:20', duration: '05:44', error: 'MEDIA_DECODE_TIMEOUT', evidenceCount: 0 },
  { id: 'job_4e08', title: '高三化学 · 实验演示', mode: 'VIDEO', status: 'CANCELLED', progress: 22, createdAt: '08-20 10:11', duration: '02:05', evidenceCount: 2 }
]

export const mockSteps: AgentStep[] = [
  { id: 's1', name: 'ingest_media', label: '接收媒体', status: 'completed', duration: '1.8s', summary: '已校验 MP4 容器、时长和隐私策略', retryCount: 0 },
  { id: 's2', name: 'extract_frames', label: '抽取关键帧', status: 'completed', duration: '8.4s', summary: '按 2s 间隔抽取 558 帧，生成可追溯 frame_id', retryCount: 0 },
  { id: 's3', name: 'transcribe', label: '语音转写', status: 'completed', duration: '24.1s', summary: 'ASR 置信度 0.94，保留原始片段时间戳', retryCount: 1 },
  { id: 's4', name: 'observe_media', label: '观察课堂行为', status: 'running', summary: '正在聚合座位区域的注意力变化', retryCount: 0 },
  { id: 's5', name: 'verify_claims', label: '校验结论', status: 'pending', summary: '等待观察结果后执行证据覆盖检查', retryCount: 0 },
  { id: 's6', name: 'compose_report', label: '生成报告', status: 'pending', summary: '输出概览、证据和行动建议', retryCount: 0 }
]

export const mockEvidence: Evidence[] = [
  { id: 'EV-042', time: '00:04:18', source: 'camera-a.mp4 · frame_129', tag: '注意力', region: '左侧第二排', review: '待复核', observation: '学生抬头看向讲台，持续约 12 秒', deterministic: '视线方向与身体朝向一致', explanation: '可能对应教师提问后的全班关注窗口', confidence: 0.91 },
  { id: 'EV-041', time: '00:03:52', source: 'camera-a.mp4 · frame_116', tag: '互动', region: '中间区域', review: '已确认', observation: '教师与学生发生举手互动', deterministic: '检测到手臂抬起并保持 3 秒', explanation: '支持“课堂互动密度上升”的报告结论', confidence: 0.88 },
  { id: 'EV-039', time: '00:02:16', source: 'audio · asr_034', tag: '讲授', region: '全班', review: '未知', observation: '“请大家先独立思考这道题”', deterministic: 'ASR 时间戳 00:02:16–00:02:20', explanation: '仅作为语境，不单独推断学习效果', confidence: 0.97 }
]

/** Citation fixtures shared by the offline report-Q&A adapter and demos. */
export const mockAnswerCitations: Citation[] = mockEvidence.slice(0, 2).map(item => ({
  evidence_id: item.id,
  source_ref: item.source,
  fact: item.observation,
}))

/** Review records use UUID-shaped ids just like the real API. */
export const mockReviewItems: ReviewItem[] = [
  {
    review_id: '8f6b6b5a-2d65-4e8f-9f5f-000000000042',
    job_id: 'job_8f21',
    status: 'PENDING',
    decision: null,
    reason: '模型观察需要人工确认',
    revision: 0,
    original_observation: {
      title: '注意力变化',
      text: '学生抬头看向讲台，持续约 12 秒',
      time: '00:04:18',
      score: '中风险',
      model_value: 'attention = present',
      confidence: 0.91,
      source: 'camera-a · frame_129',
    },
    revised_observation: null,
    evidence_ids: ['EV-042'],
  },
  {
    review_id: '8f6b6b5a-2d65-4e8f-9f5f-000000000035',
    job_id: 'job_8f21',
    status: 'PENDING',
    decision: null,
    reason: '低置信度互动观察',
    revision: 0,
    original_observation: {
      title: '互动中断',
      text: '小组讨论后出现短暂沉默',
      time: '00:01:44',
      score: '低风险',
      model_value: 'interaction = paused',
      confidence: 0.76,
      source: 'camera-a · frame_052',
    },
    revised_observation: null,
    evidence_ids: ['EV-039'],
  },
]

export const mockAnalysisResult = {
  schemaVersion: 'engine.v0.1',
  taskId: 'job_8f21',
  analysisMode: 'video',
  summary: {
    metrics: {
      focus: 81,
      participation: 78,
      interaction: 67,
      teacherGuidance: 72,
      abnormalRate: 6,
    },
    overall: 76,
    rubricSource: 'weighted_average',
    normalizedWeights: {},
  },
  evidence: [
    { evidence_id: 'EV-042', observation: '学生抬头看向讲台，持续约 12 秒' },
    { evidence_id: 'EV-041', observation: '教师与学生发生举手互动' },
  ],
  actions: [
    {
      actionId: 'a1',
      metricKey: 'interaction',
      currentValue: 67,
      suggestion: '增加小组互评与轮流发言环节，提升互动密度',
      evidenceIds: ['EV-041'],
    },
  ],
}

export const mockArtifacts = [
  {
    artifact_id: 'artifact-analysis',
    kind: 'analysis_result',
    mime: 'application/json',
    version: 'v1',
    size_bytes: JSON.stringify(mockAnalysisResult).length,
    sha256: 'mock',
    download_url: `data:application/json;charset=utf-8,${encodeURIComponent(
      JSON.stringify(mockAnalysisResult),
    )}`,
  },
  { artifact_id: 'artifact-report', kind: 'report_markdown', mime: 'text/markdown', version: 'v1', size_bytes: 2480, sha256: 'mock', download_url: 'data:text/markdown;charset=utf-8,%23%20灵眸智课分析报告%0A%0A报告由证据驱动生成，未写入任何固定分数。%0A%0A本报告的每一条结论都应可回溯到证据条目。' },
  { artifact_id: 'artifact-dashboard', kind: 'dashboard_html', mime: 'text/html', version: 'v1', size_bytes: 5120, sha256: 'mock', download_url: 'data:text/html;charset=utf-8,%3Chtml%3E%3Cbody%3E%3Ch1%3E灵眸智课分析报告%3C%2Fh1%3E%3Cp%3E本报告由证据驱动生成。%3C%2Fp%3E%3C%2Fbody%3E%3C%2Fhtml%3E' },
  { artifact_id: 'artifact-evidence', kind: 'evidence_csv', mime: 'text/csv', version: 'v1', size_bytes: 860, sha256: 'mock', download_url: 'data:text/csv;charset=utf-8,evidence_id%2Cfact%0AEV-042%2C学生抬头看向讲台' },
]

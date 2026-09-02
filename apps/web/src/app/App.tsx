import React from 'react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { askReport, completeUpload, createConversation, createJob, decideReview, getRun, initUpload, listEvidence, listJobs, sha256Hex, uploadToSignedUrl } from '../api/client'
import type { AgentStep, Answer, Evidence, Job, JobStatus } from '../types'
import '../styles/tokens.css'
import '../styles/global.css'

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 15_000 } } })

const statusText: Record<JobStatus, string> = { QUEUED: '排队中', RUNNING: '运行中', NEEDS_REVIEW: '待复核', SUCCEEDED: '成功', FAILED: '失败', CANCELLED: '已取消' }
const modeText = { IMAGE: '单图', VIDEO: '短视频', STRUCTURED: '结构化' }

function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const nav = [
    { to: '/jobs', label: '任务中心', icon: '▦' },
    { to: '/new', label: '新建分析', icon: '+' },
    { to: '/runs/job_8f21', label: 'Agent Run', icon: '◌' },
    { to: '/evidence', label: '证据浏览器', icon: '⌁' },
    { to: '/reviews', label: '复核工作台', icon: '✓' },
    { to: '/results', label: '结果与问答', icon: '⌘' }
  ]
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">L</span><span><b>灵眸智课</b><small>EvidenceClass Agent</small></span></div>
      <div className="workspace-switcher"><span className="avatar">王</span><span><b>王子豪的工作区</b><small>个人项目</small></span><span className="chevron">⌄</span></div>
      <nav aria-label="主导航">{nav.map(item => <Link key={item.to} to={item.to} className={location.pathname === item.to ? 'nav-item active' : 'nav-item'}><span className="nav-icon" aria-hidden="true">{item.icon}</span>{item.label}</Link>)}</nav>
      <div className="sidebar-bottom"><div className="system-status"><span className="status-dot" /> API 与 Worker <span className="status-ok">正常</span></div><a href="https://github.com" target="_blank" rel="noreferrer" className="help-link">文档与帮助 ↗</a></div>
    </aside>
    <main className="main-content">
      <header className="topbar"><div className="breadcrumb">灵眸智课 <span>/</span> {location.pathname.includes('new') ? '新建分析' : location.pathname.includes('runs') ? 'Agent Run 详情' : location.pathname.includes('evidence') ? '证据浏览器' : location.pathname.includes('reviews') ? '复核工作台' : location.pathname.includes('results') ? '结果与问答' : '任务中心'}</div><div className="top-actions"><button className="icon-button" aria-label="通知">♢<span className="notification-dot" /></button><button className="profile-button"><span className="avatar small">王</span><span>王子豪</span><span className="chevron">⌄</span></button></div></header>
      <Routes><Route path="/jobs" element={<JobsPage />} /><Route path="/new" element={<NewAnalysisPage />} /><Route path="/runs/:jobId" element={<RunPage />} /><Route path="/evidence" element={<EvidencePage />} /><Route path="/reviews" element={<ReviewPage />} /><Route path="/results" element={<ResultsPage />} /><Route path="*" element={<Navigate to="/jobs" replace />} /></Routes>
    </main>
  </div>
}

function PageHeader({ eyebrow, title, description, action }: { eyebrow: string; title: string; description?: string; action?: React.ReactNode }) { return <div className="page-header"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</div> }

function StatusBadge({ status }: { status: JobStatus }) { return <span className={`status-badge status-${status.toLowerCase()}`}><span className="status-dot" />{statusText[status]}</span> }

function JobsPage() {
  const navigate = useNavigate()
  const jobsQuery = useQuery({ queryKey: ['jobs'], queryFn: listJobs })
  const [filter, setFilter] = React.useState<'ALL' | JobStatus>('ALL')
  const jobs = (jobsQuery.data ?? []).filter(job => filter === 'ALL' || job.status === filter)
  return <div className="page"><PageHeader eyebrow="WORKSPACE" title="任务中心" description="管理课堂分析任务，追踪每一次 Agent 执行与证据产物。" action={<button className="primary-button" onClick={() => navigate('/new')}>＋ 新建分析</button>} />
    <div className="metric-grid"><Metric label="全部任务" value={jobsQuery.data?.length ?? '—'} hint="最近 30 天" icon="◫" /><Metric label="运行中" value={jobsQuery.data?.filter(j => j.status === 'RUNNING').length ?? '—'} hint="队列状态实时同步" icon="◌" tone="blue" /><Metric label="待复核" value={jobsQuery.data?.filter(j => j.status === 'NEEDS_REVIEW').length ?? '—'} hint="需要人工确认" icon="✓" tone="amber" /><Metric label="证据覆盖率" value="91%" hint="已完成任务平均值" icon="⌁" tone="green" /></div>
    <section className="panel"><div className="panel-toolbar"><div className="tabs" role="tablist">{(['ALL', 'RUNNING', 'NEEDS_REVIEW', 'SUCCEEDED', 'FAILED'] as const).map(value => <button key={value} className={filter === value ? 'tab active' : 'tab'} onClick={() => setFilter(value)}>{value === 'ALL' ? '全部' : statusText[value]}</button>)}</div><button className="secondary-button">筛选 <span>☷</span></button></div>
      {jobsQuery.isLoading && <LoadingState label="正在加载任务…" />}{jobsQuery.isError && <ErrorState onRetry={() => jobsQuery.refetch()} />}{!jobsQuery.isLoading && !jobsQuery.isError && jobs.length === 0 && <EmptyState onCreate={() => navigate('/new')} />}
      {!jobsQuery.isLoading && !jobsQuery.isError && jobs.length > 0 && <div className="table-wrap"><table><thead><tr><th>任务</th><th>模式</th><th>状态</th><th>进度</th><th>创建时间</th><th>证据</th><th aria-label="操作" /></tr></thead><tbody>{jobs.map(job => <tr key={job.id}><td><button className="table-link" onClick={() => navigate(`/runs/${job.id}`)}><span className="job-avatar">{job.mode === 'VIDEO' ? '▶' : job.mode === 'IMAGE' ? '▧' : '≡'}</span><span><b>{job.title}</b><small>{job.id}</small></span></button></td><td><span className="mode-pill">{modeText[job.mode]}</span></td><td><StatusBadge status={job.status} />{job.error && <small className="error-code">{job.error}</small>}</td><td><div className="progress-cell"><div className="progress-track"><span style={{ width: `${job.progress}%` }} /></div><small>{job.progress}%</small></div></td><td className="muted">{job.createdAt}</td><td className="muted">{job.evidenceCount ? `${job.evidenceCount} 条` : '—'}</td><td><button className="row-menu" aria-label={`打开 ${job.title} 操作菜单`}>•••</button></td></tr>)}</tbody></table></div>}
    </section>
  </div>
}

function NewAnalysisPage() {
  const navigate = useNavigate(); const [mode, setMode] = React.useState<Job['mode']>('VIDEO'); const [title, setTitle] = React.useState(''); const [file, setFile] = React.useState<File | null>(null); const [progress, setProgress] = React.useState(0); const [submitted, setSubmitted] = React.useState(false); const [submitError, setSubmitError] = React.useState('')
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setSubmitted(true); setSubmitError('')
    try {
      const job = await createJob(title || '未命名课堂分析', mode)
      if (file && import.meta.env.VITE_USE_MOCK_API === 'false') {
        const ticket = await initUpload(job.id, file.type || 'application/octet-stream', file.size)
        const uploadUrl = String(ticket.upload_url ?? '')
        await uploadToSignedUrl(uploadUrl, file, setProgress)
        await completeUpload(job.id, String(ticket.upload_id), file.size, await sha256Hex(file))
      } else {
        for (let value = 10; value <= 100; value += 10) { await new Promise(r => setTimeout(r, 30)); setProgress(value) }
      }
      navigate(`/runs/${job.id}`)
    } catch (error) {
      setSubmitted(false); setSubmitError(error instanceof Error ? error.message : '创建分析失败')
    }
  }
  return <div className="page narrow"><PageHeader eyebrow="NEW ANALYSIS" title="新建分析" description="上传课堂素材，Agent 会生成带时间戳的可核查证据。" /><form className="form-layout" onSubmit={submit}><section className="panel form-panel"><h2>选择分析模式</h2><div className="mode-cards">{(['VIDEO', 'IMAGE', 'STRUCTURED'] as const).map(value => <button type="button" key={value} className={mode === value ? 'mode-card selected' : 'mode-card'} onClick={() => setMode(value)}><span className="mode-icon">{value === 'VIDEO' ? '▶' : value === 'IMAGE' ? '▧' : '≡'}</span><span><b>{modeText[value]}</b><small>{value === 'VIDEO' ? '抽帧、ASR 与行为观察' : value === 'IMAGE' ? '板书或课堂快照' : '直接提交结构化特征'}</small></span>{mode === value && <span className="check">✓</span>}</button>)}</div><label className="field-label" htmlFor="title">分析名称<span>（可选）</span></label><input id="title" value={title} onChange={e => setTitle(e.target.value)} placeholder="例如：高一数学 · 函数单调性" /><label className="field-label" htmlFor="media">上传媒体</label><label className={file ? 'dropzone has-file' : 'dropzone'} htmlFor="media"><input id="media" type="file" accept={mode === 'VIDEO' ? 'video/*' : mode === 'IMAGE' ? 'image/*' : '.json,.csv'} onChange={e => setFile(e.target.files?.[0] ?? null)} />{file ? <><span className="upload-icon success">✓</span><b>{file.name}</b><small>{(file.size / 1024 / 1024).toFixed(2)} MB · 已就绪</small></> : <><span className="upload-icon">↥</span><b>拖拽文件到这里，或点击选择</b><small>支持 {mode === 'VIDEO' ? 'MP4、MOV，最大 2GB' : mode === 'IMAGE' ? 'PNG、JPG，最大 20MB' : 'JSON、CSV，最大 10MB'}</small></>}</label>{submitted && <div className="upload-progress"><div className="progress-track"><span style={{ width: `${progress}%` }} /></div><small>{progress < 100 ? `上传中 ${progress}%` : '上传完成'}</small></div>}{submitError && <div className="form-error" role="alert">{submitError}</div>}<div className="privacy-note"><span>⌾</span><p><b>隐私与能力边界</b><br />媒体默认仅保存在当前工作区。模型输出是辅助观察，不等同于对学生的诊断；所有报告结论都必须关联 Evidence。</p></div><button className="primary-button submit-button" type="submit" disabled={submitted}>{submitted ? '正在创建任务…' : '开始分析 →'}</button></section><aside className="panel side-note"><h3>分析流程</h3>{['媒体校验与抽帧', 'ASR / OCR / 视觉观察', '证据校验与报告生成', '人工复核与结果导出'].map((step, i) => <div className="flow-step" key={step}><span>{i + 1}</span><p>{step}<small>{['约 10 秒', '按素材时长', '自动执行', '可选'][i]}</small></p></div>)}</aside></form></div>
}

function RunPage() { const { jobId = 'job_8f21' } = useParams(); const runQuery = useQuery({ queryKey: ['run', jobId], queryFn: () => getRun(jobId) }); const data = runQuery.data; return <div className="page"><PageHeader eyebrow="AGENT RUN" title={data?.job.title ?? 'Agent Run 详情'} description={`${jobId} · 结构化执行记录，不展示模型私有思维链。`} action={<div className="header-actions"><button className="secondary-button">取消任务</button><button className="primary-button">重新运行</button></div>} />{runQuery.isLoading ? <LoadingState label="正在载入执行时间线…" /> : runQuery.isError || !data ? <ErrorState onRetry={() => runQuery.refetch()} /> : <div className="run-grid"><section className="panel"><div className="run-summary"><div><StatusBadge status={data.job.status} /><h2>执行进度</h2></div><strong>{data.job.progress}%</strong></div><div className="big-progress"><span style={{ width: `${data.job.progress}%` }} /></div><div className="step-list">{data.steps.map(step => <StepRow key={step.id} step={step} />)}</div></section><aside className="run-side"><section className="panel"><h3>资源摘要</h3><KeyValue label="Provider" value="local-fake" /><KeyValue label="Model" value="deterministic-v1" /><KeyValue label="版本" value="runtime@0.8" /><KeyValue label="Token 用量" value="12,480" /><KeyValue label="预估费用" value="$0.00" /><KeyValue label="剩余预算" value="$0.18" /></section><section className="panel callout"><span>ⓘ</span><p>时间线只记录结构化计划、工具输入摘要和结果摘要，不暴露模型私有思维链。</p></section></aside></div>}</div> }

function EvidencePage() { const evidenceQuery = useQuery({ queryKey: ['evidence'], queryFn: () => listEvidence() }); const [selected, setSelected] = React.useState<string | null>(() => window.localStorage.getItem('evidenceclass.selected_evidence')); const [tag, setTag] = React.useState('全部标签'); const evidence = (evidenceQuery.data ?? []).filter(item => tag === '全部标签' || item.tag === tag); const current = evidence.find(item => item.id === selected) ?? evidence[0]; return <div className="page"><PageHeader eyebrow="EVIDENCE" title="证据浏览器" description="每个结论都能回到原始帧、ASR 片段或确定性结果。" action={<div className="header-actions"><select value={tag} onChange={e => setTag(e.target.value)}><option>全部标签</option><option>注意力</option><option>互动</option><option>讲授</option></select><button className="secondary-button">导出证据清单 ↓</button></div>} /><div className="evidence-layout"><section className="panel evidence-list"><div className="panel-toolbar"><b>{evidence.length} 条证据</b><span className="muted">按时间倒序</span></div>{evidenceQuery.isLoading ? <LoadingState label="正在加载证据…" /> : evidence.map(item => <button key={item.id} className={current?.id === item.id ? 'evidence-row selected' : 'evidence-row'} onClick={() => { setSelected(item.id); window.localStorage.setItem('evidenceclass.selected_evidence', item.id) }}><div className="evidence-time">{item.time}<small>{item.id}</small></div><div className="evidence-body"><div><span className="tag">{item.tag}</span><span className={`review-state review-${item.review === '已确认' ? 'done' : item.review === '待复核' ? 'pending' : 'unknown'}`}>{item.review}</span></div><b>{item.observation}</b><small>{item.region} · 置信度 {Math.round(item.confidence * 100)}%</small></div><span className="row-arrow">›</span></button>)}</section><section className="panel evidence-detail">{current ? <><div className="detail-head"><div><span className="eyebrow">{current.id} · {current.source}</span><h2>{current.time} <span className="tag">{current.tag}</span></h2></div><button className="icon-button" aria-label="更多证据操作">•••</button></div><div className="media-frame"><div className="frame-overlay">原始帧 · {current.time}</div><div className="classroom-illustration"><div className="board" /><div className="desk-row one" /><div className="desk-row two" /><div className="desk-row three" /><span className="focus-ring" /></div><button className="play-button" aria-label="跳转到视频时间点">▶</button></div><div className="legend"><span><i className="dot raw" />原始观察</span><span><i className="dot deterministic" />确定性结果</span><span><i className="dot explanation" />LLM 解释</span></div><div className="evidence-copy"><InfoBlock title="原始观察" text={current.observation} /><InfoBlock title="确定性结果" text={current.deterministic} /><InfoBlock title="LLM 解释 · 仅供参考" text={current.explanation} muted /></div></> : <EmptyState />}</section></div></div> }

function ReviewPage() { const [selected, setSelected] = React.useState(0); const [note, setNote] = React.useState(''); const [decisionState, setDecisionState] = React.useState(''); const items = [{ id: 'EV-042', title: '注意力变化', score: '中风险', time: '00:04:18', text: '学生抬头看向讲台，持续约 12 秒' }, { id: 'EV-035', title: '互动中断', score: '低风险', time: '00:01:44', text: '小组讨论后出现短暂沉默' }]; const current = items[selected]; const onDecision = async (decision: 'APPROVED' | 'REJECTED' | 'MODIFIED') => { setDecisionState('提交中…'); try { await decideReview(current.id, decision, note); setDecisionState('已记录 · ' + decision) } catch (error) { setDecisionState(error instanceof Error ? error.message : '提交失败') } }; return <div className="page full-height"><PageHeader eyebrow="HUMAN IN THE LOOP" title="复核工作台" description="确认、修正或拒绝模型观察；每次决策都会保留原值与修订值。" action={<span className="review-counter">待处理 2</span>} /><div className="review-layout"><section className="panel review-queue"><div className="panel-toolbar"><b>待复核队列</b><button className="row-menu" aria-label="排序">⇅</button></div>{items.map((item, i) => <button key={item.id} className={selected === i ? 'queue-item selected' : 'queue-item'} onClick={() => setSelected(i)}><div className="queue-marker">{i + 1}</div><div><b>{item.title}</b><small>{item.id} · {item.time}</small><span className="risk-pill">{item.score}</span></div><span>›</span></button>)}</section><section className="panel review-media"><div className="media-frame tall"><div className="frame-overlay">视频上下文 · {current.time}</div><div className="classroom-illustration"><div className="board" /><div className="desk-row one" /><div className="desk-row two" /><div className="desk-row three" /><span className="focus-ring" /></div><div className="video-controls"><span>▶</span><div className="progress-track"><span style={{ width: '38%' }} /></div><span>{current.time} / 18:32</span></div></div><div className="context-strip"><span>前 10 秒</span><span className="current-context">当前证据</span><span>后 10 秒</span></div></section><section className="panel decision-panel"><span className="eyebrow">{current.id} · 模型观察</span><h2>{current.title}</h2><p className="decision-copy">{current.text}</p><div className="decision-grid"><KeyValue label="模型值" value="attention = present" /><KeyValue label="置信度" value="91%" /><KeyValue label="来源" value="camera-a · frame_129" /></div><label className="field-label" htmlFor="review-reason">审核理由</label><textarea id="review-reason" value={note} onChange={event => setNote(event.target.value)} placeholder="补充你确认或修正的依据…" /><div className="decision-actions"><button className="secondary-button" onClick={() => onDecision('REJECTED')}>拒绝</button><button className="secondary-button" onClick={() => onDecision('MODIFIED')}>修正字段</button><button className="primary-button" onClick={() => onDecision('APPROVED')}>确认并继续 ✓</button></div><small className="audit-note">{decisionState || '提交后将写入审计日志，并恢复等待中的 Agent 节点。'}</small></section></div></div> }

function ResultsPage() { return <div className="page"><PageHeader eyebrow="RESULT" title="结果与问答" description="高一数学 · 函数单调性 · job_8f21" action={<div className="header-actions"><button className="secondary-button">查看原始报告</button><button className="primary-button">下载报告 ↓</button></div>} /><div className="result-grid"><section className="panel result-overview"><div className="result-score"><div><span className="eyebrow">课堂参与度</span><strong>78<span>/100</span></strong><small>较上一次 +6%</small></div><div className="ring-chart"><span>78%</span></div></div><div className="bar-metrics"><BarMetric label="注意力" value={82} color="blue" /><BarMetric label="互动" value={67} color="amber" /><BarMetric label="任务完成" value={85} color="green" /></div></section><section className="panel"><div className="panel-toolbar"><h2>关键发现</h2><span className="review-state review-pending">2 条待复核</span></div><div className="finding"><span className="finding-icon blue">↗</span><div><b>讲解后的注意力窗口较稳定</b><p>00:03:50–00:04:30 期间，注意力相关证据覆盖率 91%。</p><Citation id="EV-042" /><Citation id="EV-041" /></div></div><div className="finding"><span className="finding-icon amber">!</span><div><b>小组讨论阶段存在参与度差异</b><p>右侧区域有 2 条低置信度观察，建议结合课堂座位表复核。</p><Citation id="EV-039" /></div></div></section><section className="panel qa-panel"><div className="panel-toolbar"><div><h2>报告问答</h2><small className="muted">Evidence-first · 仅基于当前任务证据</small></div></div><InteractiveQa /></section></div></div> }

function InteractiveQa() {
  const [conversationId, setConversationId] = React.useState<string | null>(null)
  const [question, setQuestion] = React.useState('')
  const [answers, setAnswers] = React.useState<Answer[]>([])
  const [pending, setPending] = React.useState(false)
  const [error, setError] = React.useState('')
  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    const content = question.trim()
    if (!content || pending) return
    setPending(true); setError('')
    try {
      let id = conversationId
      if (!id) { const conversation = await createConversation('报告问答 · job_8f21', 'job_8f21'); id = conversation.conversation_id; setConversationId(id) }
      const next = await askReport(id, content)
      setAnswers(previous => [...previous, next]); setQuestion('')
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : '问答请求失败') }
    finally { setPending(false) }
  }
  return <><div className="qa-messages">{answers.length === 0 && <div className="state-box empty-state"><span>⌁</span><p>输入问题，回答将只基于当前任务证据，并展示 Evidence ID。</p></div>}{answers.map(item => <React.Fragment key={item.assistant_message.message_id}><div className="question">{item.user_message.content}</div><div className="answer"><span className="brand-mark tiny">L</span><div><p>{item.answer}</p><div className="citation-line">{item.citations.length ? item.citations.map(citation => <Citation key={citation.evidence_id ?? citation.citation_id} id={String(citation.evidence_id ?? citation.citation_id)} />) : <span className="evidence-unavailable">未找到足够证据</span>}</div><small className="muted">来源：{item.source} · {item.evidence_available ? '证据可用' : '证据不足'}{item.limitations.length ? ` · ${item.limitations[0]}` : ''}</small></div></div></React.Fragment>)}{pending && <div className="state-box"><span className="spinner dark" /><p>正在检索当前任务证据…</p></div>}{error && <div className="form-error" role="alert">{error}</div>}</div><form className="qa-input" onSubmit={submit}><input aria-label="向报告提问" value={question} onChange={event => setQuestion(event.target.value)} placeholder="询问这份报告中的任何结论…" disabled={pending} /><button className="primary-button" type="submit" disabled={pending || !question.trim()}>{pending ? '回答中…' : '发送'}</button></form></>
}

function StepRow({ step }: { step: AgentStep }) { return <div className="step-row"><div className={`step-icon step-${step.status}`}>{step.status === 'completed' ? '✓' : step.status === 'running' ? <span className="spinner" /> : step.status === 'failed' ? '!' : '·'}</div><div className="step-content"><div><b>{step.label}</b><span className="step-name">{step.name}</span></div><p>{step.summary}</p></div><div className="step-meta">{step.duration && <span>{step.duration}</span>}{step.retryCount > 0 && <small>重试 {step.retryCount} 次</small>}</div></div> }
function Metric({ label, value, hint, icon, tone = 'purple' }: { label: string; value: string | number; hint: string; icon: string; tone?: string }) { return <div className={`metric-card tone-${tone}`}><span className="metric-icon">{icon}</span><div><span>{label}</span><strong>{value}</strong><small>{hint}</small></div></div> }
function KeyValue({ label, value }: { label: string; value: string }) { return <div className="key-value"><span>{label}</span><b>{value}</b></div> }
function BarMetric({ label, value, color }: { label: string; value: number; color: string }) { return <div className="bar-metric"><div><span>{label}</span><b>{value}</b></div><div className="progress-track"><span className={color} style={{ width: `${value}%` }} /></div></div> }
function Citation({ id }: { id: string }) { const navigate = useNavigate(); return <button className="citation" onClick={() => { window.localStorage.setItem('evidenceclass.selected_evidence', id); navigate('/evidence') }}>⌁ {id}</button> }
function InfoBlock({ title, text, muted = false }: { title: string; text: string; muted?: boolean }) { return <div className={muted ? 'info-block muted-block' : 'info-block'}><b>{title}</b><p>{text}</p></div> }
function LoadingState({ label }: { label: string }) { return <div className="state-box"><span className="spinner dark" /><p>{label}</p></div> }
function ErrorState({ onRetry }: { onRetry: () => void }) { return <div className="state-box error-state"><span>!</span><p>暂时无法加载数据</p><button className="secondary-button" onClick={onRetry}>重试</button></div> }
function EmptyState({ onCreate }: { onCreate?: () => void }) { return <div className="state-box empty-state"><span>◌</span><p>还没有符合条件的任务</p>{onCreate && <button className="primary-button" onClick={onCreate}>创建第一个分析</button>}</div> }

export default function App() { return <QueryClientProvider client={queryClient}><BrowserRouter><AppShell /></BrowserRouter></QueryClientProvider> }

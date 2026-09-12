import React from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { isMockApi, listEvidence, listJobs } from '../../api/client'
import {
  EmptyState,
  ErrorState,
  InfoBlock,
  LoadingState,
  PageHeader,
} from '../../components'

export function EvidencePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const jobsQuery = useQuery({
    queryKey: ['jobs'],
    queryFn: listJobs,
    enabled: !isMockApi,
  })
  const jobId =
    new URLSearchParams(location.search).get('job_id') ??
    (isMockApi ? 'job_8f21' : jobsQuery.data?.[0]?.id)
  const evidenceQuery = useQuery({
    queryKey: ['evidence', jobId],
    queryFn: () => listEvidence(jobId),
    enabled: Boolean(jobId),
  })
  const [selected, setSelected] = React.useState<string | null>(() =>
    window.localStorage.getItem('evidenceclass.selected_evidence'),
  )
  const [tag, setTag] = React.useState('全部标签')
  const [sourceFilter, setSourceFilter] = React.useState('全部来源')
  const [regionFilter, setRegionFilter] = React.useState('全部区域')
  const [reviewFilter, setReviewFilter] = React.useState('全部状态')
  const [message, setMessage] = React.useState('')
  const [moreOpen, setMoreOpen] = React.useState(false)

  const allEvidence = evidenceQuery.data ?? []
  const sources = [...new Set(allEvidence.map(item => item.source))]
  const regions = [...new Set(allEvidence.map(item => item.region))]
  const evidence = allEvidence.filter(
    item =>
      (tag === '全部标签' || item.tag === tag) &&
      (sourceFilter === '全部来源' || item.source === sourceFilter) &&
      (regionFilter === '全部区域' || item.region === regionFilter) &&
      (reviewFilter === '全部状态' || item.review === reviewFilter),
  )
  const current = evidence.find(item => item.id === selected) ?? evidence[0]

  const exportCsv = () => {
    const body = [
      'evidence_id,time,tag,observation,confidence',
      ...evidence.map(item =>
        [item.id, item.time, item.tag, item.observation, item.confidence]
          .map(value => `"${String(value).replaceAll('"', '""')}"`)
          .join(','),
      ),
    ].join('\n')
    const url = URL.createObjectURL(
      new Blob([body], { type: 'text/csv;charset=utf-8' }),
    )
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'evidence-list.csv'
    anchor.click()
    setTimeout(() => URL.revokeObjectURL(url), 0)
    setMessage(`已导出 ${evidence.length} 条证据`)
  }

  const copyCitation = async () => {
    if (!current) return
    try {
      await navigator.clipboard?.writeText(
        `${current.id} · ${current.source} · ${current.time}`,
      )
      setMessage(`${current.id} 已复制到本地引用`)
    } catch {
      setMessage(`${current.id} 引用：${current.source} · ${current.time}`)
    }
    setMoreOpen(false)
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="EVIDENCE"
        title="证据浏览器"
        description={`每个结论都能回到原始帧、ASR 片段或确定性结果。${jobId ? ` · ${jobId}` : ''}`}
        action={
          <div className="header-actions">
            <select
              aria-label="证据标签"
              value={tag}
              onChange={event => setTag(event.target.value)}
            >
              <option>全部标签</option>
              <option>注意力</option>
              <option>互动</option>
              <option>讲授</option>
            </select>
            <select
              aria-label="证据来源"
              value={sourceFilter}
              onChange={event => setSourceFilter(event.target.value)}
            >
              <option>全部来源</option>
              {sources.map(source => (
                <option key={source}>{source}</option>
              ))}
            </select>
            <select
              aria-label="证据区域"
              value={regionFilter}
              onChange={event => setRegionFilter(event.target.value)}
            >
              <option>全部区域</option>
              {regions.map(region => (
                <option key={region}>{region}</option>
              ))}
            </select>
            <select
              aria-label="复核状态"
              value={reviewFilter}
              onChange={event => setReviewFilter(event.target.value)}
            >
              <option>全部状态</option>
              <option>已确认</option>
              <option>待复核</option>
              <option>未知</option>
            </select>
            <button className="secondary-button" onClick={exportCsv}>
              导出证据清单 ↓
            </button>
          </div>
        }
      />
      {message && (
        <div className="success-note" role="status">
          {message}
        </div>
      )}
      <div className="evidence-layout">
        <section className="panel evidence-list">
          <div className="panel-toolbar">
            <b>{evidence.length} 条证据</b>
            <span className="muted">按时间倒序</span>
          </div>
          {evidenceQuery.isLoading ? (
            <LoadingState label="正在加载证据…" />
          ) : evidenceQuery.isError ? (
            <ErrorState onRetry={() => evidenceQuery.refetch()} />
          ) : evidence.length === 0 ? (
            <EmptyState />
          ) : (
            evidence.map(item => (
              <button
                key={item.id}
                className={
                  current?.id === item.id
                    ? 'evidence-row selected'
                    : 'evidence-row'
                }
                onClick={() => {
                  setSelected(item.id)
                  window.localStorage.setItem(
                    'evidenceclass.selected_evidence',
                    item.id,
                  )
                }}
              >
                <div className="evidence-time">
                  {item.time}
                  <small>{item.id}</small>
                </div>
                <div className="evidence-body">
                  <div>
                    <span className="tag">{item.tag}</span>
                    <span
                      className={`review-state review-${
                        item.review === '已确认'
                          ? 'done'
                          : item.review === '待复核'
                            ? 'pending'
                            : 'unknown'
                      }`}
                    >
                      {item.review}
                    </span>
                  </div>
                  <b>{item.observation}</b>
                  <small>
                    {item.region} · 置信度 {Math.round(item.confidence * 100)}%
                  </small>
                </div>
                <span className="row-arrow">›</span>
              </button>
            ))
          )}
        </section>
        <section className="panel evidence-detail">
          {current ? (
            <>
              <div className="detail-head">
                <div>
                  <span className="eyebrow">
                    {current.id} · {current.source}
                  </span>
                  <h2>
                    {current.time}{' '}
                    <span className="tag">{current.tag}</span>
                  </h2>
                </div>
                <div className="top-action-wrap">
                  <button
                    className="icon-button"
                    aria-label="更多证据操作"
                    onClick={() => setMoreOpen(value => !value)}
                  >
                    •••
                  </button>
                  {moreOpen && (
                    <div className="popover">
                      <button className="text-button" onClick={copyCitation}>
                        复制证据引用
                      </button>
                      <button
                        className="text-button"
                        onClick={() => {
                          setSelected(current.id)
                          navigate('/reviews')
                          setMoreOpen(false)
                        }}
                      >
                        提交复核
                      </button>
                    </div>
                  )}
                </div>
              </div>
              <div className="media-frame">
                <div className="frame-overlay">原始帧 · {current.time}</div>
                <div className="classroom-illustration">
                  <div className="board" />
                  <div className="desk-row one" />
                  <div className="desk-row two" />
                  <div className="desk-row three" />
                  <span className="focus-ring" />
                </div>
                <button
                  className="play-button"
                  aria-label="跳转到视频时间点"
                  onClick={() => setMessage(`已定位到 ${current.time}`)}
                >
                  ▶
                </button>
              </div>
              <div className="legend">
                <span>
                  <i className="dot raw" />
                  原始观察
                </span>
                <span>
                  <i className="dot deterministic" />
                  确定性结果
                </span>
                <span>
                  <i className="dot explanation" />
                  LLM 解释
                </span>
              </div>
              <div className="evidence-copy">
                <InfoBlock title="原始观察" text={current.observation} />
                <InfoBlock title="确定性结果" text={current.deterministic} />
                <InfoBlock
                  title="LLM 解释 · 仅供参考"
                  text={current.explanation}
                  muted
                />
              </div>
            </>
          ) : (
            <EmptyState />
          )}
        </section>
      </div>
    </div>
  )
}

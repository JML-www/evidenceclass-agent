import React from 'react'
import { useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { listArtifacts, listJobs } from '../../api/client'
import {
  BarMetric,
  Citation,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
} from '../../components'
import { InteractiveQa } from './InteractiveQa'

type AnalysisMetric = {
  focus?: number | null
  participation?: number | null
  interaction?: number | null
  teacherGuidance?: number | null
  abnormalRate?: number | null
}

type AnalysisResultData = {
  summary?: { overall?: number | null; metrics?: AnalysisMetric }
  evidence?: Array<{ evidence_id?: string; observation?: string }>
  actions?: Array<{
    actionId?: string
    metricKey?: string
    currentValue?: number | null
    suggestion?: string
    evidenceIds?: string[]
  }>
}

export function ResultsPage() {
  const location = useLocation()
  const jobsQuery = useQuery({ queryKey: ['jobs'], queryFn: listJobs })
  const jobId =
    new URLSearchParams(location.search).get('job_id') ??
    jobsQuery.data?.[0]?.id ??
    'job_8f21'
  const artifactsQuery = useQuery({
    queryKey: ['artifacts', jobId],
    queryFn: () => listArtifacts(jobId),
    enabled: Boolean(jobId),
  })
  const [artifactMessage, setArtifactMessage] = React.useState('')
  const artifacts = artifactsQuery.data ?? []
  const report =
    artifacts.find(item => String(item.kind).includes('report')) ??
    artifacts.find(item => String(item.mime).includes('markdown'))
  const resultArtifact = artifacts.find(
    item =>
      String(item.kind) === 'analysis_result' ||
      String(item.mime) === 'application/json',
  )

  const analysisQuery = useQuery({
    queryKey: ['analysisResult', resultArtifact?.download_url],
    queryFn: async () => {
      const url = resultArtifact?.download_url
      if (!url) return null
      const response = await fetch(String(url))
      if (!response.ok) throw new Error('无法获取分析产物')
      return (await response.json()) as AnalysisResultData
    },
    enabled: Boolean(resultArtifact?.download_url),
  })

  const openReport = () => {
    const url = report?.download_url
    if (url) window.open(String(url), '_blank', 'noopener,noreferrer')
    else setArtifactMessage('当前任务暂无原始报告产物')
  }
  const downloadReport = () => {
    const url = report?.download_url
    if (!url) {
      setArtifactMessage('当前任务暂无可下载报告')
      return
    }
    const anchor = document.createElement('a')
    anchor.href = String(url)
    anchor.download = `${report?.kind ?? 'report'}.${
      String(report?.mime).includes('html') ? 'html' : 'md'
    }`
    anchor.target = '_blank'
    anchor.click()
    setArtifactMessage('报告下载已开始')
  }

  const data = analysisQuery.data
  const metrics = data?.summary?.metrics ?? {}
  const participationScore =
    data?.summary?.overall != null
      ? data.summary.overall
      : metrics.participation != null
        ? metrics.participation
        : null
  const evidenceItems = data?.evidence ?? []
  const actions = data?.actions ?? []

  return (
    <div className="page">
      <PageHeader
        eyebrow="RESULT"
        title="结果与问答"
        description={`本次课堂分析 · ${jobId}`}
        action={
          <div className="header-actions">
            <button className="secondary-button" onClick={openReport}>
              查看原始报告
            </button>
            <button className="primary-button" onClick={downloadReport}>
              下载报告 ↓
            </button>
          </div>
        }
      />
      {artifactMessage && (
        <div className="success-note" role="status">
          {artifactMessage}
        </div>
      )}
      <div className="result-grid">
        {analysisQuery.isLoading ? (
          <LoadingState label="正在载入分析产物…" />
        ) : analysisQuery.isError ? (
          <ErrorState onRetry={() => analysisQuery.refetch()} />
        ) : !data ? (
          <section className="panel">
            <EmptyState
              message="当前任务暂无 AnalysisResult 产物，无法渲染真实指标。"
            />
          </section>
        ) : (
          <section className="panel result-overview">
            <div className="result-score">
              <div>
                <span className="eyebrow">课堂参与度</span>
                <strong>
                  {participationScore != null ? (
                    <>
                      {Math.round(participationScore)}
                      <span>/100</span>
                    </>
                  ) : (
                    '暂无数据'
                  )}
                </strong>
                <small>基于真实 AnalysisResult 汇总指标</small>
              </div>
              <div
                className="ring-chart"
                style={{
                  background: `radial-gradient(var(--surface) 58%, transparent 59%), conic-gradient(var(--purple) ${
                    participationScore != null
                      ? Math.round(participationScore)
                      : 0
                  }%, var(--border) 0)`,
                }}
              >
                <span>
                  {participationScore != null
                    ? `${Math.round(participationScore)}%`
                    : '—'}
                </span>
              </div>
            </div>
            <div className="bar-metrics">
              <BarMetric
                label="注意力"
                value={metrics.focus ?? null}
                color="blue"
              />
              <BarMetric
                label="互动"
                value={metrics.interaction ?? null}
                color="amber"
              />
              <BarMetric
                label="任务参与"
                value={metrics.participation ?? null}
                color="green"
              />
            </div>
          </section>
        )}
        <section className="panel">
          <div className="panel-toolbar">
            <h2>关键发现</h2>
            {evidenceItems.length > 0 && (
              <span className="review-state review-pending">
                {evidenceItems.length} 条证据
              </span>
            )}
          </div>
          {evidenceItems.length === 0 ? (
            <EmptyState message="该分析产物暂未包含可展示的证据条目。" />
          ) : (
            evidenceItems.slice(0, 4).map(item => (
              <div className="finding" key={item.evidence_id}>
                <span className="finding-icon blue">↗</span>
                <div>
                  <b>{item.observation ?? '未命名观察'}</b>
                  {item.evidence_id && (
                    <Citation id={String(item.evidence_id)} jobId={jobId} />
                  )}
                </div>
              </div>
            ))
          )}
          {actions.length > 0 && (
            <div className="finding">
              <span className="finding-icon amber">!</span>
              <div>
                <b>行动建议</b>
                <p>
                  {actions
                    .map(action => action.suggestion)
                    .filter(Boolean)
                    .slice(0, 2)
                    .join('；')}
                </p>
              </div>
            </div>
          )}
        </section>
        <section className="panel qa-panel">
          <div className="panel-toolbar">
            <div>
              <h2>报告问答</h2>
              <small className="muted">
                Evidence-first · 仅基于当前任务证据
              </small>
            </div>
          </div>
          <InteractiveQa jobId={jobId} />
        </section>
      </div>
    </div>
  )
}

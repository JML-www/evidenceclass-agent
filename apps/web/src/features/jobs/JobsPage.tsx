import React from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { cancelJob, listJobs, retryJob } from '../../api/client'
import type { Job, JobStatus } from '../../types'
import {
  EmptyState,
  ErrorState,
  LoadingState,
  Metric,
  PageHeader,
  StatusBadge,
} from '../../components'
import {
  IconCheckCircle,
  IconEvidence,
  IconImage,
  IconLayers,
  IconMore,
  IconNew,
  IconRun,
  IconTasks,
  IconVideo,
  IconX,
} from '../../components/icons'
import { useToast } from '../../components/Toast'
import { modeText, statusText } from '../../lib/constants'

const FILTERS = [
  'ALL',
  'RUNNING',
  'NEEDS_REVIEW',
  'SUCCEEDED',
  'FAILED',
  'CANCELLED',
] as const

function ModeIcon({ mode }: { mode: Job['mode'] }) {
  if (mode === 'VIDEO') return <IconVideo size={15} />
  if (mode === 'IMAGE') return <IconImage size={15} />
  return <IconLayers size={15} />
}

export function JobsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()
  const jobsQuery = useQuery({ queryKey: ['jobs'], queryFn: listJobs })
  const [filter, setFilter] = React.useState<(typeof FILTERS)[number]>('ALL')
  const [menuJob, setMenuJob] = React.useState<string | null>(null)
  const [actionError, setActionError] = React.useState('')

  const jobs = (jobsQuery.data ?? []).filter(job => filter === 'ALL' || job.status === filter)

  React.useEffect(() => {
    if (!menuJob) return
    const close = () => setMenuJob(null)
    window.addEventListener('click', close)
    return () => window.removeEventListener('click', close)
  }, [menuJob])

  const runAction = async (job: Job, action: 'cancel' | 'retry') => {
    setActionError('')
    setMenuJob(null)
    try {
      if (action === 'cancel') {
        await cancelJob(job.id)
        toast.notify('任务已取消', 'success')
      } else {
        await retryJob(job.id)
        toast.notify('任务已重新提交', 'success')
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['jobs'] }),
        queryClient.invalidateQueries({ queryKey: ['run', job.id] }),
      ])
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '操作失败')
      toast.notify(`操作失败：${error instanceof Error ? error.message : '未知错误'}`, 'danger')
    }
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="工作台"
        title="任务中心"
        description="管理课堂分析任务，追踪每一次 Agent 执行与证据产物。"
        action={
          <button className="primary-button" onClick={() => navigate('/new')}>
            <IconNew size={16} />
            新建分析
          </button>
        }
      />

      <div className="metric-grid">
        <Metric
          label="全部任务"
          value={jobsQuery.data?.length ?? '—'}
          hint="最近 30 天"
          icon={<IconTasks size={17} />}
        />
        <Metric
          label="运行中"
          value={jobsQuery.data?.filter(j => j.status === 'RUNNING').length ?? '—'}
          hint="队列状态实时同步"
          icon={<IconRun size={17} />}
          tone="blue"
        />
        <Metric
          label="待复核"
          value={jobsQuery.data?.filter(j => j.status === 'NEEDS_REVIEW').length ?? '—'}
          hint="需要人工确认"
          icon={<IconCheckCircle size={17} />}
          tone="amber"
        />
        <Metric
          label="证据覆盖率"
          value="91%"
          hint="已完成任务平均值"
          icon={<IconEvidence size={17} />}
          tone="green"
        />
      </div>

      <section className="panel">
        <div className="panel-toolbar">
          <div className="tabs" role="tablist">
            {FILTERS.map(value => (
              <button
                key={value}
                role="tab"
                aria-selected={filter === value}
                className={filter === value ? 'tab active' : 'tab'}
                onClick={() => setFilter(value)}
              >
                {value === 'ALL' ? '全部' : statusText[value as JobStatus]}
              </button>
            ))}
          </div>
          <button className="secondary-button" onClick={() => setFilter('ALL')}>
            清除筛选
            <IconX size={14} />
          </button>
        </div>

        {actionError && (
          <div className="form-error" role="alert" style={{ margin: 'var(--space-4) var(--space-5) 0' }}>
            {actionError}
          </div>
        )}

        {jobsQuery.isLoading && <LoadingState label="正在加载任务…" />}
        {jobsQuery.isError && <ErrorState onRetry={() => jobsQuery.refetch()} />}
        {!jobsQuery.isLoading && !jobsQuery.isError && jobs.length === 0 && (
          <EmptyState onCreate={() => navigate('/new')} />
        )}

        {!jobsQuery.isLoading && !jobsQuery.isError && jobs.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>任务</th>
                  <th>模式</th>
                  <th>状态</th>
                  <th>进度</th>
                  <th>创建时间</th>
                  <th>证据</th>
                  <th aria-label="操作" />
                </tr>
              </thead>
              <tbody>
                {jobs.map(job => (
                  <tr key={job.id}>
                    <td>
                      <button className="table-link" onClick={() => navigate(`/runs/${job.id}`)}>
                        <span className="job-mode-icon">
                          <ModeIcon mode={job.mode} />
                        </span>
                        <span>
                          <b>{job.title}</b>
                          <small>{job.id}</small>
                        </span>
                      </button>
                    </td>
                    <td>
                      <span className="mode-pill">{modeText[job.mode]}</span>
                    </td>
                    <td>
                      <StatusBadge status={job.status} />
                      {job.error && <small className="error-code">{job.error}</small>}
                    </td>
                    <td>
                      <div className="progress-cell">
                        <div className="progress-track">
                          <span style={{ width: `${job.progress}%` }} />
                        </div>
                        <small>{job.progress}%</small>
                      </div>
                    </td>
                    <td className="muted">{job.createdAt}</td>
                    <td className="muted">{job.evidenceCount ? `${job.evidenceCount} 条` : '—'}</td>
                    <td className="row-action-cell">
                      <button
                        className="row-menu"
                        aria-label={`打开 ${job.title} 操作菜单`}
                        aria-expanded={menuJob === job.id}
                        onClick={event => {
                          event.stopPropagation()
                          setMenuJob(menuJob === job.id ? null : job.id)
                        }}
                      >
                        <IconMore size={16} />
                      </button>
                      {menuJob === job.id && (
                        <div className="row-popover" onClick={event => event.stopPropagation()}>
                          <button onClick={() => navigate(`/runs/${job.id}`)}>打开详情</button>
                          {['RUNNING', 'QUEUED', 'NEEDS_REVIEW'].includes(job.status) && (
                            <button onClick={() => runAction(job, 'cancel')}>取消任务</button>
                          )}
                          {job.status === 'FAILED' && (
                            <button onClick={() => runAction(job, 'retry')}>重试任务</button>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

import React from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { cancelJob, getRun, isMockApi, rerunJob, streamJobEvents } from '../../api/client'
import type { AgentStep, Job, JobStatus } from '../../types'
import {
  ErrorState,
  KeyValue,
  LoadingState,
  PageHeader,
  StatusBadge,
  StepRow,
} from '../../components'
import { IconInfo, IconRefresh, IconX } from '../../components/icons'
import { useToast } from '../../components/Toast'
import { statusText } from '../../lib/constants'

export function RunPage() {
  const { jobId = 'job_8f21' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()
  const runQuery = useQuery({
    queryKey: ['run', jobId],
    queryFn: () => getRun(jobId),
    refetchInterval: query =>
      query.state.data?.job.status === 'RUNNING' || query.state.data?.job.status === 'QUEUED'
        ? 5_000
        : false,
    notifyOnChangeProps: ['data', 'isLoading', 'isError', 'isFetching', 'status'],
  })
  const data = runQuery.data
  const [actionError, setActionError] = React.useState('')

  React.useEffect(() => {
    if (isMockApi || !jobId) return
    const controller = new AbortController()
    streamJobEvents(jobId, event => {
      const progress = Number(event.payload.progress ?? event.payload.job_progress ?? NaN)
      const status = String(event.payload.status ?? event.payload.job_status ?? '').toUpperCase()
      queryClient.setQueryData(
        ['run', jobId],
        (previous: { job: Job; steps: AgentStep[] } | undefined) =>
          previous
            ? {
                ...previous,
                job: {
                  ...previous.job,
                  progress: Number.isFinite(progress) ? progress : previous.job.progress,
                  status: status in statusText ? (status as JobStatus) : previous.job.status,
                },
              }
            : previous,
      )
    }).catch(() => undefined)
    return () => controller.abort()
  }, [jobId, queryClient])

  const action = async (kind: 'cancel' | 'rerun') => {
    setActionError('')
    try {
      if (kind === 'cancel') {
        await cancelJob(jobId)
        toast.notify('任务已取消', 'success')
      } else {
        const result = await rerunJob(jobId)
        if (result && typeof result === 'object' && 'job_id' in result) {
          await queryClient.invalidateQueries({ queryKey: ['jobs'] })
          toast.notify('已创建新的执行记录', 'success')
          navigate(`/runs/${String(result.job_id)}`)
          return
        }
      }
      await queryClient.invalidateQueries({ queryKey: ['jobs'] })
      await runQuery.refetch()
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '操作失败')
      toast.notify(`操作失败：${error instanceof Error ? error.message : '未知错误'}`, 'danger')
    }
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="Agent Run"
        title={data?.job.title ?? 'Agent Run 详情'}
        description={`${jobId} · 结构化执行记录，不展示模型私有思维链。`}
        action={
          <div className="header-actions">
            <button
              className="secondary-button"
              disabled={!data || ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(data.job.status)}
              onClick={() => action('cancel')}
            >
              <IconX size={15} />
              取消任务
            </button>
            <button className="primary-button" onClick={() => action('rerun')}>
              <IconRefresh size={15} />
              重新运行
            </button>
          </div>
        }
      />

      {actionError && (
        <div className="form-error" role="alert">
          {actionError}
        </div>
      )}

      {runQuery.isLoading ? (
        <LoadingState label="正在载入执行时间线…" />
      ) : runQuery.isError || !data ? (
        <ErrorState onRetry={() => runQuery.refetch()} />
      ) : (
        <div className="run-grid">
          <section className="panel">
            {data.job.error && (
              <div className="run-error">
                <b>错误码：{data.job.error}</b>
                <p>可先检查媒体格式和大小，再使用“重新运行”创建新的执行记录。</p>
              </div>
            )}
            <div className="run-summary">
              <div>
                <StatusBadge status={data.job.status} />
                <h2>执行进度</h2>
              </div>
              <strong>{data.job.progress}%</strong>
            </div>
            <div className="big-progress">
              <span style={{ width: `${data.job.progress}%` }} />
            </div>
            <div className="step-list">
              {data.steps.map(step => (
                <StepRow key={step.id} step={step} />
              ))}
            </div>
          </section>

          <aside className="run-side">
            <section className="panel">
              <h3 className="section-title">资源摘要</h3>
              <KeyValue label="Provider" value="local-fake" />
              <KeyValue label="Model" value="deterministic-v1" />
              <KeyValue label="版本" value="runtime@0.8" />
              <KeyValue label="产物" value={`${data.steps.length} 个执行节点`} />
            </section>
            <section className="panel callout">
              <span>
                <IconInfo size={16} />
              </span>
              <p>时间线只记录结构化计划、工具输入摘要和结果摘要，不暴露模型私有思维链。</p>
            </section>
          </aside>
        </div>
      )}
    </div>
  )
}

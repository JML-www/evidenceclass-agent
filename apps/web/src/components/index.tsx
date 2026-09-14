import React from 'react'
import { useNavigate } from 'react-router-dom'
import type { AgentStep, JobStatus } from '../types'
import { statusText } from '../lib/constants'
import {
  IconAlert,
  IconCheck,
  IconEvidence,
  IconInfo,
  IconInbox,
  IconRefresh,
} from './icons'

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string
  title: string
  description?: string
  action?: React.ReactNode
}) {
  return (
    <div className="page-header">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </div>
  )
}

export function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <span className={`status-badge status-${status.toLowerCase()}`}>
      <span className="status-dot" />
      {statusText[status] ?? status}
    </span>
  )
}

export function Metric({
  label,
  value,
  hint,
  icon,
  tone = 'purple',
}: {
  label: string
  value: string | number
  hint: string
  icon: React.ReactNode
  tone?: 'purple' | 'blue' | 'amber' | 'green' | 'danger'
}) {
  return (
    <div className={`metric-card tone-${tone}`}>
      <span className="metric-icon">{icon}</span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{hint}</small>
      </div>
    </div>
  )
}

export function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="key-value">
      <span>{label}</span>
      <b>{value}</b>
    </div>
  )
}

export function BarMetric({
  label,
  value,
  color,
}: {
  label: string
  value: number | null
  color: string
}) {
  if (value == null) {
    return (
      <div className="bar-metric">
        <div>
          <span>{label}</span>
          <b className="muted">暂无数据</b>
        </div>
        <div className="progress-track">
          <span className={color} style={{ width: '0%' }} />
        </div>
      </div>
    )
  }
  return (
    <div className="bar-metric">
      <div>
        <span>{label}</span>
        <b>{value}</b>
      </div>
      <div className="progress-track">
        <span className={color} style={{ width: `${value}%` }} />
      </div>
    </div>
  )
}

export function Citation({ id, jobId }: { id: string; jobId?: string }) {
  const navigate = useNavigate()
  const go = () => {
    window.localStorage.setItem('evidenceclass.selected_evidence', id)
    const suffix = jobId ? `?job_id=${encodeURIComponent(jobId)}` : ''
    navigate(`/evidence${suffix}`)
  }
  return (
    <button className="citation" onClick={go}>
      <IconEvidence size={13} />
      {id}
    </button>
  )
}

export function InfoBlock({
  title,
  text,
  muted = false,
}: {
  title: string
  text: string
  muted?: boolean
}) {
  return (
    <div className={muted ? 'info-block muted-block' : 'info-block'}>
      <b>{title}</b>
      <p>{text}</p>
    </div>
  )
}

export function LoadingState({ label }: { label: string }) {
  return (
    <div className="state-box" role="status" aria-live="polite">
      <span className="spinner dark" />
      <p>{label}</p>
    </div>
  )
}

export function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="state-box error-state" role="alert">
      <span className="state-icon">
        <IconAlert size={20} />
      </span>
      <p>暂时无法加载数据</p>
      <button className="secondary-button" onClick={onRetry}>
        <IconRefresh size={15} />
        重试
      </button>
    </div>
  )
}

export function EmptyState({
  message,
  onCreate,
}: {
  message?: string
  onCreate?: () => void
}) {
  return (
    <div className="state-box empty-state">
      <span className="state-icon">
        <IconInbox size={20} />
      </span>
      <p>{message ?? '还没有符合条件的任务'}</p>
      {onCreate && (
        <button className="primary-button" onClick={onCreate}>
          创建第一个分析
        </button>
      )}
    </div>
  )
}

export function StepRow({ step }: { step: AgentStep }) {
  return (
    <div className="step-row">
      <div className={`step-icon step-${step.status}`}>
        {step.status === 'completed' ? (
          <IconCheck size={13} />
        ) : step.status === 'running' ? (
          <span className="spinner" />
        ) : step.status === 'failed' ? (
          <IconAlert size={13} />
        ) : (
          <IconInfo size={12} />
        )}
      </div>
      <div className="step-content">
        <div>
          <b>{step.label}</b>
          <span className="step-name">{step.name}</span>
        </div>
        <p>{step.summary}</p>
      </div>
      <div className="step-meta">
        {step.duration && <span>{step.duration}</span>}
        {step.retryCount > 0 && <small>重试 {step.retryCount} 次</small>}
      </div>
    </div>
  )
}

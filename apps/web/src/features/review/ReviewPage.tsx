import React from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { decideReview, listReviewItems } from '../../api/client'
import type { ReviewItem } from '../../types'
import {
  EmptyState,
  KeyValue,
  LoadingState,
  PageHeader,
} from '../../components'

export function ReviewPage() {
  const queryClient = useQueryClient()
  const reviewQuery = useQuery({
    queryKey: ['reviews'],
    queryFn: () => listReviewItems(),
  })
  const [selected, setSelected] = React.useState(0)
  const [note, setNote] = React.useState('')
  const [revisedText, setRevisedText] = React.useState('')
  const [decisionState, setDecisionState] = React.useState('')
  const [sortDescending, setSortDescending] = React.useState(false)
  const [pendingDecision, setPendingDecision] = React.useState(false)

  const items = (reviewQuery.data ?? [])
    .filter(item => item.status !== 'DECIDED' && !item.decision)
    .sort((a, b) => {
      const left = String(a.created_at ?? a.review_id)
      const right = String(b.created_at ?? b.review_id)
      return sortDescending
        ? right.localeCompare(left)
        : left.localeCompare(right)
    })
  const current = items[selected] ?? items[0]

  React.useEffect(() => {
    if (selected >= items.length) setSelected(0)
  }, [items.length, selected])

  const read = (item: ReviewItem | undefined, key: string, fallback: string) =>
    String(item?.original_observation?.[key] ?? fallback)

  const onDecision = async (
    decision: 'APPROVED' | 'REJECTED' | 'MODIFIED' | 'MATERIALS_REQUESTED',
  ) => {
    if (!current) return
    if (!note.trim()) {
      setDecisionState('请填写审核理由后再提交')
      return
    }
    setPendingDecision(true)
    setDecisionState('提交中…')
    try {
      await decideReview(
        current.review_id,
        decision,
        note.trim(),
        decision === 'MODIFIED'
          ? {
              ...current.original_observation,
              text: revisedText.trim() || current.original_observation.text,
              reviewer_note: note.trim(),
            }
          : undefined,
      )
      setDecisionState('已记录 · ' + decision)
      setNote('')
      setRevisedText('')
      await queryClient.invalidateQueries({ queryKey: ['reviews'] })
    } catch (error) {
      setDecisionState(
        error instanceof Error ? error.message : '提交失败',
      )
    } finally {
      setPendingDecision(false)
    }
  }

  return (
    <div className="page full-height">
      <PageHeader
        eyebrow="HUMAN IN THE LOOP"
        title="复核工作台"
        description="确认、修正或拒绝模型观察；每次决策都会保留原值与修订值。"
        action={<span className="review-counter">待处理 {items.length}</span>}
      />
      {reviewQuery.isLoading ? (
        <LoadingState label="正在加载复核队列…" />
      ) : current ? (
        <div className="review-layout">
          <section className="panel review-queue">
            <div className="panel-toolbar">
              <b>待复核队列</b>
              <button
                className="row-menu"
                aria-label="排序"
                onClick={() => setSortDescending(value => !value)}
              >
                ⇅
              </button>
            </div>
            {items.map((item, index) => (
              <button
                key={item.review_id}
                className={
                  selected === index ? 'queue-item selected' : 'queue-item'
                }
                onClick={() => {
                  setSelected(index)
                  setNote('')
                  setRevisedText('')
                  setDecisionState('')
                }}
              >
                <div className="queue-marker">{index + 1}</div>
                <div>
                  <b>{read(item, 'title', '模型观察')}</b>
                  <small>
                    {item.evidence_ids[0] ?? item.review_id} ·{' '}
                    {read(item, 'time', '未知时间')}
                  </small>
                  <span className="risk-pill">
                    {read(item, 'score', '待评估')}
                  </span>
                </div>
                <span>›</span>
              </button>
            ))}
          </section>
          <section className="panel review-media">
            <div className="media-frame tall">
              <div className="frame-overlay">
                视频上下文 · {read(current, 'time', '未知时间')}
              </div>
              <div className="classroom-illustration">
                <div className="board" />
                <div className="desk-row one" />
                <div className="desk-row two" />
                <div className="desk-row three" />
                <span className="focus-ring" />
              </div>
              <div className="video-controls">
                <span>▶</span>
                <div className="progress-track">
                  <span style={{ width: '38%' }} />
                </div>
                <span>{read(current, 'time', '未知时间')} / 18:32</span>
              </div>
            </div>
            <div className="context-strip">
              <span>前 10 秒</span>
              <span className="current-context">当前证据</span>
              <span>后 10 秒</span>
            </div>
          </section>
          <section className="panel decision-panel">
            <span className="eyebrow">
              {current.review_id} · 模型观察
            </span>
            <h2>{read(current, 'title', '模型观察')}</h2>
            <p className="decision-copy">
              {read(current, 'text', current.reason)}
            </p>
            <div className="decision-grid">
              <KeyValue
                label="模型值"
                value={read(current, 'model_value', '未提供')}
              />
              <KeyValue
                label="置信度"
                value={`${Math.round(
                  Number(current.original_observation.confidence ?? 0) * 100,
                )}%`}
              />
              <KeyValue
                label="来源"
                value={
                  read(current, 'source', current.evidence_ids.join(', ') || 'unknown')
                }
              />
            </div>
            <label className="field-label" htmlFor="review-reason">
              审核理由
            </label>
            <textarea
              id="review-reason"
              value={note}
              onChange={event => setNote(event.target.value)}
              placeholder="补充你确认或修正的依据…"
            />
            <label className="field-label" htmlFor="revised-observation">
              修订观察<span>（点击“修正字段”时生效）</span>
            </label>
            <textarea
              id="revised-observation"
              value={revisedText}
              onChange={event => setRevisedText(event.target.value)}
              placeholder={read(current, 'text', '填写修订后的观察')}
            />
            <div className="decision-actions">
              <button
                className="secondary-button"
                disabled={pendingDecision}
                onClick={() => onDecision('REJECTED')}
              >
                拒绝
              </button>
              <button
                className="secondary-button"
                disabled={pendingDecision}
                onClick={() => onDecision('MODIFIED')}
              >
                修正字段
              </button>
              <button
                className="secondary-button"
                disabled={pendingDecision}
                onClick={() => onDecision('MATERIALS_REQUESTED')}
              >
                补充材料
              </button>
              <button
                className="primary-button"
                disabled={pendingDecision}
                onClick={() => onDecision('APPROVED')}
              >
                确认并继续 ✓
              </button>
            </div>
            <small className="audit-note">
              {decisionState ||
                '提交后将写入审计日志，并恢复等待中的 Agent 节点。'}
            </small>
          </section>
        </div>
      ) : (
        <EmptyState message="复核队列已清空，没有待处理项。" />
      )}
    </div>
  )
}

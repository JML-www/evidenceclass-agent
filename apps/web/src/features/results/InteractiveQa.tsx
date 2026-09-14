import React from 'react'
import {
  askReport,
  createConversation,
  getConversationSummary,
  listConversations,
  listMessages,
  submitFeedback,
} from '../../api/client'
import type { Answer, ConversationMessage } from '../../types'
import { Citation } from '../../components'
import { IconSend, IconThumbsDown, IconThumbsUp } from '../../components/icons'

export function InteractiveQa({ jobId }: { jobId: string }) {
  const [conversationId, setConversationId] = React.useState<string | null>(() =>
    window.localStorage.getItem(`evidenceclass.conversation_id.${jobId}`) ??
    window.localStorage.getItem('evidenceclass.conversation_id'),
  )
  const [question, setQuestion] = React.useState('')
  const [answers, setAnswers] = React.useState<Answer[]>([])
  const [pending, setPending] = React.useState(false)
  const [error, setError] = React.useState('')
  const [summary, setSummary] = React.useState('')
  const [feedback, setFeedback] = React.useState<Record<string, string>>({})

  React.useEffect(() => {
    let disposed = false
    ;(async () => {
      try {
        const conversations = await listConversations(jobId)
        const id = conversationId ?? conversations.at(-1)?.conversation_id
        if (!id) return
        const messages = await listMessages(id)
        const restored = pairMessages(messages)
        if (!disposed) {
          setConversationId(id)
          setAnswers(restored)
        }
      } catch {
        /* keep the empty state usable */
      }
    })()
    return () => {
      disposed = true
    }
  }, [jobId])

  const loadSummary = async () => {
    if (!conversationId) return
    try {
      const result = await getConversationSummary(conversationId)
      setSummary(String(result.summary ?? '暂无会话摘要'))
    } catch (requestError) {
      setSummary(requestError instanceof Error ? requestError.message : '摘要读取失败')
    }
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    const content = question.trim()
    if (!content || pending) return
    setPending(true)
    setError('')
    try {
      let id = conversationId
      if (!id) {
        const conversation = await createConversation(`报告问答 · ${jobId}`, jobId)
        id = conversation.conversation_id
        setConversationId(id)
        window.localStorage.setItem(`evidenceclass.conversation_id.${jobId}`, id)
      }
      const next = await askReport(id, content)
      setAnswers(previous => [...previous, next])
      setQuestion('')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '问答请求失败')
    } finally {
      setPending(false)
    }
  }

  const sendFeedback = async (answer: Answer, decision: 'APPROVED' | 'REJECTED') => {
    const key = answer.assistant_message.message_id
    try {
      await submitFeedback(jobId, {
        decision,
        reason: decision === 'APPROVED' ? '问答引用核查通过' : '问答回答需要改进',
        evidence_ids: answer.citations.map(item =>
          String(item.evidence_id ?? item.citation_id ?? ''),
        ),
      })
      setFeedback(previous => ({
        ...previous,
        [key]: decision === 'APPROVED' ? '感谢反馈' : '已记录改进建议',
      }))
    } catch (requestError) {
      setFeedback(previous => ({
        ...previous,
        [key]: requestError instanceof Error ? requestError.message : '反馈提交失败',
      }))
    }
  }

  return (
    <>
      <div className="qa-messages">
        {answers.length === 0 && (
          <div className="state-box empty-state">
            <span className="state-icon">
              <IconSend size={20} />
            </span>
            <p>输入问题，回答将只基于当前任务证据，并展示 Evidence ID。</p>
          </div>
        )}

        {answers.map(item => (
          <React.Fragment key={item.assistant_message.message_id}>
            <div className="question">{item.user_message.content}</div>
            <div className="answer">
              <span className="brand-mark tiny">灵</span>
              <div className="answer-body">
                <p>{item.answer}</p>
                <div className="citation-line">
                  {item.citations.length ? (
                    item.citations.map(citation => (
                      <Citation
                        key={citation.evidence_id ?? citation.citation_id}
                        id={String(citation.evidence_id ?? citation.citation_id)}
                        jobId={jobId}
                      />
                    ))
                  ) : (
                    <span className="evidence-unavailable">未找到足够证据</span>
                  )}
                </div>
                <small className="muted">
                  来源：{item.source} · {item.evidence_available ? '证据可用' : '证据不足'}
                  {item.limitations.length ? ` · ${item.limitations[0]}` : ''}
                </small>
                <div className="feedback-actions">
                  <button
                    className="text-button"
                    aria-label="有帮助"
                    onClick={() => sendFeedback(item, 'APPROVED')}
                  >
                    <IconThumbsUp size={14} />
                    有帮助
                  </button>
                  <button
                    className="text-button"
                    aria-label="需要改进"
                    onClick={() => sendFeedback(item, 'REJECTED')}
                  >
                    <IconThumbsDown size={14} />
                    需要改进
                  </button>
                  {feedback[item.assistant_message.message_id] && (
                    <small className="muted">{feedback[item.assistant_message.message_id]}</small>
                  )}
                </div>
              </div>
            </div>
          </React.Fragment>
        ))}

        {pending && (
          <div className="state-box">
            <span className="spinner dark" />
            <p>正在检索当前任务证据…</p>
          </div>
        )}

        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}

        {summary && (
          <div className="summary-box">
            <b>会话摘要</b>
            <p>{summary}</p>
          </div>
        )}
      </div>

      <div className="qa-toolbar">
        <button
          type="button"
          className="text-button"
          onClick={loadSummary}
          disabled={!conversationId}
        >
          读取会话摘要
        </button>
      </div>

      <form className="qa-composer" onSubmit={submit}>
        <input
          aria-label="向报告提问"
          value={question}
          onChange={event => setQuestion(event.target.value)}
          placeholder="询问这份报告中的任何结论…"
          disabled={pending}
        />
        <button className="primary-button" type="submit" disabled={pending || !question.trim()}>
          {pending ? '回答中…' : (
            <>
              <IconSend size={15} />
              发送
            </>
          )}
        </button>
      </form>
    </>
  )
}

function pairMessages(messages: ConversationMessage[]): Answer[] {
  const result: Answer[] = []
  for (let index = 0; index < messages.length; index += 1) {
    const assistant = messages[index]
    if (assistant.role !== 'assistant') continue
    const user =
      messages[index - 1]?.role === 'user'
        ? messages[index - 1]
        : { ...assistant, role: 'user' as const, content: '历史问题' }
    result.push({
      conversation_id: assistant.conversation_id,
      user_message: user,
      assistant_message: assistant,
      answer: assistant.content,
      citations: assistant.citations,
      evidence_available: assistant.evidence_available,
      source: assistant.source ?? 'unknown',
      limitations: assistant.limitations,
      boundary: assistant.boundary,
      summary_version: 0,
    })
  }
  return result
}

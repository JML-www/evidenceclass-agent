/** @vitest-environment jsdom */

import { describe, expect, it } from 'vitest'
import { askReport, createConversation, getConversationSummary, listMessages } from './client'

describe('mock report Q&A adapter', () => {
  it('returns grounded answers with evidence citations', async () => {
    const conversation = await createConversation('test')
    const result = await askReport(conversation.conversation_id, '为什么参与度发生变化？')

    expect(result.evidence_available).toBe(true)
    expect(result.source).toBe('deterministic/mock')
    expect(result.citations.map(citation => citation.evidence_id)).toEqual(['EV-042', 'EV-041'])
    expect(result.assistant_message.citations).toHaveLength(2)
    expect((await listMessages(conversation.conversation_id)).map(message => message.role)).toEqual(['user', 'assistant'])
    expect((await getConversationSummary(conversation.conversation_id)).version).toBe(1)
  })

  it('returns an explicit unavailable fallback instead of guessing', async () => {
    const result = await askReport('conversation-test', '没有证据时可以猜测吗？')

    expect(result.evidence_available).toBe(false)
    expect(result.source).toBe('unavailable_fallback')
    expect(result.citations).toEqual([])
    expect(result.answer).toContain('证据不足')
  })
})

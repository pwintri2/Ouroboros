import { useRef, useState } from 'react'
import { openDemoStream, orchestrateTask, uploadAttachment } from '../../lib/api'
import { useDiffStore } from '../../stores/diffStore'
import { useMessageStore } from '../../stores/messageStore'
import { useSessionStore } from '../../stores/sessionStore'

function styleForAgent(agent: string) {
  const lowered = agent.toLowerCase()
  if (lowered.includes('developer')) return 'backend' as const
  if (lowered.includes('voorzitter')) return 'qa' as const
  if (lowered.includes('kritiek')) return 'docs' as const
  if (lowered.includes('ui')) return 'intuitive' as const
  return 'neutral' as const
}

export function ChatComposer() {
  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState<File[]>([])
  const [voiceEnabled, setVoiceEnabled] = useState(false)
  const [uploadStatus, setUploadStatus] = useState('')
  const [streaming, setStreaming] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const streamMessageIdRef = useRef<string | null>(null)
  const appendMessage = useMessageStore((state) => state.appendMessage)
  const setMessages = useMessageStore((state) => state.setMessages)
  const messages = useMessageStore((state) => state.messages)
  const isSubmitting = useMessageStore((state) => state.isSubmitting)
  const setSubmitting = useMessageStore((state) => state.setSubmitting)
  const addDiff = useDiffStore((state) => state.addDiff)
  const meetingMode = useSessionStore((state) => state.meetingMode)
  const setMeetingMode = useSessionStore((state) => state.setMeetingMode)

  async function handleSubmit() {
    const prompt = input.trim()
    if (!prompt || isSubmitting) return

    const uploaded: string[] = []
    for (const file of attachments) {
      try {
        const result = await uploadAttachment(file)
        uploaded.push(`${result.filename}${result.ingested ? ' (ingested)' : ''}`)
      } catch (error) {
        uploaded.push(`${file.name} (upload failed)`)
      }
    }

    const attachmentSuffix = uploaded.length ? `\n\nBijlagen: ${uploaded.join(', ')}` : ''

    const now = new Date().toISOString()
    appendMessage({
      id: `user-${Date.now()}`,
      threadId: 'mission-control',
      source: 'user',
      observer: 'human-philip',
      phase: 'observed',
      content: `${prompt}${attachmentSuffix}`,
      styleVariant: 'neutral',
      createdAt: now,
      updatedAt: now
    })

    setInput('')
    setSubmitting(true)
    setUploadStatus(uploaded.length ? `Uploads verwerkt: ${uploaded.join(', ')}` : '')
    setStreaming(true)

    const streamMessageId = `stream-${Date.now()}`
    streamMessageIdRef.current = streamMessageId
    appendMessage({
      id: streamMessageId,
      threadId: 'mission-control',
      source: 'agent',
      observer: 'orchestrator',
      phase: 'streaming',
      content: '',
      partialContent: 'Streaming start...',
      styleVariant: 'escalated',
      createdAt: now,
      updatedAt: now,
      protocol: 'WINTRIP-AGENT/1.0'
    })

    const source = openDemoStream(
      prompt,
      (chunk) => {
        setMessages(
          messages.map((message) =>
            message.id === streamMessageId
              ? {
                  ...message,
                  partialContent: `${message.partialContent || ''}\n${chunk}`.trim(),
                  updatedAt: new Date().toISOString()
                }
              : message
          )
        )
      },
      () => {
        setStreaming(false)
      }
    )

    try {
      const result = await orchestrateTask(prompt)
      const reviewTime = new Date().toISOString()

      if (Array.isArray(result.agents)) {
        result.agents.forEach((agentResult, index) => {
          appendMessage({
            id: `agent-${Date.now()}-${index}`,
            threadId: 'mission-control',
            source: 'agent',
            observer: agentResult.agent,
            phase: 'collapsed',
            content: agentResult.summary,
            styleVariant: styleForAgent(agentResult.agent),
            createdAt: reviewTime,
            updatedAt: reviewTime,
            protocol: 'WINTRIP-AGENT/1.0'
          })
        })
      }

      addDiff({
        id: `diff-${Date.now()}`,
        taskId: `task-${Date.now()}`,
        sourceAgent: 'Wintrip UI (Frontend)',
        language: 'typescript',
        filePath: '/output/mission-control-review.md',
        after: result.review || result.final_output || 'Geen output ontvangen.',
        unifiedPatch: `@@ review\n+ ${(result.review || result.final_output || 'Geen output ontvangen.').replace(/\n/g, '\n+ ')}`,
        status: 'pending_approval',
        outputTarget: '/output/',
        createdAt: reviewTime
      })

      appendMessage({
        id: `review-${Date.now()}`,
        threadId: 'mission-control',
        source: 'system',
        observer: 'orchestrator',
        phase: 'collapsed',
        content: result.review || result.final_output || 'Geen orchestrator output ontvangen.',
        styleVariant: 'escalated',
        createdAt: reviewTime,
        updatedAt: reviewTime,
        protocol: 'WINTRIP-AGENT/1.0'
      })
    } catch (error) {
      const failTime = new Date().toISOString()
      appendMessage({
        id: `error-${Date.now()}`,
        threadId: 'mission-control',
        source: 'system',
        observer: 'orchestrator',
        phase: 'rejected',
        content: error instanceof Error ? error.message : 'Onbekende fout tijdens orchestratie.',
        styleVariant: 'critic',
        createdAt: failTime,
        updatedAt: failTime
      })
    } finally {
      source.close()
      setSubmitting(false)
      setAttachments([])
      setStreaming(false)
    }
  }

  return (
    <div className="border-t border-[#d9c7ab] p-4">
      <div className="mb-3 flex items-center justify-between rounded-[14px] border border-[#ccb28c] bg-[#f7efdf] px-3 py-2 text-xs text-[#71593a]">
        <span>{meetingMode ? 'Vergadertafel modus actief' : 'Algemene chat / agentische opdracht box'}</span>
        <button onClick={() => setMeetingMode(!meetingMode)} className="blueprint-button py-1 text-xs">
          {meetingMode ? 'Schakel naar algemene chat' : 'Schakel naar vergadertafel'}
        </button>
      </div>

      <div className="flex items-end gap-3 rounded-[16px] border border-[#ccb28c] bg-[#fbf5e8] p-3">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(event) => setAttachments(Array.from(event.target.files || []))}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#c9ad84] bg-[#f2e7d1] text-[#6d5430]"
        >
          📎
        </button>
        <button
          onClick={() => setVoiceEnabled((value) => !value)}
          className={`flex h-10 w-10 items-center justify-center rounded-xl border border-[#c9ad84] ${voiceEnabled ? 'bg-[#ecd8b3]' : 'bg-[#f2e7d1]'} text-[#6d5430]`}
        >
          🎤
        </button>
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              void handleSubmit()
            }
          }}
          placeholder={meetingMode ? 'Laat de vergadertafel overleggen...' : 'Type a message'}
          className="min-h-[70px] flex-1 resize-none rounded-xl border border-[#ccb28c] bg-[#fffaf0] px-4 py-3 text-sm text-[#352918] outline-none placeholder:text-[#9b825f]"
        />
        <button
          type="button"
          onClick={() => void handleSubmit()}
          disabled={isSubmitting}
          className="blueprint-button-accent min-w-[116px] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSubmitting ? 'Working...' : 'Send'}
        </button>
      </div>

      {(attachments.length > 0 || voiceEnabled || uploadStatus || streaming) && (
        <div className="mt-3 rounded-[14px] border border-[#ccb28c] bg-[#f7efdf] px-3 py-2 text-xs text-[#71593a]">
          {attachments.length > 0 && <div>Bijlagen klaar: {attachments.map((file) => file.name).join(', ')}</div>}
          {voiceEnabled && <div>Spraakchat geactiveerd (UI placeholder).</div>}
          {uploadStatus && <div>{uploadStatus}</div>}
          {streaming && <div>Streaming demo actief...</div>}
        </div>
      )}
    </div>
  )
}

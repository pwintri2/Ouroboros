import { useMemo } from 'react'
import { useMessageStore } from '../../stores/messageStore'

export function MeetingSummaryCard() {
  const messages = useMessageStore((state) => state.messages)

  const summary = useMemo(() => {
    const orchestratorMessages = [...messages].reverse().filter((message) => message.observer === 'orchestrator')
    return orchestratorMessages[0]?.content || 'Nog geen samenvatting beschikbaar.'
  }, [messages])

  return (
    <div className="rounded-[16px] border border-[#ccb28c] bg-[#f7efdf] p-3">
      <div className="tech-label">Voorzitter Summary</div>
      <div className="mt-2 text-sm leading-6 text-[#4b3923]">{summary}</div>
    </div>
  )
}

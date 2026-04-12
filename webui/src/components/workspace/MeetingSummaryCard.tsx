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
      <div className="mt-3 flex flex-wrap gap-2 text-[10px] uppercase tracking-[0.16em] text-[#8b6f4c]">
        <span className="rounded-full border border-[#ccb28c] bg-[#fff7ea] px-2 py-1">Developer</span>
        <span className="rounded-full border border-[#ccb28c] bg-[#fff7ea] px-2 py-1">UI</span>
        <span className="rounded-full border border-[#ccb28c] bg-[#fff7ea] px-2 py-1">Voorzitter</span>
        <span className="rounded-full border border-[#ccb28c] bg-[#fff7ea] px-2 py-1">Kritiek</span>
      </div>
    </div>
  )
}

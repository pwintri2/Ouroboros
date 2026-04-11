import { useMemo } from 'react'
import { useMessageStore } from '../../stores/messageStore'
import { ChatComposer } from './ChatComposer'
import { MeetingSummaryCard } from './MeetingSummaryCard'
import { MessageBubble } from './MessageBubble'

export function ChatStreamPanel() {
  const messages = useMessageStore((state) => state.messages)

  const sortedMessages = useMemo(
    () => [...messages].sort((a, b) => a.createdAt.localeCompare(b.createdAt)),
    [messages]
  )

  return (
    <section className="panel flex h-full flex-col overflow-hidden">
      <div className="border-b border-[#d8c5a8] px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="panel-title">Chat</div>
            <div className="mt-1 text-xs text-[#7c6545]">Raw discussion plus orchestrator summary.</div>
          </div>
          <button className="rounded-xl border border-[#ccb28c] bg-[#f4e7cf] px-3 py-2 text-xs font-medium text-[#5c4526]">
            Sources
          </button>
        </div>
      </div>

      <div className="flex-1 space-y-3 overflow-auto bg-[#fcf7ed] p-4">
        <MeetingSummaryCard />
        {sortedMessages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
      </div>

      <ChatComposer />
    </section>
  )
}

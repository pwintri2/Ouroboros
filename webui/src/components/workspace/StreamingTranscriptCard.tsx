import { useMemo } from 'react'
import { useMessageStore } from '../../stores/messageStore'

export function StreamingTranscriptCard() {
  const messages = useMessageStore((state) => state.messages)

  const streamingMessage = useMemo(
    () => [...messages].reverse().find((message) => message.phase === 'streaming' || !!message.partialContent),
    [messages]
  )

  if (!streamingMessage) {
    return null
  }

  return (
    <div className="rounded-[16px] border border-[#ccb28c] bg-[#fff7ea] p-3">
      <div className="tech-label">Live Transcript</div>
      <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[#4b3923]">
        {streamingMessage.partialContent || streamingMessage.content}
      </div>
    </div>
  )
}

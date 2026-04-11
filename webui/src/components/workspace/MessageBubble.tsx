import type { ChatMessage } from '../../types/chat'

const bubbleClasses: Record<ChatMessage['styleVariant'], string> = {
  neutral: 'border-[#cdb48f] bg-[#fbf6ec] text-[#2d2418]',
  critic: 'border-[#d5b4a8] bg-[#f6e4de] text-[#5d3128]',
  intuitive: 'border-[#ccb690] bg-[#f4ecdb] text-[#4f3b21]',
  backend: 'border-[#cdb48f] bg-[#f5efdf] text-[#3d301e]',
  qa: 'border-[#bfd0b0] bg-[#eef2e5] text-[#324024]',
  docs: 'border-[#d7c3a0] bg-[#f4ead8] text-[#4b3923]',
  escalated: 'border-[#d8b06f] bg-[#f1dfbd] text-[#513a18]'
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isHuman = message.source === 'user'

  return (
    <div className={`flex ${isHuman ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[78%] rounded-[18px] border px-4 py-3 ${bubbleClasses[message.styleVariant]}`}>
        <div className="mb-2 flex items-center justify-between gap-4 text-[10px] uppercase tracking-[0.18em] text-[#8d7149]">
          <span>{message.observer}</span>
          <span>{message.phase}</span>
        </div>
        <div className="whitespace-pre-wrap text-[13px] leading-6">{message.partialContent || message.content}</div>
      </div>
    </div>
  )
}

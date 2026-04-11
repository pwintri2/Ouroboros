import { useEffect } from 'react'
import { createChat, fetchChat, fetchChats } from '../../lib/api'
import { useChatStore } from '../../stores/chatStore'
import { useMessageStore } from '../../stores/messageStore'

function mapSenderToStyle(sender: string) {
  if (sender === 'assistant') return 'escalated' as const
  return 'neutral' as const
}

export function ChatHistoryPanel() {
  const chats = useChatStore((state) => state.chats)
  const activeChatId = useChatStore((state) => state.activeChatId)
  const setChats = useChatStore((state) => state.setChats)
  const prependChat = useChatStore((state) => state.prependChat)
  const setActiveChatId = useChatStore((state) => state.setActiveChatId)
  const setMessages = useMessageStore((state) => state.setMessages)

  useEffect(() => {
    let active = true
    fetchChats()
      .then((items) => {
        if (!active) return
        setChats(items)
      })
      .catch(() => {
        // chat API optional during startup
      })
    return () => {
      active = false
    }
  }, [setChats])

  async function handleNewChat() {
    const created = await createChat()
    prependChat({ id: created.id, title: 'Nieuwe Chat', last_modified: Date.now() / 1000 })
    setMessages([])
  }

  async function handleOpenChat(chatId: string) {
    setActiveChatId(chatId)
    const chat = await fetchChat(chatId)
    const baseTime = Date.now()
    setMessages(
      (chat.messages || []).map((message, index) => ({
        id: `${chatId}-${index}`,
        threadId: chatId,
        source: message.sender === 'assistant' ? 'system' : 'user',
        observer: message.sender === 'assistant' ? 'orchestrator' : 'human-philip',
        phase: 'collapsed',
        content: message.text,
        styleVariant: mapSenderToStyle(message.sender),
        createdAt: new Date(baseTime + index * 1000).toISOString(),
        updatedAt: new Date(baseTime + index * 1000).toISOString(),
        protocol: message.sender === 'assistant' ? 'WINTRIP-AGENT/1.0' : undefined
      }))
    )
  }

  return (
    <div className="mb-3 rounded-[14px] border border-[#ccb28c] bg-[#fbf3e4] p-3 text-sm text-[#5a472d]">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="tech-label">Chats</div>
        <button onClick={() => void handleNewChat()} className="blueprint-button py-1 text-xs">
          + Nieuw
        </button>
      </div>
      <div className="max-h-40 space-y-2 overflow-auto pr-1">
        {chats.map((chat) => (
          <button
            key={chat.id}
            onClick={() => void handleOpenChat(chat.id)}
            className={`w-full rounded-xl border px-3 py-2 text-left text-xs ${chat.id === activeChatId ? 'border-[#b88e4a] bg-[#f2e4ca]' : 'border-[#ccb28c] bg-[#fff9ef]'}`}
          >
            <div className="font-semibold text-[#342817]">{chat.title}</div>
            <div className="mt-1 text-[#7c6545]">{chat.id}</div>
          </button>
        ))}
      </div>
    </div>
  )
}

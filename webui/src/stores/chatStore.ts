import { create } from 'zustand'
import type { ChatListItem } from '../lib/api'

interface ChatState {
  chats: ChatListItem[]
  activeChatId: string | null
  setChats: (chats: ChatListItem[]) => void
  prependChat: (chat: ChatListItem) => void
  touchChat: (chatId: string, title?: string) => void
  setActiveChatId: (chatId: string | null) => void
}

export const useChatStore = create<ChatState>((set) => ({
  chats: [],
  activeChatId: null,
  setChats: (chats) => set({ chats, activeChatId: chats[0]?.id ?? null }),
  prependChat: (chat) =>
    set((state) => ({
      chats: [chat, ...state.chats.filter((item) => item.id !== chat.id)],
      activeChatId: chat.id
    })),
  touchChat: (chatId, title) =>
    set((state) => ({
      chats: [
        { id: chatId, title: title || 'Actieve Chat', last_modified: Date.now() / 1000 },
        ...state.chats.filter((item) => item.id !== chatId)
      ],
      activeChatId: chatId
    })),
  setActiveChatId: (activeChatId) => set({ activeChatId })
}))

import { create } from 'zustand'
import type { ChatListItem } from '../lib/api'

interface ChatState {
  chats: ChatListItem[]
  activeChatId: string | null
  setChats: (chats: ChatListItem[]) => void
  prependChat: (chat: ChatListItem) => void
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
  setActiveChatId: (activeChatId) => set({ activeChatId })
}))

import { create } from 'zustand'
import type { ChatMessage } from '../types/chat'

interface MessageState {
  messages: ChatMessage[]
  isSubmitting: boolean
  clearMessages: () => void
  setMessages: (messages: ChatMessage[]) => void
  appendMessage: (message: ChatMessage) => void
  updateMessage: (id: string, patch: Partial<ChatMessage>) => void
  setSubmitting: (value: boolean) => void
}

const now = new Date().toISOString()

const initialMessages: ChatMessage[] = [
  {
    id: 'm1',
    threadId: 'mission-control',
    source: 'system',
    observer: 'orchestrator',
    phase: 'collapsed',
    content: 'Mission Control online. Hybrid orchestration loaded. Waiting for observer input.',
    styleVariant: 'escalated',
    createdAt: now,
    updatedAt: now,
    protocol: 'WINTRIP-AGENT/1.0'
  }
]

export const useMessageStore = create<MessageState>((set) => ({
  messages: initialMessages,
  isSubmitting: false,
  clearMessages: () => set({ messages: initialMessages }),
  setMessages: (messages) => set({ messages }),
  appendMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  updateMessage: (id, patch) =>
    set((state) => ({
      messages: state.messages.map((message) => (message.id === id ? { ...message, ...patch } : message))
    })),
  setSubmitting: (isSubmitting) => set({ isSubmitting })
}))

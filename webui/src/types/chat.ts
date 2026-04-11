import type { WintripEnvelope } from './protocol'

export type MessagePhase =
  | 'latent'
  | 'streaming'
  | 'observed'
  | 'collapsed'
  | 'diff_pending'
  | 'approved'
  | 'rejected'
  | 'sandbox_result'

export interface ChatMessage {
  id: string
  threadId: string
  source: 'user' | 'agent' | 'system' | 'sandbox'
  observer: string
  phase: MessagePhase
  content: string
  partialContent?: string
  styleVariant: 'neutral' | 'critic' | 'intuitive' | 'backend' | 'qa' | 'docs' | 'escalated'
  createdAt: string
  updatedAt: string
  protocol?: 'WINTRIP-AGENT/1.0'
  envelope?: WintripEnvelope
}

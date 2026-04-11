export type ProviderId = 'ollama' | 'gemini' | 'groq' | 'human'
export type TierId = 'local' | 'cloud' | 'human'

export type PersonaStatus =
  | 'idle'
  | 'thinking'
  | 'observing'
  | 'collapsing'
  | 'sandboxing'
  | 'blocked'
  | 'offline'

export interface PersonaCard {
  id: string
  name: string
  role: string
  provider: ProviderId
  model?: string
  tier: TierId
  status: PersonaStatus
  observerPulse: boolean
  currentTaskId?: string
  resonanceScore?: number
  description?: string
  photo?: string | null
}

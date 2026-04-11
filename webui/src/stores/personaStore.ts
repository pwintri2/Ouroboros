import { create } from 'zustand'
import type { PersonaCard } from '../types/persona'

interface PersonaState {
  personas: PersonaCard[]
  selectedPersonaId: string | null
  seatedPersonaIds: string[]
  setPersonas: (personas: PersonaCard[]) => void
  mergePersonas: (personas: PersonaCard[]) => void
  setSelectedPersonaId: (personaId: string | null) => void
  patchPersonaStatus: (personaId: string, status: PersonaCard['status'], observerPulse?: boolean) => void
  setSeatedPersonaIds: (personaIds: string[]) => void
}

const initialPersonas: PersonaCard[] = [
  {
    id: 'wintrip-developer-backend',
    name: 'Wintrip Developer (Backend)',
    role: 'FastAPI, Python, Docker runtime',
    provider: 'ollama',
    model: 'gemma4:latest',
    tier: 'local',
    status: 'observing',
    observerPulse: true,
    resonanceScore: 0.72
  },
  {
    id: 'wintrip-ui-frontend',
    name: 'Wintrip UI (Frontend)',
    role: 'Mission Control, React, Tailwind',
    provider: 'ollama',
    model: 'gemma4:latest',
    tier: 'local',
    status: 'thinking',
    observerPulse: true,
    resonanceScore: 0.63
  },
  {
    id: 'wintrip-voorzitter-qa-tester',
    name: 'Wintrip Voorzitter (QA & Tester)',
    role: 'Validation, sandbox, testing',
    provider: 'ollama',
    model: 'gemma4:latest',
    tier: 'local',
    status: 'idle',
    observerPulse: false,
    resonanceScore: 0.48
  },
  {
    id: 'wintrip-kritiek-docs-planning',
    name: 'Wintrip Kritiek (Docs/Planning)',
    role: 'Roadmap, architecture, critique',
    provider: 'ollama',
    model: 'gemma4:latest',
    tier: 'local',
    status: 'collapsing',
    observerPulse: true,
    resonanceScore: 0.67
  }
]

export const usePersonaStore = create<PersonaState>((set) => ({
  personas: initialPersonas,
  selectedPersonaId: initialPersonas[0]?.id ?? null,
  seatedPersonaIds: [],
  setPersonas: (personas) =>
    set((state) => ({
      personas,
      selectedPersonaId:
        state.selectedPersonaId && personas.some((persona) => persona.id === state.selectedPersonaId)
          ? state.selectedPersonaId
          : personas[0]?.id ?? null
    })),
  mergePersonas: (incoming) =>
    set((state) => {
      const map = new Map<string, PersonaCard>()
      state.personas.forEach((persona) => map.set(persona.id, persona))
      incoming.forEach((persona) => {
        const existing = map.get(persona.id)
        map.set(persona.id, { ...existing, ...persona })
      })
      const personas = Array.from(map.values())
      return {
        personas,
        selectedPersonaId:
          state.selectedPersonaId && personas.some((persona) => persona.id === state.selectedPersonaId)
            ? state.selectedPersonaId
            : personas[0]?.id ?? null
      }
    }),
  setSelectedPersonaId: (selectedPersonaId) => set({ selectedPersonaId }),
  patchPersonaStatus: (personaId, status, observerPulse = false) =>
    set((state) => ({
      personas: state.personas.map((persona) =>
        persona.id === personaId ? { ...persona, status, observerPulse } : persona
      )
    })),
  setSeatedPersonaIds: (seatedPersonaIds) => set({ seatedPersonaIds })
}))

import { create } from 'zustand'
import type { TelemetrySignal } from '../types/telemetry'

interface TelemetryState {
  signals: TelemetrySignal[]
  setSignals: (signals: TelemetrySignal[]) => void
  upsertSignal: (signal: TelemetrySignal) => void
}

const now = new Date().toISOString()

export const useTelemetryStore = create<TelemetryState>((set) => ({
  signals: [
    {
      id: 't1',
      type: 'resonance',
      value: 0.72,
      status: 'active',
      source: 'Entanglement Daemon',
      timestamp: now,
      meta: { threshold: 0.65 }
    },
    {
      id: 't2',
      type: 'sandbox',
      value: 'idle',
      status: 'ok',
      source: 'Docker Sandbox',
      timestamp: now
    },
    {
      id: 't3',
      type: 'chromadb',
      value: 'online',
      status: 'ok',
      source: '11D Hippocampus',
      timestamp: now
    },
    {
      id: 't4',
      type: 'provider_switch',
      value: 'gemini-2.5-pro',
      status: 'warn',
      source: 'Escalation Pyramid',
      timestamp: now
    }
  ],
  setSignals: (signals) => set({ signals }),
  upsertSignal: (signal) =>
    set((state) => {
      const exists = state.signals.some((item) => item.id === signal.id)
      return {
        signals: exists
          ? state.signals.map((item) => (item.id === signal.id ? signal : item))
          : [...state.signals, signal]
      }
    })
}))

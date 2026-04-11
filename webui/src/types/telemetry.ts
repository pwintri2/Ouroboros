export type TelemetryKind =
  | 'resonance'
  | 'sandbox'
  | 'main_py'
  | 'chromadb'
  | 'vps'
  | 'provider_switch'
  | 'latency'

export interface TelemetrySignal {
  id: string
  type: TelemetryKind
  value: number | string | boolean
  status: 'ok' | 'warn' | 'error' | 'active'
  source: string
  timestamp: string
  meta?: Record<string, unknown>
}

export type WintripProtocol = 'WINTRIP-AGENT/1.0'

export type WintripEnvelopeType =
  | 'proposal'
  | 'status'
  | 'result'
  | 'blocker'
  | 'escalation'

export interface WintripScope {
  owned_paths: string[]
  read_paths: string[]
  write_paths: string[]
}

export interface WintripEnvelope {
  protocol: WintripProtocol
  agent: string
  task_id: string
  type: WintripEnvelopeType
  summary: string
  scope: WintripScope
  inputs: unknown[]
  outputs: unknown[]
  risks: string[]
  needs_review: boolean
  requires_human: boolean
}

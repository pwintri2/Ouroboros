import type { PersonaCard } from '../types/persona'

export interface AgentConfigResponse {
  orchestrator: {
    provider: string
    model: string
  }
  agents: Record<string, {
    agent_id: string
    label: string
    provider: string
    model: string
    owned_paths: string[]
  }>
}

export interface ProvidersResponse {
  [key: string]: {
    available?: boolean
    version?: string
    models?: string[]
  }
}

export interface HealthResponse {
  status: string
  service?: string
  phase?: string
  agent?: string
}

export interface RuntimeStatusResponse {
  status: string
  orchestrator: {
    provider: string
    model: string
  }
  providers: ProvidersResponse
  sandbox: {
    available: boolean
  }
  docker_socket: boolean
}

export interface RuntimeActionResponse {
  status: string
  action: string
  output?: string[]
  detail?: string
}

export interface OrchestrateResponse {
  status: string
  mode?: string
  review?: string
  final_output?: string
  history?: Array<{ iteration: number; classification: string; insight: string }>
  agents?: Array<{
    agent: string
    task_id: string
    type: string
    summary: string
    outputs: string[]
  }>
}

export interface StreamStatusResponse {
  state: string
  persona: string
  poll_interval: number
  sources_count: number
  max_items_per_source: number
  stats: Record<string, unknown>
}

export interface CommitPreviewResponse {
  status: string
  filename: string
  preview: string
  full_length: string
  target_directory: string
  instruction: string
}

export interface CommitSaveResponse {
  status: string
  message?: string
  detail?: string
}

export interface PersonaApiItem {
  id: string
  name: string
  description?: string
  photo?: string | null
}

export interface ChatListItem {
  id: string
  title: string
  last_modified: number
}

export interface ChatMessageItem {
  sender: string
  text: string
}

export interface ChatRecord {
  id: string
  title: string
  messages: ChatMessageItem[]
}

export interface TableStateResponse {
  table_id: string
  seated: string[]
}

export interface UploadResponse {
  status: string
  filename: string
  path: string
  size: number
  ingested: boolean
}

export async function fetchAgentConfig(): Promise<AgentConfigResponse> {
  const response = await fetch('/agent/config')
  if (!response.ok) {
    throw new Error(`Failed to load /agent/config: ${response.status}`)
  }
  return response.json()
}

export async function fetchProviders(): Promise<ProvidersResponse> {
  const response = await fetch('/providers')
  if (!response.ok) {
    throw new Error(`Failed to load /providers: ${response.status}`)
  }
  return response.json()
}

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch('/api/health')
  if (!response.ok) {
    throw new Error(`Failed to load /api/health: ${response.status}`)
  }
  return response.json()
}

export async function fetchRuntimeStatus(): Promise<RuntimeStatusResponse> {
  const response = await fetch('/runtime/status')
  if (!response.ok) {
    throw new Error(`Failed to load /runtime/status: ${response.status}`)
  }
  return response.json()
}

export async function runRuntimeAction(action: string): Promise<RuntimeActionResponse> {
  const response = await fetch('/runtime/action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action })
  })
  if (!response.ok) {
    throw new Error(`Failed to call /runtime/action: ${response.status}`)
  }
  return response.json()
}

export async function switchModel(model: string, provider?: string): Promise<{ status: string; active_model: string; provider: string }> {
  const response = await fetch('/model/switch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, provider })
  })
  if (!response.ok) {
    throw new Error(`Failed to call /model/switch: ${response.status}`)
  }
  return response.json()
}

export async function fetchStreamStatus(): Promise<StreamStatusResponse | null> {
  const response = await fetch('/stream/status')
  if (!response.ok) {
    return null
  }
  return response.json()
}

export async function orchestrateTask(task: string): Promise<OrchestrateResponse> {
  const response = await fetch('/orchestrate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task, max_iterations: 3 })
  })

  if (!response.ok) {
    throw new Error(`Failed to call /orchestrate: ${response.status}`)
  }

  return response.json()
}

export async function previewCommit(filename: string, content: string): Promise<CommitPreviewResponse> {
  const response = await fetch('/commit_preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, content })
  })
  if (!response.ok) {
    throw new Error(`Failed to call /commit_preview: ${response.status}`)
  }
  return response.json()
}

export async function saveCommit(filename: string, content: string): Promise<CommitSaveResponse> {
  const response = await fetch('/commit_save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, content })
  })
  if (!response.ok) {
    throw new Error(`Failed to call /commit_save: ${response.status}`)
  }
  return response.json()
}

export async function fetchPersonas(): Promise<PersonaApiItem[]> {
  const response = await fetch('/api/personas')
  if (!response.ok) {
    throw new Error(`Failed to load /api/personas: ${response.status}`)
  }
  const data = await response.json()
  return data.personas || []
}

export async function createPersona(name: string, description: string): Promise<PersonaApiItem> {
  const response = await fetch('/api/personas', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description })
  })
  if (!response.ok) {
    throw new Error(`Failed to create persona: ${response.status}`)
  }
  return response.json()
}

export async function fetchChats(): Promise<ChatListItem[]> {
  const response = await fetch('/api/chats')
  if (!response.ok) {
    throw new Error(`Failed to load /api/chats: ${response.status}`)
  }
  const data = await response.json()
  return data.chats || []
}

export async function fetchChat(chatId: string): Promise<ChatRecord> {
  const response = await fetch(`/api/chats/${chatId}`)
  if (!response.ok) {
    throw new Error(`Failed to load chat ${chatId}: ${response.status}`)
  }
  return response.json()
}

export async function createChat(): Promise<{ id: string }> {
  const response = await fetch('/api/chats', { method: 'POST' })
  if (!response.ok) {
    throw new Error(`Failed to create chat: ${response.status}`)
  }
  return response.json()
}

export async function invitePersona(personaId: string, tableId = 'main-table'): Promise<TableStateResponse> {
  const response = await fetch('/vergadertafel/invite', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ persona_id: personaId, table_id: tableId })
  })
  if (!response.ok) {
    throw new Error(`Failed to invite persona: ${response.status}`)
  }
  return response.json()
}

export async function removePersona(personaId: string, tableId = 'main-table'): Promise<TableStateResponse> {
  const response = await fetch('/vergadertafel/remove', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ persona_id: personaId, table_id: tableId })
  })
  if (!response.ok) {
    throw new Error(`Failed to remove persona: ${response.status}`)
  }
  return response.json()
}

export async function fetchTableState(tableId = 'main-table'): Promise<TableStateResponse> {
  const response = await fetch(`/vergadertafel/${tableId}`)
  if (!response.ok) {
    throw new Error(`Failed to load table state: ${response.status}`)
  }
  return response.json()
}

export async function uploadAttachment(file: File): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  const response = await fetch('/api/upload?ingest=true', {
    method: 'POST',
    body: formData
  })
  if (!response.ok) {
    throw new Error(`Failed to upload attachment: ${response.status}`)
  }
  return response.json()
}

export function openDemoStream(
  prompt: string,
  onMessage: (chunk: string) => void,
  onDone?: () => void
): EventSource {
  const source = new EventSource(`/api/stream/demo?prompt=${encodeURIComponent(prompt)}`)
  source.onmessage = (event) => {
    onMessage(event.data)
  }
  source.addEventListener('done', () => {
    onDone?.()
    source.close()
  })
  source.onerror = () => {
    source.close()
  }
  return source
}

export function mapAgentsToPersonas(config: AgentConfigResponse): PersonaCard[] {
  return Object.values(config.agents).map((agent) => ({
    id: agent.agent_id,
    name: agent.label,
    role: agent.owned_paths[0] ?? 'Unassigned domain',
    provider: agent.provider === 'gemini' ? 'gemini' : agent.provider === 'groq' ? 'groq' : 'ollama',
    model: agent.model,
    tier: agent.provider === 'ollama' ? 'local' : 'cloud',
    status: 'idle',
    observerPulse: false,
    currentTaskId: undefined,
    resonanceScore: undefined,
    description: agent.owned_paths.join(', '),
    photo: null
  }))
}

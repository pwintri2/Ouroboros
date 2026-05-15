import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import {
  Activity,
  Bot,
  BrainCircuit,
  CheckCircle2,
  CircleStop,
  Cpu,
  Database,
  FolderTree,
  Globe2,
  Hammer,
  History,
  KeyRound,
  Layers,
  MessageSquare,
  Mic,
  Paperclip,
  Pause,
  Plug,
  Play,
  Rocket,
  RefreshCw,
  Send,
  ShieldCheck,
  TerminalSquare,
  TestTube2,
  Volume2,
  VolumeX,
  Wrench,
  X,
  XCircle,
} from "lucide-react";
import "@xterm/xterm/css/xterm.css";
import ouroborosLogoUrl from "./assets/ouroboros-logo.png";

export const BACKEND_BASE_CONFIG_KEYS = ["VITE_BACKEND_URL", "TAURI_BACKEND_URL"] as const;

export const OUROBOROS_BACKEND_CONTRACT = {
  health: "/health",
  modelStatus: "/api/ouroboros/status",
  createFlow: "/api/ouroboros/model/create-flow",
  browserResearch: "/api/ouroboros/research/browser",
  chatgptBrowser: "/api/ouroboros/chatgpt/browser",
  trainingIngest: "/api/ouroboros/training/ingest",
  hippocampusInspect: "/api/ouroboros/hippocampus/inspect",
  selfTrainingStep: "/api/ouroboros/self-training/step",
  loopStart: "/api/ouroboros/loop/start",
  loopPause: "/api/ouroboros/loop/pause",
  loopAbort: "/api/ouroboros/loop/abort",
  loopStatus: "/api/ouroboros/loop/status",
  shell: "/sandbox/shell",
  safeShellTool: "safe_shell",
  cockpitChat: "/api/cockpit/chat",
  openclawVoiceStatus: "/api/openclaw-voice/status",
  agentTool: "/agent/tool",
  apiKeys: "/api/cockpit/api-keys",
  subscriptions: "/api/cockpit/subscriptions",
  rooAuthLogin: "/api/cockpit/roo/auth/login",
  runtimeDoctor: "/api/ouroboros/runtime/doctor",
  connectors: "/api/cockpit/connectors",
  googleOAuthStatus: "/api/cockpit/connectors/google/oauth/status",
  googleOAuthStart: "/api/cockpit/connectors/google/oauth/start",
  googleOAuthExchange: "/api/cockpit/connectors/google/oauth/exchange",
  agentArchitecture: "/api/ouroboros/agents/architecture",
  agentArchitectureReview: "/api/ouroboros/agents/architecture/review",
  worldAgentStatus: "/api/world-agent/status",
  worldAgentGrok: "/api/world-agent/grok/ask",
  worldAgentSearch: "/api/world-agent/memory/search",
  upload: "/api/upload",
  approvalPhrase: "Akkoord",
} as const;

type ActiveTab = "chat" | "tools" | "models" | "connectors" | "agents" | "memory" | "trainer" | "context";

type BackendConfig = {
  backend_url: string;
  approval_phrase: string;
  reachable?: boolean;
  status?: string;
  message?: string;
};

type Health = {
  status?: string;
  agent?: string;
  memories?: number;
  training?: string;
};

type ProviderDetails = {
  provider: string;
  label?: string;
  model?: string;
  models?: string[];
  available?: boolean;
  enabled?: boolean;
  configured?: boolean;
  local_only?: boolean;
  legacy?: boolean;
  status?: string;
  reason?: string;
  message?: string;
  default_model?: string;
  key_source?: string;
  masked_key?: string;
  subscription_active?: boolean;
  subscription_plan?: string;
  subscription_login?: {
    provider?: string;
    status?: string;
    logged_in?: boolean;
    via_bridge?: boolean;
    source?: string;
    secrets_returned?: boolean;
  };
  model_catalog_status?: {
    status?: string;
    available?: boolean;
    model_count?: number;
    via_bridge?: boolean;
    reason?: string;
  };
  roo_cloud_models?: string[];
};

type CockpitConfig = {
  status?: string;
  backend?: Health & { models_available?: number };
  providers?: Record<string, ProviderDetails>;
  provider_options?: Record<string, ProviderDetails>;
  models?: string[];
  available_models?: {
    ollama?: string[];
    local?: string[];
    ollama_inventory?: string[];
    raw_local?: string[];
    ignored_disallowed_models?: string[];
    multi_api?: Record<string, string[]>;
  };
  required_approval_phrase?: string;
  approval?: { required_phrase?: string; case_sensitive?: boolean };
  api_keys?: ApiKeyStatusPayload;
  subscriptions?: SubscriptionStatusPayload;
  self_context?: {
    status?: string;
    enabled?: boolean;
    conversation_count?: number;
    lesson_count?: number;
    recent_lessons?: Array<{ id?: string; text?: string; provider?: string; model?: string; status?: string; at?: number }>;
  };
  chroma?: {
    status?: string;
    available?: boolean;
    mode?: string;
    remote_url?: string;
    persist_dir?: string;
    collections?: Record<string, { status?: string; count?: number; reason?: string }>;
  };
  slash_agents?: Record<string, unknown>;
};

type OuroborosStatus = {
  status?: string;
  model?: {
    name?: string;
    online?: boolean;
    status?: string;
    active_base?: string;
    available_bases?: string[];
    ollama_online?: boolean;
    create_flow?: { status?: string; created?: boolean; next_action?: string; flags?: string[] };
  };
  ollama?: { online?: boolean; available_models?: string[]; count?: number; inventory_error?: string };
  role_models?: Record<string, { model?: string; available?: boolean; source?: string }>;
  ollama_router?: { selected_by_role?: Record<string, string>; available_models?: string[] };
  external_providers?: unknown;
  blocked_external_providers?: string[];
  roo_adapter?: { status?: string; available?: boolean; local_python_adapters?: string[]; fake_success?: boolean };
  geometry_11d?: { dimension_count?: number; radius?: number; volume?: number; oppervlakte?: number; record_count?: number };
  records?: {
    main_collection_count?: number;
    training_collection_count?: number;
    total_count?: number;
    recent_training_ids?: string[];
  };
  learning_11d?: {
    status?: string;
    chromadb?: { available?: boolean; main_collection_count?: number; training_collection_count?: number; total_count?: number };
  };
  integrity?: { fake_tool_success?: boolean; fake_fine_tune_success?: boolean };
  self_modification_pipeline?: { status?: string; stages?: Array<{ name?: string; status?: string }> };
  last_tool_call?: { tool_name?: string; status?: string; stdout?: string; stderr?: string; error?: string };
  learned?: string;
  mentor?: string;
  next_action?: string;
};

type LoopStatus = {
  status: string;
  running?: boolean;
  queued?: boolean;
  iteration?: number;
  loop?: Record<string, unknown>;
  last_step?: Record<string, unknown> | null;
  last_result?: Record<string, unknown> | null;
  next_action?: string;
  updated_at?: number;
};

type AgentJob = {
  job_id: string;
  agent: string;
  status: string;
  task?: string;
  created_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
  exit_code?: number | null;
  response_preview?: string;
  output_dir?: string;
  events_file?: string;
  cancel_requested?: boolean;
  metadata?: {
    ouroboros_esoteric?: {
      pan_dimensional?: {
        metrics?: Record<string, unknown>;
        entropy?: Record<string, unknown>;
        cosmic_storage?: Record<string, unknown>;
      };
    };
  };
};

type AgentJobEvent = {
  index?: number;
  ts?: string;
  type?: string;
  data?: Record<string, unknown>;
};

type ExternalCapability = {
  status?: string;
  exists?: boolean;
  root?: string;
  entrypoints?: Array<{ kind?: string; label?: string; path?: string }>;
  packages?: Array<{ kind?: string; label?: string; path?: string }>;
  agentic_patterns?: Array<{ id?: string; label?: string; value?: string; source?: string }>;
  role_taxonomy?: Array<{ id?: string; label?: string; value?: string; source?: string }>;
  safe_notes?: string[];
};

type ExternalCapabilitiesStatus = {
  status?: string;
  via_bridge?: boolean;
  capabilities?: Record<string, ExternalCapability>;
  tool_schemas?: Array<{ function?: { name?: string } }>;
  reason?: string;
};

type RuntimeToolsStatus = {
  status?: string;
  tools?: string[];
  write_tools_require_approval?: string[];
  fake_success?: boolean;
  reason?: string;
};

type RuntimeDoctorStatus = {
  status?: "ready" | "degraded" | "failed" | "unknown" | string;
  version?: string;
  blockers?: string[];
  checks?: Record<string, { status?: string; reason?: string; url?: string; path?: string; [key: string]: unknown }>;
  defaults?: { backend_url?: string; preview_url?: string; bridge_url?: string; workspace?: string };
  ready_requires?: string[];
  ts?: number;
  reason?: string;
};

type AgentArchitectureInterface = {
  method?: string;
  path?: string;
  prefix?: string;
};

type AgentArchitectureAgent = {
  id?: string;
  name?: string;
  role?: string;
  mission?: string;
  readiness?: string;
  allowed_tools?: string[];
  available_tools?: string[];
  missing_tools?: string[];
  approval_required_for?: string[];
  phases?: Array<{ index?: number; description?: string }>;
  blocked_gaps?: string[];
  interfaces?: AgentArchitectureInterface[];
  fake_success?: boolean;
};

type AgentArchitectureStatus = {
  status?: string;
  version?: string;
  agent_count?: number;
  agents?: AgentArchitectureAgent[];
  readiness_summary?: Record<string, number>;
  blocked_gaps?: string[];
  approval_policy?: {
    approval_phrase?: string;
    private_reads_require_approval?: boolean;
    mutations_require_approval?: boolean;
    connector_writes_preview_first?: boolean;
    self_copy_install_v1?: string;
    fake_success?: boolean;
  };
  public_interfaces?: Record<string, AgentArchitectureInterface>;
  observed_runtime?: { tool_names?: string[]; registered_tool_count?: number; bridge_tool_count?: number };
  fake_success?: boolean;
  secrets_returned?: boolean;
  reason?: string;
};

type AgentArchitectureReview = {
  status?: string;
  decision?: string;
  review_id?: string;
  risk_level?: string;
  risk_categories?: string[];
  execute_allowed?: boolean;
  execution_performed?: boolean;
  approval_required?: boolean;
  approval_status?: string;
  self_copy_install?: boolean;
  private_data?: boolean;
  mutating?: boolean;
  public_read?: boolean;
  critic?: {
    findings?: string[];
    blocked_reasons?: string[];
    secrets_check?: string;
  };
  dry_run_manifest?: {
    status?: string;
    steps?: string[];
    target_platforms?: string[];
    rollback?: string;
    network?: string;
    writes?: string;
  };
  fake_success?: boolean;
  secrets_returned?: boolean;
  reason?: string;
};

type ConnectorTool = {
  name?: string;
  kind?: string;
  enabled?: boolean;
  connector_enabled?: boolean;
  status_tool?: boolean;
  requires_approval?: boolean;
  description?: string;
  approval_phrase?: string;
  fake_success?: boolean;
};

type ConnectorItem = {
  id?: string;
  name?: string;
  provider?: string;
  category?: string;
  description?: string;
  enabled?: boolean;
  readiness?: string;
  configured?: boolean;
  available?: boolean;
  status?: string;
  status_detail?: Record<string, unknown>;
  tools?: ConnectorTool[];
  routes?: Array<{ method?: string; path?: string; tool_name?: string }>;
  setup?: Record<string, unknown>;
  approval?: {
    toggle_requires_approval?: boolean;
    private_read_requires_approval?: boolean;
    write_requires_approval?: boolean;
    approval_phrase?: string;
  };
  settings?: {
    has_override?: boolean;
    updated_at?: string;
    updated_by?: string;
    notes?: string;
    tool_overrides?: Record<string, boolean>;
  };
  fake_success?: boolean;
  secrets_returned?: boolean;
};

type ConnectorAgentWorkPackage = {
  id?: string;
  agent?: string;
  role?: string;
  status?: string;
  priority?: number;
  target?: string;
  command_hint?: string;
  title?: string;
  prompt?: string;
  scope?: string[];
  acceptance?: string[];
  approval?: {
    required_for_execution?: boolean;
    phrase?: string;
    note?: string;
  };
};

type ConnectorCatalogStatus = {
  status?: string;
  version?: string;
  connector_count?: number;
  enabled_count?: number;
  disabled_count?: number;
  configured_count?: number;
  connectors?: ConnectorItem[];
  agent_work_packages?: ConnectorAgentWorkPackage[];
  tool_index?: Record<string, { enabled?: boolean; connector_id?: string; connector_name?: string; kind?: string; requires_approval?: boolean; status_tool?: boolean }>;
  disabled_tools?: string[];
  approval_phrase?: string;
  policy?: Record<string, unknown>;
  fake_success?: boolean;
  secrets_returned?: boolean;
  reason?: string;
};

type GoogleOAuthStatus = {
  status?: string;
  provider?: string;
  client?: {
    configured?: boolean;
    client_id_configured?: boolean;
    valid_client_id?: boolean;
    validation_reason?: string;
    client_secret_configured?: boolean;
    project_id_configured?: boolean;
    client_type?: string;
    redirect_uri?: string;
    scopes?: string[];
    updated_at?: string;
    path?: string;
    secrets_returned?: boolean;
  };
  token?: {
    exists?: boolean;
    path?: string;
    scopes?: string[];
    expires_at?: string;
    token_type?: string;
    has_refresh_token?: boolean;
    secrets_returned?: boolean;
    status?: string;
    reason?: string;
  };
  pending_code?: {
    available?: boolean;
    received_at?: string;
    expires_at?: string;
    expired?: boolean;
    secrets_returned?: boolean;
  };
  last_exchange?: {
    status?: string;
    updated_at?: string;
    token_saved?: boolean;
    has_refresh_token?: boolean;
    using_pending_code?: boolean;
    reason?: string;
    secrets_returned?: boolean;
  };
  required_scopes?: string[];
  missing_scopes?: string[];
  redirect_uri?: string;
  token_path?: string;
  setup_ready?: boolean;
  can_send_gmail?: boolean;
  approval_required?: boolean;
  approval_phrase?: string;
  secrets_returned?: boolean;
  fake_success?: boolean;
  reason?: string;
};

type GoogleOAuthStartResult = {
  status?: string;
  authorization_url?: string;
  redirect_uri?: string;
  scopes?: string[];
  client_configured?: boolean;
  project_id_configured?: boolean;
  client_type?: string;
  warnings?: string[];
  next_step?: string;
  secrets_returned?: boolean;
  fake_success?: boolean;
  reason?: string;
};

type CodexCapability = {
  key?: string;
  label?: string;
  description?: string;
  detected?: boolean;
  paths?: string[];
  invocation?: string;
};

type CodexBinaryInfo = {
  status?: string;
  path?: string | null;
  size_bytes?: number;
};

type CodexAuthInfo = {
  status?: string;
  home?: string;
  auth_present?: boolean;
  auth_age_seconds?: number | null;
  auth_mode?: string | null;
  config_present?: boolean;
  session_count?: number;
  sessions_dir?: string | null;
  skills_dir?: string | null;
  plugins_dir?: string | null;
};

type CodexVersionInfo = {
  status?: string;
  version?: string | null;
  raw?: string | null;
  exit_code?: number | null;
  binary?: CodexBinaryInfo;
};

type CodexJobsInfo = {
  status?: string;
  count?: number;
  jobs?: AgentJob[];
  reason?: string;
};

type CodexStatus = {
  status?: string;
  repo_path?: string;
  repo_present?: boolean;
  binary?: CodexBinaryInfo;
  version?: CodexVersionInfo;
  auth?: CodexAuthInfo;
  capabilities?: {
    summary?: { detected?: number; total?: number; rust_detected?: number; root_detected?: number };
    status?: string;
    rust_workspace?: string | null;
  };
  evidence_summary?: Record<string, number>;
  jobs?: CodexJobsInfo;
  fake_success?: boolean;
};

type CodexCapabilityInventory = {
  status?: string;
  repo_path?: string;
  callable_python?: { status?: string; count?: number; callable_count?: number; functions?: Array<{ name?: string; signature?: string; doc?: string; relative_path?: string }> };
  subsystems?: CodexCapability[];
  subsystems_summary?: { detected?: number; total?: number; rust_detected?: number; root_detected?: number };
  rust_workspace?: string | null;
};

type ProviderChoice = {
  id: string;
  label: string;
  kind: "local" | "external";
  enabled: boolean;
  status: string;
  models: string[];
  defaultModel: string;
  reason: string;
  keySource?: string;
  maskedKey?: string;
};

type NexusEvent = {
  event_id?: string;
  ts?: string;
  job_id?: string;
  agent?: string;
  phase?: string;
  action?: string;
  severity?: number;
  coherence?: number;
  entropy_level?: number;
  omega_converged?: boolean;
  frequency?: number;
  reason?: string;
  recommended_prompt?: string;
};

type NexusStatus = {
  status?: string;
  version?: string;
  reason?: string;
  healing_events?: number;
  sacred_corruptions?: number;
  total_corruption_events?: number;
  omega_convergences?: number;
  tool_rejections?: number;
  omega_vector?: {
    converged?: boolean;
    coherence?: number;
    entropy_level?: number;
    last_action?: string;
  };
  last_event?: NexusEvent | null;
  recent_events?: NexusEvent[];
  operational?: NexusOperationalSummary;
};

type LivingMemoryEntry = {
  id?: string;
  ts?: string;
  kind?: string;
  text?: string;
  source?: string;
};

type LivingStatus = {
  status?: string;
  mode?: string;
  version?: string;
  reason?: string;
  running?: boolean;
  interval_seconds?: number;
  current_thought?: string;
  current_question?: string;
  last_whisper?: string;
  last_action?: string;
  last_tick_at?: string;
  last_output_at?: string;
  tick_count?: number;
  tick_count_24h?: number;
  recent?: LivingMemoryEntry[];
  needs_attention?: string[];
  signal_summary?: string;
  memory?: {
    entry_count?: number;
    path?: string;
    counts?: Record<string, number>;
    recent?: LivingMemoryEntry[];
  };
  memory_count?: number;
};

type QuantumFoamGeometry = {
  dimension?: number;
  dimension_label?: string;
  geometry?: string;
  geometry_en?: string;
  geometry_nl?: string;
  visual_model?: string;
  clique_size?: number;
  electron_count?: number;
  electron_clique?: {
    all_to_all_connected?: boolean;
    actual_edge_count?: number;
    required_edge_count?: number;
    electron_ids?: string[];
    node_ids?: string[];
  };
};

type QuantumFoamFieldSummary = {
  field_id?: string;
  status?: string;
  task?: string;
  tick_count?: number;
  max_ticks?: number;
  node_count?: number;
  active_node_count?: number;
  field_coherence?: number;
  field_coherence_percent?: number;
  dimensional_geometry?: QuantumFoamGeometry;
  mesh?: { edge_count?: number };
  nodes?: Array<{
    node_id?: string;
    node_type?: string;
    weight?: number;
    coherence?: number;
    active?: boolean;
    connection_count?: number;
    thoughts?: string[];
  }>;
  collapse_essence?: {
    summary?: string;
    key_insights?: string[];
    ram_released_estimate_nodes?: number;
    dimensional_geometry?: QuantumFoamGeometry;
  } | null;
};

type QuantumFoamStatus = {
  status?: string;
  version?: string;
  reason?: string;
  active_field_count?: number;
  field_count?: number;
  field_coherence?: number;
  field_coherence_percent?: number;
  active_field?: QuantumFoamFieldSummary | null;
  latest_field?: QuantumFoamFieldSummary | null;
  last_event?: {
    action?: string;
    field_id?: string;
    field_coherence?: number;
    node_count?: number;
    tick_count?: number;
    metadata?: {
      essence?: {
        summary?: string;
        ram_released_estimate_nodes?: number;
      };
    };
  } | null;
  history?: Array<{ action?: string; field_id?: string; field_coherence?: number; ts?: string }>;
  lifecycle?: { max_nodes?: number; default_max_ticks?: number; collapse_required?: boolean };
};

type AgentsSubsystemStatus = {
  status?: string;
  root?: string;
  root_exists?: boolean;
  runtime_reachable?: boolean;
  launch_test?: string;
  variant?: string;
  entrypoints_verified?: number;
  capabilities?: string[];
  variants?: string[];
  reason?: string;
};

type OpenHandsSubsystemStatus = {
  status?: string;
  root?: string;
  root_exists?: boolean;
  server_reachable?: boolean;
  runtime_launch_test?: string;
  skills_count?: number;
  frontend_present?: boolean;
  capabilities?: string[];
  reason?: string;
};

type NexusOperationalSummary = {
  status?: string;
  event_ingestion?: string;
  active_job_count?: number;
  recent_error_count?: number;
  coherence_score?: number;
  converged?: boolean;
  reason?: string;
  qcn_status?: string;
  sources_seen?: Record<string, number>;
  sources_fresh?: Record<string, boolean>;
};

type WorldAction = {
  ts?: string;
  status?: string;
  action?: string;
  action_id?: string;
  question?: string;
  query?: string;
  response?: string;
  reason?: string;
  next_action?: string;
  url?: string;
  via_bridge?: boolean;
  browser_action_performed?: boolean;
  tab_opened?: boolean;
  memory?: { stored?: boolean; memory_id?: string; status?: string; reason?: string };
};

type WorldStatus = {
  status?: string;
  reason?: string;
  agent?: string;
  grok_url?: string;
  host_bridge?: boolean;
  dependencies?: { chromadb?: boolean; playwright?: boolean };
  memory?: { available?: boolean; collection?: string; count?: number; reason?: string; embedding_mode?: string };
  recent_actions?: WorldAction[];
  via_bridge?: boolean;
};

type OpenClawVoiceStatus = {
  status?: string;
  configured?: boolean;
  available?: boolean;
  reachable_from_backend?: boolean;
  root?: string;
  server_url?: string;
  websocket_url?: string;
  gateway_url?: string;
  gateway_chat_completions?: string;
  start_script?: string;
  next_action?: string;
  reason?: string;
  fake_success?: boolean;
};

type ApiKeyStatusPayload = {
  status?: string;
  secrets_returned?: boolean;
  providers?: Record<string, ApiKeyProviderStatus>;
};

type ApiKeyProviderStatus = {
  provider: string;
  configured?: boolean;
  source?: string;
  masked?: string;
  required_key_env?: string[];
  writable?: boolean;
};

type SubscriptionProviderStatus = {
  provider: string;
  label?: string;
  active?: boolean;
  auth_mode?: string;
  auth_modes_available?: string[];
  plan_label?: string;
  status?: string;
  has_credential?: boolean;
  api_key_ready?: boolean;
  masked_credential?: string;
  expires_at?: number;
  expired?: boolean;
  last_validated?: number;
  validation_status?: string;
  models?: string[];
  subscription_url?: string;
  api_key_url?: string;
  docs_url?: string;
  writable?: boolean;
};

type SubscriptionStatusPayload = {
  status?: string;
  providers?: Record<string, SubscriptionProviderStatus>;
  secrets_returned?: boolean;
  reason?: string;
};

type OperationEvent = {
  id: string;
  title: string;
  status: string;
  detail: string;
  raw?: unknown;
  at: string;
};

const DEFAULT_BACKEND = import.meta.env.VITE_BACKEND_URL ?? import.meta.env.TAURI_BACKEND_URL ?? "http://localhost:8010";
const LEGACY_BACKEND_HINT = "http://localhost:8000";

const PROVIDER_LABELS: Record<string, string> = {
  ouroboros: "Ouroboros Runtime",
  ollama: "Ollama Local",
  roo: "Roo Code Agent",
  openai: "ChatGPT Pro",
  anthropic: "Claude Opus",
  deepseek: "DeepSeek API",
  xai: "Grok",
  mistral: "Mistral",
  google: "Gemini",
  brave: "Brave Search",
  gemini: "Gemini Legacy",
  claude: "Claude Legacy",
  chatgpt: "ChatGPT Legacy",
  groq: "Groq Legacy",
};

const CANONICAL_PROVIDERS = ["ouroboros", "ollama", "roo", "openai", "anthropic", "deepseek", "xai", "mistral", "google"];
const API_KEY_PROVIDERS = ["openai", "anthropic", "deepseek", "xai", "mistral", "google", "brave"];
const API_REQUEST_TIMEOUT_MS = 30_000;
const CHAT_REQUEST_TIMEOUT_MS = 90_000;

type ApiRequestInit = RequestInit & {
  timeoutMs?: number;
};

type FrontendAction = {
  type?: string;
  url?: string;
  target?: string;
  action_id?: string;
};

type ExternalOpenResult = {
  opened: boolean;
  detail: string;
  via: string;
};

function isLikelyTauriRuntime(): boolean {
  const currentWindow = window as Window & { __TAURI_INTERNALS__?: unknown };
  return Boolean(currentWindow.__TAURI_INTERNALS__);
}

function isApprovedGrokPrompt(prompt: string, approval: string, approvalPhrase: string): boolean {
  const text = prompt.trim().toLowerCase();
  return approval.trim() === approvalPhrase && /\bgrok(?:\.com)?\b/.test(text) && /\b(open|ga naar|start|vraag|vragen|stel|stellen|ask|tell)\b/.test(text);
}

function isLikelyAgenticPrompt(prompt: string, approvalPhrase: string): boolean {
  const raw = prompt.trim();
  const text = raw.toLowerCase();
  if (!text) return false;
  if (raw === approvalPhrase || raw.startsWith(`${approvalPhrase} `) || raw.startsWith(`${approvalPhrase}:`)) return true;
  if (/^\/(codex|deepseek|atlas|ruflo|roo|claude|agents)\b/i.test(raw)) return true;
  if (/\b(open|openen|start|lanceer|bezoek|ga naar|navigeer|zoek|lees|download|check|controleer)\b/i.test(raw) && /\b(?:https?:\/\/|www\.)?\w[\w.-]*\.(?:nl|com|org|net|io|dev|app)\b/i.test(raw)) return true;
  return /\b(zoek|internet|brave|browser|bestand|bestanden|file|files|map|folder|directory|lees|lijst|toon bestanden|zoek in|shell|commando|command|voer uit|uitvoeren|draai|run tests?|test|unittest|pytest|codex|gemini|grok|agentic|agentisch|agents|deepseek|atlas)\b/i.test(raw);
}

function reserveExternalWindow(prompt: string, approval: string, approvalPhrase: string): Window | null {
  if (isLikelyTauriRuntime() || !isApprovedGrokPrompt(prompt, approval, approvalPhrase)) return null;
  try {
    return window.open("about:blank", "_blank");
  } catch {
    return null;
  }
}

function closeReservedWindow(reservedWindow: Window | null) {
  try {
    if (reservedWindow && !reservedWindow.closed) reservedWindow.close();
  } catch {
    // ignore
  }
}

async function openExternalUrl(url: string, target = "_blank", reservedWindow: Window | null = null): Promise<ExternalOpenResult> {
  let openerDetail = "";
  try {
    const opened = await invoke<boolean>("open_external_url", { url });
    if (opened) {
      closeReservedWindow(reservedWindow);
      return {
        opened: true,
        detail: "Tauri native opener launched the external URL",
        via: "tauri",
      };
    }
    openerDetail = "Tauri native opener returned false";
  } catch (error) {
    openerDetail = `Tauri opener unavailable: ${error instanceof Error ? error.message : String(error)}`;
  }

  if (reservedWindow && !reservedWindow.closed) {
    try {
      reservedWindow.opener = null;
      reservedWindow.location.href = url;
      return {
        opened: true,
        detail: `${openerDetail}; pre-opened browser tab was navigated to the external URL`,
        via: "reserved-window",
      };
    } catch (error) {
      openerDetail = `${openerDetail}; reserved tab navigation failed: ${error instanceof Error ? error.message : String(error)}`;
    }
  }

  const opened = window.open(url, target, "noopener,noreferrer");
  return {
    opened: Boolean(opened),
    detail: opened ? `${openerDetail}; window.open returned a Window handle` : `${openerDetail}; browser/webview blocked window.open`,
    via: "window.open",
  };
}

export default function App() {
  const [backend, setBackend] = useState(DEFAULT_BACKEND);
  const [approvalPhrase, setApprovalPhrase] = useState<string>(OUROBOROS_BACKEND_CONTRACT.approvalPhrase);
  const [approval, setApproval] = useState("");
  const [health, setHealth] = useState<Health>({});
  const [config, setConfig] = useState<CockpitConfig>({});
  const [status, setStatus] = useState<OuroborosStatus>({});
  const [loop, setLoop] = useState<LoopStatus>({ status: "idle", running: false, queued: false, iteration: 0 });
  const [provider, setProvider] = useState("ollama");
  const [model, setModel] = useState("llama3.2:latest");
  const [prompt, setPrompt] = useState("Ontwerp de volgende kleine backend-first verbetering voor Ouroboros.");
  const [command, setCommand] = useState("python3 -m unittest sandbox_tests.test_tauri_backend_routes");
  const [testSelector, setTestSelector] = useState("sandbox_tests.test_tauri_backend_routes sandbox_tests.test_multi_api_router");
  const [runTestsWithLoop, setRunTestsWithLoop] = useState(false);
  const [chatOutput, setChatOutput] = useState("");
  const [lastChatResult, setLastChatResult] = useState<Record<string, unknown> | null>(null);
  const [events, setEvents] = useState<OperationEvent[]>([]);
  const [apiKeyInputs, setApiKeyInputs] = useState<Record<string, string>>({});
  const [subscriptionInputs, setSubscriptionInputs] = useState<Record<string, { auth_mode: string; api_key: string; plan_label: string }>>({});
  const [busy, setBusy] = useState(false);
  const [activeTab, setActiveTab] = useState<ActiveTab>("chat");
  const [trainerStatus, setTrainerStatus] = useState<any>(null);
  const [trainerJobs, setTrainerJobs] = useState<any[]>([]);
  const [contextData, setContextData] = useState<any>(null);
  const [agentJobs, setAgentJobs] = useState<AgentJob[]>([]);
  const [selectedAgentJobId, setSelectedAgentJobId] = useState<string | null>(null);
  const [agentJobEvents, setAgentJobEvents] = useState<AgentJobEvent[]>([]);
  const [nexusStatus, setNexusStatus] = useState<NexusStatus>({ status: "unknown" });
  const [livingStatus, setLivingStatus] = useState<LivingStatus>({ status: "unknown" });
  const [quantumFoamStatus, setQuantumFoamStatus] = useState<QuantumFoamStatus>({ status: "unknown" });
  const [worldStatus, setWorldStatus] = useState<WorldStatus>({ status: "unknown" });
  const [openclawVoiceStatus, setOpenclawVoiceStatus] = useState<OpenClawVoiceStatus>({ status: "unknown" });
  const [voiceConnected, setVoiceConnected] = useState(false);
  const [voiceRecording, setVoiceRecording] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState("");
  const [voiceResponse, setVoiceResponse] = useState("");
  const [voiceError, setVoiceError] = useState("");
  const [voiceBrowserFallback, setVoiceBrowserFallback] = useState(true);
  const [externalCapabilities, setExternalCapabilities] = useState<ExternalCapabilitiesStatus>({ status: "unknown" });
  const [runtimeTools, setRuntimeTools] = useState<RuntimeToolsStatus>({ status: "unknown" });
  const [runtimeDoctor, setRuntimeDoctor] = useState<RuntimeDoctorStatus>({ status: "unknown" });
  const [connectors, setConnectors] = useState<ConnectorCatalogStatus>({ status: "unknown", connectors: [] });
  const [selectedConnectorId, setSelectedConnectorId] = useState("");
  const [googleOAuthStatus, setGoogleOAuthStatus] = useState<GoogleOAuthStatus>({ status: "unknown" });
  const [googleOAuthClientId, setGoogleOAuthClientId] = useState("");
  const [googleOAuthClientSecret, setGoogleOAuthClientSecret] = useState("");
  const [googleOAuthClientJson, setGoogleOAuthClientJson] = useState("");
  const [googleOAuthRedirectUri, setGoogleOAuthRedirectUri] = useState("");
  const [googleOAuthCode, setGoogleOAuthCode] = useState("");
  const [googleOAuthStartResult, setGoogleOAuthStartResult] = useState<GoogleOAuthStartResult | null>(null);
  const [agentArchitecture, setAgentArchitecture] = useState<AgentArchitectureStatus>({ status: "unknown" });
  const [agentArchitectureReview, setAgentArchitectureReview] = useState<AgentArchitectureReview | null>(null);
  const [codexStatus, setCodexStatus] = useState<CodexStatus>({ status: "unknown" });
  const [codexCapabilities, setCodexCapabilities] = useState<CodexCapabilityInventory>({ status: "unknown" });
  const [codexRunPrompt, setCodexRunPrompt] = useState("");
  const [uploadedFiles, setUploadedFiles] = useState<Array<{ filename: string; path: string; size: number }>>([]);
  const [uploading, setUploading] = useState(false);
  const [agentsStatus, setAgentsStatus] = useState<AgentsSubsystemStatus>({ status: "unknown" });
  const [openhandsStatus, setOpenhandsStatus] = useState<OpenHandsSubsystemStatus>({ status: "unknown" });
  const terminalHost = useRef<HTMLDivElement | null>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const providerInitialized = useRef(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const voiceWsRef = useRef<WebSocket | null>(null);
  const voiceStreamRef = useRef<MediaStream | null>(null);
  const voiceAudioContextRef = useRef<AudioContext | null>(null);
  const voiceSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const voiceProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const voiceRecordingRef = useRef(false);
  const voiceTranscriptRef = useRef("");
  const voiceAudibleAudioRef = useRef(false);
  const voiceAudioQueueRef = useRef<Array<{ data: string; sampleRate: number }>>([]);
  const voiceAudioPlayingRef = useRef(false);

  const api = useCallback(
    async <T,>(path: string, init?: ApiRequestInit): Promise<T> => {
      const controller = new AbortController();
      const requestTimeoutMs = init?.timeoutMs ?? API_REQUEST_TIMEOUT_MS;
      const { timeoutMs: _timeoutMs, ...requestInit } = init ?? {};
      const timeout = window.setTimeout(() => controller.abort(), requestTimeoutMs);
      try {
        const response = await fetch(`${backend}${path}`, {
          ...requestInit,
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            ...(requestInit.headers ?? {}),
          },
        });
        const text = await response.text();
        let data: any = {};
        try {
          data = text ? JSON.parse(text) : {};
        } catch {
          data = { raw: text };
        }
        if (!response.ok) {
          const detail = data?.detail ?? data?.error ?? data?.reason ?? data?.raw ?? response.statusText;
          const message = typeof detail === "string" ? detail : JSON.stringify(detail);
          throw new Error(`HTTP ${response.status}: ${message}`);
        }
        return data as T;
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          throw new Error(`Request timeout after ${Math.round(requestTimeoutMs / 1000)}s: ${path}`);
        }
        throw error;
      } finally {
        window.clearTimeout(timeout);
      }
    },
    [backend],
  );

  const providerChoices = useMemo(() => buildProviderChoices(config, status), [config, status]);
  const selectedProvider = providerChoices.find((item) => item.id === provider) ?? providerChoices[0];
  const selectedModels = selectedProvider?.models.length ? selectedProvider.models : [model].filter(Boolean);
  const approvalReady = approval === approvalPhrase;
  const canCallSelectedProvider = selectedProvider?.enabled ?? false;
  const slashPrompt = prompt.trim().startsWith("/");
  const agenticPrompt = isLikelyAgenticPrompt(prompt, approvalPhrase);
  const voiceStatusLabel = voiceRecording
    ? "listening"
    : voiceConnected
      ? "connected"
      : openclawVoiceStatus.status ?? "unknown";
  const voiceReady = voiceConnected || openclawVoiceStatus.status === "online";

  const writeTerm = useCallback((text: string) => {
    terminalRef.current?.writeln(text.replace(/\n/g, "\r\n"));
  }, []);

  const pushEvent = useCallback((title: string, raw: unknown) => {
    const detail = summarizeResult(raw);
    const statusText = resultStatus(raw);
    setEvents((previous) => [
      {
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        title,
        status: statusText,
        detail,
        raw,
        at: new Date().toLocaleTimeString(),
      },
      ...previous.slice(0, 7),
    ]);
    writeTerm(`${title}: ${statusText}`);
    if (detail) writeTerm(detail);
  }, [writeTerm]);

  const loadNexusStatus = useCallback(async () => {
    try {
      const data = await api<NexusStatus>("/api/agent-runtime/nexus/status?limit=8");
      setNexusStatus(data);
    } catch (error) {
      setNexusStatus((previous) => ({
        ...previous,
        status: unavailableStatus(previous.status),
        reason: error instanceof Error ? error.message : String(error),
      }));
    }
  }, [api]);

  const loadLivingStatus = useCallback(async () => {
    try {
      const data = await api<LivingStatus>("/api/ouroboros/esoteric/living/status?limit=8");
      setLivingStatus(data);
    } catch (error) {
      setLivingStatus((previous) => ({
        ...previous,
        status: unavailableStatus(previous.status),
        reason: error instanceof Error ? error.message : String(error),
      }));
    }
  }, [api]);

  const loadQuantumFoamStatus = useCallback(async () => {
    try {
      const data = await api<QuantumFoamStatus>("/api/ouroboros/esoteric/quantum-foam/status?limit=5");
      setQuantumFoamStatus(data);
    } catch (error) {
      setQuantumFoamStatus((previous) => ({
        ...previous,
        status: unavailableStatus(previous.status),
        reason: error instanceof Error ? error.message : String(error),
      }));
    }
  }, [api]);

  const loadWorldStatus = useCallback(async () => {
    try {
      const data = await api<WorldStatus>(OUROBOROS_BACKEND_CONTRACT.worldAgentStatus);
      setWorldStatus(data);
    } catch (error) {
      setWorldStatus((previous) => ({
        ...previous,
        status: unavailableStatus(previous.status),
        reason: error instanceof Error ? error.message : String(error),
      }));
    }
  }, [api]);

  const loadOpenclawVoiceStatus = useCallback(async () => {
    try {
      const data = await api<OpenClawVoiceStatus>(OUROBOROS_BACKEND_CONTRACT.openclawVoiceStatus);
      setOpenclawVoiceStatus(data);
    } catch (error) {
      setOpenclawVoiceStatus((previous) => ({
        ...previous,
        status: unavailableStatus(previous.status),
        reason: error instanceof Error ? error.message : String(error),
      }));
    }
  }, [api]);

  const loadExternalCapabilities = useCallback(async () => {
    try {
      const data = await api<ExternalCapabilitiesStatus>("/api/fase8/external-capabilities");
      setExternalCapabilities(data);
    } catch (error) {
      setExternalCapabilities((previous) => ({
        ...previous,
        status: unavailableStatus(previous.status),
        reason: error instanceof Error ? error.message : String(error),
      }));
    }
  }, [api]);

  const loadRuntimeTools = useCallback(async () => {
    try {
      const data = await api<RuntimeToolsStatus>("/api/agent-runtime/tools/status");
      setRuntimeTools(data);
    } catch (error) {
      setRuntimeTools((previous) => ({
        ...previous,
        status: unavailableStatus(previous.status),
        reason: error instanceof Error ? error.message : String(error),
      }));
    }
  }, [api]);

  const loadRuntimeDoctor = useCallback(async () => {
    try {
      const data = await api<RuntimeDoctorStatus>(OUROBOROS_BACKEND_CONTRACT.runtimeDoctor);
      setRuntimeDoctor(data);
    } catch (error) {
      setRuntimeDoctor((previous) => ({
        ...previous,
        status: "failed",
        reason: error instanceof Error ? error.message : String(error),
      }));
    }
  }, [api]);

  const loadConnectorsStatus = useCallback(async () => {
    try {
      const data = await api<ConnectorCatalogStatus>(OUROBOROS_BACKEND_CONTRACT.connectors);
      setConnectors(data);
      setSelectedConnectorId((current) => {
        const ids = (data.connectors ?? []).map((connector) => connector.id).filter(Boolean) as string[];
        return current && ids.includes(current) ? current : ids[0] ?? "";
      });
    } catch (error) {
      setConnectors((previous) => ({
        ...previous,
        status: unavailableStatus(previous.status),
        reason: error instanceof Error ? error.message : String(error),
      }));
    }
  }, [api]);

  const loadGoogleOAuthStatus = useCallback(async () => {
    try {
      const data = await api<GoogleOAuthStatus>(OUROBOROS_BACKEND_CONTRACT.googleOAuthStatus);
      setGoogleOAuthStatus(data);
      setGoogleOAuthRedirectUri((current) => current || data.redirect_uri || "");
    } catch (error) {
      setGoogleOAuthStatus((previous) => ({
        ...previous,
        status: unavailableStatus(previous.status),
        reason: error instanceof Error ? error.message : String(error),
      }));
    }
  }, [api]);

  const loadAgentArchitecture = useCallback(async () => {
    try {
      const data = await api<AgentArchitectureStatus>(OUROBOROS_BACKEND_CONTRACT.agentArchitecture);
      setAgentArchitecture(data);
    } catch (error) {
      setAgentArchitecture((previous) => ({
        ...previous,
        status: unavailableStatus(previous.status),
        reason: error instanceof Error ? error.message : String(error),
      }));
    }
  }, [api]);

  const loadCodexStatus = useCallback(async () => {
    try {
      const data = await api<CodexStatus>("/api/codex/status");
      setCodexStatus(data);
    } catch (error) {
      setCodexStatus((previous) => ({
        ...previous,
        status: unavailableStatus(previous.status),
      }));
    }
  }, [api]);

  const loadAgentsStatus = useCallback(async () => {
    try {
      const data = await api<AgentsSubsystemStatus>("/api/agents/status");
      setAgentsStatus(data);
    } catch (error) {
      setAgentsStatus((previous) => ({
        ...previous,
        status: unavailableStatus(previous.status),
        reason: error instanceof Error ? error.message : String(error),
      }));
    }
  }, [api]);

  const loadOpenhandsStatus = useCallback(async () => {
    try {
      const data = await api<OpenHandsSubsystemStatus>("/api/openhands/status");
      setOpenhandsStatus(data);
    } catch (error) {
      setOpenhandsStatus((previous) => ({
        ...previous,
        status: unavailableStatus(previous.status),
        reason: error instanceof Error ? error.message : String(error),
      }));
    }
  }, [api]);

  const loadCodexCapabilities = useCallback(async () => {
    try {
      const data = await api<CodexCapabilityInventory>("/api/codex/capabilities");
      setCodexCapabilities(data);
    } catch (error) {
      setCodexCapabilities((previous) => ({
        ...previous,
        status: unavailableStatus(previous.status),
      }));
    }
  }, [api]);

  const submitCodexRun = useCallback(async () => {
    const task = codexRunPrompt.trim();
    if (!task) return;
    if (!approvalReady) {
      pushEvent("Codex run", { status: "blocked", reason: `Type ${approvalPhrase} in het Akkoord-veld om Codex te starten.` });
      return;
    }
    try {
      setBusy(true);
      const result = await api<unknown>("/api/codex/run", {
        method: "POST",
        body: JSON.stringify({ task, approval, timeout_seconds: 1800 }),
      });
      pushEvent("Codex run", result);
      setCodexRunPrompt("");
      await loadCodexStatus();
      try {
        const jobsResponse = await api<{ jobs?: AgentJob[] }>("/api/agent-runtime/jobs?limit=20");
        setAgentJobs(Array.isArray(jobsResponse.jobs) ? jobsResponse.jobs : []);
      } catch {
        // ignore
      }
    } catch (error) {
      pushEvent("Codex run error", { status: "error", reason: error instanceof Error ? error.message : String(error) });
    } finally {
      setBusy(false);
    }
  }, [api, approval, approvalPhrase, approvalReady, codexRunPrompt, loadCodexStatus, pushEvent]);

  const runArchitectureReview = useCallback(async () => {
    const task = prompt.trim();
    if (!task) {
      pushEvent("Criticus review", { status: "blocked", reason: "Geen prompt om te beoordelen." });
      return;
    }
    try {
      setBusy(true);
      const result = await api<AgentArchitectureReview>(OUROBOROS_BACKEND_CONTRACT.agentArchitectureReview, {
        method: "POST",
        body: JSON.stringify({
          prompt: task,
          agent_id: "criticus",
          action: "cockpit_prompt_review",
          requested_mode: "preview",
          approval,
          data_scope: "current cockpit prompt",
        }),
      });
      setAgentArchitectureReview(result);
      pushEvent("Criticus review", result);
    } catch (error) {
      const result = { status: "error", reason: error instanceof Error ? error.message : String(error) };
      setAgentArchitectureReview(result);
      pushEvent("Criticus review error", result);
    } finally {
      setBusy(false);
    }
  }, [api, approval, prompt, pushEvent]);

  const refresh = useCallback(async () => {
    const [healthResult, configResult, statusResult] = await Promise.allSettled([
      api<Health>(OUROBOROS_BACKEND_CONTRACT.health, { timeoutMs: 5_000 }),
      api<CockpitConfig>("/api/cockpit/config", { timeoutMs: 10_000 }),
      api<OuroborosStatus>(OUROBOROS_BACKEND_CONTRACT.modelStatus, { timeoutMs: 8_000 }),
    ]);
    if (healthResult.status === "fulfilled") {
      setHealth(healthResult.value);
    }
    if (configResult.status === "fulfilled") {
      setConfig(configResult.value);
      const phrase = configResult.value.required_approval_phrase ?? configResult.value.approval?.required_phrase;
      if (phrase) setApprovalPhrase(phrase);
    } else {
      setConfig((previous) => ({ ...previous, status: unavailableStatus(previous.status), message: configResult.reason instanceof Error ? configResult.reason.message : String(configResult.reason) }));
    }
    if (statusResult.status === "fulfilled") {
      setStatus(statusResult.value);
    } else {
      setStatus((previous) => ({ ...previous, status: unavailableStatus(previous.status), mentor: statusResult.reason instanceof Error ? statusResult.reason.message : String(statusResult.reason) }));
    }
    try {
      setLoop(await api<LoopStatus>(OUROBOROS_BACKEND_CONTRACT.loopStatus, { timeoutMs: 5_000 }));
    } catch {
      setLoop((previous) => ({ ...previous, status: previous.status || "idle" }));
    }
    if (activeTab === "trainer") {
      try {
        const [trainerData, jobsData] = await Promise.all([
          api<any>("/trainer/status"),
          api<any>("/trainer/jobs"),
        ]);
        setTrainerStatus(trainerData);
        setTrainerJobs(jobsData.jobs || []);
      } catch {
        // Trainer endpoints may not be available yet
      }
    }
    if (activeTab === "context") {
      try {
        const contextData = await api<any>("/context/summary");
        setContextData(contextData);
      } catch {
        // Context endpoints may not be available yet
      }
    }
    if (activeTab !== "trainer" && activeTab !== "context") {
      try {
        const jobsResponse = await api<{ jobs?: AgentJob[] }>("/api/agent-runtime/jobs?limit=20");
        setAgentJobs(Array.isArray(jobsResponse.jobs) ? jobsResponse.jobs : []);
        await loadNexusStatus();
        await loadLivingStatus();
        await loadQuantumFoamStatus();
        await loadWorldStatus();
        await loadOpenclawVoiceStatus();
        await loadExternalCapabilities();
        await loadRuntimeTools();
        await loadRuntimeDoctor();
        await loadConnectorsStatus();
        await loadGoogleOAuthStatus();
        await loadAgentArchitecture();
        await loadCodexStatus();
        await loadAgentsStatus();
        await loadOpenhandsStatus();
      } catch {
        // Agent runtime not available yet — leave previous list intact.
      }
    }
  }, [api, activeTab, loadNexusStatus, loadLivingStatus, loadQuantumFoamStatus, loadWorldStatus, loadOpenclawVoiceStatus, loadExternalCapabilities, loadRuntimeTools, loadRuntimeDoctor, loadConnectorsStatus, loadGoogleOAuthStatus, loadAgentArchitecture, loadCodexStatus, loadAgentsStatus, loadOpenhandsStatus]);

  useEffect(() => {
    invoke<BackendConfig>("backend_config")
      .then((tauriConfig) => {
        if (tauriConfig.backend_url) setBackend(tauriConfig.backend_url);
        if (tauriConfig.approval_phrase) setApprovalPhrase(tauriConfig.approval_phrase);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh().catch((error) => writeTerm(`status error: ${error.message}`));
    const id = window.setInterval(() => refresh().catch(() => undefined), 5000);
    return () => window.clearInterval(id);
  }, [refresh, writeTerm]);

  useEffect(() => {
    loadNexusStatus().catch(() => undefined);
    loadLivingStatus().catch(() => undefined);
    loadQuantumFoamStatus().catch(() => undefined);
    loadWorldStatus().catch(() => undefined);
    loadOpenclawVoiceStatus().catch(() => undefined);
    loadExternalCapabilities().catch(() => undefined);
    loadRuntimeTools().catch(() => undefined);
    loadRuntimeDoctor().catch(() => undefined);
    loadConnectorsStatus().catch(() => undefined);
    loadGoogleOAuthStatus().catch(() => undefined);
    loadAgentArchitecture().catch(() => undefined);
    loadCodexStatus().catch(() => undefined);
    loadCodexCapabilities().catch(() => undefined);
    loadAgentsStatus().catch(() => undefined);
    loadOpenhandsStatus().catch(() => undefined);
    const id = window.setInterval(() => {
      loadNexusStatus().catch(() => undefined);
      loadLivingStatus().catch(() => undefined);
      loadQuantumFoamStatus().catch(() => undefined);
      loadWorldStatus().catch(() => undefined);
      loadOpenclawVoiceStatus().catch(() => undefined);
      loadExternalCapabilities().catch(() => undefined);
      loadRuntimeTools().catch(() => undefined);
      loadRuntimeDoctor().catch(() => undefined);
      loadConnectorsStatus().catch(() => undefined);
      loadGoogleOAuthStatus().catch(() => undefined);
      loadAgentArchitecture().catch(() => undefined);
      loadCodexStatus().catch(() => undefined);
      loadAgentsStatus().catch(() => undefined);
      loadOpenhandsStatus().catch(() => undefined);
    }, 2000);
    const capabilitiesId = window.setInterval(() => {
      loadCodexCapabilities().catch(() => undefined);
    }, 30000);
    return () => {
      window.clearInterval(id);
      window.clearInterval(capabilitiesId);
    };
  }, [loadNexusStatus, loadLivingStatus, loadQuantumFoamStatus, loadWorldStatus, loadOpenclawVoiceStatus, loadExternalCapabilities, loadRuntimeTools, loadRuntimeDoctor, loadConnectorsStatus, loadGoogleOAuthStatus, loadAgentArchitecture, loadCodexStatus, loadCodexCapabilities, loadAgentsStatus, loadOpenhandsStatus]);

  useEffect(() => {
    const pingId = window.setInterval(() => {
      if (voiceWsRef.current?.readyState === WebSocket.OPEN) {
        voiceWsRef.current.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);
    return () => {
      window.clearInterval(pingId);
      cleanupVoiceCapture(false);
      voiceWsRef.current?.close(1000, "cockpit unload");
      window.speechSynthesis?.cancel();
    };
  }, []);

  useEffect(() => {
    if (!terminalHost.current || terminalRef.current) return;
    const terminal = new Terminal({
      cursorBlink: true,
      fontFamily: "JetBrains Mono, Fira Code, ui-monospace, monospace",
      fontSize: 12,
      theme: { background: "#07100d", foreground: "#d7fbe8", cursor: "#34d399" },
    });
    const fit = new FitAddon();
    terminal.loadAddon(fit);
    terminal.open(terminalHost.current);
    fit.fit();
    terminal.writeln("Ouroboros terminal ready. Commands execute through /sandbox/shell and safe_shell.");
    terminal.writeln(`Backend ${backend}; legacy hint ${LEGACY_BACKEND_HINT}`);
    terminalRef.current = terminal;
    fitRef.current = fit;
    const onResize = () => fit.fit();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      terminal.dispose();
      terminalRef.current = null;
      fitRef.current = null;
    };
  }, [activeTab, backend]);

  useEffect(() => {
    if (activeTab === "trainer") {
      api<any>("/trainer/status")
        .then((trainerData) => setTrainerStatus(trainerData))
        .catch(() => undefined);
      api<any>("/trainer/jobs")
        .then((jobsData) => setTrainerJobs(jobsData.jobs || []))
        .catch(() => undefined);
    }
    if (activeTab === "context") {
      api<any>("/context/summary")
        .then((contextData) => setContextData(contextData))
        .catch(() => undefined);
    }
  }, [activeTab, api]);

  useEffect(() => {
    if (!selectedAgentJobId) {
      setAgentJobEvents([]);
      return;
    }
    let cancelled = false;
    const load = async () => {
      try {
        const response = await api<{ events?: AgentJobEvent[] }>(`/api/agent-runtime/jobs/${selectedAgentJobId}/events?limit=200`);
        if (cancelled) return;
        setAgentJobEvents(Array.isArray(response.events) ? response.events : []);
      } catch {
        // Job may have been removed; clear and stop polling next tick.
      }
    };
    load();
    const id = window.setInterval(load, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [selectedAgentJobId, api]);

  useEffect(() => {
    if (providerInitialized.current || providerChoices.length === 0) return;
    const local =
      providerChoices.find((item) => item.id === "ouroboros" && item.enabled) ??
      providerChoices.find((item) => item.id === "ollama" && item.enabled) ??
      providerChoices.find((item) => item.enabled);
    if (!local) return;
    providerInitialized.current = true;
    setProvider(local.id);
    setModel(local.id === "ollama" ? status.model?.active_base || local.defaultModel || local.models[0] || "llama3.2:latest" : local.defaultModel || local.models[0] || "living-runtime");
  }, [providerChoices, status.model?.active_base]);

  function onProviderChange(nextProvider: string) {
    const option = providerChoices.find((item) => item.id === nextProvider) ?? providerChoices[0];
    if (!option) return;
    setProvider(option.id);
    const keepCurrentModel = option.id === "roo" && model && option.models.includes(model);
    setModel(keepCurrentModel ? model : option.defaultModel || option.models[0] || "");
  }

  async function perform<T>(title: string, action: () => Promise<T>): Promise<T | null> {
    setBusy(true);
    try {
      const data = await action();
      pushEvent(title, data);
      await refresh();
      return data;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const failed = { status: "error", error: message };
      pushEvent(title, failed);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function handleFileUpload(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;
    setUploading(true);
    try {
      const formData = new FormData();
      for (let i = 0; i < fileList.length; i++) {
        formData.append("files", fileList[i]);
      }
      const response = await fetch(`${backend}/api/upload`, {
        method: "POST",
        body: formData,
      });
      const result = await response.json();
      if (result.files && Array.isArray(result.files)) {
        const successFiles = result.files
          .filter((f: any) => f.status === "ok")
          .map((f: any) => ({ filename: f.filename, path: f.path, size: f.size }));
        setUploadedFiles((prev) => [...prev, ...successFiles]);
        pushEvent("File upload", result);
      }
    } catch (error) {
      pushEvent("File upload error", { status: "error", error: error instanceof Error ? error.message : String(error) });
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  function removeUploadedFile(index: number) {
    setUploadedFiles((prev) => prev.filter((_, i) => i !== index));
  }

  function openclawVoiceWsUrl() {
    if (openclawVoiceStatus.websocket_url) return openclawVoiceStatus.websocket_url;
    const host = window.location.hostname || "127.0.0.1";
    return `ws://${host}:8765/ws`;
  }

  function openclawVoiceServerUrl() {
    if (openclawVoiceStatus.server_url) return openclawVoiceStatus.server_url;
    const host = window.location.hostname || "127.0.0.1";
    return `http://${host}:8765`;
  }

  function openclawVoiceOfflineMessage() {
    const serverUrl = openclawVoiceServerUrl();
    const action = openclawVoiceStatus.start_script || "scripts/start_openclaw_ouroboros_voice.sh";
    return `OpenClaw voice draait nog niet op ${serverUrl}. Start ${action} en probeer daarna opnieuw.`;
  }

  async function browserCanReachOpenclawVoice() {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 1200);
    try {
      await fetch(openclawVoiceServerUrl(), {
        method: "GET",
        mode: "no-cors",
        cache: "no-store",
        signal: controller.signal,
      });
      return true;
    } catch {
      return false;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  async function microphonePermissionHint(error?: unknown) {
    const details: string[] = [];
    const errorRecord = error instanceof Error ? error : null;
    if (errorRecord?.name) details.push(errorRecord.name);
    if (errorRecord?.message) details.push(errorRecord.message);

    try {
      const permissionsApi = navigator.permissions as Permissions & {
        query: (descriptor: PermissionDescriptor | { name: "microphone" }) => Promise<PermissionStatus>;
      };
      const permission = await permissionsApi?.query?.({ name: "microphone" });
      if (permission?.state) details.push(`permission=${permission.state}`);
    } catch {
      details.push("permission=unknown");
    }

    const secureEnough = window.isSecureContext || ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
    details.push(`origin=${window.location.origin}`);
    details.push(`secureContext=${String(window.isSecureContext)}`);
    if (!secureEnough) details.push("microfoon vereist localhost of https");

    return [
      "Microfoon wordt door browser/WebView of OS geblokkeerd.",
      "Akkoord is alleen voor Ouroboros-acties; microfoontoegang moet in de browser/site/OS toestemming krijgen.",
      details.filter(Boolean).join(" | "),
      "Reset de microfoonpermission voor deze Cockpit of open http://127.0.0.1:1420 in een normale browser en sta Microphone toe.",
    ].join(" ");
  }

  function cleanupVoiceCapture(notifyServer = true) {
    const wasRecording = voiceRecordingRef.current;
    voiceRecordingRef.current = false;
    setVoiceRecording(false);
    if (voiceProcessorRef.current) {
      voiceProcessorRef.current.disconnect();
      voiceProcessorRef.current = null;
    }
    if (voiceSourceRef.current) {
      voiceSourceRef.current.disconnect();
      voiceSourceRef.current = null;
    }
    if (voiceAudioContextRef.current) {
      voiceAudioContextRef.current.close().catch(() => undefined);
      voiceAudioContextRef.current = null;
    }
    if (voiceStreamRef.current) {
      voiceStreamRef.current.getTracks().forEach((track) => track.stop());
      voiceStreamRef.current = null;
    }
    const ws = voiceWsRef.current;
    if (notifyServer && wasRecording && ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "stop_listening" }));
    }
  }

  function handleOpenclawMessage(raw: unknown) {
    const msg = asRecord(raw);
    const type = summarizeValue(msg.type);
    if (type === "listening_started") {
      setVoiceError("");
      return;
    }
    if (type === "listening_stopped") {
      setVoiceRecording(false);
      voiceRecordingRef.current = false;
      return;
    }
    if (type === "transcript") {
      const text = summarizeValue(msg.text);
      if (text) {
        voiceTranscriptRef.current = text;
        setVoiceTranscript(text);
        setPrompt(text);
        setVoiceResponse("");
        voiceAudibleAudioRef.current = false;
        pushEvent("OpenClaw transcript", { status: "success", transcript: text, fake_success: false });
      }
      return;
    }
    if (type === "response_chunk") {
      const text = summarizeValue(msg.text);
      if (text) setVoiceResponse((previous) => `${previous}${text}`.slice(-4000));
      return;
    }
    if (type === "audio_chunk") {
      const data = summarizeValue(msg.data);
      const sampleRate = Number(msg.sample_rate ?? 24000);
      if (data) queueOpenclawAudio(data, Number.isFinite(sampleRate) ? sampleRate : 24000);
      return;
    }
    if (type === "response_complete") {
      const text = summarizeValue(msg.text) || voiceResponse;
      if (text) setVoiceResponse(text);
      const payload = {
        status: "success",
        route: "openclaw_voice",
        provider: "ouroboros",
        model: "living-runtime",
        transcript: voiceTranscriptRef.current,
        response: text,
        openclaw_voice: {
          status: "completed",
          websocket_url: openclawVoiceWsUrl(),
          browser_fallback: voiceBrowserFallback,
          audible_server_audio: voiceAudibleAudioRef.current,
          fake_success: false,
        },
        fake_success: false,
      };
      setLastChatResult(payload);
      setChatOutput(renderResponse(payload));
      pushEvent("OpenClaw voice response", payload);
      if (voiceBrowserFallback && text) {
        window.setTimeout(() => {
          if (!voiceAudibleAudioRef.current) speakVoiceText(text);
        }, 900);
      }
      return;
    }
    if (type === "error") {
      setVoiceError(summarizeValue(msg.error) || summarizeValue(msg.reason) || "OpenClaw voice error");
    }
  }

  async function ensureOpenclawVoiceConnected(): Promise<WebSocket> {
    const existing = voiceWsRef.current;
    if (existing?.readyState === WebSocket.OPEN) return existing;
    if (existing?.readyState === WebSocket.CONNECTING) {
      return new Promise((resolve, reject) => {
        const timeout = window.setTimeout(() => reject(new Error("OpenClaw voice connection timed out.")), 5000);
        existing.addEventListener("open", () => {
          window.clearTimeout(timeout);
          resolve(existing);
        }, { once: true });
        existing.addEventListener("error", () => {
          window.clearTimeout(timeout);
          reject(new Error("OpenClaw voice websocket failed while connecting."));
        }, { once: true });
      });
    }

    const url = openclawVoiceWsUrl();
    const reachable = await browserCanReachOpenclawVoice();
    if (!reachable) {
      await loadOpenclawVoiceStatus().catch(() => undefined);
      throw new Error(openclawVoiceOfflineMessage());
    }
    setVoiceError("");
    return new Promise((resolve, reject) => {
      let settled = false;
      const ws = new WebSocket(url);
      voiceWsRef.current = ws;
      const fail = (message: string) => {
        if (!settled) {
          settled = true;
          reject(new Error(message));
        }
      };
      ws.onopen = () => {
        settled = true;
        setVoiceConnected(true);
        setVoiceError("");
        pushEvent("OpenClaw voice", { status: "connected", websocket_url: url, fake_success: false });
        resolve(ws);
      };
      ws.onmessage = (event) => {
        try {
          handleOpenclawMessage(JSON.parse(event.data));
        } catch (error) {
          setVoiceError(error instanceof Error ? error.message : String(error));
        }
      };
      ws.onerror = () => {
        setVoiceConnected(false);
        fail(openclawVoiceOfflineMessage());
      };
      ws.onclose = (event) => {
        setVoiceConnected(false);
        cleanupVoiceCapture(false);
        if (voiceWsRef.current === ws) voiceWsRef.current = null;
        if (!settled) fail(event.code === 1006 ? openclawVoiceOfflineMessage() : `OpenClaw voice gesloten (${event.code || "no code"}).`);
        if (event.code && event.code !== 1000) {
          setVoiceError(event.code === 1006 ? openclawVoiceOfflineMessage() : `OpenClaw voice gesloten (${event.code}).`);
        }
      };
    });
  }

  function disconnectOpenclawVoice() {
    cleanupVoiceCapture(false);
    voiceWsRef.current?.close(1000, "cockpit disconnect");
    voiceWsRef.current = null;
    setVoiceConnected(false);
  }

  function downsampleFloat32(input: Float32Array, inputRate: number, outputRate: number) {
    if (!input.length || inputRate === outputRate) return new Float32Array(input);
    const ratio = inputRate / outputRate;
    const outputLength = Math.max(1, Math.round(input.length / ratio));
    const output = new Float32Array(outputLength);
    for (let i = 0; i < outputLength; i += 1) {
      const start = Math.floor(i * ratio);
      const end = Math.min(input.length, Math.floor((i + 1) * ratio));
      let sum = 0;
      for (let j = start; j < end; j += 1) sum += input[j];
      output[i] = sum / Math.max(1, end - start);
    }
    return output;
  }

  function float32ToBase64(input: Float32Array) {
    const bytes = new Uint8Array(new Float32Array(input).buffer);
    let binary = "";
    for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
    return window.btoa(binary);
  }

  function requestVoiceMicStream() {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("navigator.mediaDevices.getUserMedia is niet beschikbaar in deze browser/WebView.");
    }
    return navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
  }

  async function startVoiceRecording() {
    if (voiceRecordingRef.current) return;
    let stream: MediaStream | null = null;
    try {
      const AudioCtor = window.AudioContext || (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioCtor) throw new Error("AudioContext is niet beschikbaar in deze runtime.");
      stream = await requestVoiceMicStream();
      const ws = await ensureOpenclawVoiceConnected();
      const audioContext = new AudioCtor({ sampleRate: 16000 });
      await audioContext.resume().catch(() => undefined);
      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      voiceStreamRef.current = stream;
      stream = null;
      voiceAudioContextRef.current = audioContext;
      voiceSourceRef.current = source;
      voiceProcessorRef.current = processor;
      voiceRecordingRef.current = true;
      setVoiceRecording(true);
      setVoiceTranscript("");
      setVoiceResponse("");
      setVoiceError("");
      voiceAudibleAudioRef.current = false;
      ws.send(JSON.stringify({ type: "start_listening" }));
      processor.onaudioprocess = (event) => {
        const activeWs = voiceWsRef.current;
        if (!voiceRecordingRef.current || activeWs?.readyState !== WebSocket.OPEN) return;
        const input = event.inputBuffer.getChannelData(0);
        const pcm16k = downsampleFloat32(input, audioContext.sampleRate, 16000);
        activeWs.send(JSON.stringify({ type: "audio", data: float32ToBase64(pcm16k) }));
      };
      source.connect(processor);
      processor.connect(audioContext.destination);
    } catch (error) {
      stream?.getTracks().forEach((track) => track.stop());
      cleanupVoiceCapture(false);
      const message = error instanceof DOMException && ["NotAllowedError", "SecurityError", "NotFoundError"].includes(error.name)
        ? await microphonePermissionHint(error)
        : error instanceof Error && /not allowed|denied|permission|user agent|platform/i.test(error.message)
          ? await microphonePermissionHint(error)
          : error instanceof Error ? error.message : String(error);
      setVoiceError(message);
      pushEvent("OpenClaw mic blocked", { status: "blocked", error: message, fake_success: false });
    }
  }

  function stopVoiceRecording() {
    cleanupVoiceCapture(true);
  }

  function queueOpenclawAudio(data: string, sampleRate: number) {
    voiceAudioQueueRef.current.push({ data, sampleRate });
    void drainOpenclawAudioQueue();
  }

  function decodeOpenclawPcm(data: string) {
    const binary = window.atob(data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    if (bytes.byteLength % 4 === 0) {
      const floatView = new Float32Array(buffer);
      let maxFloat = 0;
      let validFloat = floatView.length > 0;
      for (let i = 0; i < floatView.length; i += 1) {
        const value = floatView[i];
        if (!Number.isFinite(value) || Math.abs(value) > 1.25) validFloat = false;
        maxFloat = Math.max(maxFloat, Math.abs(value));
      }
      if (validFloat && maxFloat > 0.0001) {
        voiceAudibleAudioRef.current = true;
        return floatView;
      }
    }
    const int16 = new Int16Array(buffer.slice(0, bytes.byteLength - (bytes.byteLength % 2)));
    const float32 = new Float32Array(int16.length);
    let maxInt = 0;
    for (let i = 0; i < int16.length; i += 1) {
      maxInt = Math.max(maxInt, Math.abs(int16[i]));
      float32[i] = int16[i] / 32768;
    }
    if (maxInt > 4) voiceAudibleAudioRef.current = true;
    return float32;
  }

  async function drainOpenclawAudioQueue() {
    if (voiceAudioPlayingRef.current) return;
    voiceAudioPlayingRef.current = true;
    try {
      while (voiceAudioQueueRef.current.length) {
        const chunk = voiceAudioQueueRef.current.shift();
        if (!chunk) break;
        const AudioCtor = window.AudioContext || (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        if (!AudioCtor) break;
        const audio = decodeOpenclawPcm(chunk.data);
        if (!audio.length) continue;
        const audioContext = new AudioCtor({ sampleRate: chunk.sampleRate });
        const buffer = audioContext.createBuffer(1, audio.length, chunk.sampleRate);
        buffer.copyToChannel(audio, 0);
        const source = audioContext.createBufferSource();
        source.buffer = buffer;
        source.connect(audioContext.destination);
        await new Promise<void>((resolve) => {
          source.onended = () => {
            audioContext.close().catch(() => undefined);
            resolve();
          };
          source.start();
        });
      }
    } catch (error) {
      setVoiceError(error instanceof Error ? error.message : String(error));
    } finally {
      voiceAudioPlayingRef.current = false;
    }
  }

  function speakVoiceText(text: string) {
    if (!("speechSynthesis" in window)) return;
    const cleaned = text
      .replace(/```[\s\S]*?```/g, "codeblok")
      .replace(/[`*_#>-]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (!cleaned) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(cleaned);
    utterance.lang = "nl-NL";
    utterance.rate = 1;
    window.speechSynthesis.speak(utterance);
  }

  async function sendChat() {
    setChatOutput("");
    const filePaths = uploadedFiles.map((f) => f.path);
    const reservedWindow = reserveExternalWindow(prompt, approval, approvalPhrase);
    const data = await perform("Agent chat", () =>
      api<Record<string, unknown>>(OUROBOROS_BACKEND_CONTRACT.cockpitChat, {
        method: "POST",
        timeoutMs: CHAT_REQUEST_TIMEOUT_MS,
        body: JSON.stringify({ provider, model, prompt, approval, include_tools: true, files: filePaths.length ? filePaths : undefined }),
      }),
    );
    if (data) {
      const openResult = await handleFrontendAction(data, reservedWindow);
      if (!openResult) closeReservedWindow(reservedWindow);
      setLastChatResult(data);
      setChatOutput(renderResponse(data, openResult));
      await loadQuantumFoamStatus();
      await loadLivingStatus();
      await loadNexusStatus();
      // Slash-agent dispatched a background job — pull it into the Agent Jobs panel right away
      // instead of waiting for the next 5s poll.
      const job = (data as { job?: { job_id?: string } }).job;
      if ((data.route === "slash_agent" || data.route === "roo_runtime") && job?.job_id) {
        setSelectedAgentJobId(job.job_id);
        try {
          const jobsResponse = await api<{ jobs?: AgentJob[] }>("/api/agent-runtime/jobs?limit=20");
          setAgentJobs(Array.isArray(jobsResponse.jobs) ? jobsResponse.jobs : []);
        } catch {
          // ignore — the regular refresh will catch up
        }
      }
    } else {
      closeReservedWindow(reservedWindow);
    }
  }

  async function handleFrontendAction(data: Record<string, unknown>, reservedWindow: Window | null = null): Promise<ExternalOpenResult | null> {
    const action = data.frontend_action as FrontendAction | undefined;
    if (action?.type !== "open_url" || !action.url) return null;
    const openResult = await openExternalUrl(action.url, action.target ?? "_blank", reservedWindow);
    if (action.action_id) {
      await api("/trainer/codex/agent/frontend-event", {
        method: "POST",
        body: JSON.stringify({
          action_id: action.action_id,
          status: openResult.opened ? "opened" : "blocked_by_browser",
          detail: openResult.detail,
          payload: { url: action.url, source: "cockpit_chat", via: openResult.via },
        }),
      }).catch(() => undefined);
    }
    return openResult;
  }

  function insertSlash(prefix: string) {
    setPrompt((current) => {
      const text = current.trim();
      if (!text || text.startsWith("/")) return `${prefix} `;
      return `${prefix} ${current}`;
    });
  }

  async function createModel() {
    await perform("Create/Refresh Ouroboros Model", () =>
      api<Record<string, unknown>>(OUROBOROS_BACKEND_CONTRACT.createFlow, {
        method: "POST",
        body: JSON.stringify({ base_model: model, approval, execute: approvalReady }),
      }),
    );
  }

  async function selfTrainingStep() {
    await perform("Self-training step", () =>
      api<Record<string, unknown>>(OUROBOROS_BACKEND_CONTRACT.selfTrainingStep, {
        method: "POST",
        body: JSON.stringify({ prompt, approval, run_tests: runTestsWithLoop, test_selector: testSelector }),
      }),
    );
  }

  async function runTests() {
    await perform("Run backend tests", () =>
      api<Record<string, unknown>>(OUROBOROS_BACKEND_CONTRACT.agentTool, {
        method: "POST",
        body: JSON.stringify({
          tool_name: "run_tests",
          args: { test_selector: testSelector, approval },
        }),
      }),
    );
  }

  async function inspectMemory() {
    await perform("Inspect 11D memory", () =>
      api<Record<string, unknown>>(OUROBOROS_BACKEND_CONTRACT.hippocampusInspect, {
        method: "POST",
        body: JSON.stringify({ limit: 7 }),
      }),
    );
  }

  async function saveApiKey(providerId: string) {
    const apiKey = apiKeyInputs[providerId] ?? "";
    await perform(`Save ${PROVIDER_LABELS[providerId] ?? providerId} key`, () =>
      api<Record<string, unknown>>(OUROBOROS_BACKEND_CONTRACT.apiKeys, {
        method: "POST",
        body: JSON.stringify({ provider: providerId, api_key: apiKey, approval }),
      }),
    );
    setApiKeyInputs((previous) => ({ ...previous, [providerId]: "" }));
  }

  async function deleteApiKey(providerId: string) {
    await perform(`Delete ${PROVIDER_LABELS[providerId] ?? providerId} key`, () =>
      api<Record<string, unknown>>(OUROBOROS_BACKEND_CONTRACT.apiKeys, {
        method: "POST",
        body: JSON.stringify({ provider: providerId, delete: true, approval }),
      }),
    );
  }

  async function saveSubscription(providerId: string) {
    const input = subscriptionInputs[providerId] ?? { auth_mode: "api_key_from_subscription", api_key: "", plan_label: "" };
    const authMode = input.auth_mode || "api_key_from_subscription";
    const credential = input.api_key.trim();
    await perform(`Save ${PROVIDER_LABELS[providerId] ?? providerId} subscription`, () =>
      api<Record<string, unknown>>(OUROBOROS_BACKEND_CONTRACT.subscriptions, {
        method: "POST",
        body: JSON.stringify({
          provider: providerId,
          auth_mode: authMode,
          api_key: authMode === "api_key_from_subscription" ? credential : undefined,
          session_token: authMode === "session_token" ? credential : undefined,
          refresh_token: authMode === "oauth_refresh_token" ? credential : undefined,
          plan_label: input.plan_label || undefined,
          active: true,
          approval,
        }),
      }),
    );
    setSubscriptionInputs((previous) => ({ ...previous, [providerId]: { auth_mode: "", api_key: "", plan_label: "" } }));
  }

  async function deleteSubscription(providerId: string) {
    await perform(`Delete ${PROVIDER_LABELS[providerId] ?? providerId} subscription`, () =>
      api<Record<string, unknown>>(OUROBOROS_BACKEND_CONTRACT.subscriptions, {
        method: "POST",
        body: JSON.stringify({ provider: providerId, delete: true, approval }),
      }),
    );
  }

  async function toggleSubscription(providerId: string, active: boolean) {
    await perform(`${active ? "Activate" : "Deactivate"} ${PROVIDER_LABELS[providerId] ?? providerId} subscription`, () =>
      api<Record<string, unknown>>(OUROBOROS_BACKEND_CONTRACT.subscriptions, {
        method: "POST",
        body: JSON.stringify({ provider: providerId, toggle_active: true, active, approval }),
      }),
    );
  }

  async function validateSubscription(providerId: string) {
    await perform(`Validate ${PROVIDER_LABELS[providerId] ?? providerId} subscription`, () =>
      api<Record<string, unknown>>(OUROBOROS_BACKEND_CONTRACT.subscriptions, {
        method: "POST",
        body: JSON.stringify({ provider: providerId, validate_only: true, approval }),
      }),
    );
  }

  async function toggleConnector(connectorId: string, enabled: boolean) {
    const result = await perform(`${enabled ? "Enable" : "Disable"} ${connectorId}`, () =>
      api<Record<string, unknown>>(`${OUROBOROS_BACKEND_CONTRACT.connectors}/${encodeURIComponent(connectorId)}`, {
        method: "POST",
        body: JSON.stringify({ enabled, approval, updated_by: "cockpit" }),
      }),
    );
    if (result) await loadConnectorsStatus();
  }

  async function toggleConnectorTool(toolName: string, enabled: boolean) {
    const result = await perform(`${enabled ? "Enable" : "Disable"} ${toolName}`, () =>
      api<Record<string, unknown>>(`${OUROBOROS_BACKEND_CONTRACT.connectors}/tools/${encodeURIComponent(toolName)}`, {
        method: "POST",
        body: JSON.stringify({ enabled, approval, updated_by: "cockpit" }),
      }),
    );
    if (result) await loadConnectorsStatus();
  }

  async function startGoogleOAuth() {
    if (!approvalReady) {
      pushEvent("Google OAuth start", { status: "blocked", reason: `Type ${approvalPhrase} om Google OAuth te configureren.` });
      return;
    }
    let reservedWindow: Window | null = null;
    if (!isLikelyTauriRuntime()) {
      try {
        reservedWindow = window.open("about:blank", "_blank");
      } catch {
        reservedWindow = null;
      }
    }
    const redirectUri =
      googleOAuthRedirectUri.trim() ||
      `${backend}${OUROBOROS_BACKEND_CONTRACT.googleOAuthStatus.replace("/status", "/callback")}`;
    const result = await perform("Google OAuth start", () =>
      api<GoogleOAuthStartResult>(OUROBOROS_BACKEND_CONTRACT.googleOAuthStart, {
        method: "POST",
        body: JSON.stringify({
          client_id: googleOAuthClientId.trim(),
          client_secret: googleOAuthClientSecret.trim(),
          client_json: googleOAuthClientJson.trim(),
          redirect_uri: redirectUri,
          approval,
        }),
      }),
    );
    if (result) {
      setGoogleOAuthStartResult(result);
      setGoogleOAuthClientSecret("");
      setGoogleOAuthClientJson("");
      setGoogleOAuthRedirectUri(redirectUri);
      if (result.authorization_url) {
        const openResult = await openExternalUrl(result.authorization_url, "_blank", reservedWindow);
        reservedWindow = null;
        pushEvent("Google OAuth page", {
          status: openResult.opened ? "opened" : "blocked_by_browser",
          detail: openResult.detail,
          via: openResult.via,
        });
      } else {
        closeReservedWindow(reservedWindow);
        reservedWindow = null;
      }
      await loadGoogleOAuthStatus();
      await loadConnectorsStatus();
    } else {
      closeReservedWindow(reservedWindow);
    }
  }

  async function exchangeGoogleOAuthCode() {
    if (!approvalReady) {
      pushEvent("Google OAuth exchange", { status: "blocked", reason: `Type ${approvalPhrase} om de Google-code op te slaan.` });
      return;
    }
    const code = googleOAuthCode.trim();
    let latestOAuth = googleOAuthStatus;
    try {
      latestOAuth = await api<GoogleOAuthStatus>(OUROBOROS_BACKEND_CONTRACT.googleOAuthStatus);
      setGoogleOAuthStatus(latestOAuth);
    } catch {
      // Use the last polled status if the preflight refresh fails.
    }
    const usePendingCode = !code && Boolean(latestOAuth.pending_code?.available);
    if (!code && !usePendingCode) {
      pushEvent("Google OAuth exchange", { status: "blocked", reason: "Plak eerst de Google authorization code of rond de Google callback af." });
      return;
    }
    const result = await perform("Google OAuth exchange", () =>
      api<GoogleOAuthStatus>(OUROBOROS_BACKEND_CONTRACT.googleOAuthExchange, {
        method: "POST",
        body: JSON.stringify({
          code,
          client_id: googleOAuthClientId.trim(),
          client_secret: googleOAuthClientSecret.trim(),
          client_json: googleOAuthClientJson.trim(),
          redirect_uri: googleOAuthRedirectUri.trim(),
          use_pending_code: usePendingCode,
          approval,
        }),
      }),
    );
    if (result) {
      setGoogleOAuthCode("");
      setGoogleOAuthClientSecret("");
      setGoogleOAuthClientJson("");
      setGoogleOAuthStartResult(null);
      await loadGoogleOAuthStatus();
      await loadConnectorsStatus();
    }
  }

  async function startRooCloudLogin() {
    let reservedWindow: Window | null = null;
    if (!isLikelyTauriRuntime()) {
      try {
        reservedWindow = window.open("about:blank", "_blank");
      } catch {
        reservedWindow = null;
      }
    }
    const result = await perform("Roo Cloud login", () =>
      api<Record<string, unknown>>(OUROBOROS_BACKEND_CONTRACT.rooAuthLogin, {
        method: "POST",
        body: JSON.stringify({ approval }),
        timeoutMs: 25000,
      }),
    );
    if (result) {
      const action = result.frontend_action as { url?: unknown; target?: unknown } | undefined;
      const authUrl = typeof result.auth_url === "string" ? result.auth_url : typeof action?.url === "string" ? action.url : "";
      const target = typeof action?.target === "string" ? action.target : "_blank";
      if (authUrl) {
        const openResult = await openExternalUrl(authUrl, target, reservedWindow);
        reservedWindow = null;
        pushEvent("Roo OAuth page opened", {
          status: openResult.opened ? "opened" : "blocked_by_browser",
          detail: openResult.detail,
          via: openResult.via,
        });
      } else {
        closeReservedWindow(reservedWindow);
      }
      await refresh();
    } else {
      closeReservedWindow(reservedWindow);
    }
  }

  async function loopAction(action: "start" | "pause" | "abort") {
    const endpoint =
      action === "start"
        ? OUROBOROS_BACKEND_CONTRACT.loopStart
        : action === "pause"
          ? OUROBOROS_BACKEND_CONTRACT.loopPause
          : OUROBOROS_BACKEND_CONTRACT.loopAbort;
    await perform(`Loop ${action}`, () =>
      api<LoopStatus>(endpoint, {
        method: "POST",
        body: action === "start"
          ? JSON.stringify({ prompt, provider, model, approval, run_tests: runTestsWithLoop, test_selector: testSelector })
          : JSON.stringify({ reason: action }),
      }),
    );
  }

  async function runCommand() {
    setBusy(true);
    writeTerm(`$ ${command}`);
    try {
      const data = await api<{ status: string; stdout?: string; stderr?: string; exit_code?: number }>(
        OUROBOROS_BACKEND_CONTRACT.shell,
        { method: "POST", body: JSON.stringify({ command, approval, timeout: 20 }) },
      );
      if (data.stdout) writeTerm(data.stdout.trimEnd());
      if (data.stderr) writeTerm(data.stderr.trimEnd());
      writeTerm(`exit=${data.exit_code ?? "n/a"} status=${data.status}`);
      pushEvent("Safe shell", data);
      await refresh();
    } catch (error) {
      writeTerm(`shell error: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function cancelAgentJob(jobId: string) {
    setBusy(true);
    try {
      const data = await api<{ status: string; job: AgentJob }>(
        `/api/agent-runtime/jobs/${jobId}/cancel`,
        { method: "POST" },
      );
      pushEvent(`Agent job ${jobId.slice(0, 18)} cancelled`, data);
      await refresh();
    } catch (error) {
      pushEvent(`Agent job cancel error`, { status: "error", error: error instanceof Error ? error.message : String(error) });
    } finally {
      setBusy(false);
    }
  }

  async function livingAction(action: "start" | "tick" | "stop") {
    const endpoint =
      action === "start"
        ? "/api/ouroboros/esoteric/living/start"
        : action === "stop"
          ? "/api/ouroboros/esoteric/living/stop"
          : "/api/ouroboros/esoteric/living/tick";
    const data = await perform(`Living Ouroboros ${action}`, () =>
      api<Record<string, unknown>>(endpoint, {
        method: "POST",
        body: action === "tick" ? JSON.stringify({ trigger: "cockpit", payload: { provider, model } }) : undefined,
      }),
    );
    if (data) {
      await loadLivingStatus();
      await loadQuantumFoamStatus();
    }
  }

  async function quantumFoamAction(action: "initiate" | "tick" | "collapse") {
    const endpoint =
      action === "initiate"
        ? "/api/ouroboros/esoteric/quantum-foam/initiate"
        : action === "collapse"
          ? "/api/ouroboros/esoteric/quantum-foam/collapse"
          : "/api/ouroboros/esoteric/quantum-foam/tick";
    const body =
      action === "initiate"
        ? { task: prompt || "Cockpit Quantum Foam field", context: { provider, model }, collapse_existing: true }
        : action === "collapse"
          ? { reason: "cockpit_manual_collapse" }
          : { trigger: "cockpit", evolve: true };
    const data = await perform(`Quantum Foam ${action}`, () =>
      api<Record<string, unknown>>(endpoint, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    );
    if (data) {
      await loadQuantumFoamStatus();
      await loadLivingStatus();
      await loadNexusStatus();
    }
  }

  const records = status.records ?? {};
  const learning = status.learning_11d?.chromadb ?? {};
  const createFlow = status.model?.create_flow;
  const loopResult = loop.last_result ?? loop.last_step ?? loop.loop ?? {};
  const roleEntries = Object.entries(status.role_models ?? {});
  const toolCount = status.roo_adapter?.local_python_adapters?.length ?? 0;
  const apiKeyStatus = config.api_keys?.providers ?? {};
  const apiKeyChoices = API_KEY_PROVIDERS.map((id) => {
    const details = (config.provider_options ?? config.providers ?? {})[id] ?? {};
    return {
      id,
      label: PROVIDER_LABELS[id] ?? details.label ?? id,
      enabled: !!details.enabled,
      keySource: details.key_source,
      maskedKey: details.masked_key,
    };
  });
  const selfContext = config.self_context;
  const rooDetails = (config.provider_options ?? config.providers ?? {}).roo ?? {};
  const rooLogin = rooDetails.subscription_login;
  const rooCloudModels = rooDetails.roo_cloud_models ?? [];
  const rooCatalog = rooDetails.model_catalog_status;
  const rooCatalogOnline = (rooCatalog?.status === "online" || !!rooCatalog?.available) && ((rooCatalog?.model_count ?? rooCloudModels.length) > 0);
  const rooLoggedIn = Boolean(rooLogin?.logged_in || rooCatalogOnline);
  const chroma = config.chroma ?? {};
  const chromaCollections = chroma.collections ?? {};
  const localModels = config.available_models?.ollama ?? status.model?.available_bases ?? [];
  const subscriptionProviderCount = providerChoices.filter((item) => item.kind === "external").length;
  const configuredKeyCount = apiKeyChoices.filter((item) => {
    const key = apiKeyStatus[item.id];
    return !!key?.configured || !!item.enabled;
  }).length;
  const connectorList = connectors.connectors ?? [];
  const connectorEnabledCount = connectorList.filter((connector) => connector.enabled).length;
  const connectorTotal = connectorList.length || connectors.connector_count || 0;
  const architectureAgents = agentArchitecture.agents ?? [];
  const architectureReady = architectureAgents.filter((agent) => agent.readiness === "klaar").length;
  const architectureStatus = agentArchitecture.status ?? "unknown";
  const navItems: Array<{ id: ActiveTab; label: string; icon: ReactNode; hint: string }> = [
    { id: "chat", label: "Chat", icon: <MessageSquare size={16} />, hint: `${selfContext?.conversation_count ?? 0} chats` },
    { id: "tools", label: "Tools", icon: <Wrench size={16} />, hint: "shell + tests" },
    { id: "models", label: "Models", icon: <KeyRound size={16} />, hint: `${localModels.length} local / ${configuredKeyCount} keys / ${rooLoggedIn ? "Roo login" : "Roo off"}` },
    { id: "connectors", label: "Connectors", icon: <Plug size={16} />, hint: `${connectorEnabledCount}/${connectorTotal} on` },
    { id: "agents", label: "Agents", icon: <Bot size={16} />, hint: `${architectureAgents.length || agentArchitecture.agent_count || 0} roles / ${agentJobs.length} jobs` },
    { id: "memory", label: "Memory", icon: <History size={16} />, hint: `${records.total_count ?? 0} records` },
    { id: "trainer", label: "Trainer", icon: <Layers size={16} />, hint: trainerStatus?.status ?? "learning" },
    { id: "context", label: "Context", icon: <FolderTree size={16} />, hint: "workspace" },
  ];
  const selectedAgentJob = agentJobs.find((job) => job.job_id === selectedAgentJobId) ?? null;
  const agentJobTerminalStatuses = new Set(["completed", "failed", "cancelled"]);
  const deepseekCapability = externalCapabilities.capabilities?.deepseek;
  const atlasCapability = externalCapabilities.capabilities?.atlas;
  const deepseekCapabilityStatus = capabilityStatusLabel(deepseekCapability?.status);
  const atlasCapabilityStatus = capabilityStatusLabel(atlasCapability?.status);
  const agentShortcuts: Array<{ label: string; slash: string; icon: ReactNode; value: string; ok: boolean }> = [
    {
      label: "Roo Code",
      slash: "/roo",
      icon: <Bot size={15} />,
      value: status.roo_adapter?.available ? "online" : status.roo_adapter?.status ?? "unknown",
      ok: !!status.roo_adapter?.available,
    },
    {
      label: "DeepSeek",
      slash: "/deepseek",
      icon: <Layers size={15} />,
      value: deepseekCapabilityStatus,
      ok: capabilityStatusOk(deepseekCapability?.status),
    },
  ];
  const runtimeDoctorStatus = runtimeDoctor.status ?? "unknown";
  const runtimeDoctorOk = runtimeDoctorStatus === "ready";
  const runtimeDoctorBlockers = Array.isArray(runtimeDoctor.blockers) ? runtimeDoctor.blockers.slice(0, 3) : [];
  const runtimeDoctorChecks = runtimeDoctor.checks ?? {};
  const runtimeDoctorSummary =
    runtimeDoctorBlockers.length > 0
      ? runtimeDoctorBlockers.join(" · ")
      : `backend ${runtimeDoctorChecks.backend_http?.status ?? "unknown"} · preview ${runtimeDoctorChecks.web_preview?.status ?? "unknown"} · bridge ${runtimeDoctorChecks.host_bridge?.status ?? "unknown"}`;

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <img className="brand-logo" src={ouroborosLogoUrl} alt="Ouroboros logo" />
          <div>
            <h1>Ouroboros</h1>
            <span>{health.status ?? "unknown"} / {records.total_count ?? health.memories ?? 0} records</span>
          </div>
        </div>

        <div className="tab-nav">
          {navItems.map((item) => (
            <button className={activeTab === item.id ? "active" : ""} onClick={() => setActiveTab(item.id)} key={item.id}>
              {item.icon}
              <span>{item.label}</span>
              <em>{item.hint}</em>
            </button>
          ))}
        </div>

        <div className="agent-shortcuts">
          {agentShortcuts.map((item) => (
            <button
              className={item.ok ? "online" : "warn"}
              key={item.slash}
              onClick={() => {
                setActiveTab("chat");
                insertSlash(item.slash);
              }}
              title={`${item.slash} ${item.value}`}
              type="button"
            >
              {item.icon}
              <span>{item.label}</span>
              <em>{item.value}</em>
            </button>
          ))}
        </div>

        <label>
          Motor
          <select value={provider} onChange={(event) => onProviderChange(event.target.value)}>
            {providerChoices.map((item) => (
              <option value={item.id} key={item.id} disabled={!item.enabled}>
                {item.label} {item.enabled ? "" : `(${item.status})`}
              </option>
            ))}
          </select>
        </label>

        <label>
          Model
          <select value={model} onChange={(event) => setModel(event.target.value)}>
            {selectedModels.map((item) => (
              <option value={item} key={item}>
                {item}
              </option>
            ))}
          </select>
        </label>

        <label>
          Akkoord
          <input value={approval} onChange={(event) => setApproval(event.target.value)} placeholder={approvalPhrase} />
        </label>

        <label className="check-row">
          <input type="checkbox" checked={runTestsWithLoop} onChange={(event) => setRunTestsWithLoop(event.target.checked)} />
          Test na agentstap
        </label>

        <div className="status-grid">
          <Metric label="Model" value={status.model?.status ?? "--"} tone={status.model?.online ? "good" : "warn"} />
          <Metric label="Roo" value={status.roo_adapter?.status ?? "--"} tone={status.roo_adapter?.available ? "good" : "warn"} />
          <Metric label="11D" value={status.learning_11d?.status ?? "--"} tone={learning.available ? "good" : "warn"} />
          <Metric label="Loop" value={loop.status ?? "--"} tone={loop.status === "completed" || loop.status === "idle" ? "good" : "warn"} />
        </div>

        <div className="provider-note">
          <strong>{selectedProvider?.label ?? "Geen motor"}</strong>
          <span>{selectedProvider?.enabled ? selectedProvider.status : selectedProvider?.reason}</span>
        </div>

        <button className="ghost" onClick={refresh}>
          <RefreshCw size={15} /> Refresh
        </button>
      </aside>

      <section className="workspace">
        <header className="system-strip">
          <StatusPill
            icon={<Activity size={16} />}
            label="Runtime Doctor"
            value={runtimeDoctorStatus}
            ok={runtimeDoctorOk}
          />
          <StatusPill icon={<Cpu size={16} />} label="Ollama" value={status.model?.ollama_online ? "online" : "offline"} ok={!!status.model?.ollama_online} />
          <StatusPill icon={<Bot size={16} />} label="Ouroboros" value={status.model?.online ? "created" : "offline"} ok={!!status.model?.online} />
          <StatusPill icon={<Hammer size={16} />} label="Pipeline" value={status.self_modification_pipeline?.status ?? "not configured"} ok={status.self_modification_pipeline?.status === "online"} />
          <StatusPill icon={<Plug size={16} />} label="Connectors" value={`${connectorEnabledCount}/${connectorTotal || "?"} on`} ok={connectors.status === "online" && connectorEnabledCount > 0} />
          <StatusPill icon={<ShieldCheck size={16} />} label="Architecture" value={`${architectureReady}/${architectureAgents.length || agentArchitecture.agent_count || 4} klaar`} ok={architectureStatus === "online" && architectureReady >= 1} />
          <StatusPill icon={<Database size={16} />} label="11D" value={`${learning.total_count ?? records.total_count ?? 0}`} ok={!!learning.available} />
          <StatusPill icon={<ShieldCheck size={16} />} label="Approval" value={approvalReady ? "approved" : "locked"} ok={approvalReady} />
          <StatusPill
            icon={<Activity size={16} />}
            label="Ω Nexus"
            value={nexusStatus.operational?.status ?? nexusStatus.status ?? "unknown"}
            ok={nexusStatus.operational?.status === "online" || (nexusStatus.operational?.status !== "degraded" && nexusStatus.status === "online")}
          />
          <StatusPill
            icon={<BrainCircuit size={16} />}
            label="Living"
            value={livingStatus.mode ?? livingStatus.status ?? "idle"}
            ok={livingStatus.mode === "speaking" || livingStatus.mode === "running" || livingStatus.status === "idle"}
          />
          <StatusPill
            icon={<Activity size={16} />}
            label="Quantum Foam Field"
            value={quantumFoamStatus.active_field_count ? `active ${Math.round(quantumFoamStatus.field_coherence_percent ?? 0)}%` : quantumFoamStatus.latest_field?.status ?? quantumFoamStatus.status ?? "idle"}
            ok={quantumFoamStatus.status === "online" || quantumFoamStatus.status === "idle"}
          />
          <StatusPill icon={<Globe2 size={16} />} label="World" value={worldStatus.status ?? "unknown"} ok={worldStatus.status === "online"} />
          <StatusPill icon={<Mic size={16} />} label="Voice" value={voiceStatusLabel} ok={voiceReady} />
          <StatusPill
            icon={<Bot size={16} />}
            label="AgentS"
            value={agentsStatus.status ?? "unknown"}
            ok={agentsStatus.status === "online" || agentsStatus.status === "available" || agentsStatus.runtime_reachable === true}
          />
          <StatusPill
            icon={<Hammer size={16} />}
            label="OpenHands"
            value={openhandsStatus.status ?? "unknown"}
            ok={openhandsStatus.status === "online" || openhandsStatus.status === "available"}
          />
          <StatusPill
            icon={<Layers size={16} />}
            label="DeepSeek"
            value={deepseekCapabilityStatus}
            ok={capabilityStatusOk(deepseekCapability?.status)}
          />
          <StatusPill
            icon={<FolderTree size={16} />}
            label="Atlas"
            value={atlasCapabilityStatus}
            ok={capabilityStatusOk(atlasCapability?.status)}
          />
        </header>

        <section className={`runtime-doctor runtime-doctor-${runtimeDoctorStatus}`}>
          <div>
            <strong>Runtime Doctor</strong>
            <span>{runtimeDoctorSummary}</span>
          </div>
          <div className="runtime-doctor-checks">
            {["backend_http", "web_preview", "host_bridge", "chroma", "tool_registry", "agentic_router"].map((key) => (
              <span className={runtimeDoctorChecks[key]?.status === "online" ? "good" : "warn"} key={key}>
                {key.replace("_", " ")}: {runtimeDoctorChecks[key]?.status ?? "unknown"}
              </span>
            ))}
          </div>
        </section>

        <section className="toolbar">
          <button onClick={createModel} disabled={busy}>
            <Cpu size={15} /> Create/Refresh
          </button>
          <button onClick={selfTrainingStep} disabled={busy || !prompt.trim()}>
            <BrainCircuit size={15} /> Step
          </button>
          <button onClick={runTests} disabled={busy || !approvalReady}>
            <TestTube2 size={15} /> Tests
          </button>
          <button onClick={inspectMemory} disabled={busy}>
            <Database size={15} /> Memory
          </button>
          <button onClick={() => loopAction("start")} disabled={busy || !prompt.trim()}>
            <Play size={15} /> Start
          </button>
          <button onClick={() => loopAction("pause")} disabled={busy}>
            <Pause size={15} /> Pause
          </button>
          <button onClick={() => loopAction("abort")} disabled={busy}>
            <CircleStop size={15} /> Abort
          </button>
        </section>

        {activeTab === "chat" && (
          <>
            <section className="prompt-pane">
              <div className="prompt-stack">
                <div className="slash-strip">
                  {["/codex", "/deepseek", "/atlas", "/ruflo", "/roo", "/claude", "/agents"].map((item) => (
                    <button type="button" key={item} onClick={() => insertSlash(item)}>{item}</button>
                  ))}
                </div>
                <div className="voice-strip">
                  <button
                    type="button"
                    className={voiceRecording ? "voice-recording" : ""}
                    onClick={voiceRecording ? stopVoiceRecording : startVoiceRecording}
                    disabled={busy}
                    title={voiceRecording ? "Stop opname" : "Start spraakcommando"}
                  >
                    {voiceRecording ? <CircleStop size={14} /> : <Mic size={14} />}
                    {voiceRecording ? "Stop" : "Praat"}
                  </button>
                  <button
                    type="button"
                    onClick={disconnectOpenclawVoice}
                    disabled={!voiceConnected && !voiceRecording}
                    title="Verbreek OpenClaw voice"
                  >
                    <Plug size={14} /> Los
                  </button>
                  <button
                    type="button"
                    className={voiceBrowserFallback ? "voice-fallback-on" : ""}
                    onClick={() => setVoiceBrowserFallback((value) => !value)}
                    title="Browserstem als OpenClaw geen hoorbare audio teruggeeft"
                  >
                    {voiceBrowserFallback ? <Volume2 size={14} /> : <VolumeX size={14} />}
                    Stem
                  </button>
                  <span className={`voice-dot ${voiceRecording ? "recording" : voiceConnected ? "connected" : ""}`} />
                  <span className="voice-state">{voiceStatusLabel}</span>
                  {voiceError && <span className="voice-error">{voiceError}</span>}
                  {!voiceError && openclawVoiceStatus.next_action && !voiceConnected && (
                    <span className="voice-hint">{openclawVoiceStatus.next_action}</span>
                  )}
                </div>
                {(voiceTranscript || voiceResponse) && (
                  <div className="voice-live">
                    {voiceTranscript && <span><strong>Jij</strong> {voiceTranscript}</span>}
                    {voiceResponse && <span><strong>Ouroboros</strong> {voiceResponse}</span>}
                  </div>
                )}
                <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} />
                <div className="file-upload-strip">
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".txt,.md,.csv,.json,.pdf,.docx,.py,.js,.ts,.tsx,.html,.css,.xml,.yaml,.yml,.toml,.log"
                    style={{ display: "none" }}
                    onChange={(event) => handleFileUpload(event.target.files)}
                  />
                  <button type="button" className="attach-btn" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
                    <Paperclip size={14} /> {uploading ? "Uploading…" : "Bestand toevoegen"}
                  </button>
                  {uploadedFiles.map((file, index) => (
                    <span className="file-chip" key={`${file.path}-${index}`}>
                      {file.filename} <em>({Math.round(file.size / 1024)}KB)</em>
                      <button type="button" onClick={() => removeUploadedFile(index)} title="Verwijder">
                        <X size={12} />
                      </button>
                    </span>
                  ))}
                </div>
                {slashPrompt && !approvalReady && (
                  <div className="status-pill warn" style={{ alignSelf: "flex-start" }}>
                    Slash agents have approval needed: type <strong>{approvalPhrase}</strong> in the Akkoord field.
                  </div>
                )}
              </div>
              <button onClick={sendChat} disabled={busy || !prompt.trim() || (!slashPrompt && !agenticPrompt && !canCallSelectedProvider)}>
                <Send size={15} /> Send
              </button>
            </section>

            <section className="cockpit-grid focus-grid">
              <section className="panel primary-panel">
                <PanelHeader title="Chat Lane" />
                <pre className="response-box chat-response">{chatOutput || summarizeResult(loopResult) || "Nog geen response."}</pre>
              </section>

              <section className="panel">
                <PanelHeader title="Remembered Chats" />
                <div className="fact-list">
                  <Fact label="Self-context" value={selfContext?.status ?? "unknown"} state={selfContext?.enabled ? "enabled" : "disabled"} />
                  <Fact label="Conversations" value={`${selfContext?.conversation_count ?? 0}`} />
                  <Fact label="Lessons" value={`${selfContext?.lesson_count ?? 0}`} />
                </div>
                <PanelHeader title="Recent Lessons" small />
                <div className="memory-list">
                  {(selfContext?.recent_lessons ?? []).slice(0, 4).map((lesson) => (
                    <div className="memory-row" key={lesson.id ?? lesson.text}>
                      <strong>{lesson.provider ?? "chat"} / {lesson.model ?? "model"}</strong>
                      <p>{summarizeValue(lesson.text).slice(0, 260)}</p>
                    </div>
                  ))}
                  {!(selfContext?.recent_lessons ?? []).length && <div className="empty-state">Nog geen server-side chatlessen gevonden.</div>}
                </div>
              </section>

              <section className="panel">
                <PanelHeader title="Session Actions" />
                <div className="action-summary stacked">
                  <div>
                    <span>Motor</span>
                    <strong>{selectedProvider?.label ?? provider}</strong>
                  </div>
                  <div>
                    <span>Model</span>
                    <strong>{model}</strong>
                  </div>
                  <div>
                    <span>Approval</span>
                    <strong>{approvalReady ? "Akkoord" : "locked"}</strong>
                  </div>
                </div>
                <AgenticTraceReadout data={lastChatResult} />
                <PocketVoiceReadout data={lastChatResult} />
                <PanelHeader title="Events" small />
                <div className="feed">
                  {events.length === 0 ? (
                    <div className="empty-state">Nog geen cockpitactie in deze sessie.</div>
                  ) : (
                    events.map((event) => <EventItem event={event} key={event.id} />)
                  )}
                </div>
              </section>
            </section>
          </>
        )}

        {activeTab === "tools" && (
          <section className="single-lane">
            <section className="panel">
              <PanelHeader title="Shell Commands" />
              <div className="terminal-bar embedded">
                <TerminalSquare size={16} />
                <input value={command} onChange={(event) => setCommand(event.target.value)} onKeyDown={(event) => {
                  if (event.key === "Enter") runCommand();
                }} />
                <button onClick={runCommand} disabled={busy || !command.trim() || !approvalReady}>
                  Run
                </button>
              </div>
              <div className="terminal-host expanded" ref={terminalHost} />
            </section>

            <section className="panel">
              <PanelHeader title="Tests & Loop Tools" />
              <div className="tool-grid">
                <label>
                  Test selector
                  <input value={testSelector} onChange={(event) => setTestSelector(event.target.value)} />
                </label>
                <button onClick={runTests} disabled={busy || !approvalReady}>
                  <TestTube2 size={15} /> Run tests
                </button>
                <button onClick={selfTrainingStep} disabled={busy || !prompt.trim()}>
                  <BrainCircuit size={15} /> Self-training step
                </button>
                <button onClick={() => loopAction("start")} disabled={busy || !prompt.trim()}>
                  <Play size={15} /> Start OODA loop
                </button>
                <button onClick={() => loopAction("pause")} disabled={busy}>
                  <Pause size={15} /> Pause
                </button>
                <button onClick={() => loopAction("abort")} disabled={busy}>
                  <CircleStop size={15} /> Abort
                </button>
              </div>
            </section>
          </section>
        )}

        {activeTab === "models" && (
          <section className="cockpit-grid focus-grid">
            <section className="panel">
              <PanelHeader title="Local Models" />
	              <div className="fact-list">
	                <Fact label="Active base" value={status.model?.active_base ?? model} state={status.model?.status} />
	                <Fact label="Ollama inventory" value={`${status.ollama?.count ?? localModels.length}`} state={status.ollama?.online ? "online" : "offline"} />
		                <Fact label="Cloud providers" value={`${subscriptionProviderCount}`} />
	              </div>
              <PanelHeader title="Available Local Models" small />
              <div className="model-chip-list">
                {localModels.map((item) => <button key={item} type="button" onClick={() => { setProvider("ollama"); setModel(item); }}>{item}</button>)}
	              </div>
	            </section>

	            <section className="panel primary-panel">
	              <PanelHeader title="Roo Cloud Account" />
	              <div className="fact-list">
	                <Fact label="Login" value={rooLoggedIn ? "logged in" : "missing"} state={rooLoggedIn ? "online" : "offline"} />
	                <Fact label="Catalog" value={`${rooCatalog?.model_count ?? rooCloudModels.length}`} state={rooCatalog?.status ?? "unknown"} />
	                <Fact label="Bridge" value={(rooCatalog?.via_bridge || rooLogin?.via_bridge) ? "host" : "local"} state={rooDetails.status ?? "unknown"} />
	              </div>
	              <div className="key-row">
	                <div>
	                  <strong>Roo Code Cloud</strong>
	                  <span>
	                    {rooLoggedIn
	                      ? "Gebruikt de ingelogde Roo-account voor modellen zoals openai/gpt-5 en anthropic/claude-opus-4.7."
	                      : "Start de Roo Cloud login op de host. Dit is de enige web-loginroute die Roo zelf kan gebruiken."}
	                  </span>
	                </div>
	                <button onClick={startRooCloudLogin} disabled={busy || !approvalReady}>
	                  Login
	                </button>
	                <button onClick={refresh} disabled={busy}>
	                  Refresh
	                </button>
	              </div>
		              {rooCloudModels.length > 0 && (
		                <div className="model-chip-list">
		                  {rooCloudModels.map((item) => (
		                    <button key={item} type="button" onClick={() => { setProvider("roo"); setModel(item); }}>{item}</button>
		                  ))}
		                </div>
		              )}
	            </section>

	            <section className="panel primary-panel">
	              <PanelHeader title="Direct API Keys" />
              <div className="key-list">
                {apiKeyChoices.map((item) => {
                  const key = apiKeyStatus[item.id];
                  const configured = !!key?.configured || !!item.enabled;
                  return (
                    <div className="key-row" key={item.id}>
                      <div>
                        <strong>{item.label}</strong>
                        <span>{configured ? `${key?.source ?? item.keySource ?? "configured"} ${key?.masked ?? item.maskedKey ?? ""}` : "missing key"}</span>
                      </div>
                      <input
                        type="password"
                        value={apiKeyInputs[item.id] ?? ""}
                        onChange={(event) => setApiKeyInputs((previous) => ({ ...previous, [item.id]: event.target.value }))}
                        placeholder={configured ? "replace key" : "paste key"}
                      />
                      <button onClick={() => saveApiKey(item.id)} disabled={busy || !approvalReady || !(apiKeyInputs[item.id] ?? "").trim()}>
                        Save
                      </button>
                      <button onClick={() => deleteApiKey(item.id)} disabled={busy || !approvalReady || !configured}>
                        Clear
                      </button>
                    </div>
                  );
                })}
              </div>
            </section>

	            <section className="panel">
	              <PanelHeader title="Provider Catalog" />
	              <div className="role-list">
	                {providerChoices.map((item) => (
	                  <div className="role-row" key={item.id}>
	                    <span>{item.kind === "local" ? "local" : "cloud"}</span>
                    <strong>{item.label}</strong>
                    <em>{item.status}</em>
                  </div>
                ))}
              </div>
            </section>
          </section>
        )}

        {activeTab === "connectors" && (
          <section className="cockpit-grid connector-grid">
            <section className="panel connector-main-panel">
              <PanelHeader title="Connectors" />
              <ConnectorCockpitPanel
                catalog={connectors}
                selectedConnectorId={selectedConnectorId}
                onSelectConnector={setSelectedConnectorId}
                approvalReady={approvalReady}
                busy={busy}
                onRefresh={loadConnectorsStatus}
                onToggleConnector={toggleConnector}
              />
            </section>

            <section className="panel">
              <PanelHeader title="Connector Tools" />
              <ConnectorToolsPanel
                connector={(connectors.connectors ?? []).find((item) => item.id === selectedConnectorId) ?? (connectors.connectors ?? [])[0]}
                approvalReady={approvalReady}
                busy={busy}
                onToggleTool={toggleConnectorTool}
              />
            </section>

            <section className="panel">
              <PanelHeader title="Connector Status" />
              <ConnectorStatusPanel
                connector={(connectors.connectors ?? []).find((item) => item.id === selectedConnectorId) ?? (connectors.connectors ?? [])[0]}
                catalog={connectors}
                googleOAuth={googleOAuthStatus}
                googleOAuthStartResult={googleOAuthStartResult}
                googleOAuthClientId={googleOAuthClientId}
                googleOAuthClientSecret={googleOAuthClientSecret}
                googleOAuthClientJson={googleOAuthClientJson}
                googleOAuthRedirectUri={googleOAuthRedirectUri}
                googleOAuthCode={googleOAuthCode}
                approvalReady={approvalReady}
                busy={busy}
                onGoogleOAuthClientIdChange={setGoogleOAuthClientId}
                onGoogleOAuthClientSecretChange={setGoogleOAuthClientSecret}
                onGoogleOAuthClientJsonChange={setGoogleOAuthClientJson}
                onGoogleOAuthRedirectUriChange={setGoogleOAuthRedirectUri}
                onGoogleOAuthCodeChange={setGoogleOAuthCode}
                onStartGoogleOAuth={startGoogleOAuth}
                onExchangeGoogleOAuthCode={exchangeGoogleOAuthCode}
                onUsePrompt={(text) => {
                  setPrompt(text);
                  setActiveTab("chat");
                }}
              />
            </section>
          </section>
        )}

        {activeTab === "agents" && (
          <section className="cockpit-grid focus-grid">
            <section className="panel">
              <PanelHeader title="Agent Architecture" />
              <AgentArchitecturePanel
                architecture={agentArchitecture}
                review={agentArchitectureReview}
                busy={busy}
                onReview={runArchitectureReview}
              />
            </section>

            <section className="panel">
              <PanelHeader title="Agent Capabilities" />
              <AgentCapabilitiesPanel
                external={externalCapabilities}
                runtimeTools={runtimeTools}
                rooStatus={status.roo_adapter}
                codexJobs={agentJobs.filter((job) => job.agent === "codex")}
                agentsStatus={agentsStatus}
                openhandsStatus={openhandsStatus}
              />
            </section>

            <section className="panel">
              <PanelHeader title="Codex Subsystem" />
              <CodexPanel
                codexStatus={codexStatus}
                codexCapabilities={codexCapabilities}
                codexJobs={agentJobs.filter((job) => job.agent === "codex")}
                runPrompt={codexRunPrompt}
                setRunPrompt={setCodexRunPrompt}
                approvalReady={approvalReady}
                busy={busy}
                onRun={submitCodexRun}
              />
            </section>

            <section className="panel">
              <PanelHeader title="Agent Jobs" />
              <OmegaPointNexusPanel nexus={nexusStatus} />
              {agentJobs.length === 0 ? (
                <div className="empty-state">Nog geen agent jobs. Start er een met /codex, /deepseek of /atlas &lt;opdracht&gt;.</div>
              ) : (
                <div className="role-list">
                  {agentJobs.map((job) => {
                    const isSelected = job.job_id === selectedAgentJobId;
                    const isTerminal = agentJobTerminalStatuses.has(job.status);
                    const pan = job.metadata?.ouroboros_esoteric?.pan_dimensional;
                    const metrics = pan?.metrics ?? {};
                    const entropy = pan?.entropy ?? {};
                    return (
                      <div className="role-row" key={job.job_id} style={{ flexDirection: "column", alignItems: "stretch", gap: 4 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
                          <button
                            type="button"
                            onClick={() => setSelectedAgentJobId(isSelected ? null : job.job_id)}
                            style={{ background: "transparent", border: "none", color: "inherit", padding: 0, cursor: "pointer", textAlign: "left", flex: 1 }}
                          >
                            <strong>{job.agent}</strong> <span>{job.status}</span>
                            <div style={{ fontSize: 11, opacity: 0.7 }}>{job.job_id}</div>
                          </button>
                          {!isTerminal && (
                            <button onClick={() => cancelAgentJob(job.job_id)} disabled={busy || !!job.cancel_requested}>
                              {job.cancel_requested ? "stopping" : "cancel"}
                            </button>
                          )}
                        </div>
                        {job.task && <div style={{ fontSize: 11, opacity: 0.7 }}>{job.task.slice(0, 160)}{job.task.length > 160 ? "..." : ""}</div>}
                        {pan && (
                          <div className="metric-strip">
                            <span>COH <strong>{formatMetric(metrics.coh)}</strong></span>
                            <span>FLUX <strong>{formatMetric(metrics.flux)}</strong></span>
                            <span>ENT <strong>{formatMetric(entropy.entropy_level)}</strong></span>
                            <span>SNR <strong>{formatMetric(entropy.signal_noise_ratio)}</strong></span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              {selectedAgentJob && (
                <>
                  <PanelHeader title={`Events (${selectedAgentJob.job_id.slice(0, 18)})`} small />
                  <pre className="response-box" style={{ maxHeight: 220, overflowY: "auto" }}>
                    {agentJobEvents.length === 0
                      ? "Nog geen events."
                      : agentJobEvents
                          .map((event) => `${event.ts ?? ""} ${event.type ?? ""} ${event.data ? JSON.stringify(event.data) : ""}`.trim())
                          .join("\n")}
                  </pre>
                  {selectedAgentJob.response_preview && (
                    <>
                      <PanelHeader title="Response preview" small />
                      <pre className="response-box">{selectedAgentJob.response_preview}</pre>
                    </>
                  )}
                </>
              )}
            </section>
          </section>
        )}

        {activeTab === "memory" && (
          <section className="cockpit-grid focus-grid">
            <section className="panel">
              <PanelHeader title="11D Memory" />
              <div className="fact-list">
                <Fact label="Main memory" value={`${records.main_collection_count ?? 0}`} />
                <Fact label="Training memory" value={`${records.training_collection_count ?? 0}`} />
                <Fact label="Total" value={`${records.total_count ?? 0}`} state={status.learning_11d?.status} />
                <Fact label="Geometry" value={`${status.geometry_11d?.dimension_count ?? 11}D`} />
                <Fact label="Chroma runtime" value={chroma.mode ?? "persistent"} state={chroma.status} />
                <Fact label="Brain target" value={chroma.remote_url ? "VPS remote" : (chroma.persist_dir ? "local disk" : "--")} />
              </div>
              <div className="memory-list compact">
                {Object.entries(chromaCollections).map(([name, details]) => (
                  <div className="memory-row" key={name}>
                    <span>{name}</span>
                    <strong>{details.count ?? 0}</strong>
                  </div>
                ))}
              </div>
              <PanelHeader title="Agent Roles" small />
              <div className="role-list">
                {roleEntries.length ? roleEntries.map(([role, details]) => (
                  <div className="role-row" key={role}>
                    <span>{role}</span>
                    <strong>{details.model ?? "--"}</strong>
                    {details.available ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                  </div>
                )) : <div className="empty-state">Rolrouter nog niet beschikbaar.</div>}
              </div>
            </section>

            <section className="panel">
              <PanelHeader title="Living Ouroboros" />
              <LivingOuroborosPanel
                living={livingStatus}
                busy={busy}
                onStart={() => livingAction("start")}
                onTick={() => livingAction("tick")}
                onStop={() => livingAction("stop")}
              />
            </section>

            <section className="panel">
              <PanelHeader title="Quantum Foam Field" />
              <QuantumFoamPanel
                field={quantumFoamStatus}
                busy={busy}
                onInitiate={() => quantumFoamAction("initiate")}
                onTick={() => quantumFoamAction("tick")}
                onCollapse={() => quantumFoamAction("collapse")}
              />
            </section>

            <section className="panel">
              <PanelHeader title="World Actions" />
              <WorldActionsPanel world={worldStatus} />
              <details>
                <summary>Raw status</summary>
                <pre>{JSON.stringify(status, null, 2)}</pre>
              </details>
            </section>
          </section>
        )}

        {activeTab === "trainer" && (
          <TrainerPanel api={api} trainerStatus={trainerStatus} trainerJobs={trainerJobs} approval={approval} approvalReady={approvalReady} refresh={refresh} />
        )}

        {activeTab === "context" && (
          <ContextPanel api={api} contextData={contextData} approval={approval} approvalReady={approvalReady} />
        )}

      </section>
    </main>
  );
}

function buildProviderChoices(config: CockpitConfig, status: OuroborosStatus): ProviderChoice[] {
  const options = config.provider_options ?? config.providers ?? {};
  const configuredLocalModels = config.available_models?.ollama ?? config.models ?? status.model?.available_bases ?? [];
  const localFallbackModel =
    status.model?.active_base ??
    options.ollama?.default_model ??
    options.ollama?.model ??
    "llama3.2:latest";
  const localModels = configuredLocalModels.length ? configuredLocalModels : [localFallbackModel].filter(Boolean);
  const choices: ProviderChoice[] = CANONICAL_PROVIDERS.map((id) => {
    const details = options[id] ?? { provider: id };
    const isLocalRuntime = id === "ollama" || id === "ouroboros" || id === "roo";
    const models = id === "ollama" ? localModels : details.models ?? config.available_models?.multi_api?.[id] ?? [];
    const catalog = details.model_catalog_status;
    const rooCatalogReady =
      id === "roo" &&
      Boolean((catalog?.status === "online" || catalog?.available) && ((catalog?.model_count ?? details.roo_cloud_models?.length ?? 0) > 0));
    const enabled =
      id === "ollama"
        ? Boolean(details.enabled ?? true) && models.length > 0
        : id === "roo"
          ? Boolean((details.enabled || details.available || rooCatalogReady) && models.length > 0)
          : !!details.enabled;
    return {
      id,
      label: PROVIDER_LABELS[id] ?? details.label ?? id,
      kind: isLocalRuntime ? "local" : "external",
      enabled,
      status: details.status ?? (enabled ? "online" : "disabled"),
      models,
      defaultModel: (id === "ollama" ? status.model?.active_base ?? details.default_model : details.default_model) ?? details.model ?? models[0] ?? "",
      reason: details.reason ?? details.message ?? (enabled ? "Beschikbaar" : "Niet geconfigureerd."),
      keySource: details.key_source,
      maskedKey: details.masked_key,
    };
  });

  return choices.filter((item) => item.kind === "local" || item.models.length > 0);
}

function resultStatus(raw: unknown): string {
  if (raw && typeof raw === "object" && "status" in raw) {
    return String((raw as { status?: unknown }).status ?? "unknown");
  }
  return raw ? "success" : "idle";
}

function unavailableStatus(previous?: string): string {
  return previous && previous !== "unknown" && previous !== "loading" ? previous : "unavailable";
}

function formatMetric(value: unknown): string {
  if (typeof value === "number") return Number.isFinite(value) ? value.toFixed(value >= 10 ? 1 : 3) : "--";
  if (typeof value === "string" && value.trim()) return value;
  return "--";
}

function summarizeValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(summarizeValue).filter(Boolean).join(", ");
  if (typeof value === "object") {
    const data = value as Record<string, unknown>;
    const direct = [data.name, data.model, data.active_base, data.status]
      .map(summarizeValue)
      .filter(Boolean);
    if (direct.length) return direct.join("/");
    return JSON.stringify(data);
  }
  return String(value);
}

function shouldSurfaceDiagnostic(data: Record<string, unknown>): boolean {
  const status = summarizeValue(data.status).toLowerCase();
  return Boolean(
    data.error ||
    ["error", "blocked", "failed", "failure", "disabled", "unavailable", "approval_required", "rate_limited"].includes(status),
  );
}

function summarizeResult(raw: unknown): string {
  if (!raw || typeof raw !== "object") return raw ? String(raw) : "";
  const data = raw as Record<string, unknown>;
  const route = summarizeValue(data.route);
  const agent = summarizeValue(data.agent);
  const isSlashAgent = route === "slash_agent";
  const isAgentic = route === "agentic_processor";
  if (isSlashAgent && agent === "catalog" && (data.response || data.message)) {
    return summarizeValue(data.response || data.message).slice(0, 4000);
  }
  const livingEcho =
    !isSlashAgent && data.living_echo && typeof data.living_echo === "object"
      ? (data.living_echo as Record<string, unknown>)
      : null;
  const pocketVoice = !isSlashAgent ? asRecord(data.pocket_voice) : {};
  const provenance = isAgentic ? asRecord(data.provenance) : {};
  const sourceTrace = asRecord(data.source_trace);
  const quantumCollapse = !isSlashAgent ? asRecord(data.quantum_collapse) : {};
  const cirqRuntime = asRecord(quantumCollapse.cirq_runtime ?? pocketVoice.cirq_runtime);
  const dominant = Array.isArray(pocketVoice.dominant_dimensions)
    ? pocketVoice.dominant_dimensions.map(summarizeValue).filter(Boolean).join(", ")
    : "";
  const toolsUsedRaw = sourceTrace.tools_executed ?? provenance.tools_used;
  const toolsUsed = Array.isArray(toolsUsedRaw)
    ? toolsUsedRaw.map(summarizeValue).filter(Boolean).join(" -> ")
    : "";
  const toolsBlocked = Array.isArray(sourceTrace.tools_blocked)
    ? sourceTrace.tools_blocked.map(summarizeValue).filter(Boolean).join(" -> ")
    : "";
  const plannerGuardrails = Array.isArray(sourceTrace.planner_guardrails_applied)
    ? sourceTrace.planner_guardrails_applied.map(summarizeValue).filter(Boolean).join(" -> ")
    : Array.isArray(provenance.planner_guardrails_applied)
      ? provenance.planner_guardrails_applied.map(summarizeValue).filter(Boolean).join(" -> ")
      : "";
  const memoryStatus = summarizeValue(sourceTrace.memory_status ?? provenance.memory_status ?? asRecord(data.memory_status).status ?? data.memory_status);
  const showDiagnostic = shouldSurfaceDiagnostic(data);
  const parts = [
    data.status ? `status=${summarizeValue(data.status)}` : "",
    route ? `route=${route}` : "",
    sourceTrace.source_kind ? `source_kind=${summarizeValue(sourceTrace.source_kind)}` : "",
    sourceTrace.model_only !== undefined ? `model_only=${summarizeValue(sourceTrace.model_only)}` : "",
    !isSlashAgent && data.provider ? `provider=${summarizeValue(data.provider)}` : "",
    !isSlashAgent && data.model ? `model=${summarizeValue(data.model)}` : "",
    sourceTrace.planner_source ? `planner_source=${summarizeValue(sourceTrace.planner_source)}` : "",
    sourceTrace.selected_model_interprets_answer !== undefined ? `selected_model_interprets_answer=${summarizeValue(sourceTrace.selected_model_interprets_answer)}` : "",
    sourceTrace.brave_search_used !== undefined || provenance.brave_search_used !== undefined ? `brave_search_used=${summarizeValue(sourceTrace.brave_search_used ?? provenance.brave_search_used)}` : "",
    sourceTrace.pocket_processed !== undefined || provenance.pocket_processed_steps !== undefined ? `pocket_processed=${summarizeValue(sourceTrace.pocket_processed ?? provenance.pocket_processed_steps)}/${summarizeValue(sourceTrace.pocket_step_count ?? provenance.step_count) || "0"}` : "",
    toolsUsed ? `tools_executed=${toolsUsed}` : "",
    toolsBlocked ? `tools_blocked=${toolsBlocked}` : "",
    plannerGuardrails ? `planner_guardrails_applied=${plannerGuardrails}` : "",
    memoryStatus && memoryStatus !== "not_applicable" ? `memory_status=${memoryStatus}` : "",
    data.next_action ? `next=${summarizeValue(data.next_action)}` : "",
    data.response ? summarizeValue(data.response) : "",
    data.message ? summarizeValue(data.message) : "",
    data.reason ? summarizeValue(data.reason) : "",
    showDiagnostic && data.stderr ? `stderr: ${summarizeValue(data.stderr)}` : "",
    showDiagnostic && data.stdout ? `stdout: ${summarizeValue(data.stdout)}` : "",
    data.error ? `error: ${summarizeValue(data.error)}` : "",
    pocketVoice.response ? `pocket_voice: ${summarizeValue(pocketVoice.response)}` : "",
    dominant ? `dominant_dimensions: ${dominant}` : "",
    data.local_model_translation_used !== undefined ? `local_model_translation_used=${summarizeValue(data.local_model_translation_used)}` : "",
    cirqRuntime.available !== undefined ? `cirq_available=${summarizeValue(cirqRuntime.available)}` : "",
    livingEcho?.current_thought ? `thought: ${summarizeValue(livingEcho.current_thought)}` : "",
    livingEcho?.last_whisper ? `whisper: ${summarizeValue(livingEcho.last_whisper)}` : "",
  ].filter(Boolean);
  return parts.join("\n").slice(0, 4000);
}

function renderResponse(raw: unknown, openResult: ExternalOpenResult | null = null): string {
  const summary = summarizeResult(raw);
  const response = summary || JSON.stringify(raw, null, 2);
  if (!openResult) return response;
  const openLine = openResult.opened
    ? `frontend_open=opened via=${openResult.via}`
    : `frontend_open=blocked via=${openResult.via}: ${openResult.detail}`;
  return `${openLine}\n${response}`.slice(0, 4000);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function AgenticTraceReadout({ data }: { data: Record<string, unknown> | null }) {
  if (!data) return null;
  const route = summarizeValue(data.route) || "model";
  const isAgentic = route === "agentic_processor";
  const sourceTrace = asRecord(data.source_trace);
  const provenance = asRecord(data.provenance);
  const steps = Array.isArray(data.steps) ? data.steps.map(asRecord) : [];
  const braveUsed = Boolean(sourceTrace.brave_search_used ?? provenance.brave_search_used);
  const braveSuccess = Boolean(sourceTrace.brave_search_success ?? provenance.brave_search_success);
  const agenticEcosystemUsed = Boolean(sourceTrace.agentic_ecosystem_used ?? provenance.agentic_ecosystem_used);
  const agenticEcosystemSources = Array.isArray(sourceTrace.agentic_ecosystem_sources)
    ? sourceTrace.agentic_ecosystem_sources.map(summarizeValue).filter(Boolean)
    : Array.isArray(provenance.agentic_ecosystem_sources)
      ? provenance.agentic_ecosystem_sources.map(summarizeValue).filter(Boolean)
      : [];
  const pocketCount = summarizeValue(sourceTrace.pocket_processed ?? provenance.pocket_processed_steps) || "0";
  const stepCount = summarizeValue(sourceTrace.pocket_step_count ?? provenance.step_count) || String(steps.length);
  const memoryStatus = summarizeValue(sourceTrace.memory_status ?? provenance.memory_status ?? asRecord(data.memory_status).status ?? data.memory_status) || "--";
  const tools = Array.isArray(sourceTrace.tools_executed)
    ? sourceTrace.tools_executed.map(summarizeValue).filter(Boolean)
    : Array.isArray(provenance.tools_used)
      ? provenance.tools_used.map(summarizeValue).filter(Boolean)
      : steps.map((step) => summarizeValue(step.tool)).filter(Boolean);
  const blockedTools = Array.isArray(sourceTrace.tools_blocked)
    ? sourceTrace.tools_blocked.map(summarizeValue).filter(Boolean)
    : [];
  const guardrailsApplied = Array.isArray(sourceTrace.planner_guardrails_applied)
    ? sourceTrace.planner_guardrails_applied.map(summarizeValue).filter(Boolean)
    : Array.isArray(provenance.planner_guardrails_applied)
      ? provenance.planner_guardrails_applied.map(summarizeValue).filter(Boolean)
      : [];
  const sourceValue = summarizeValue(sourceTrace.source_kind) || (isAgentic ? "agentic" : "model-only");
  const braveValue = braveUsed ? (braveSuccess ? "used" : "attempted") : "not used";
  const agenticEcosystemValue = agenticEcosystemUsed ? (agenticEcosystemSources.join("+") || "used") : "standby";
  const modelValue = Boolean(sourceTrace.selected_model_interprets_answer) ? "interprets" : "not used";
  const actionValue = summarizeValue(sourceTrace.action_status) || (blockedTools.length ? "blocked" : (tools.length ? "executed" : "none"));
  const guardrailValue = guardrailsApplied.length ? String(guardrailsApplied.length) : "none";
  return (
    <div className="agentic-trace-readout">
      <div className="status-grid pocket-badges">
        <StatusPill icon={<Layers size={15} />} label="Bronpad" value={sourceValue} ok={sourceValue !== "unknown"} />
        <StatusPill icon={<Globe2 size={15} />} label="Brave Search" value={braveValue} ok={braveUsed && braveSuccess} />
        <StatusPill icon={<FolderTree size={15} />} label="DeepSeek/Atlas" value={agenticEcosystemValue} ok={agenticEcosystemUsed} />
        <StatusPill icon={<BrainCircuit size={15} />} label="11D pocket" value={`${pocketCount}/${stepCount}`} ok={Number(pocketCount) > 0} />
        <StatusPill icon={<Bot size={15} />} label="Model" value={modelValue} ok={Boolean(sourceTrace.selected_model_interprets_answer)} />
        <StatusPill icon={<ShieldCheck size={15} />} label="Guardrails" value={guardrailValue} ok={guardrailsApplied.length > 0} />
        <StatusPill icon={<Hammer size={15} />} label="Actie" value={actionValue} ok={actionValue === "executed"} />
        <StatusPill icon={<Database size={15} />} label="Memory" value={memoryStatus} ok={["stored", "success"].includes(memoryStatus)} />
      </div>
      {tools.length > 0 && (
        <div className="dimension-chip-list agentic-tool-chips">
          {tools.slice(0, 8).map((item, index) => <span key={`${item}-${index}`}>{item}</span>)}
        </div>
      )}
      {guardrailsApplied.length > 0 && (
        <div className="dimension-chip-list agentic-guardrail-chips">
          {guardrailsApplied.slice(0, 8).map((item, index) => <span key={`${item}-${index}`}>{item}</span>)}
        </div>
      )}
      {agenticEcosystemSources.length > 0 && (
        <div className="dimension-chip-list agentic-ecosystem-chips">
          {agenticEcosystemSources.slice(0, 4).map((item, index) => <span key={`${item}-${index}`}>{item}</span>)}
        </div>
      )}
      {blockedTools.length > 0 && (
        <div className="dimension-chip-list agentic-blocked-chips">
          {blockedTools.slice(0, 8).map((item, index) => <span key={`${item}-${index}`}>{item}</span>)}
        </div>
      )}
      {steps.length > 0 && (
        <div className="agentic-step-list">
          {steps.slice(0, 8).map((step, index) => (
            <div className="agentic-step-row" key={`${summarizeValue(step.tool) || "step"}-${index}`}>
              <span>{summarizeValue(step.index) || String(index + 1)}</span>
              <strong>{summarizeValue(step.tool) || "tool"}</strong>
              <em>{summarizeValue(step.status) || "unknown"}</em>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PocketVoiceReadout({ data }: { data: Record<string, unknown> | null }) {
  if (!data || data.route !== "ouroboros_runtime") return null;
  const voice = asRecord(data.pocket_voice);
  const quantum = asRecord(data.quantum_collapse);
  const cirqRuntime = asRecord(quantum.cirq_runtime ?? voice.cirq_runtime);
  const topology = asRecord(voice.pocket_topology);
  const networkFlow = asRecord(voice.network_flow);
  const dominant = Array.isArray(voice.dominant_dimensions) ? voice.dominant_dimensions.map(summarizeValue).filter(Boolean) : [];
  const translated = Boolean(data.local_model_translation_used) || summarizeValue(voice.status) === "translated";
  const cirqAvailable = Boolean(cirqRuntime.available) || summarizeValue(quantum.sdk ?? voice.quantum_runtime) === "cirq" || summarizeValue(quantum.runtime ?? voice.quantum_runtime) === "cirq_density_matrix_local";
  const fallbackActive = !cirqAvailable && Boolean(quantum.runtime || voice.quantum_runtime);
  return (
    <div className="pocket-voice-readout">
      <div className="status-grid pocket-badges">
        <StatusPill icon={<BrainCircuit size={15} />} label="Ouroboros voice" value={summarizeValue(voice.status) || "unknown"} ok={translated} />
        <StatusPill icon={<Activity size={15} />} label="Cirq local measurement" value={cirqAvailable ? "available" : "offline"} ok={cirqAvailable} />
        <StatusPill icon={<Cpu size={15} />} label="NumPy fallback" value={fallbackActive ? "active" : "standby"} ok={fallbackActive} />
      </div>
      {voice.response ? <p className="pocket-response">{summarizeValue(voice.response)}</p> : null}
      <div className="fact-list pocket-facts">
        <Fact label="Local model" value={String(Boolean(data.local_model_translation_used))} state={summarizeValue(voice.model)} />
        <Fact label="Cirq available" value={String(cirqAvailable)} state={summarizeValue(cirqRuntime.runtime ?? quantum.runtime ?? voice.quantum_runtime)} />
        <Fact label="Pocket route" value={summarizeValue(networkFlow.observed_route) || "--"} state={summarizeValue(networkFlow.dhcp_state)} />
        <Fact label="Pocket depth" value={`hubs ${summarizeValue(topology.hub_count) || 0}`} state={`micro ${summarizeValue(topology.micro_observation_count) || 0}`} />
      </div>
      {dominant.length > 0 && (
        <div className="dimension-chip-list">
          {dominant.slice(0, 5).map((item) => <span key={item}>{item}</span>)}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "good" | "warn" | "neutral" }) {
  return (
    <div className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusPill({ icon, label, value, ok }: { icon: React.ReactNode; label: string; value: string; ok: boolean }) {
  return (
    <div className={`status-pill ${ok ? "good" : "warn"}`}>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function capabilityStatusOk(status?: string) {
  return ["available", "configured", "detected", "pattern_catalog"].includes(String(status || ""));
}

function capabilityStatusLabel(status?: string) {
  return status === "pattern_catalog" ? "catalog" : status ?? "unknown";
}

function PanelHeader({ title, small = false }: { title: string; small?: boolean }) {
  return <h2 className={small ? "small-heading" : ""}>{title}</h2>;
}

function ConnectorCockpitPanel({
  catalog,
  selectedConnectorId,
  onSelectConnector,
  approvalReady,
  busy,
  onRefresh,
  onToggleConnector,
}: {
  catalog: ConnectorCatalogStatus;
  selectedConnectorId: string;
  onSelectConnector: (id: string) => void;
  approvalReady: boolean;
  busy: boolean;
  onRefresh: () => void;
  onToggleConnector: (id: string, enabled: boolean) => void;
}) {
  const connectors = catalog.connectors ?? [];
  const selected = selectedConnectorId || connectors[0]?.id || "";
  return (
    <div className="connector-panel">
      <div className="nexus-stats">
        <span>Status <strong>{catalog.status ?? "unknown"}</strong></span>
        <span>On <strong>{catalog.enabled_count ?? connectors.filter((item) => item.enabled).length}</strong></span>
        <span>Off <strong>{catalog.disabled_count ?? connectors.filter((item) => !item.enabled).length}</strong></span>
        <span>Ready <strong>{catalog.configured_count ?? connectors.filter((item) => item.configured).length}</strong></span>
        <span>Tools off <strong>{catalog.disabled_tools?.length ?? 0}</strong></span>
        <span>Fake <strong>{String(catalog.fake_success ?? false)}</strong></span>
      </div>

      <div className="connector-toolbar">
        <button onClick={onRefresh} disabled={busy} type="button">
          <RefreshCw size={15} /> Refresh
        </button>
        <span>{catalog.approval_phrase ?? "Akkoord"}</span>
      </div>

      <div className="connector-card-list">
        {connectors.map((connector) => {
          const enabled = Boolean(connector.enabled);
          const isSelected = selected === connector.id;
          const ready = connector.readiness === "ready" || connector.configured || connector.available;
          return (
            <div className={`connector-card ${enabled ? "on" : "off"} ${isSelected ? "selected" : ""}`} key={connector.id ?? connector.name}>
              <button className="connector-card-body" onClick={() => onSelectConnector(connector.id ?? "")} type="button">
                <div className="connector-card-head">
                  <i className={enabled && ready ? "good" : ""} />
                  <div>
                    <strong>{connector.name ?? connector.id}</strong>
                    <span>{connector.provider ?? connector.category ?? "connector"}</span>
                  </div>
                  <em>{enabled ? "on" : "off"}</em>
                </div>
                <p>{connector.description ?? connector.status ?? ""}</p>
                <div className="dimension-chip-list connector-chips">
                  <span>{connector.readiness ?? "unknown"}</span>
                  <span>{connector.status ?? "status"}</span>
                  <span>{connector.tools?.length ?? 0} tools</span>
                </div>
              </button>
              <div className="connector-card-actions">
                <button
                  onClick={() => onToggleConnector(connector.id ?? "", !enabled)}
                  disabled={busy || !approvalReady || !connector.id}
                  type="button"
                >
                  {enabled ? <CircleStop size={15} /> : <CheckCircle2 size={15} />}
                  {enabled ? "Off" : "On"}
                </button>
              </div>
            </div>
          );
        })}
        {!connectors.length && <div className="empty-state">{catalog.reason ?? "Connectorcatalogus nog niet geladen."}</div>}
      </div>
    </div>
  );
}

function ConnectorToolsPanel({
  connector,
  approvalReady,
  busy,
  onToggleTool,
}: {
  connector?: ConnectorItem;
  approvalReady: boolean;
  busy: boolean;
  onToggleTool: (toolName: string, enabled: boolean) => void;
}) {
  if (!connector) {
    return <div className="empty-state">Geen connector geselecteerd.</div>;
  }
  const tools = connector.tools ?? [];
  return (
    <div className="connector-panel">
      <div className="connector-selected-head">
        <div>
          <strong>{connector.name ?? connector.id}</strong>
          <span>{connector.category ?? connector.provider ?? "connector"}</span>
        </div>
        <em className={connector.enabled ? "good" : "warn"}>{connector.enabled ? "on" : "off"}</em>
      </div>
      <div className="connector-tool-list">
        {tools.map((tool) => {
          const enabled = Boolean(tool.enabled);
          const name = tool.name ?? "";
          const statusTool = Boolean(tool.status_tool);
          return (
            <div className={`connector-tool-row ${enabled ? "on" : "off"}`} key={name}>
              <span>{tool.kind ?? "tool"}</span>
              <strong>{name}</strong>
              <em>{statusTool ? "always on" : tool.requires_approval ? "Akkoord" : "read"}</em>
              <button
                onClick={() => onToggleTool(name, !enabled)}
                disabled={busy || !approvalReady || statusTool || !name}
                title={statusTool ? "Status tools blijven altijd leesbaar." : undefined}
                type="button"
              >
                {statusTool ? <ShieldCheck size={14} /> : enabled ? <CircleStop size={14} /> : <CheckCircle2 size={14} />}
                {statusTool ? "Always" : enabled ? "Off" : "On"}
              </button>
            </div>
          );
        })}
        {!tools.length && <div className="empty-state">Geen tools voor deze connector.</div>}
      </div>
    </div>
  );
}

function ConnectorStatusPanel({
  connector,
  catalog,
  googleOAuth,
  googleOAuthStartResult,
  googleOAuthClientId,
  googleOAuthClientSecret,
  googleOAuthClientJson,
  googleOAuthRedirectUri,
  googleOAuthCode,
  approvalReady,
  busy,
  onGoogleOAuthClientIdChange,
  onGoogleOAuthClientSecretChange,
  onGoogleOAuthClientJsonChange,
  onGoogleOAuthRedirectUriChange,
  onGoogleOAuthCodeChange,
  onStartGoogleOAuth,
  onExchangeGoogleOAuthCode,
  onUsePrompt,
}: {
  connector?: ConnectorItem;
  catalog: ConnectorCatalogStatus;
  googleOAuth: GoogleOAuthStatus;
  googleOAuthStartResult: GoogleOAuthStartResult | null;
  googleOAuthClientId: string;
  googleOAuthClientSecret: string;
  googleOAuthClientJson: string;
  googleOAuthRedirectUri: string;
  googleOAuthCode: string;
  approvalReady: boolean;
  busy: boolean;
  onGoogleOAuthClientIdChange: (value: string) => void;
  onGoogleOAuthClientSecretChange: (value: string) => void;
  onGoogleOAuthClientJsonChange: (value: string) => void;
  onGoogleOAuthRedirectUriChange: (value: string) => void;
  onGoogleOAuthCodeChange: (value: string) => void;
  onStartGoogleOAuth: () => void;
  onExchangeGoogleOAuthCode: () => void;
  onUsePrompt: (prompt: string) => void;
}) {
  if (!connector) {
    return <div className="empty-state">{catalog.reason ?? "Geen connectorstatus beschikbaar."}</div>;
  }
  const routes = connector.routes ?? [];
  const setup = connector.setup ?? {};
  const packages = catalog.agent_work_packages ?? [];
  return (
    <div className="connector-panel">
      <div className="fact-list">
        <Fact label="Connector" value={connector.name ?? connector.id ?? "--"} state={connector.readiness ?? connector.status} />
        <Fact label="Provider" value={connector.provider ?? "--"} state={connector.category ?? ""} />
        <Fact label="Configured" value={String(Boolean(connector.configured))} state={connector.status ?? "unknown"} />
        <Fact label="Updated" value={connector.settings?.updated_at || "--"} state={connector.settings?.updated_by || "catalog"} />
        <Fact label="Credential" value={summarizeValue(setup.credential) || "--"} state={summarizeValue(setup.env) || ""} />
      </div>
      {["gmail", "google_drive"].includes(connector.id ?? "") && (
        <GoogleOAuthSetupPanel
          status={googleOAuth}
          startResult={googleOAuthStartResult}
          clientId={googleOAuthClientId}
          clientSecret={googleOAuthClientSecret}
          clientJson={googleOAuthClientJson}
          redirectUri={googleOAuthRedirectUri}
          code={googleOAuthCode}
          approvalReady={approvalReady}
          busy={busy}
          onClientIdChange={onGoogleOAuthClientIdChange}
          onClientSecretChange={onGoogleOAuthClientSecretChange}
          onClientJsonChange={onGoogleOAuthClientJsonChange}
          onRedirectUriChange={onGoogleOAuthRedirectUriChange}
          onCodeChange={onGoogleOAuthCodeChange}
          onStart={onStartGoogleOAuth}
          onExchange={onExchangeGoogleOAuthCode}
        />
      )}
      {routes.length > 0 && (
        <>
          <PanelHeader title="Routes" small />
          <div className="fact-list">
            {routes.map((route, index) => (
              <Fact key={`${route.path}-${index}`} label={route.tool_name ?? route.method ?? "route"} value={route.path ?? "--"} state={route.method ?? ""} />
            ))}
          </div>
        </>
      )}
      <PanelHeader title="Status Detail" small />
      <pre className="connector-status-json">{JSON.stringify(connector.status_detail ?? {}, null, 2)}</pre>
      <PanelHeader title="Agent Instructions" small />
      <div className="connector-work-list">
        {packages.map((item) => (
          <div className="connector-work-card" key={item.id ?? item.agent}>
            <div>
              <strong>{item.agent ?? "Agent"} · {item.title ?? item.target ?? "Werkpakket"}</strong>
              <span>{item.role ?? item.target ?? ""} · {item.command_hint ?? ""}</span>
            </div>
            <p>{item.prompt ?? ""}</p>
            <div className="dimension-chip-list connector-chips">
              {(item.acceptance ?? []).slice(0, 3).map((criterion, index) => <span key={`${item.id}-accept-${index}`}>{criterion}</span>)}
            </div>
            <button onClick={() => onUsePrompt(`${item.command_hint ?? ""} ${item.prompt ?? ""}`.trim())} type="button">
              <MessageSquare size={14} /> Naar chat
            </button>
          </div>
        ))}
        {!packages.length && <div className="empty-state">Nog geen agent-opdrachten geladen.</div>}
      </div>
    </div>
  );
}

function GoogleOAuthSetupPanel({
  status,
  startResult,
  clientId,
  clientSecret,
  clientJson,
  redirectUri,
  code,
  approvalReady,
  busy,
  onClientIdChange,
  onClientSecretChange,
  onClientJsonChange,
  onRedirectUriChange,
  onCodeChange,
  onStart,
  onExchange,
}: {
  status: GoogleOAuthStatus;
  startResult: GoogleOAuthStartResult | null;
  clientId: string;
  clientSecret: string;
  clientJson: string;
  redirectUri: string;
  code: string;
  approvalReady: boolean;
  busy: boolean;
  onClientIdChange: (value: string) => void;
  onClientSecretChange: (value: string) => void;
  onClientJsonChange: (value: string) => void;
  onRedirectUriChange: (value: string) => void;
  onCodeChange: (value: string) => void;
  onStart: () => void;
  onExchange: () => void;
}) {
  const tokenExists = Boolean(status.token?.exists);
  const hasRefresh = Boolean(status.token?.has_refresh_token);
  const clientConfigured = Boolean(status.client?.configured);
  const pendingCode = Boolean(status.pending_code?.available);
  const hasManualCredentials = Boolean(clientId.trim() && clientSecret.trim());
  const hasClientJson = Boolean(clientJson.trim());
  const hasTypedCode = Boolean(code.trim());
  const missingScopes = status.missing_scopes ?? [];
  const warnings = startResult?.warnings ?? [];
  const validationReason = status.client?.validation_reason || "";
  const exchangeReason = status.last_exchange?.reason || "";
  const authUrl = startResult?.authorization_url ?? "";
  return (
    <div className="google-oauth-panel">
      <PanelHeader title="Google OAuth" small />
      <div className="fact-list">
        <Fact label="Client" value={clientConfigured ? "configured" : "missing"} state={status.client?.updated_at || ""} />
        <Fact label="Project" value={status.client?.project_id_configured ? "configured" : "missing"} state={status.client?.client_type || startResult?.client_type || "oauth"} />
        <Fact label="Token" value={tokenExists ? "saved" : "missing"} state={hasRefresh ? "refresh token" : "no refresh"} />
        <Fact label="Callback" value={pendingCode ? "received" : "waiting"} state={status.pending_code?.expires_at || ""} />
        <Fact label="Exchange" value={status.last_exchange?.status ?? "never"} state={status.last_exchange?.updated_at || ""} />
        <Fact label="Gmail send" value={status.can_send_gmail ? "ready" : "blocked"} state={status.status ?? "unknown"} />
        <Fact label="Scopes missing" value={`${missingScopes.length}`} state={status.setup_ready ? "complete" : "incomplete"} />
      </div>
      <div className="oauth-form-grid">
        <label>
          <span>Client ID</span>
          <input value={clientId} onChange={(event) => onClientIdChange(event.target.value)} placeholder={status.client?.client_id_configured ? "configured" : "Google OAuth client ID"} />
        </label>
        <label>
          <span>Client Secret</span>
          <input type="password" value={clientSecret} onChange={(event) => onClientSecretChange(event.target.value)} placeholder={status.client?.client_secret_configured ? "configured" : "Google OAuth client secret"} />
        </label>
        <label className="oauth-wide-field">
          <span>Redirect URI</span>
          <input value={redirectUri || status.redirect_uri || ""} onChange={(event) => onRedirectUriChange(event.target.value)} placeholder={status.redirect_uri || "http://127.0.0.1:8010/api/cockpit/connectors/google/oauth/callback"} />
        </label>
        <label className="oauth-wide-field">
          <span>Client JSON</span>
          <textarea value={clientJson} onChange={(event) => onClientJsonChange(event.target.value)} placeholder="Paste downloaded OAuth client JSON" rows={4} />
        </label>
      </div>
      <div className="connector-toolbar">
        <button onClick={onStart} disabled={busy || !approvalReady || (!clientConfigured && !hasManualCredentials && !hasClientJson)} type="button">
          <KeyRound size={15} /> Auth URL
        </button>
        {authUrl && (
          <a className="button-link" href={authUrl} target="_blank" rel="noreferrer">
            <Globe2 size={15} /> Open Google
          </a>
        )}
      </div>
      <div className="oauth-form-grid">
        <label className="oauth-wide-field">
          <span>Authorization Code</span>
          <input value={code} onChange={(event) => onCodeChange(event.target.value)} placeholder="code or callback URL" />
        </label>
      </div>
      <div className="connector-toolbar">
        <button onClick={onExchange} disabled={busy || !approvalReady || (!hasTypedCode && !pendingCode)} type="button">
          <CheckCircle2 size={15} /> {hasTypedCode ? "Save Token" : "Save Callback Code"}
        </button>
        <span>{status.secrets_returned ? "secrets returned" : "secrets hidden"}</span>
      </div>
      {missingScopes.length > 0 && (
        <div className="dimension-chip-list connector-chips">
          {missingScopes.slice(0, 5).map((scope) => <span key={scope}>{scope.replace("https://www.googleapis.com/auth/", "")}</span>)}
        </div>
      )}
      {warnings.length > 0 && (
        <div className="dimension-chip-list agentic-guardrail-chips">
          {warnings.slice(0, 3).map((warning, index) => <span key={`google-oauth-warning-${index}`}>{warning}</span>)}
        </div>
      )}
      {validationReason && (
        <div className="dimension-chip-list agentic-blocked-chips">
          <span>{validationReason}</span>
        </div>
      )}
      {exchangeReason && status.last_exchange?.status !== "token_saved" && (
        <div className="dimension-chip-list agentic-blocked-chips">
          <span>{exchangeReason}</span>
        </div>
      )}
    </div>
  );
}

function AgentArchitecturePanel({
  architecture,
  review,
  busy,
  onReview,
}: {
  architecture: AgentArchitectureStatus;
  review: AgentArchitectureReview | null;
  busy: boolean;
  onReview: () => void;
}) {
  const agents = architecture.agents ?? [];
  const policy = architecture.approval_policy ?? {};
  const interfaces = Object.entries(architecture.public_interfaces ?? {});
  const blockedGaps = architecture.blocked_gaps ?? [];
  const readyCount = agents.filter((agent) => agent.readiness === "klaar").length;
  return (
    <div className="world-panel architecture-panel">
      <div className="nexus-stats">
        <span>Status <strong>{architecture.status ?? "unknown"}</strong></span>
        <span>Agents <strong>{agents.length || architecture.agent_count || 0}</strong></span>
        <span>Klaar <strong>{readyCount}</strong></span>
        <span>Policy <strong>{policy.self_copy_install_v1 ?? "dry-run"}</strong></span>
        <span>Tools <strong>{architecture.observed_runtime?.tool_names?.length ?? 0}</strong></span>
        <span>Fake <strong>{String(architecture.fake_success ?? false)}</strong></span>
      </div>

      <div className="world-action-list">
        {agents.map((agent) => (
          <div className="world-action" key={agent.id ?? agent.name}>
            <div>
              <strong>{agent.name ?? agent.id}</strong>
              <span>{agent.readiness ?? "unknown"}</span>
            </div>
            <p>{agent.role ?? ""}: {agent.mission ?? ""}</p>
            <div className="dimension-chip-list agentic-tool-chips">
              {(agent.allowed_tools ?? []).slice(0, 8).map((tool) => <span key={`${agent.id}-${tool}`}>{tool}</span>)}
            </div>
            {(agent.approval_required_for ?? []).length > 0 && (
              <div className="dimension-chip-list agentic-guardrail-chips">
                {(agent.approval_required_for ?? []).slice(0, 6).map((tool) => <span key={`${agent.id}-gate-${tool}`}>{tool}: {policy.approval_phrase ?? "Akkoord"}</span>)}
              </div>
            )}
          </div>
        ))}
        {!agents.length && <div className="empty-state">{architecture.reason ?? "Agent-architectuur nog niet geladen."}</div>}
      </div>

      <PanelHeader title="Criticus Preview" small />
      <div className="nexus-last">
        <button onClick={onReview} disabled={busy}>
          <ShieldCheck size={15} /> Review huidige prompt
        </button>
        {review && (
          <div className="world-action">
            <div>
              <strong>{review.status ?? "unknown"} · {review.decision ?? "preview"}</strong>
              <span>{review.risk_level ?? "risk"}</span>
            </div>
            <p>
              Execute allowed: {String(review.execute_allowed ?? false)} · uitgevoerd: {String(review.execution_performed ?? false)} · approval: {review.approval_status ?? "unknown"}
            </p>
            <div className="dimension-chip-list agentic-blocked-chips">
              {(review.critic?.blocked_reasons ?? []).map((reason, index) => <span key={`blocked-${index}`}>{reason}</span>)}
            </div>
            <div className="dimension-chip-list agentic-ecosystem-chips">
              {(review.risk_categories ?? []).map((category) => <span key={category}>{category}</span>)}
            </div>
          </div>
        )}
      </div>

      <PanelHeader title="Interfaces" small />
      <div className="fact-list">
        {interfaces.slice(0, 8).map(([key, item]) => (
          <Fact key={key} label={key} value={`${item.method ?? "GET"} ${item.path ?? ""}`} state={item.prefix ? `prefix ${item.prefix}` : "route"} />
        ))}
      </div>
      {blockedGaps.length > 0 && (
        <>
          <PanelHeader title="Open Gaps" small />
          <div className="dimension-chip-list agentic-guardrail-chips">
            {blockedGaps.slice(0, 8).map((gap, index) => <span key={`gap-${index}`}>{gap}</span>)}
          </div>
        </>
      )}
    </div>
  );
}

function AgentCapabilitiesPanel({
  external,
  runtimeTools,
  rooStatus,
  codexJobs,
  agentsStatus,
  openhandsStatus,
}: {
  external: ExternalCapabilitiesStatus;
  runtimeTools: RuntimeToolsStatus;
  rooStatus?: OuroborosStatus["roo_adapter"];
  codexJobs: AgentJob[];
  agentsStatus: AgentsSubsystemStatus;
  openhandsStatus: OpenHandsSubsystemStatus;
}) {
  const agents = external.capabilities?.agents;
  const openhands = external.capabilities?.openhands;
  const deepseek = external.capabilities?.deepseek;
  const atlas = external.capabilities?.atlas;
  const toolNames = runtimeTools.tools ?? [];
  const schemaNames = (external.tool_schemas ?? []).map((schema) => schema.function?.name).filter(Boolean);
  const agenticPatterns = [
    ...(deepseek?.agentic_patterns ?? []).map((item) => ({ ...item, system: "DeepSeek" })),
    ...(atlas?.agentic_patterns ?? []).map((item) => ({ ...item, system: "Atlas" })),
  ];
  const roleTaxonomy = [
    ...(deepseek?.role_taxonomy ?? []).map((item) => ({ ...item, system: "DeepSeek" })),
    ...(atlas?.role_taxonomy ?? []).map((item) => ({ ...item, system: "Atlas" })),
  ];
  const ecosystemEntryPoints = [
    ...(agents?.entrypoints ?? []),
    ...(openhands?.entrypoints ?? []),
    ...(deepseek?.entrypoints ?? []),
    ...(atlas?.entrypoints ?? []),
  ];
  return (
    <div className="world-panel">
      <div className="nexus-stats">
        <span>AgentS <strong>{agentsStatus.status ?? agents?.status ?? "unknown"}</strong></span>
        <span>OpenHands <strong>{openhandsStatus.status ?? openhands?.status ?? "unknown"}</strong></span>
        <span>DeepSeek <strong>{deepseek?.status ?? "unknown"}</strong></span>
        <span>Atlas <strong>{atlas?.status ?? "unknown"}</strong></span>
        <span>Roo <strong>{rooStatus?.status ?? "unknown"}</strong></span>
        <span>Codex jobs <strong>{codexJobs.length}</strong></span>
      </div>
      <div className="fact-list">
        <Fact
          label="AgentS root"
          value={agentsStatus.root ?? agents?.root ?? "/home/pwintri2/AgentS"}
          state={agentsStatus.runtime_reachable ? `runtime ${agentsStatus.launch_test ?? "ok"}` : agentsStatus.status ?? (agents?.exists ? "detected" : agents?.status)}
        />
        <Fact
          label="OpenHands root"
          value={openhandsStatus.root ?? openhands?.root ?? "/home/pwintri2/OpenHands"}
          state={openhandsStatus.server_reachable ? "server reachable" : openhandsStatus.status ?? (openhands?.exists ? "detected" : openhands?.status)}
        />
        <Fact label="Roo tools" value={`${rooStatus?.local_python_adapters?.length ?? 0}`} state={rooStatus?.available ? "available" : rooStatus?.status} />
        <Fact label="Runtime tools" value={toolNames.length ? toolNames.join(", ") : "--"} state={runtimeTools.status} />
        <Fact label="Fase 8 tools" value={schemaNames.length ? schemaNames.join(", ") : "--"} state={external.via_bridge ? "via bridge" : external.status} />
        <Fact label="DeepSeek root" value={deepseek?.root ?? "/home/pwintri2/deepseek"} state={deepseek?.status ?? (deepseek?.exists ? "detected" : "missing")} />
        <Fact label="Atlas root" value={atlas?.root ?? "/home/pwintri2/atlas"} state={atlas?.status ?? (atlas?.exists ? "detected" : "missing")} />
      </div>
      <PanelHeader title="DeepSeek / Atlas Patterns" small />
      <div className="world-action-list agent-pattern-list">
        {agenticPatterns.slice(0, 8).map((pattern, index) => (
          <div className="world-action" key={`${pattern.system}-${pattern.id ?? pattern.label ?? index}`}>
            <div>
              <strong>{pattern.label ?? pattern.id ?? "Agentic pattern"}</strong>
              <span>{pattern.system}</span>
            </div>
            <p>{pattern.value ?? pattern.source ?? ""}</p>
          </div>
        ))}
        {!agenticPatterns.length && (
          <div className="empty-state">Nog geen DeepSeek/Atlas agentische patronen zichtbaar.</div>
        )}
      </div>
      <div className="dimension-chip-list agentic-ecosystem-chips">
        {roleTaxonomy.slice(0, 12).map((role, index) => <span key={`${role.system}-${role.id ?? role.label ?? index}`}>{role.system}: {role.label ?? role.id}</span>)}
      </div>
      <PanelHeader title="Entry Points" small />
      <div className="world-action-list">
        {ecosystemEntryPoints.slice(0, 12).map((entry) => (
          <div className="world-action" key={`${entry.kind ?? "entry"}-${entry.path ?? entry.label}`}>
            <div>
              <strong>{entry.label ?? entry.path}</strong>
              <span>{entry.kind ?? "entry"}</span>
            </div>
            <p>{entry.path ?? ""}</p>
          </div>
        ))}
        {!ecosystemEntryPoints.length && (
          <div className="empty-state">{external.reason ?? "Nog geen AgentS/OpenHands/DeepSeek/Atlas capability data geladen."}</div>
        )}
      </div>
      <div className="nexus-last">
        <strong>Slash agents</strong>
        <span>Gebruik `/codex ...`, `/deepseek ...`, `/atlas ...` of `/roo ...` in de chat; DeepSeek/Atlas status, doctor en jobs zijn nu direct routeerbaar.</span>
      </div>
    </div>
  );
}

function CodexPanel({
  codexStatus,
  codexCapabilities,
  codexJobs,
  runPrompt,
  setRunPrompt,
  approvalReady,
  busy,
  onRun,
}: {
  codexStatus: CodexStatus;
  codexCapabilities: CodexCapabilityInventory;
  codexJobs: AgentJob[];
  runPrompt: string;
  setRunPrompt: (value: string) => void;
  approvalReady: boolean;
  busy: boolean;
  onRun: () => void;
}) {
  const binary = codexStatus.binary ?? {};
  const auth = codexStatus.auth ?? {};
  const version = codexStatus.version ?? {};
  const subsystems = codexCapabilities.subsystems ?? [];
  const detectedCount = subsystems.filter((item) => item.detected).length;
  const overall = codexStatus.status ?? "unknown";
  const overallTone = overall === "online" || overall === "authenticated" ? "good" : overall === "missing" ? "warn" : "warn";
  const recentJobs = codexJobs.slice(0, 5);
  return (
    <div className="world-panel">
      <div className="world-head">
        <div>
          <strong>Codex {version.version ? `v${version.version}` : ""}</strong>
          <span>{codexStatus.repo_path ?? "/home/pwintri2/Codex"}</span>
        </div>
        <i className={overallTone === "good" ? "good" : "warn"} />
      </div>
      <div className="nexus-stats">
        <span>State <strong>{overall}</strong></span>
        <span>Binary <strong>{binary.status ?? "unknown"}</strong></span>
        <span>Auth <strong>{auth.status ?? "unknown"}</strong></span>
        <span>Caps <strong>{detectedCount}/{subsystems.length}</strong></span>
      </div>
      <div className="fact-list">
        <Fact label="Repo" value={codexStatus.repo_path ?? "--"} state={codexStatus.repo_present ? "present" : "missing"} />
        <Fact label="Binary path" value={binary.path ?? "--"} state={binary.status} />
        <Fact label="Version" value={version.version ?? "--"} state={version.status} />
        <Fact label="Auth mode" value={auth.auth_mode ?? "--"} state={auth.status} />
        <Fact label="Codex home" value={auth.home ?? "--"} state={auth.config_present ? "configured" : "missing"} />
        <Fact label="Sessions" value={`${auth.session_count ?? 0}`} />
        <Fact label="Python helpers" value={`${codexCapabilities.callable_python?.callable_count ?? 0}`} state={codexCapabilities.callable_python?.status} />
      </div>
      <PanelHeader title="Subsystems" small />
      <div className="world-action-list">
        {subsystems.length === 0 ? (
          <div className="empty-state">Capability inventory wordt nog geladen.</div>
        ) : (
          subsystems.map((item) => (
            <div className="world-action" key={item.key ?? item.label}>
              <div>
                <strong>{item.label ?? item.key}</strong>
                <span>{item.detected ? item.invocation ?? "detected" : "absent"}</span>
              </div>
              <p>{item.description ?? ""}</p>
              {item.paths && item.paths.length > 0 && (
                <em>{item.paths.slice(0, 3).join(", ")}{item.paths.length > 3 ? " …" : ""}</em>
              )}
            </div>
          ))
        )}
      </div>
      <PanelHeader title="Run Codex task" small />
      <div className="prompt-stack">
        <textarea
          value={runPrompt}
          onChange={(event) => setRunPrompt(event.target.value)}
          placeholder="Beschrijf wat Codex moet doen (Akkoord vereist)"
          rows={3}
        />
        <button onClick={onRun} disabled={busy || !approvalReady || !runPrompt.trim() || binary.status !== "found"}>
          <Send size={14} /> {approvalReady ? "Run codex" : "Akkoord vereist"}
        </button>
      </div>
      <PanelHeader title="Recent codex jobs" small />
      <div className="world-action-list">
        {recentJobs.length === 0 ? (
          <div className="empty-state">Nog geen codex jobs.</div>
        ) : (
          recentJobs.map((job) => (
            <div className="world-action" key={job.job_id}>
              <div>
                <strong>{job.status}</strong>
                <span>{job.job_id}</span>
              </div>
              <p>{(job.task ?? "").slice(0, 200)}{job.task && job.task.length > 200 ? "…" : ""}</p>
              {job.response_preview && <em>{job.response_preview.slice(0, 160)}</em>}
            </div>
          ))
        )}
      </div>
      {codexStatus.fake_success === false && overall !== "online" && (
        <div className="nexus-last">
          <strong>Status</strong>
          <span>
            {overall === "missing"
              ? "Codex repo niet gevonden — controleer WINTRIP_CODEX_PATH."
              : overall === "discoverable"
                ? "Repo aanwezig; geen runtime binary in PATH/extensions gevonden."
                : overall === "binary_present_no_auth"
                  ? "Binary aanwezig, geen auth; voer codex login uit op de host."
                  : "Codex layer wacht nog op alle componenten."}
          </span>
        </div>
      )}
    </div>
  );
}

function WorldActionsPanel({ world }: { world: WorldStatus }) {
  const actions = Array.isArray(world.recent_actions) ? world.recent_actions.slice().reverse().slice(0, 8) : [];
  const memory = world.memory ?? {};
  return (
    <div className="world-panel">
      <div className="world-head">
        <div>
          <strong>{world.grok_url ?? "https://grok.com"}</strong>
          <span>{world.host_bridge ? "host bridge" : "backend"} / {memory.embedding_mode ?? "hash"} vectors</span>
        </div>
        <i className={world.status === "online" ? "good" : "warn"} />
      </div>
      <div className="nexus-stats">
        <span>Memory <strong>{memory.available ? "online" : "off"}</strong></span>
        <span>Count <strong>{memory.count ?? 0}</strong></span>
        <span>Browser <strong>{world.dependencies?.playwright ? "ready" : "setup"}</strong></span>
        <span>Chroma <strong>{world.dependencies?.chromadb ? "ready" : "setup"}</strong></span>
      </div>
      <div className="world-action-list">
        {actions.length === 0 ? (
          <div className="empty-state">Nog geen wereldacties. Typ bijvoorbeeld: open grok.com en vraag iets concreets.</div>
        ) : (
          actions.map((action, index) => (
            <div className="world-action" key={action.action_id ?? `${action.ts ?? "action"}-${index}`}>
              <div>
                <strong>{action.action ?? "world"} · {action.status ?? "unknown"}</strong>
                <span>{action.ts ? new Date(action.ts).toLocaleTimeString() : ""}</span>
              </div>
              <p>{action.question || action.query || action.reason || action.response || action.next_action || "Geen detail."}</p>
              {action.memory?.stored && <em>stored {action.memory.memory_id?.slice(0, 24) ?? "memory"}</em>}
            </div>
          ))
        )}
      </div>
      {world.reason && <div className="nexus-last"><strong>{world.status ?? "unavailable"}</strong><span>{world.reason}</span></div>}
    </div>
  );
}

function OmegaPointNexusPanel({ nexus }: { nexus: NexusStatus }) {
  const omega = nexus.omega_vector ?? {};
  const last = nexus.last_event ?? null;
  const coherence = typeof omega.coherence === "number" ? omega.coherence : last?.coherence;
  const entropy = typeof omega.entropy_level === "number" ? omega.entropy_level : last?.entropy_level;
  const coherencePercent = Math.max(0, Math.min(100, Math.round((coherence ?? 0) * 100)));
  const entropyPercent = Math.max(0, Math.min(100, Math.round((entropy ?? 0) * 100)));
  return (
    <div className="nexus-panel">
      <div className="nexus-head">
        <div>
          <strong>Ω-Point Recursion Vector</strong>
          <span>{nexus.version ?? "v4.x"} / {omega.converged ? "converged" : omega.last_action ?? nexus.status ?? "observing"}</span>
        </div>
        <i className={omega.converged ? "good" : "warn"} />
      </div>
      <div className="nexus-stats">
        <span>Heal <strong>{nexus.healing_events ?? 0}</strong></span>
        <span>Creative <strong>{nexus.sacred_corruptions ?? 0}</strong></span>
        <span>Total <strong>{nexus.total_corruption_events ?? 0}</strong></span>
        <span>Rejected <strong>{nexus.tool_rejections ?? 0}</strong></span>
      </div>
      <div className="nexus-bars">
        <label>
          <span>COH {formatMetric(coherence)}</span>
          <b><em style={{ width: `${coherencePercent}%` }} /></b>
        </label>
        <label>
          <span>ENT {formatMetric(entropy)}</span>
          <b><em className="warn" style={{ width: `${entropyPercent}%` }} /></b>
        </label>
      </div>
      {last && (
        <div className="nexus-last">
          <strong>{last.action ?? "event"} · {last.agent ?? "agent"}</strong>
          <span>{last.reason ?? last.phase ?? ""}</span>
        </div>
      )}
      {!last && nexus.reason && (
        <div className="nexus-last">
          <strong>{nexus.status ?? "unavailable"}</strong>
          <span>{nexus.reason}</span>
        </div>
      )}
    </div>
  );
}

function LivingOuroborosPanel({
  living,
  busy,
  onStart,
  onTick,
  onStop,
}: {
  living: LivingStatus;
  busy: boolean;
  onStart: () => void;
  onTick: () => void;
  onStop: () => void;
}) {
  const recent = living.recent ?? living.memory?.recent ?? [];
  return (
    <div className="living-panel">
      <div className="living-head">
        <div>
          <strong>{living.running ? "Background loop active" : "Reflective loop idle"}</strong>
          <span>{living.memory?.entry_count ?? 0} persistent events / {living.version ?? "v4.6"}</span>
        </div>
        <div className="living-actions">
          <button onClick={onStart} disabled={busy || living.running}>Start</button>
          <button onClick={onTick} disabled={busy}>Tick</button>
          <button onClick={onStop} disabled={busy || !living.running}>Stop</button>
        </div>
      </div>
      <div className="living-thought">
        <span>Thought</span>
        <strong>{living.current_thought || "Nog stil."}</strong>
      </div>
      <div className="living-thought">
        <span>Question</span>
        <strong>{living.current_question || "Nog geen vraag."}</strong>
      </div>
      {living.last_whisper && (
        <div className="living-whisper">
          <span>{living.last_whisper}</span>
        </div>
      )}
      {!living.last_whisper && living.reason && (
        <div className="living-whisper">
          <span>{living.reason}</span>
        </div>
      )}
      {recent.length > 0 && (
        <div className="living-timeline">
          {recent.slice(-4).reverse().map((entry) => (
            <div key={entry.id ?? `${entry.kind}-${entry.ts}`}>
              <span>{entry.kind ?? "event"}</span>
              <strong>{entry.text ?? ""}</strong>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function QuantumFoamPanel({
  field,
  busy,
  onInitiate,
  onTick,
  onCollapse,
}: {
  field: QuantumFoamStatus;
  busy: boolean;
  onInitiate: () => void;
  onTick: () => void;
  onCollapse: () => void;
}) {
  const active = field.active_field ?? null;
  const latest = active ?? field.latest_field ?? null;
  const coherence = latest?.field_coherence ?? field.field_coherence ?? 0;
  const coherencePercent = Math.max(0, Math.min(100, Math.round((latest?.field_coherence_percent ?? field.field_coherence_percent ?? coherence * 100) || 0)));
  const nodes = latest?.nodes ?? [];
  const collapsed = latest?.collapse_essence ?? null;
  const geometry = latest?.dimensional_geometry ?? collapsed?.dimensional_geometry ?? null;
  const geometryLabel = geometry
    ? `${geometry.dimension_label ?? `${geometry.dimension ?? 0}D`} ${geometry.geometry_en ?? geometry.geometry ?? ""}`.trim()
    : "--";
  const cliqueSize = geometry?.clique_size ?? geometry?.electron_count ?? 0;
  const collapseEvent = field.last_event?.action === "collapsed" || latest?.status === "collapsed" || !!collapsed;
  const releasedNodes = collapsed?.ram_released_estimate_nodes ?? field.last_event?.metadata?.essence?.ram_released_estimate_nodes ?? 0;
  return (
    <div className="quantum-foam-panel">
      <div className="living-head">
        <div>
          <strong>{latest ? latest.field_id ?? "field" : field.status === "idle" ? "Field idle" : field.status ?? "unknown"}</strong>
          <span>{field.version ?? "v4.9"} / {latest?.status ?? field.status ?? "idle"} / {latest?.node_count ?? 0} nodes / {latest?.mesh?.edge_count ?? 0} links</span>
        </div>
        <div className="living-actions">
          <button onClick={onInitiate} disabled={busy}>Initiate</button>
          <button onClick={onTick} disabled={busy || !active}>Tick</button>
          <button onClick={onCollapse} disabled={busy || !active}>Collapse</button>
        </div>
      </div>
      <div className={active ? "field-state-badge active" : "field-state-badge"} aria-label={active ? "Quantum Foam Field active" : "Quantum Foam Field idle"}>
        <strong>Quantum Foam Field {active ? "active" : latest?.status ?? field.status ?? "idle"}</strong>
        <span>Coherence: {coherencePercent}% / {geometryLabel}</span>
      </div>
      <div className="nexus-bars">
        <label>
          <span>FIELD COH {formatMetric(coherence)}</span>
          <b><em style={{ width: `${coherencePercent}%` }} /></b>
        </label>
      </div>
      {latest?.task && (
        <div className="living-thought">
          <span>Task</span>
          <strong>{latest.task}</strong>
        </div>
      )}
      <div className="metric-strip">
        <span>Ticks <strong>{latest?.tick_count ?? 0}/{latest?.max_ticks ?? field.lifecycle?.default_max_ticks ?? "--"}</strong></span>
        <span>Active <strong>{latest?.active_node_count ?? 0}</strong></span>
        <span>Fields <strong>{field.field_count ?? 0}</strong></span>
        <span>Limit <strong>{field.lifecycle?.max_nodes ?? 25}</strong></span>
        <span>Foam <strong>{geometryLabel}</strong></span>
        <span>Clique <strong>{cliqueSize || "--"}</strong></span>
      </div>
      {nodes.length > 0 && (
        <div className="quantum-node-list">
          {nodes.slice(0, 8).map((node) => (
            <div key={node.node_id ?? `${node.node_type}-${node.weight}`}>
              <span>{node.node_type ?? "Node"}</span>
              <strong>weight {formatMetric(node.weight)} / coh {formatMetric(node.coherence)} / {node.connection_count ?? 0} links</strong>
            </div>
          ))}
        </div>
      )}
      {collapseEvent && (
        <div className="field-collapse-event">
          <strong>Field Collapse</strong>
          <span>{collapsed?.summary ?? field.last_event?.metadata?.essence?.summary ?? "Essentie bewaard; tijdelijke nodes vrijgegeven."}</span>
          <em>{releasedNodes} nodes released</em>
        </div>
      )}
      {collapsed?.summary && (
        <div className="living-whisper">
          <span>{collapsed.summary}</span>
        </div>
      )}
      {!active && field.reason && (
        <div className="living-whisper">
          <span>{field.reason}</span>
        </div>
      )}
    </div>
  );
}

function Fact({ label, value, state }: { label: string; value: ReactNode; state?: string }) {
  return (
    <div className="fact-row">
      <span>{label}</span>
      <strong>{value}</strong>
      {state ? <em>{state}</em> : null}
    </div>
  );
}

function EventItem({ event }: { event: OperationEvent }) {
  const ok = ["success", "completed", "stored", "preview", "online", "idle"].includes(event.status);
  return (
    <article className={`event-item ${ok ? "good" : "warn"}`}>
      <div>
        <strong>{event.title}</strong>
        <span>{event.at}</span>
      </div>
      <p>{event.detail || event.status}</p>
      <details>
        <summary>{event.status}</summary>
        <pre>{JSON.stringify(event.raw, null, 2)}</pre>
      </details>
    </article>
  );
}

function TrainerPanel({ api, trainerStatus, trainerJobs, approval, approvalReady, refresh }: { api: any; trainerStatus: any; trainerJobs: any[]; approval: string; approvalReady: boolean; refresh: () => Promise<void> }) {
  const [baseModel, setBaseModel] = useState("llama3.2:latest");
  const [method, setMethod] = useState("litgpt");
  const [datasetPreview, setDatasetPreview] = useState<any>(null);
  const [blueSamples, setBlueSamples] = useState(10000);
  const [blueEstimators, setBlueEstimators] = useState(300);
  const [blueMaxDepth, setBlueMaxDepth] = useState(12);
  const [blueCycles, setBlueCycles] = useState(3);
  const [continuousLitgpt, setContinuousLitgpt] = useState(true);
  const [continuousUnsloth, setContinuousUnsloth] = useState(true);
  const [continuousInterval, setContinuousInterval] = useState(300);
  const [continuousExecute, setContinuousExecute] = useState(false);
  const [rotatingSamples, setRotatingSamples] = useState(1000);
  const [rotatingEstimators, setRotatingEstimators] = useState(120);
  const [rotatingDepth, setRotatingDepth] = useState(12);
  const [rotatingInterval, setRotatingInterval] = useState(0);
  const [rotatingMax, setRotatingMax] = useState(0);
  const [rotatingClockMode, setRotatingClockMode] = useState(true);
  const [rotatingMaxHz, setRotatingMaxHz] = useState(20000);
  const [rotatingClockDivisor, setRotatingClockDivisor] = useState(100000);
  const [rotatingTrainEvery, setRotatingTrainEvery] = useState(10000);
  const [streamingSteps, setStreamingSteps] = useState(25);
  const [streamingInterval, setStreamingInterval] = useState(0.2);
  const [streamingExportSamples, setStreamingExportSamples] = useState(1000);
  const [codexFunctions, setCodexFunctions] = useState<any[]>([]);
  const [selectedCodexFunction, setSelectedCodexFunction] = useState("");
  const [codexArgs, setCodexArgs] = useState("[]");
  const [codexKwargs, setCodexKwargs] = useState("{}");
  const [codexResult, setCodexResult] = useState<any>(null);
  const [codexMonitor, setCodexMonitor] = useState<any>(null);
  const [trainerActionResult, setTrainerActionResult] = useState<any>(null);
  const [codexAgentPrompt, setCodexAgentPrompt] = useState("Open een browser naar https://example.com");
  const [codexAgentAutoExtend, setCodexAgentAutoExtend] = useState(true);
  const [codexAgentExecute, setCodexAgentExecute] = useState(true);
  const [codexAgentStatus, setCodexAgentStatus] = useState<any>(null);
  const [codexAgentResult, setCodexAgentResult] = useState<any>(null);
  const [codeneuronQuery, setCodeneuronQuery] = useState("mechanism mpi soa");
  const [codeneuronSearch, setCodeneuronSearch] = useState<any>(null);
  const [pocketMap, setPocketMap] = useState<any>(null);
  const [machineStatus, setMachineStatus] = useState<any>(null);
  const [independenceStatus, setIndependenceStatus] = useState<any>(null);
  const [knowledgeAcquisition, setKnowledgeAcquisition] = useState<any>(null);
  const [knowledgeMode, setKnowledgeMode] = useState("gemma_brave");
  const [knowledgeMaxTopics, setKnowledgeMaxTopics] = useState(2);
  const [knowledgePasses, setKnowledgePasses] = useState(3);
  const [knowledgeModel, setKnowledgeModel] = useState("gemma4:latest");
  const isBlueBrain = method === "blue_brain";
  const continuousMethods = [
    continuousLitgpt ? "litgpt" : "",
    continuousUnsloth ? "unsloth" : "",
  ].filter(Boolean);

  useEffect(() => {
    loadCodexFunctions()
      .catch((error: unknown) => console.error("Failed to load Codex functions:", error));
    loadKnowledgeStatus()
      .catch((error: unknown) => console.error("Failed to load knowledge status:", error));
  }, [api]);

  async function loadCodexFunctions() {
    const [functionsData, monitorData] = await Promise.all([
      api("/trainer/codex/functions"),
      api("/trainer/codex/monitor"),
    ]);
    const functions = functionsData?.functions ?? [];
    setCodexFunctions(functions);
    setCodexMonitor(monitorData);
    setSelectedCodexFunction((current) => current || functions[0]?.name || "");
    setCodexArgs((current) => current === "[]" && functions[0]?.signature?.includes("content:") ? "[\"# Demo\\n\\n## Live Codex\"]" : current);
    setTrainerActionResult({
      title: "Codex Registry Refresh",
      at: new Date().toLocaleTimeString(),
      status: functionsData?.status ?? "--",
      data: { functions: functionsData, monitor: monitorData },
    });
  }

  async function loadCodexAgentStatus() {
    const data = await api("/trainer/codex/agent/status");
    setCodexAgentStatus(data);
    return data;
  }

  async function loadKnowledgeStatus() {
    const [pocketData, machineData, independenceData, acquisitionData] = await Promise.all([
      api("/trainer/codeneuron/pocket-map"),
      api("/trainer/local-machine/status"),
      api("/trainer/independence/status"),
      api("/trainer/knowledge/status"),
    ]);
    setPocketMap(pocketData);
    setMachineStatus(machineData);
    setIndependenceStatus(independenceData);
    setKnowledgeAcquisition(acquisitionData);
    return { pocketData, machineData, independenceData, acquisitionData };
  }

  function recordTrainerAction(title: string, data: any) {
    setTrainerActionResult({
      title,
      at: new Date().toLocaleTimeString(),
      status: data?.status ?? data?.state ?? "success",
      data,
    });
  }

  function recordTrainerError(title: string, error: unknown) {
    const data = { status: "error", reason: error instanceof Error ? error.message : String(error) };
    setTrainerActionResult({
      title,
      at: new Date().toLocaleTimeString(),
      status: "error",
      data,
    });
  }

  async function createJob() {
    const resolvedBaseModel = isBlueBrain ? baseModel || "blue-brain-random-forest" : baseModel.trim();
    if (!resolvedBaseModel) {
      recordTrainerError("Create Job", new Error("Base model is required. Vul eerst een base model in."));
      return;
    }
    try {
      const data = await api("/trainer/jobs", {
        method: "POST",
        body: JSON.stringify({
          base_model: resolvedBaseModel,
          method,
          epochs: isBlueBrain ? blueCycles : 3,
          blue_samples: blueSamples,
          blue_estimators: blueEstimators,
          blue_max_depth: blueMaxDepth,
        }),
      });
      recordTrainerAction("Create Job", data);
      await refresh();
    } catch (error) {
      recordTrainerError("Create Job", error);
    }
  }

  async function setupBlueBrain() {
    try {
      const data = await api("/trainer/blue-brain/setup", {
        method: "POST",
        body: JSON.stringify({ approval }),
      });
      recordTrainerAction("Setup Blue", data);
      await refresh();
    } catch (error) {
      recordTrainerError("Setup Blue", error);
      console.error("Failed to setup Blue Brain:", error);
    }
  }

  async function setupLitgpt() {
    try {
      const data = await api("/trainer/litgpt/setup", {
        method: "POST",
        body: JSON.stringify({ approval }),
      });
      recordTrainerAction("Setup LitGPT", data);
      await refresh();
    } catch (error) {
      recordTrainerError("Setup LitGPT", error);
      console.error("Failed to setup LitGPT:", error);
    }
  }

  async function setupUnsloth() {
    try {
      const data = await api("/trainer/unsloth/setup", {
        method: "POST",
        body: JSON.stringify({ approval }),
      });
      recordTrainerAction("Setup Unsloth", data);
      await refresh();
    } catch (error) {
      recordTrainerError("Setup Unsloth", error);
      console.error("Failed to setup Unsloth:", error);
    }
  }

  async function startJob(jobId: string) {
    try {
      const data = await api("/trainer/training/start", {
        method: "POST",
        body: JSON.stringify({ job_id: jobId, approval }),
      });
      recordTrainerAction("Start Job", data);
      await refresh();
    } catch (error) {
      recordTrainerError("Start Job", error);
      console.error("Failed to start trainer job:", error);
    }
  }

  async function startContinuous() {
    const intervalSeconds = Math.max(30, Math.min(86400, Number(continuousInterval) || 300));
    if (intervalSeconds !== continuousInterval) {
      setContinuousInterval(intervalSeconds);
    }
    try {
      const data = await api("/trainer/continuous/start", {
        method: "POST",
        body: JSON.stringify({
          approval,
          methods: continuousMethods,
          interval_seconds: intervalSeconds,
          execute_training: continuousExecute,
          run_immediately: false,
          litgpt_base_model: baseModel || "llama3.2:latest",
          unsloth_base_model: baseModel || "unsloth/tinyllama-bnb-4bit",
        }),
      });
      recordTrainerAction("Continuous Start", data);
      await refresh();
    } catch (error) {
      recordTrainerError("Continuous Start", error);
      console.error("Failed to start continuous trainer:", error);
    }
  }

  async function stopContinuous() {
    try {
      const data = await api("/trainer/continuous/stop", {
        method: "POST",
        body: JSON.stringify({ approval }),
      });
      recordTrainerAction("Continuous Stop", data);
      await refresh();
    } catch (error) {
      recordTrainerError("Continuous Stop", error);
      console.error("Failed to stop continuous trainer:", error);
    }
  }

  async function tickContinuous() {
    try {
      const data = await api("/trainer/continuous/tick", {
        method: "POST",
        body: JSON.stringify({
          approval,
          force: true,
          execute_training: continuousExecute,
          methods: continuousMethods,
        }),
      });
      recordTrainerAction("Continuous Tick", data);
      await refresh();
    } catch (error) {
      recordTrainerError("Continuous Tick", error);
      console.error("Failed to tick continuous trainer:", error);
    }
  }

  async function accelerateLearning() {
    try {
      const data = await api("/trainer/learning/accelerate", {
        method: "POST",
        body: JSON.stringify({
          approval,
          knowledge_mode: knowledgeMode,
          knowledge_topics: knowledgeMaxTopics,
          knowledge_passes: knowledgePasses,
          model: knowledgeModel,
          continuous_methods: continuousMethods,
          execute_training: continuousExecute,
          max_records: 1000,
        }),
      });
      recordTrainerAction("Accelerate Learning", data);
      setKnowledgeAcquisition(data?.knowledge?.state ?? data?.knowledge ?? data);
      await loadKnowledgeStatus();
      await refresh();
    } catch (error) {
      recordTrainerError("Accelerate Learning", error);
      console.error("Failed to accelerate learning:", error);
    }
  }

  async function startRotatingBlue() {
    try {
      const data = await api("/trainer/rotating-blue/start", {
        method: "POST",
        body: JSON.stringify({
          approval,
          n_samples: rotatingSamples,
          interval_seconds: rotatingInterval,
          max_rotations: rotatingMax,
          cpu_clock_mode: rotatingClockMode,
          max_rotation_hz: rotatingMaxHz,
          clock_divisor: rotatingClockDivisor,
          train_every_rotations: rotatingTrainEvery,
          clock_burst_seconds: 0.05,
          n_estimators: rotatingEstimators,
          max_depth: rotatingDepth,
          run_immediately: false,
        }),
      });
      recordTrainerAction("Rotating Blue Start", data);
      await refresh();
    } catch (error) {
      recordTrainerError("Rotating Blue Start", error);
      console.error("Failed to start rotating Blue Brain:", error);
    }
  }

  async function stopRotatingBlue() {
    try {
      const data = await api("/trainer/rotating-blue/stop", {
        method: "POST",
        body: JSON.stringify({ approval }),
      });
      recordTrainerAction("Rotating Blue Stop", data);
      await refresh();
    } catch (error) {
      recordTrainerError("Rotating Blue Stop", error);
      console.error("Failed to stop rotating Blue Brain:", error);
    }
  }

  async function tickRotatingBlue() {
    try {
      const data = await api("/trainer/rotating-blue/tick", {
        method: "POST",
        body: JSON.stringify({ approval, force: true }),
      });
      recordTrainerAction("Rotating Blue Tick", data);
      await refresh();
    } catch (error) {
      recordTrainerError("Rotating Blue Tick", error);
      console.error("Failed to tick rotating Blue Brain:", error);
    }
  }

  async function startStreamingConsciousness() {
    try {
      const data = await api("/trainer/streaming-consciousness/start", {
        method: "POST",
        body: JSON.stringify({
          approval,
          n_samples: 8000,
          interval_seconds: streamingInterval,
          steps_per_tick: streamingSteps,
          run_immediately: true,
        }),
      });
      recordTrainerAction("Streaming Consciousness Start", data);
      await refresh();
    } catch (error) {
      recordTrainerError("Streaming Consciousness Start", error);
      console.error("Failed to start Streaming Consciousness:", error);
    }
  }

  async function stopStreamingConsciousness() {
    try {
      const data = await api("/trainer/streaming-consciousness/stop", {
        method: "POST",
        body: JSON.stringify({ approval }),
      });
      recordTrainerAction("Streaming Consciousness Stop", data);
      await refresh();
    } catch (error) {
      recordTrainerError("Streaming Consciousness Stop", error);
      console.error("Failed to stop Streaming Consciousness:", error);
    }
  }

  async function tickStreamingConsciousness() {
    try {
      const data = await api("/trainer/streaming-consciousness/tick", {
        method: "POST",
        body: JSON.stringify({ approval, force: true, steps: streamingSteps }),
      });
      recordTrainerAction("Streaming Consciousness Tick", data);
      await refresh();
    } catch (error) {
      recordTrainerError("Streaming Consciousness Tick", error);
      console.error("Failed to tick Streaming Consciousness:", error);
    }
  }

  async function exportStreamingDataset() {
    try {
      const data = await api("/trainer/streaming-consciousness/export-dataset", {
        method: "POST",
        body: JSON.stringify({ approval, n_samples: streamingExportSamples }),
      });
      recordTrainerAction("Streaming Dataset Export", data);
      await refresh();
    } catch (error) {
      recordTrainerError("Streaming Dataset Export", error);
      console.error("Failed to export Streaming Consciousness dataset:", error);
    }
  }

  async function callCodexFunction() {
    try {
      const parsedArgs = JSON.parse(codexArgs || "[]");
      const parsedKwargs = JSON.parse(codexKwargs || "{}");
      const data = await api("/trainer/codex/call", {
        method: "POST",
        body: JSON.stringify({
          approval,
          function: selectedCodexFunction,
          args: Array.isArray(parsedArgs) ? parsedArgs : [parsedArgs],
          kwargs: parsedKwargs && typeof parsedKwargs === "object" && !Array.isArray(parsedKwargs) ? parsedKwargs : {},
        }),
      });
      setCodexResult(data);
      recordTrainerAction("Codex Function Call", data);
      await loadCodexFunctions();
    } catch (error) {
      const data = { status: "error", reason: error instanceof Error ? error.message : String(error) };
      setCodexResult(data);
      recordTrainerError("Codex Function Call", error);
      await loadCodexFunctions().catch(() => undefined);
      console.error("Failed to call Codex function:", error);
    }
  }

  async function runCodexAgent() {
    try {
      const data = await api("/trainer/codex/agent/chat", {
        method: "POST",
        body: JSON.stringify({
          message: codexAgentPrompt,
          approval,
          auto_extend: codexAgentAutoExtend,
          execute: codexAgentExecute,
        }),
      });
      setCodexAgentResult(data);
      recordTrainerAction("Codex Agent", data);
      if (data?.frontend_action?.type === "open_url" && data.frontend_action.url) {
        const openResult = await openExternalUrl(data.frontend_action.url, data.frontend_action.target ?? "_blank");
        await api("/trainer/codex/agent/frontend-event", {
          method: "POST",
          body: JSON.stringify({
            action_id: data.frontend_action.action_id,
            status: openResult.opened ? "opened" : "blocked_by_browser",
            detail: openResult.detail,
            payload: { url: data.frontend_action.url, via: openResult.via },
          }),
        });
      }
      await loadCodexAgentStatus();
      await refresh();
    } catch (error) {
      recordTrainerError("Codex Agent", error);
      console.error("Failed to run Codex Agent:", error);
    }
  }

  async function indexCodeNeuron() {
    try {
      const data = await api("/trainer/codeneuron/index", {
        method: "POST",
        body: JSON.stringify({ max_files: 1500, max_bytes_per_file: 50000 }),
      });
      recordTrainerAction("CodeNeuron Index", data);
      await loadKnowledgeStatus();
      await refresh();
    } catch (error) {
      recordTrainerError("CodeNeuron Index", error);
      console.error("Failed to index CodeNeuron:", error);
    }
  }

  async function searchCodeNeuron() {
    try {
      const data = await api(`/trainer/codeneuron/search?q=${encodeURIComponent(codeneuronQuery)}&limit=12`);
      setCodeneuronSearch(data);
      recordTrainerAction("CodeNeuron Search", data);
    } catch (error) {
      recordTrainerError("CodeNeuron Search", error);
      console.error("Failed to search CodeNeuron:", error);
    }
  }

  async function snapshotLocalMachine() {
    try {
      const data = await api("/trainer/local-machine/snapshot", {
        method: "POST",
        body: JSON.stringify({ approval }),
      });
      recordTrainerAction("Local Machine Snapshot", data);
      await loadKnowledgeStatus();
      await refresh();
    } catch (error) {
      recordTrainerError("Local Machine Snapshot", error);
      console.error("Failed to snapshot local machine:", error);
    }
  }

  async function loadIndependenceStatus() {
    try {
      const data = await api("/trainer/independence/status");
      setIndependenceStatus(data);
      recordTrainerAction("Independence Refresh", data);
    } catch (error) {
      recordTrainerError("Independence Refresh", error);
      console.error("Failed to load independence status:", error);
    }
  }

  async function indexKnowledgeList() {
    try {
      const data = await api("/trainer/knowledge/index-list", {
        method: "POST",
        body: JSON.stringify({ approval }),
      });
      recordTrainerAction("Knowledge List Index", data);
      await loadKnowledgeStatus();
      await refresh();
    } catch (error) {
      recordTrainerError("Knowledge List Index", error);
      console.error("Failed to index knowledge list:", error);
    }
  }

  async function tickKnowledgeAcquisition() {
    try {
      const data = await api("/trainer/knowledge/tick", {
        method: "POST",
        body: JSON.stringify({
          approval,
          mode: knowledgeMode,
          max_topics: knowledgeMaxTopics,
          model: knowledgeModel,
        }),
      });
      recordTrainerAction("Knowledge Acquisition Tick", data);
      setKnowledgeAcquisition(data?.state ?? data);
      await loadKnowledgeStatus();
      await refresh();
    } catch (error) {
      recordTrainerError("Knowledge Acquisition Tick", error);
      console.error("Failed to run knowledge acquisition:", error);
    }
  }

  async function previewDataset() {
    try {
      const data = await api("/trainer/dataset/preview", { method: "POST", body: JSON.stringify({ max_records: 10 }) });
      setDatasetPreview(data);
    } catch (error) {
      console.error("Failed to preview dataset:", error);
    }
  }

  return (
    <section className="panel trainer-panel" style={{ gridColumn: "1 / -1", minHeight: "400px" }}>
      <PanelHeader title="Trainer Pipeline" />
      <div className="trainer-status">
        <Metric label="LitGPT" value={trainerStatus?.litgpt?.status ?? "--"} tone={trainerStatus?.litgpt?.status === "online" ? "good" : "warn"} />
        <Metric label="Unsloth" value={trainerStatus?.unsloth?.status ?? "--"} tone={trainerStatus?.unsloth?.status === "online" ? "good" : "warn"} />
        <Metric label="Blue Brain" value={trainerStatus?.blue_brain?.status ?? "--"} tone={trainerStatus?.blue_brain?.status === "online" ? "good" : "warn"} />
        <Metric label="Approved Records" value={trainerStatus?.approved_dataset_records ?? 0} />
        <Metric label="Total Jobs" value={trainerStatus?.pipeline?.total_jobs ?? 0} />
        <Metric label="Artifacts" value={trainerStatus?.artifacts?.total_artifacts ?? 0} />
        <Metric label="Continuous" value={trainerStatus?.continuous?.status ?? "--"} tone={trainerStatus?.continuous?.enabled ? "good" : "warn"} />
        <Metric label="New Records" value={trainerStatus?.continuous?.new_records_available ?? 0} />
        <Metric label="Rotating" value={trainerStatus?.rotating_blue?.status ?? "--"} tone={trainerStatus?.rotating_blue?.enabled ? "good" : "warn"} />
        <Metric label="Stream 11D" value={trainerStatus?.streaming_consciousness?.status ?? "--"} tone={trainerStatus?.streaming_consciousness?.enabled ? "good" : "warn"} />
        <Metric label="Codex" value={trainerStatus?.codex_registry?.callable_count ?? 0} />
        <Metric label="CodeNeuron" value={trainerStatus?.codeneuron?.status ?? "--"} tone={trainerStatus?.codeneuron?.indexed ? "good" : "warn"} />
        <Metric label="Knowledge" value={trainerStatus?.knowledge_acquisition?.total_records ?? knowledgeAcquisition?.total_records ?? 0} tone={(trainerStatus?.knowledge_acquisition?.total_records ?? knowledgeAcquisition?.total_records ?? 0) > 0 ? "good" : "warn"} />
        <Metric label="Independence" value={Number(independenceStatus?.independence_score ?? trainerStatus?.independence?.independence_score ?? 0).toFixed(2)} tone={(independenceStatus?.external_model_needed ?? trainerStatus?.independence?.external_model_needed) ? "warn" : "good"} />
      </div>

      <PanelHeader title="Ecosystem Status" small />
      <div className="trainer-status">
        <Metric label="Pop!_OS" value={trainerStatus?.ecosystem?.ecosystem_adapters?.popos?.status ?? trainerStatus?.popos_diagnostics?.status ?? "--"} tone={trainerStatus?.popos_diagnostics?.status === "ready" ? "good" : "warn"} />
        <Metric label="Google" value={trainerStatus?.ecosystem?.ecosystem_adapters?.google?.status ?? trainerStatus?.google_workspace?.status ?? "--"} tone={(trainerStatus?.google_workspace?.status === "connected") ? "good" : "warn"} />
        <Metric label="Microsoft" value={trainerStatus?.ecosystem?.ecosystem_adapters?.microsoft?.status ?? trainerStatus?.microsoft_graph?.status ?? "--"} tone={(trainerStatus?.microsoft_graph?.status === "connected") ? "good" : "warn"} />
        <Metric label="SharePoint" value={trainerStatus?.ecosystem?.ecosystem_adapters?.sharepoint?.status ?? trainerStatus?.sharepoint?.status ?? "--"} tone={(trainerStatus?.sharepoint?.status === "ready") ? "good" : "warn"} />
        <Metric label="Crawler" value={trainerStatus?.agentic_crawler?.status ?? trainerStatus?.ecosystem?.crawl_stats?.status ?? "--"} tone={(trainerStatus?.agentic_crawler?.indexed_files ?? 0) > 0 ? "good" : "warn"} />
        <Metric label="Indexed Files" value={trainerStatus?.agentic_crawler?.indexed_files ?? trainerStatus?.ecosystem?.crawl_stats?.indexed_files ?? 0} />
        <Metric label="Programs" value={trainerStatus?.program_inventory?.desktop_app_count ?? trainerStatus?.ecosystem?.program_inventory?.desktop_app_count ?? 0} tone={(trainerStatus?.program_inventory?.desktop_app_count ?? trainerStatus?.ecosystem?.program_inventory?.desktop_app_count ?? 0) > 0 ? "good" : "warn"} />
        <Metric label="Packages" value={trainerStatus?.program_inventory?.package_count ?? trainerStatus?.ecosystem?.program_inventory?.package_count ?? 0} />
        <Metric label="Host Flows" value={trainerStatus?.host_sensory?.active_flow_count ?? trainerStatus?.ecosystem?.host_sensory?.active_flow_count ?? 0} tone={(trainerStatus?.host_sensory?.active_flow_count ?? trainerStatus?.ecosystem?.host_sensory?.active_flow_count ?? 0) > 0 ? "good" : "warn"} />
        <Metric label="Host Apps" value={trainerStatus?.host_sensory?.process_count ?? trainerStatus?.ecosystem?.host_sensory?.process_count ?? 0} />
        <Metric label="Ecosystem Topics" value={trainerStatus?.ecosystem_knowledge?.topic_count ?? trainerStatus?.ecosystem?.ecosystem_knowledge?.topic_count ?? 0} />
        <Metric label="11D Overlay" value={trainerStatus?.streaming_consciousness?.ecosystem_overlay?.status ?? "--"} tone={trainerStatus?.streaming_consciousness?.ecosystem_overlay?.status === "available" ? "good" : "warn"} />
      </div>
      
      <PanelHeader title="Create Job" small />
      <div className="trainer-form">
        <label>
          Base Model
          <input value={baseModel} onChange={(e) => setBaseModel(e.target.value)} placeholder="llama3.2:latest" />
        </label>
        <label>
          Method
          <select value={method} onChange={(e) => setMethod(e.target.value)}>
            <option value="litgpt">LitGPT</option>
            <option value="unsloth">Unsloth</option>
            <option value="blue_brain">Blue Brain</option>
          </select>
        </label>
        {isBlueBrain && (
          <div className="blue-brain-grid">
            <label>
              Samples
              <input type="number" min={100} max={200000} value={blueSamples} onChange={(e) => setBlueSamples(Number(e.target.value))} />
            </label>
            <label>
              Trees
              <input type="number" min={10} max={2000} value={blueEstimators} onChange={(e) => setBlueEstimators(Number(e.target.value))} />
            </label>
            <label>
              Depth
              <input type="number" min={1} max={100} value={blueMaxDepth} onChange={(e) => setBlueMaxDepth(Number(e.target.value))} />
            </label>
            <label>
              Cycles
              <input type="number" min={1} max={50} value={blueCycles} onChange={(e) => setBlueCycles(Number(e.target.value))} />
            </label>
          </div>
        )}
        {isBlueBrain && (
          <div className="trainer-actions">
            <button onClick={setupBlueBrain} disabled={!approvalReady}>
              <Activity size={15} /> Setup Blue
            </button>
          </div>
        )}
        {method === "litgpt" && (
          <div className="trainer-actions">
            <button onClick={setupLitgpt} disabled={!approvalReady}>
              <Activity size={15} /> Setup LitGPT
            </button>
          </div>
        )}
        {method === "unsloth" && (
          <div className="trainer-actions">
            <button onClick={setupUnsloth} disabled={!approvalReady}>
              <Activity size={15} /> Setup Unsloth
            </button>
          </div>
        )}
        <button onClick={createJob}>
          <BrainCircuit size={15} /> Create Job
        </button>
      </div>

      {trainerActionResult && (
        <div className={`trainer-action-result ${trainerActionResult.status === "error" ? "warn" : "good"}`}>
          <div>
            <strong>{trainerActionResult.title}</strong>
            <span>{trainerActionResult.at}</span>
          </div>
          <pre>{JSON.stringify(trainerActionResult.data, null, 2)}</pre>
        </div>
      )}

      <PanelHeader title="Continuous" small />
      <div className="continuous-controls">
        <label className="check-row">
          <input type="checkbox" checked={continuousLitgpt} onChange={(e) => setContinuousLitgpt(e.target.checked)} />
          LitGPT
        </label>
        <label className="check-row">
          <input type="checkbox" checked={continuousUnsloth} onChange={(e) => setContinuousUnsloth(e.target.checked)} />
          Unsloth
        </label>
        <label className="check-row">
          <input type="checkbox" checked={continuousExecute} onChange={(e) => setContinuousExecute(e.target.checked)} />
          Train
        </label>
        <label>
          Interval
          <input type="number" min={30} max={86400} value={continuousInterval} onChange={(e) => setContinuousInterval(Number(e.target.value))} />
        </label>
        <button onClick={startContinuous} disabled={!approvalReady || continuousMethods.length === 0}>
          <Play size={15} /> Start
        </button>
        <button onClick={tickContinuous} disabled={continuousMethods.length === 0 || (continuousExecute && !approvalReady)}>
          <RefreshCw size={15} /> Tick
        </button>
        <button onClick={stopContinuous} disabled={!approvalReady}>
          <Pause size={15} /> Stop
        </button>
      </div>

      <PanelHeader title="Blue Brain Rotating" small />
      <div className="rotating-blue-panel">
        <div className="trainer-status">
          <Metric label="Status" value={trainerStatus?.rotating_blue?.status ?? "--"} tone={trainerStatus?.rotating_blue?.enabled ? "good" : "warn"} />
          <Metric label="Rotations" value={trainerStatus?.rotating_blue?.rotation_count ?? 0} />
          <Metric label="Accuracy" value={trainerStatus?.rotating_blue?.last_metrics?.accuracy ? Number(trainerStatus.rotating_blue.last_metrics.accuracy).toFixed(4) : "--"} />
          <Metric label="Macro F1" value={trainerStatus?.rotating_blue?.last_metrics?.macro_f1 ? Number(trainerStatus.rotating_blue.last_metrics.macro_f1).toFixed(4) : "--"} />
          <Metric label="Best" value={trainerStatus?.rotating_blue?.best_accuracy ? Number(trainerStatus.rotating_blue.best_accuracy).toFixed(4) : "--"} />
          <Metric label="Clock Hz" value={trainerStatus?.rotating_blue?.clock_rotation_hz ? Math.round(Number(trainerStatus.rotating_blue.clock_rotation_hz)).toLocaleString() : "--"} tone={trainerStatus?.rotating_blue?.cpu_clock_mode ? "good" : undefined} />
          <Metric label="CPU GHz" value={trainerStatus?.rotating_blue?.cpu_clock_ghz ? Number(trainerStatus.rotating_blue.cpu_clock_ghz).toFixed(2) : "--"} />
          <Metric label="Train Ticks" value={trainerStatus?.rotating_blue?.training_rotation_count ?? 0} />
        </div>
        <div className="rotating-controls">
          <label className="check-row">
            <input type="checkbox" checked={rotatingClockMode} onChange={(e) => setRotatingClockMode(e.target.checked)} />
            CPU Clock
          </label>
          <label>
            Samples
            <input type="number" min={100} max={200000} value={rotatingSamples} onChange={(e) => setRotatingSamples(Number(e.target.value))} />
          </label>
          <label>
            Trees
            <input type="number" min={10} max={2000} value={rotatingEstimators} onChange={(e) => setRotatingEstimators(Number(e.target.value))} />
          </label>
          <label>
            Depth
            <input type="number" min={1} max={100} value={rotatingDepth} onChange={(e) => setRotatingDepth(Number(e.target.value))} />
          </label>
          <label>
            Interval
            <input type="number" min={0} max={86400} value={rotatingInterval} onChange={(e) => setRotatingInterval(Number(e.target.value))} disabled={rotatingClockMode} />
          </label>
          <label>
            Hz Cap
            <input type="number" min={1} max={2000000} value={rotatingMaxHz} onChange={(e) => setRotatingMaxHz(Number(e.target.value))} disabled={!rotatingClockMode} />
          </label>
          <label>
            Clock Div
            <input type="number" min={1} max={1000000000} value={rotatingClockDivisor} onChange={(e) => setRotatingClockDivisor(Number(e.target.value))} disabled={!rotatingClockMode} />
          </label>
          <label>
            Train Every
            <input type="number" min={1} max={10000000} value={rotatingTrainEvery} onChange={(e) => setRotatingTrainEvery(Number(e.target.value))} disabled={!rotatingClockMode} />
          </label>
          <label>
            Max
            <input type="number" min={0} max={1000000000} value={rotatingMax} onChange={(e) => setRotatingMax(Number(e.target.value))} />
          </label>
          <button onClick={startRotatingBlue} disabled={!approvalReady}>
            <Play size={15} /> Start
          </button>
          <button onClick={tickRotatingBlue} disabled={!approvalReady}>
            <RefreshCw size={15} /> Tick
          </button>
          <button onClick={stopRotatingBlue} disabled={!approvalReady}>
            <Pause size={15} /> Stop
          </button>
        </div>
        <ProjectionPlot points={trainerStatus?.rotating_blue?.last_projection ?? []} />
      </div>

      <PanelHeader title="Streaming Consciousness 11D" small />
      <div className="streaming-consciousness-panel">
        <div className="trainer-status">
          <Metric label="Status" value={trainerStatus?.streaming_consciousness?.status ?? "--"} tone={trainerStatus?.streaming_consciousness?.enabled ? "good" : "warn"} />
          <Metric label="Steps" value={trainerStatus?.streaming_consciousness?.step_count ?? 0} />
          <Metric label="Steps/s" value={trainerStatus?.streaming_consciousness?.steps_per_second ? Number(trainerStatus.streaming_consciousness.steps_per_second).toFixed(1) : "--"} />
          <Metric label="Input" value={trainerStatus?.streaming_consciousness?.last_event?.reality?.input_mode ?? trainerStatus?.streaming_consciousness?.runtime_input?.source ?? "--"} tone={(trainerStatus?.streaming_consciousness?.last_event?.reality?.real_observation ?? trainerStatus?.streaming_consciousness?.runtime_input?.real_observation) ? "good" : "warn"} />
          <Metric label="Flows" value={trainerStatus?.streaming_consciousness?.runtime_input?.active_flow_count ?? trainerStatus?.streaming_consciousness?.last_event?.network?.mini_router?.real_observations ?? 0} />
          <Metric label="Bind" value={trainerStatus?.streaming_consciousness?.last_event?.network?.dhcp ?? "--"} />
          <Metric label="IP" value={trainerStatus?.streaming_consciousness?.last_event?.network?.local_ip ?? "--"} />
          <Metric label="V avg" value={trainerStatus?.streaming_consciousness?.last_event?.elec?.v_avg ? `${Number(trainerStatus.streaming_consciousness.last_event.elec.v_avg).toFixed(1)}mV` : "--"} />
          <Metric label="Projection" value={trainerStatus?.streaming_consciousness?.last_event?.quantum?.expectation !== undefined ? Number(trainerStatus.streaming_consciousness.last_event.quantum.expectation).toFixed(4) : "--"} tone={trainerStatus?.streaming_consciousness?.quantum_collapse?.enabled ? "good" : undefined} />
          <Metric label="Bytes" value={trainerStatus?.streaming_consciousness?.latest_state?.total_bytes ?? 0} />
          <Metric label="Packets" value={trainerStatus?.streaming_consciousness?.last_event?.network?.total_received ?? 0} />
        </div>
        <div className="streaming-controls">
          <label>
            Steps/tick
            <input type="number" min={1} max={5000} value={streamingSteps} onChange={(e) => setStreamingSteps(Number(e.target.value))} />
          </label>
          <label>
            Interval
            <input type="number" min={0.01} max={3600} step={0.01} value={streamingInterval} onChange={(e) => setStreamingInterval(Number(e.target.value))} />
          </label>
          <label>
            Export
            <input type="number" min={1} max={100000} value={streamingExportSamples} onChange={(e) => setStreamingExportSamples(Number(e.target.value))} />
          </label>
          <button onClick={startStreamingConsciousness} disabled={!approvalReady}>
            <Play size={15} /> Start
          </button>
          <button onClick={tickStreamingConsciousness} disabled={!approvalReady}>
            <RefreshCw size={15} /> Tick
          </button>
          <button onClick={stopStreamingConsciousness} disabled={!approvalReady}>
            <Pause size={15} /> Stop
          </button>
          <button onClick={exportStreamingDataset} disabled={!approvalReady}>
            <Database size={15} /> Export
          </button>
        </div>
        <ProjectionPlot points={trainerStatus?.streaming_consciousness?.last_projection ?? []} />
      </div>

      <PanelHeader title="CodeNeuron 11D Pocket" small />
      <div className="codeneuron-panel">
        <div className="trainer-status">
          <Metric label="Status" value={trainerStatus?.codeneuron?.status ?? "--"} tone={trainerStatus?.codeneuron?.indexed ? "good" : "warn"} />
          <Metric label="Files" value={trainerStatus?.codeneuron?.file_count ?? 0} />
          <Metric label="Lines" value={trainerStatus?.codeneuron?.total_lines ?? 0} />
          <Metric label="Dims" value={pocketMap?.dimension_count ?? 11} />
        </div>
        <div className="codeneuron-controls">
          <button onClick={indexCodeNeuron}>
            <Database size={15} /> Index
          </button>
          <label>
            Search
            <input value={codeneuronQuery} onChange={(e) => setCodeneuronQuery(e.target.value)} />
          </label>
          <button onClick={searchCodeNeuron}>
            <RefreshCw size={15} /> Search
          </button>
          <button onClick={loadKnowledgeStatus}>
            <Layers size={15} /> Map
          </button>
        </div>
        <div className="pocket-map">
          {(pocketMap?.dimensions ?? []).slice(0, 11).map((dimension: any) => (
            <div className="pocket-card" key={dimension.id}>
              <div>
                <strong>{dimension.index}. {dimension.title}</strong>
                <span>{dimension.e_type}</span>
              </div>
              <p>{dimension.summary}</p>
              <small>{dimension.source_count ?? 0} CodeNeuron sources</small>
            </div>
          ))}
        </div>
        {codeneuronSearch?.results?.length > 0 && (
          <div className="codeneuron-results">
            {codeneuronSearch.results.map((result: any) => (
              <div key={result.path}>
                <strong>{result.path}</strong>
                <span>{result.subsystem} · score {result.score}</span>
                <p>{result.summary}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <PanelHeader title="Curriculum + Machine + Independence" small />
      <div className="knowledge-panel">
        <div className="trainer-status">
          <Metric label="Curriculum Records" value={trainerStatus?.curriculum?.record_count ?? 0} />
          <Metric label="Machine" value={machineStatus?.status ?? trainerStatus?.local_machine?.status ?? "--"} tone={(machineStatus?.has_snapshot ?? trainerStatus?.local_machine?.has_snapshot) ? "good" : "warn"} />
          <Metric label="Scope" value={machineStatus?.environment?.scope ?? trainerStatus?.local_machine?.environment?.scope ?? "--"} />
          <Metric label="Label" value={independenceStatus?.label ?? trainerStatus?.independence?.label ?? "--"} />
          <Metric label="External Needed" value={String(independenceStatus?.external_model_needed ?? trainerStatus?.independence?.external_model_needed ?? true)} tone={(independenceStatus?.external_model_needed ?? trainerStatus?.independence?.external_model_needed ?? true) ? "warn" : "good"} />
        </div>
        <div className="knowledge-controls">
          <button onClick={snapshotLocalMachine} disabled={!approvalReady}>
            <Cpu size={15} /> Snapshot
          </button>
          <button onClick={loadIndependenceStatus}>
            <ShieldCheck size={15} /> Score
          </button>
        </div>
        <div className="trainer-status">
          <Metric label="Knowledge List" value={knowledgeAcquisition?.status ?? trainerStatus?.knowledge_acquisition?.status ?? "--"} tone={(knowledgeAcquisition?.topic_count ?? trainerStatus?.knowledge_acquisition?.topic_count ?? 0) > 0 ? "good" : "warn"} />
          <Metric label="Topics" value={knowledgeAcquisition?.topic_count ?? trainerStatus?.knowledge_acquisition?.topic_count ?? 0} />
          <Metric label="Gemma" value={knowledgeAcquisition?.gemma_completed ?? trainerStatus?.knowledge_acquisition?.gemma_completed ?? 0} />
          <Metric label="Brave" value={knowledgeAcquisition?.brave_completed ?? trainerStatus?.knowledge_acquisition?.brave_completed ?? 0} />
          <Metric label="Browser" value={knowledgeAcquisition?.browser_completed ?? trainerStatus?.knowledge_acquisition?.browser_completed ?? 0} />
        </div>
        <div className="knowledge-controls">
          <label>
            Mode
            <select value={knowledgeMode} onChange={(e) => setKnowledgeMode(e.target.value)}>
              <option value="gemma_brave">Gemma + Brave</option>
              <option value="all">Gemma + Brave + Browser</option>
              <option value="both">Gemma + Browser</option>
              <option value="gemma">Gemma</option>
              <option value="brave">Brave</option>
              <option value="browser">Browser</option>
            </select>
          </label>
          <label>
            Max
            <input type="number" min={1} max={10} value={knowledgeMaxTopics} onChange={(e) => setKnowledgeMaxTopics(Number(e.target.value))} />
          </label>
          <label>
            Batches
            <input type="number" min={1} max={5} value={knowledgePasses} onChange={(e) => setKnowledgePasses(Math.max(1, Math.min(5, Number(e.target.value) || 1)))} />
          </label>
          <label>
            Model
            <input value={knowledgeModel} onChange={(e) => setKnowledgeModel(e.target.value)} />
          </label>
          <button onClick={indexKnowledgeList} disabled={!approvalReady}>
            <Database size={15} /> Index List
          </button>
          <button onClick={tickKnowledgeAcquisition} disabled={!approvalReady}>
            <RefreshCw size={15} /> Acquire
          </button>
          <button onClick={accelerateLearning} disabled={!approvalReady || continuousMethods.length === 0}>
            <Rocket size={15} /> Accelerate
          </button>
        </div>
        {(knowledgeAcquisition?.recent_records ?? trainerStatus?.knowledge_acquisition?.recent_records ?? []).length > 0 && (
          <div className="codex-monitor">
            {(knowledgeAcquisition?.recent_records ?? trainerStatus?.knowledge_acquisition?.recent_records ?? []).slice(-5).reverse().map((record: any) => (
              <div className={record.status === "success" ? "good" : "warn"} key={`${record.topic_id}-${record.source_type}-${record.timestamp}`}>
                <strong>{record.source_type}</strong>
                <span>{record.topic_title} · {record.curriculum_primary} · {record.chars ?? 0} chars</span>
              </div>
            ))}
          </div>
        )}
        <div className="curriculum-grid">
          {(trainerStatus?.curriculum?.curricula ?? []).map((curriculum: any) => (
            <div key={curriculum.id}>
              <strong>{curriculum.label}</strong>
              <span>{trainerStatus?.curriculum?.label_counts?.[curriculum.id] ?? 0} records</span>
            </div>
          ))}
        </div>
        <div className="independence-meter">
          <div style={{ width: `${Math.max(2, Math.min(100, Number((independenceStatus?.independence_score ?? trainerStatus?.independence?.independence_score ?? 0) * 100)))}%` }} />
        </div>
        {(independenceStatus?.recommendations ?? trainerStatus?.independence?.recommendations ?? []).length > 0 && (
          <div className="codex-monitor">
            {(independenceStatus?.recommendations ?? trainerStatus?.independence?.recommendations ?? []).slice(0, 5).map((item: string) => (
              <div className="warn" key={item}>
                <strong>Gap</strong>
                <span>{item}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <PanelHeader title="Codex Registry" small />
      <div className="trainer-status">
        <Metric label="Callable" value={String(codexFunctions.length)} tone={codexFunctions.length > 0 ? "good" : "warn"} />
        <Metric label="Calls" value={codexMonitor?.total_calls ?? trainerStatus?.codex_registry?.monitor?.total_calls ?? 0} />
        <Metric label="Success" value={codexMonitor?.success_calls ?? trainerStatus?.codex_registry?.monitor?.success_calls ?? 0} tone="good" />
        <Metric label="Errors" value={codexMonitor?.error_calls ?? trainerStatus?.codex_registry?.monitor?.error_calls ?? 0} tone={(codexMonitor?.error_calls ?? trainerStatus?.codex_registry?.monitor?.error_calls ?? 0) ? "warn" : undefined} />
      </div>
      <div className="codex-controls">
        <label>
          Function
          <select value={selectedCodexFunction} onChange={(e) => setSelectedCodexFunction(e.target.value)}>
            {codexFunctions.length === 0 ? (
              <option value="">No callable functions</option>
            ) : (
              codexFunctions.map((fn: any) => (
                <option value={fn.name} key={fn.name}>
                  {fn.name}
                </option>
              ))
            )}
          </select>
        </label>
        <label>
          Args
          <input value={codexArgs} onChange={(e) => setCodexArgs(e.target.value)} />
        </label>
        <label>
          Kwargs
          <input value={codexKwargs} onChange={(e) => setCodexKwargs(e.target.value)} />
        </label>
        <button onClick={callCodexFunction} disabled={!approvalReady || !selectedCodexFunction}>
          <TerminalSquare size={15} /> Call
        </button>
        <button onClick={loadCodexFunctions}>
          <RefreshCw size={15} /> Refresh
        </button>
      </div>
      <div className="codex-list">
        {codexFunctions.slice(0, 8).map((fn: any) => (
          <span title={fn.signature} key={fn.name}>{fn.function}</span>
        ))}
      </div>
      {(codexMonitor?.recent_calls ?? trainerStatus?.codex_registry?.monitor?.recent_calls ?? []).length > 0 && (
        <div className="codex-monitor">
          {(codexMonitor?.recent_calls ?? trainerStatus?.codex_registry?.monitor?.recent_calls ?? []).slice(0, 5).map((call: any) => (
            <div className={call.status === "success" ? "good" : "warn"} key={`${call.timestamp}-${call.function}`}>
              <strong>{call.function}</strong>
              <span>{call.status} · {call.duration_ms}ms · {call.timestamp}</span>
            </div>
          ))}
        </div>
      )}
      {codexResult && <pre className="dataset-preview">{JSON.stringify(codexResult, null, 2)}</pre>}

      <PanelHeader title="Codex Agent" small />
      <div className="trainer-status">
        <Metric label="Agent" value={codexAgentStatus?.status ?? trainerStatus?.codex_agent?.status ?? "--"} tone={(codexAgentStatus?.status ?? trainerStatus?.codex_agent?.status) === "online" ? "good" : "warn"} />
        <Metric label="Memory" value={codexAgentStatus?.memory_count ?? trainerStatus?.codex_agent?.memory_count ?? 0} />
        <Metric label="Gaps" value={codexAgentStatus?.capability_gap_count ?? trainerStatus?.codex_agent?.capability_gap_count ?? 0} />
        <Metric label="Fake" value={String(codexAgentStatus?.fake_success ?? trainerStatus?.codex_agent?.fake_success ?? false)} tone={(codexAgentStatus?.fake_success ?? trainerStatus?.codex_agent?.fake_success) ? "warn" : "good"} />
      </div>
      <div className="codex-agent-controls">
        <label>
          Agent Prompt
          <textarea value={codexAgentPrompt} onChange={(e) => setCodexAgentPrompt(e.target.value)} rows={3} />
        </label>
        <label className="check-row">
          <input type="checkbox" checked={codexAgentExecute} onChange={(e) => setCodexAgentExecute(e.target.checked)} />
          Execute
        </label>
        <label className="check-row">
          <input type="checkbox" checked={codexAgentAutoExtend} onChange={(e) => setCodexAgentAutoExtend(e.target.checked)} />
          Auto-gap
        </label>
        <button onClick={runCodexAgent}>
          <Bot size={15} /> Agent Run
        </button>
        <button onClick={loadCodexAgentStatus}>
          <RefreshCw size={15} /> Status
        </button>
      </div>
      {codexAgentResult && <pre className="dataset-preview">{JSON.stringify(codexAgentResult, null, 2)}</pre>}
      {(codexAgentStatus?.recent_events ?? trainerStatus?.codex_agent?.recent_events ?? []).length > 0 && (
        <div className="codex-monitor">
          {(codexAgentStatus?.recent_events ?? trainerStatus?.codex_agent?.recent_events ?? []).slice(0, 5).map((event: any) => (
            <div className={event.status === "success" || event.status === "opened" || event.status === "requires_frontend" ? "good" : "warn"} key={`${event.timestamp}-${event.action_id}`}>
              <strong>{event.tool}</strong>
              <span>{event.status} · {event.timestamp}</span>
            </div>
          ))}
        </div>
      )}

      <PanelHeader title="Jobs" small />
      <div className="job-list">
        {trainerJobs.length === 0 ? (
          <div className="empty-state">No jobs yet. Create one above.</div>
        ) : (
          trainerJobs.map((job: any) => (
            <div className="job-item" key={job.job_id}>
              <div>
                <strong>{job.job_id.slice(0, 8)}</strong>
                <span>{job.state}</span>
              </div>
              <div>
                <span>{job.base_model}</span>
                <span>{job.method}</span>
              </div>
              {job.exported_artifacts?.blue_brain_model?.metadata?.accuracy && (
                <div>
                  <span>accuracy</span>
                  <strong>{Number(job.exported_artifacts.blue_brain_model.metadata.accuracy).toFixed(4)}</strong>
                </div>
              )}
              <div className="job-actions">
                <button onClick={() => startJob(job.job_id)} disabled={!approvalReady || ["training", "online"].includes(job.state)}>
                  <Rocket size={15} /> Start
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      <PanelHeader title="Dataset" small />
      <button onClick={previewDataset}>Preview Dataset</button>
      {datasetPreview && (
        <pre className="dataset-preview">{JSON.stringify(datasetPreview, null, 2)}</pre>
      )}
    </section>
  );
}

function ProjectionPlot({ points }: { points: any[] }) {
  const width = 420;
  const height = 180;
  const safePoints = Array.isArray(points) ? points.slice(0, 100) : [];
  const xs = safePoints.map((point) => Number(point.x));
  const ys = safePoints.map((point) => Number(point.y));
  const minX = xs.length ? Math.min(...xs) : -1;
  const maxX = xs.length ? Math.max(...xs) : 1;
  const minY = ys.length ? Math.min(...ys) : -1;
  const maxY = ys.length ? Math.max(...ys) : 1;
  const scaleX = (value: number) => 18 + ((value - minX) / Math.max(maxX - minX, 0.0001)) * (width - 36);
  const scaleY = (value: number) => height - 18 - ((value - minY) / Math.max(maxY - minY, 0.0001)) * (height - 36);

  return (
    <div className="projection-plot">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Blue Brain 2D projection">
        <rect x="0" y="0" width={width} height={height} rx="6" />
        {safePoints.map((point, index) => (
          <circle
            key={`${point.x}-${point.y}-${index}`}
            cx={scaleX(Number(point.x))}
            cy={scaleY(Number(point.y))}
            r="3"
            className={Number(point.label) === 1 ? "sync" : "async"}
          />
        ))}
      </svg>
    </div>
  );
}

function ContextPanel({ api, contextData, approval, approvalReady }: { api: any; contextData: any; approval: string; approvalReady: boolean }) {
  const [fileTree, setFileTree] = useState<any>(null);
  const [changedFiles, setChangedFiles] = useState<any>(null);
  const [localContext, setLocalContext] = useState<any>(null);
  const [bridgeContext, setBridgeContext] = useState<any>(null);
  const [vpsStatus, setVpsStatus] = useState<any>(null);
  const [vpsResult, setVpsResult] = useState<any>(null);
  const [vpsBusy, setVpsBusy] = useState(false);
  const [chromaSyncStatus, setChromaSyncStatus] = useState<any>(null);
  const [chromaSyncResult, setChromaSyncResult] = useState<any>(null);
  const [chromaSyncBusy, setChromaSyncBusy] = useState(false);
  const [syncSourcePath, setSyncSourcePath] = useState("");
  const [syncRemotePath, setSyncRemotePath] = useState("");

  const currentBridgeContext = bridgeContext ?? (contextData?.via_bridge ? contextData : null);
  const currentLocalContext = localContext ?? (!contextData?.via_bridge ? contextData : null);

  useEffect(() => {
    loadContextSummaries().catch(() => undefined);
    loadVpsStatus().catch(() => undefined);
  }, []);

  async function loadContextSummaries() {
    const [local, bridge] = await Promise.allSettled([
      api("/context/summary?source=local"),
      api("/context/summary?source=bridge"),
    ]);
    if (local.status === "fulfilled") setLocalContext(local.value);
    if (bridge.status === "fulfilled") setBridgeContext(bridge.value);
  }

  async function loadFileTree() {
    try {
      const data = await api("/context/file_tree?max_depth=2&limit=100&source=local");
      setFileTree(data);
    } catch (error) {
      console.error("Failed to load file tree:", error);
    }
  }

  async function loadChangedFiles() {
    try {
      const data = await api("/context/changed_files?limit=20&source=local");
      setChangedFiles(data);
    } catch (error) {
      console.error("Failed to load changed files:", error);
    }
  }

  async function loadVpsStatus() {
    const data = await api("/agent/tool", {
      method: "POST",
      body: JSON.stringify({ tool_name: "vps_status", args: {} }),
    });
    setVpsStatus(data);
    return data;
  }

  async function runVpsTool(toolName: "vps_login_check" | "vps_sync_preview" | "vps_sync_execute" | "vps_ui_sync_preview" | "vps_ui_sync_execute") {
    setVpsBusy(true);
    try {
      const args: Record<string, unknown> = {};
      if (toolName === "vps_sync_preview" || toolName === "vps_sync_execute") {
        args.source_path = syncSourcePath;
        args.remote_path = syncRemotePath;
        args.timeout_seconds = 120;
      }
      if (toolName === "vps_ui_sync_preview" || toolName === "vps_ui_sync_execute") {
        args.remote_path = syncRemotePath;
        args.timeout_seconds = 180;
      }
      if (toolName === "vps_sync_execute" || toolName === "vps_ui_sync_execute") args.approval = approval;
      if (toolName === "vps_ui_sync_execute") args.build_first = true;
      const data = await api("/agent/tool", {
        method: "POST",
        body: JSON.stringify({ tool_name: toolName, args }),
        timeoutMs: toolName === "vps_ui_sync_execute" ? 300000 : 180000,
      });
      setVpsResult(data);
      await loadVpsStatus();
    } finally {
      setVpsBusy(false);
    }
  }

  async function loadChromaSyncStatus() {
    const data = await api("/agent/tool", {
      method: "POST",
      body: JSON.stringify({ tool_name: "chroma_sync_status", args: { timeout_seconds: 45 } }),
      timeoutMs: 90000,
    });
    setChromaSyncStatus(data);
    return data;
  }

  async function runChromaSyncTool(toolName: "chroma_sync_preview" | "chroma_sync_execute") {
    setChromaSyncBusy(true);
    try {
      const args: Record<string, unknown> = { timeout_seconds: toolName === "chroma_sync_execute" ? 300 : 120 };
      if (toolName === "chroma_sync_execute") args.approval = approval;
      const data = await api("/agent/tool", {
        method: "POST",
        body: JSON.stringify({ tool_name: toolName, args }),
        timeoutMs: toolName === "chroma_sync_execute" ? 420000 : 180000,
      });
      setChromaSyncResult(data);
      await loadChromaSyncStatus();
    } finally {
      setChromaSyncBusy(false);
    }
  }

  return (
    <section className="panel context-panel" style={{ gridColumn: "1 / -1", minHeight: "400px" }}>
      <PanelHeader title="Project Context" />
      <div className="context-toolbar">
        <button onClick={loadContextSummaries}><RefreshCw size={15} /> Refresh Context</button>
        <span>{currentBridgeContext?.via_bridge ? "Bridge context online" : "Bridge context not active"}</span>
      </div>
      <div className="context-compare">
        <ContextSummaryCard title="Local Backend" data={currentLocalContext} />
        <ContextSummaryCard title="Host / Bridge" data={currentBridgeContext} />
      </div>

      <PanelHeader title="VPS Sync" small />
      <div className="vps-panel">
        <div className="context-summary">
          <Fact label="Adapter" value={vpsStatus?.result?.status ?? "--"} state={vpsStatus?.result?.status === "ready" ? "good" : "warn"} />
          <Fact label="SSH Alias" value={vpsStatus?.result?.profile?.ssh_host_alias || "not configured"} />
          <Fact label="Remote Root" value={vpsStatus?.result?.remote_target ?? "/var/www/philip-wintrip.nl/html/Ouroboros/"} />
          <Fact label="Env File" value={vpsStatus?.result?.env_file?.exists ? "present" : "missing"} state={vpsStatus?.result?.env_file?.exists ? "good" : "warn"} />
        </div>
        <div className="vps-reason">{vpsStatus?.result?.reason ?? vpsStatus?.result?.setup_hint ?? "VPS status nog niet geladen."}</div>
        <div className="vps-inputs">
          <label>
            Source path
            <input value={syncSourcePath} onChange={(event) => setSyncSourcePath(event.target.value)} placeholder="blank = WintripAI workspace" />
          </label>
          <label>
            Remote child path
            <input value={syncRemotePath} onChange={(event) => setSyncRemotePath(event.target.value)} placeholder="blank = fixed Ouroboros root" />
          </label>
        </div>
        <div className="vps-actions">
          <button onClick={loadVpsStatus} disabled={vpsBusy}><RefreshCw size={15} /> Status</button>
          <button onClick={() => runVpsTool("vps_login_check")} disabled={vpsBusy}><KeyRound size={15} /> Login Check</button>
          <button onClick={() => runVpsTool("vps_sync_preview")} disabled={vpsBusy}><ShieldCheck size={15} /> Dry-run Sync</button>
          <button onClick={() => runVpsTool("vps_sync_execute")} disabled={vpsBusy || !approvalReady}><Rocket size={15} /> Execute Sync</button>
        </div>
        <div className="vps-actions secondary">
          <button onClick={() => runVpsTool("vps_ui_sync_preview")} disabled={vpsBusy}><ShieldCheck size={15} /> UI Dry-run</button>
          <button onClick={() => runVpsTool("vps_ui_sync_execute")} disabled={vpsBusy || !approvalReady}><Rocket size={15} /> UI Execute</button>
          <span>UI Execute bouwt eerst <strong>ouroboros_cockpit/dist</strong> en zet alleen die artifact op de VPS webroot.</span>
        </div>
        {!approvalReady && <div className="vps-reason">Voor echte sync moet het Akkoord-veld exact op Akkoord staan. Dry-run muteert niets.</div>}
        {vpsResult && <pre className="vps-result">{JSON.stringify(vpsResult, null, 2)}</pre>}
      </div>

      <PanelHeader title="Chroma Merge" small />
      <div className="vps-panel">
        <div className="context-summary">
          <Fact label="Sync" value={chromaSyncStatus?.result?.status ?? "--"} state={chromaSyncStatus?.result?.status === "ready" || chromaSyncStatus?.status === "success" ? "good" : "warn"} />
          <Fact label="Local Mode" value={chromaSyncStatus?.result?.local?.mode ?? "--"} />
          <Fact label="Remote Mode" value={chromaSyncStatus?.result?.remote?.mode ?? "--"} />
          <Fact label="Collections" value={`${chromaSyncStatus?.result?.config?.collections?.length ?? 0}`} />
        </div>
        <div className="vps-reason">Preview vergelijkt IDs/content-hashes. Merge verplaatst wel geheugenrecords over SSH, maar de tooloutput toont alleen tellingen.</div>
        <div className="vps-actions">
          <button onClick={loadChromaSyncStatus} disabled={chromaSyncBusy}><Database size={15} /> Chroma Status</button>
          <button onClick={() => runChromaSyncTool("chroma_sync_preview")} disabled={chromaSyncBusy}><ShieldCheck size={15} /> Chroma Preview</button>
          <button onClick={() => runChromaSyncTool("chroma_sync_execute")} disabled={chromaSyncBusy || !approvalReady}><Rocket size={15} /> Chroma Merge</button>
        </div>
        {!approvalReady && <div className="vps-reason">Voor Chroma Merge moet het Akkoord-veld exact op Akkoord staan.</div>}
        {chromaSyncResult && <pre className="vps-result">{JSON.stringify(chromaSyncResult, null, 2)}</pre>}
      </div>

      <PanelHeader title="File Tree" small />
      <button onClick={loadFileTree}>Load File Tree</button>
      {fileTree && (
        <pre className="file-tree">{JSON.stringify(fileTree, null, 2)}</pre>
      )}

      <PanelHeader title="Changed Files" small />
      <button onClick={loadChangedFiles}>Load Changed Files</button>
      {changedFiles && (
        <pre className="changed-files">{JSON.stringify(changedFiles, null, 2)}</pre>
      )}
    </section>
  );
}

function ContextSummaryCard({ title, data }: { title: string; data: any }) {
  const source = data?.resolved_source ?? (data?.via_bridge ? "bridge" : data ? "local" : "--");
  const bridgeFallback = data?.bridge_unavailable ? "host bridge fallback" : source;
  return (
    <div className="context-source-card">
      <h3>{title}</h3>
      <div className="context-summary">
        <Fact label="Source" value={bridgeFallback} state={source === "bridge" ? "good" : data?.bridge_unavailable ? "warn" : undefined} />
        <Fact label="Root" value={data?.project_root ?? data?.root ?? "--"} />
        <Fact label="Total Files" value={data?.structure?.total_files ?? "--"} />
        <Fact label="Changed Files" value={data?.changed_files?.count ?? "--"} />
        <Fact label="Test Files" value={data?.test_files?.count ?? "--"} />
      </div>
      {data?.reason && <div className="vps-reason">{data.reason}</div>}
    </div>
  );
}

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
  agentTool: "/agent/tool",
  apiKeys: "/api/cockpit/api-keys",
  worldAgentStatus: "/api/world-agent/status",
  worldAgentGrok: "/api/world-agent/grok/ask",
  worldAgentSearch: "/api/world-agent/memory/search",
  approvalPhrase: "Akkoord",
} as const;

export type BackendConfig = {
  backend_url: string;
  approval_phrase: string;
  reachable?: boolean;
  status?: string;
  message?: string;
};

export type Health = {
  status?: string;
  agent?: string;
  memories?: number;
  training?: string;
};

export type ProviderDetails = {
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
};

export type ApiKeyStatusPayload = Record<string, { configured?: boolean; source?: string; masked?: string }>;

export type CockpitConfig = {
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
  slash_agents?: Record<string, unknown>;
};

export type OuroborosStatus = {
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

export type LoopStatus = {
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

export type AgentJob = {
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

export type AgentJobEvent = {
  index?: number;
  ts?: string;
  type?: string;
  data?: Record<string, unknown>;
};

export type ExternalCapability = {
  status?: string;
  exists?: boolean;
  root?: string;
  entrypoints?: Array<{ kind?: string; label?: string; path?: string }>;
  packages?: Array<{ kind?: string; label?: string; path?: string }>;
  agentic_patterns?: Array<{ id?: string; label?: string; value?: string; source?: string }>;
  role_taxonomy?: Array<{ id?: string; label?: string; value?: string; source?: string }>;
  safe_notes?: string[];
};

export type ExternalCapabilitiesStatus = {
  status?: string;
  via_bridge?: boolean;
  capabilities?: Record<string, ExternalCapability>;
  tool_schemas?: Array<{ function?: { name?: string } }>;
};

export type ProviderChoice = {
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

export type OperationEvent = {
  id: string;
  ts: number;
  message: string;
  status?: string;
  error?: string;
};

export type ExternalOpenResult = {
  opened: boolean;
  method?: string;
  error?: string;
  reservedWindow?: Window | null;
};

export type LivingStatus = {
  status?: string;
  mode?: string;
  tick_count?: number;
  tick_count_24h?: number;
  signal_summary?: {
    attention_markers?: Record<string, unknown>;
    next_question?: string;
    agent_runtime?: Record<string, unknown>;
  };
  last_action?: string;
  last_output_at?: string;
  last_tick_at?: string;
};

export type WorldStatus = {
  status?: string;
  browser?: string;
  x11?: string;
  files?: Record<string, unknown>;
  internet?: string;
  memory_available?: boolean;
};

export type NexusStatus = {
  status?: string;
  active_jobs?: number;
  coherence_score?: number;
  operational?: {
    status?: string;
    events_ingested?: number;
    reason?: string;
  };
};

export type SubsystemStatus = {
  status?: string;
  version?: string;
  runtime_reachable?: boolean;
  capabilities?: Record<string, unknown>;
};

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  Hammer,
  Layers,
  Pause,
  Play,
  Rocket,
  RefreshCw,
  Send,
  ShieldCheck,
  TerminalSquare,
  TestTube2,
  XCircle,
} from "lucide-react";
import "@xterm/xterm/css/xterm.css";

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
  approvalPhrase: "Akkoord",
} as const;

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
    raw_local?: string[];
    ignored_disallowed_models?: string[];
    multi_api?: Record<string, string[]>;
  };
  required_approval_phrase?: string;
  approval?: { required_phrase?: string; case_sensitive?: boolean };
  api_keys?: ApiKeyStatusPayload;
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
  ollama: "Ouroboros Local",
  openai: "ChatGPT Pro",
  anthropic: "Claude Opus",
  xai: "Grok",
  mistral: "Mistral",
  google: "Gemini",
  gemini: "Gemini Legacy",
  claude: "Claude Legacy",
  chatgpt: "ChatGPT Legacy",
  groq: "Groq Legacy",
};

const CANONICAL_PROVIDERS = ["ollama", "openai", "anthropic", "xai", "mistral", "google"];

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
  const [events, setEvents] = useState<OperationEvent[]>([]);
  const [apiKeyInputs, setApiKeyInputs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [activeTab, setActiveTab] = useState<"main" | "trainer" | "context">("main");
  const [trainerStatus, setTrainerStatus] = useState<any>(null);
  const [trainerJobs, setTrainerJobs] = useState<any[]>([]);
  const [contextData, setContextData] = useState<any>(null);
  const terminalHost = useRef<HTMLDivElement | null>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const providerInitialized = useRef(false);

  const api = useCallback(
    async <T,>(path: string, init?: RequestInit): Promise<T> => {
      const response = await fetch(`${backend}${path}`, {
        ...init,
        headers: {
          "Content-Type": "application/json",
          ...(init?.headers ?? {}),
        },
      });
      const text = await response.text();
      const data = text ? JSON.parse(text) : {};
      if (!response.ok) {
        throw new Error(data.detail ?? data.error ?? response.statusText);
      }
      return data as T;
    },
    [backend],
  );

  const providerChoices = useMemo(() => buildProviderChoices(config, status), [config, status]);
  const selectedProvider = providerChoices.find((item) => item.id === provider) ?? providerChoices[0];
  const selectedModels = selectedProvider?.models.length ? selectedProvider.models : [model].filter(Boolean);
  const approvalReady = approval === approvalPhrase;
  const canCallSelectedProvider = selectedProvider?.enabled ?? false;

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

  const refresh = useCallback(async () => {
    const [healthData, configData, statusData] = await Promise.all([
      api<Health>(OUROBOROS_BACKEND_CONTRACT.health),
      api<CockpitConfig>("/api/cockpit/config"),
      api<OuroborosStatus>(OUROBOROS_BACKEND_CONTRACT.modelStatus),
    ]);
    setHealth(healthData);
    setConfig(configData);
    setStatus(statusData);
    const phrase = configData.required_approval_phrase ?? configData.approval?.required_phrase;
    if (phrase) setApprovalPhrase(phrase);
    try {
      setLoop(await api<LoopStatus>(OUROBOROS_BACKEND_CONTRACT.loopStatus));
    } catch {
      setLoop((previous) => ({ ...previous, status: previous.status || "idle" }));
    }
    // Refresh trainer and context data if on those tabs
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
  }, [api, activeTab]);

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
    return () => window.removeEventListener("resize", onResize);
  }, [backend]);

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
    if (providerInitialized.current || providerChoices.length === 0) return;
    const local = providerChoices.find((item) => item.id === "ollama" && item.enabled) ?? providerChoices.find((item) => item.enabled);
    if (!local) return;
    providerInitialized.current = true;
    setProvider(local.id);
    setModel(status.model?.active_base || local.defaultModel || local.models[0] || "llama3.2:latest");
  }, [providerChoices, status.model?.active_base]);

  function onProviderChange(nextProvider: string) {
    const option = providerChoices.find((item) => item.id === nextProvider) ?? providerChoices[0];
    if (!option) return;
    setProvider(option.id);
    setModel(option.defaultModel || option.models[0] || "");
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

  async function sendChat() {
    setChatOutput("");
    const data = await perform("Agent chat", () =>
      api<Record<string, unknown>>(OUROBOROS_BACKEND_CONTRACT.cockpitChat, {
        method: "POST",
        body: JSON.stringify({ provider, model, prompt, approval, include_tools: true }),
      }),
    );
    if (data) setChatOutput(renderResponse(data));
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

  const records = status.records ?? {};
  const learning = status.learning_11d?.chromadb ?? {};
  const createFlow = status.model?.create_flow;
  const loopResult = loop.last_result ?? loop.last_step ?? loop.loop ?? {};
  const roleEntries = Object.entries(status.role_models ?? {});
  const toolCount = status.roo_adapter?.local_python_adapters?.length ?? 0;
  const externalProviderChoices = providerChoices.filter((item) => item.kind === "external");
  const apiKeyStatus = config.api_keys?.providers ?? {};

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Bot size={22} />
          <div>
            <h1>Ouroboros</h1>
            <span>{health.status ?? "unknown"} / {records.total_count ?? health.memories ?? 0} records</span>
          </div>
        </div>

        <div className="tab-nav">
          <button className={activeTab === "main" ? "active" : ""} onClick={() => setActiveTab("main")}>
            <Cpu size={16} /> Main
          </button>
          <button className={activeTab === "trainer" ? "active" : ""} onClick={() => setActiveTab("trainer")}>
            <Layers size={16} /> Trainer
          </button>
          <button className={activeTab === "context" ? "active" : ""} onClick={() => setActiveTab("context")}>
            <FolderTree size={16} /> Context
          </button>
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
          <StatusPill icon={<Cpu size={16} />} label="Ollama" value={status.model?.ollama_online ? "online" : "offline"} ok={!!status.model?.ollama_online} />
          <StatusPill icon={<Bot size={16} />} label="Ouroboros" value={status.model?.online ? "created" : "offline"} ok={!!status.model?.online} />
          <StatusPill icon={<Hammer size={16} />} label="Pipeline" value={status.self_modification_pipeline?.status ?? "not configured"} ok={status.self_modification_pipeline?.status === "online"} />
          <StatusPill icon={<Database size={16} />} label="11D" value={`${learning.total_count ?? records.total_count ?? 0}`} ok={!!learning.available} />
          <StatusPill icon={<ShieldCheck size={16} />} label="Approval" value={approvalReady ? "approved" : "locked"} ok={approvalReady} />
        </header>

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

        <section className="prompt-pane">
          <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} />
          <button onClick={sendChat} disabled={busy || !prompt.trim() || !canCallSelectedProvider}>
            <Send size={15} /> Send
          </button>
        </section>

        {activeTab === "main" && (
          <section className="cockpit-grid">
            <section className="panel primary-panel">
              <PanelHeader title="Mission Control" />
              <div className="action-summary">
                <div>
                  <span>Next</span>
                  <strong>{status.next_action ?? createFlow?.next_action ?? "Ready"}</strong>
                </div>
                <div>
                  <span>Base</span>
                  <strong>{status.model?.active_base ?? model}</strong>
                </div>
                <div>
                  <span>Iteration</span>
                  <strong>{loop.iteration ?? 0}</strong>
                </div>
              </div>
              <div className="feed">
                {events.length === 0 ? (
                  <div className="empty-state">Nog geen cockpitactie in deze sessie. Kies een lokale motor en start een concrete stap.</div>
                ) : (
                  events.map((event) => <EventItem event={event} key={event.id} />)
                )}
              </div>
            </section>

            <section className="panel">
              <PanelHeader title="Runtime" />
              <div className="fact-list">
                <Fact label="Ouroboros model" value={status.model?.name ?? "ouroboros"} state={status.model?.status} />
                <Fact label="Create flow" value={createFlow?.status ?? "idle"} state={createFlow?.created ? "created" : "pending"} />
                <Fact label="Local models" value={`${status.ollama?.count ?? status.model?.available_bases?.length ?? 0}`} />
                <Fact label="Roo tools" value={`${toolCount}`} state={status.roo_adapter?.status} />
                <Fact label="Main memory" value={`${records.main_collection_count ?? 0}`} />
                <Fact label="Training memory" value={`${records.training_collection_count ?? 0}`} />
              </div>
              <PanelHeader title="API Keys" small />
              <div className="key-list">
                {externalProviderChoices.map((item) => {
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
              <details>
                <summary>Raw status</summary>
                <pre>{JSON.stringify(status, null, 2)}</pre>
              </details>
            </section>

            <section className="panel">
              <PanelHeader title="Agent Roles" />
              <div className="role-list">
                {roleEntries.length ? roleEntries.map(([role, details]) => (
                  <div className="role-row" key={role}>
                    <span>{role}</span>
                    <strong>{details.model ?? "--"}</strong>
                    {details.available ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                  </div>
                )) : <div className="empty-state">Rolrouter nog niet beschikbaar.</div>}
              </div>
              <PanelHeader title="Last Response" small />
              <pre className="response-box">{chatOutput || summarizeResult(loopResult) || "Nog geen response."}</pre>
            </section>
          </section>
        )}

        {activeTab === "trainer" && (
          <TrainerPanel api={api} trainerStatus={trainerStatus} trainerJobs={trainerJobs} approval={approval} approvalReady={approvalReady} refresh={refresh} />
        )}

        {activeTab === "context" && (
          <ContextPanel api={api} contextData={contextData} />
        )}

        {activeTab === "main" && (
          <section className="terminal-panel">
            <div className="terminal-bar">
              <TerminalSquare size={16} />
              <input value={command} onChange={(event) => setCommand(event.target.value)} onKeyDown={(event) => {
                if (event.key === "Enter") runCommand();
              }} />
              <input className="test-selector" value={testSelector} onChange={(event) => setTestSelector(event.target.value)} />
              <button onClick={runCommand} disabled={busy || !command.trim() || !approvalReady}>
                Run
              </button>
            </div>
            <div className="terminal-host" ref={terminalHost} />
          </section>
        )}
      </section>
    </main>
  );
}

function buildProviderChoices(config: CockpitConfig, status: OuroborosStatus): ProviderChoice[] {
  const options = config.provider_options ?? config.providers ?? {};
  const localModels = config.available_models?.ollama ?? config.models ?? status.model?.available_bases ?? [];
  const choices: ProviderChoice[] = CANONICAL_PROVIDERS.map((id) => {
    const details = options[id] ?? { provider: id };
    const models = id === "ollama" ? localModels : details.models ?? config.available_models?.multi_api?.[id] ?? [];
    const enabled = id === "ollama" ? models.length > 0 : !!details.enabled;
    return {
      id,
      label: PROVIDER_LABELS[id] ?? details.label ?? id,
      kind: id === "ollama" ? "local" : "external",
      enabled,
      status: details.status ?? (enabled ? "online" : "disabled"),
      models,
      defaultModel: (id === "ollama" ? status.model?.active_base : details.default_model) ?? details.model ?? models[0] ?? "",
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

function summarizeResult(raw: unknown): string {
  if (!raw || typeof raw !== "object") return raw ? String(raw) : "";
  const data = raw as Record<string, unknown>;
  const parts = [
    data.status ? `status=${data.status}` : "",
    data.provider ? `provider=${data.provider}` : "",
    data.model ? `model=${data.model}` : "",
    data.next_action ? `next=${data.next_action}` : "",
    data.response ? String(data.response) : "",
    data.message ? String(data.message) : "",
    data.reason ? String(data.reason) : "",
    data.stderr ? `stderr: ${String(data.stderr).trim()}` : "",
    data.stdout ? `stdout: ${String(data.stdout).trim()}` : "",
    data.error ? `error: ${String(data.error).trim()}` : "",
  ].filter(Boolean);
  return parts.join("\n").slice(0, 4000);
}

function renderResponse(raw: unknown): string {
  const summary = summarizeResult(raw);
  if (summary) return summary;
  return JSON.stringify(raw, null, 2);
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

function PanelHeader({ title, small = false }: { title: string; small?: boolean }) {
  return <h2 className={small ? "small-heading" : ""}>{title}</h2>;
}

function Fact({ label, value, state }: { label: string; value: string; state?: string }) {
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
  const [knowledgeMode, setKnowledgeMode] = useState("both");
  const [knowledgeMaxTopics, setKnowledgeMaxTopics] = useState(2);
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
    try {
      const data = await api("/trainer/jobs", {
        method: "POST",
        body: JSON.stringify({
          base_model: isBlueBrain ? baseModel || "blue-brain-random-forest" : baseModel,
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
      console.error("Failed to create job:", error);
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
    try {
      const data = await api("/trainer/continuous/start", {
        method: "POST",
        body: JSON.stringify({
          approval,
          methods: continuousMethods,
          interval_seconds: continuousInterval,
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
        const opened = window.open(data.frontend_action.url, data.frontend_action.target ?? "_blank", "noopener,noreferrer");
        await api("/trainer/codex/agent/frontend-event", {
          method: "POST",
          body: JSON.stringify({
            action_id: data.frontend_action.action_id,
            status: opened ? "opened" : "blocked_by_browser",
            detail: opened ? "window.open returned a Window handle" : "Browser blocked the popup or no window handle was returned",
            payload: { url: data.frontend_action.url },
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
          <Metric label="DHCP" value={trainerStatus?.streaming_consciousness?.last_event?.network?.dhcp ?? "--"} />
          <Metric label="IP" value={trainerStatus?.streaming_consciousness?.last_event?.network?.local_ip ?? "--"} />
          <Metric label="V avg" value={trainerStatus?.streaming_consciousness?.last_event?.elec?.v_avg ? `${Number(trainerStatus.streaming_consciousness.last_event.elec.v_avg).toFixed(1)}mV` : "--"} />
          <Metric label="Quantum" value={trainerStatus?.streaming_consciousness?.last_event?.quantum?.expectation !== undefined ? Number(trainerStatus.streaming_consciousness.last_event.quantum.expectation).toFixed(4) : "--"} tone={trainerStatus?.streaming_consciousness?.quantum_collapse?.enabled ? "good" : undefined} />
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
          <Metric label="Browser" value={knowledgeAcquisition?.browser_completed ?? trainerStatus?.knowledge_acquisition?.browser_completed ?? 0} />
        </div>
        <div className="knowledge-controls">
          <label>
            Mode
            <select value={knowledgeMode} onChange={(e) => setKnowledgeMode(e.target.value)}>
              <option value="both">Gemma + Browser</option>
              <option value="gemma">Gemma</option>
              <option value="browser">Browser</option>
            </select>
          </label>
          <label>
            Max
            <input type="number" min={1} max={10} value={knowledgeMaxTopics} onChange={(e) => setKnowledgeMaxTopics(Number(e.target.value))} />
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

function ContextPanel({ api, contextData }: { api: any; contextData: any }) {
  const [fileTree, setFileTree] = useState<any>(null);
  const [changedFiles, setChangedFiles] = useState<any>(null);

  async function loadFileTree() {
    try {
      const data = await api("/context/file_tree?max_depth=2&limit=100");
      setFileTree(data);
    } catch (error) {
      console.error("Failed to load file tree:", error);
    }
  }

  async function loadChangedFiles() {
    try {
      const data = await api("/context/changed_files?limit=20");
      setChangedFiles(data);
    } catch (error) {
      console.error("Failed to load changed files:", error);
    }
  }

  return (
    <section className="panel context-panel" style={{ gridColumn: "1 / -1", minHeight: "400px" }}>
      <PanelHeader title="Project Context" />
      <div className="context-summary">
        <Fact label="Total Files" value={contextData?.structure?.total_files ?? "--"} />
        <Fact label="Changed Files" value={contextData?.changed_files?.count ?? "--"} />
        <Fact label="Test Files" value={contextData?.test_files?.count ?? "--"} />
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

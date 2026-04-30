import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import {
  Bot,
  BrainCircuit,
  CheckCircle2,
  CircleStop,
  Cpu,
  Database,
  Hammer,
  Pause,
  Play,
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
  }, [api]);

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

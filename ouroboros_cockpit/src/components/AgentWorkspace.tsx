import {
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  CirclePlay,
  Clock,
  Database,
  FileCode2,
  Layers,
  Loader2,
  PauseCircle,
  RefreshCw,
  Send,
  ShieldAlert,
  StopCircle,
  Wrench,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  AgenticEvent,
  AgenticEventsResponse,
  AgenticSessionSnapshot,
  AgenticSessionsResponse,
} from "../types";

type AgentWorkspaceProps = {
  backend: string;
  approvalPhrase: string;
  approvalReady: boolean;
  approvalValue: string;
  provider: string;
  model: string;
  busy: boolean;
  defaultPrompt?: string;
  onSubmit: (payload: {
    prompt: string;
    planMode: "act" | "plan";
    sessionId: string;
  }) => Promise<{ sessionId?: string } | void>;
  onRequestApproval: () => void;
};

type EventTypeMeta = {
  label: string;
  tone: "neutral" | "good" | "warn" | "block" | "info";
  icon: JSX.Element;
};

const EVENT_META: Record<string, EventTypeMeta> = {
  session_started: { label: "Sessie gestart", tone: "info", icon: <CirclePlay size={14} /> },
  plan_built: { label: "Plan opgesteld", tone: "info", icon: <Layers size={14} /> },
  tool_planned: { label: "Tool gepland", tone: "neutral", icon: <Wrench size={14} /> },
  tool_validated: { label: "Validatie", tone: "neutral", icon: <CheckCircle2 size={14} /> },
  tool_awaiting_approval: { label: "Wacht op Akkoord", tone: "warn", icon: <ShieldAlert size={14} /> },
  tool_running: { label: "Tool actief", tone: "info", icon: <Loader2 size={14} /> },
  tool_completed: { label: "Tool klaar", tone: "good", icon: <CheckCircle2 size={14} /> },
  tool_blocked: { label: "Tool geblokkeerd", tone: "block", icon: <XCircle size={14} /> },
  tool_failed: { label: "Tool faalde", tone: "block", icon: <AlertTriangle size={14} /> },
  loop_warning: { label: "Loop waarschuwing", tone: "warn", icon: <AlertTriangle size={14} /> },
  loop_blocked: { label: "Loop geblokkeerd", tone: "block", icon: <ShieldAlert size={14} /> },
  memory_write: { label: "Memory geschreven", tone: "info", icon: <Database size={14} /> },
  session_completed: { label: "Sessie klaar", tone: "good", icon: <CheckCircle2 size={14} /> },
  session_failed: { label: "Sessie faalde", tone: "block", icon: <AlertTriangle size={14} /> },
  session_cancelled: { label: "Sessie geannuleerd", tone: "warn", icon: <StopCircle size={14} /> },
  checkpoint_recorded: { label: "Checkpoint", tone: "info", icon: <FileCode2 size={14} /> },
};

const TOOL_SUMMARY_KEYS: Array<{ key: keyof NonNullable<AgenticSessionSnapshot["tool_summary"]>; label: string; tone: EventTypeMeta["tone"] }> = [
  { key: "planned", label: "plan", tone: "neutral" },
  { key: "running", label: "loop", tone: "info" },
  { key: "completed", label: "klaar", tone: "good" },
  { key: "blocked", label: "blocked", tone: "block" },
  { key: "failed", label: "fail", tone: "warn" },
];

function relativeTime(iso?: string | null): string {
  if (!iso) return "--";
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return iso;
  const delta = (Date.now() - ts) / 1000;
  if (delta < 5) return "net nu";
  if (delta < 60) return `${Math.round(delta)}s`;
  if (delta < 3600) return `${Math.round(delta / 60)}m`;
  if (delta < 86400) return `${Math.round(delta / 3600)}u`;
  return `${Math.round(delta / 86400)}d`;
}

function statusTone(status?: string): EventTypeMeta["tone"] {
  const value = (status || "").toLowerCase();
  if (["success", "completed", "stored", "opened"].includes(value)) return "good";
  if (["running", "planned", "info", "online", "rate_limited", "skipped"].includes(value)) return "info";
  if (["blocked", "approval_required", "configuration_required"].includes(value)) return "block";
  if (["failed", "error", "rejected", "unknown", "unavailable"].includes(value)) return "warn";
  return "neutral";
}

function classNamesForTone(tone: EventTypeMeta["tone"]): string {
  switch (tone) {
    case "good":
      return "agent-tone-good";
    case "warn":
      return "agent-tone-warn";
    case "block":
      return "agent-tone-block";
    case "info":
      return "agent-tone-info";
    default:
      return "agent-tone-neutral";
  }
}

function safeJson(value: unknown, max = 280): string {
  if (value == null) return "";
  try {
    const text = typeof value === "string" ? value : JSON.stringify(value, null, 0);
    return text.length > max ? `${text.slice(0, max)}…` : text;
  } catch {
    return String(value).slice(0, max);
  }
}

export function AgentWorkspace(props: AgentWorkspaceProps) {
  const {
    backend,
    approvalPhrase,
    approvalReady,
    approvalValue,
    provider,
    model,
    busy,
    defaultPrompt = "",
    onSubmit,
    onRequestApproval,
  } = props;

  const [sessions, setSessions] = useState<AgenticSessionSnapshot[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [events, setEvents] = useState<AgenticEvent[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [planMode, setPlanMode] = useState<"act" | "plan">("act");
  const [prompt, setPrompt] = useState<string>(defaultPrompt);
  const [error, setError] = useState<string>("");
  const [policySummary, setPolicySummary] = useState<{
    allowCount: number;
    denyCount: number;
  } | null>(null);
  const timelineRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setPrompt(defaultPrompt);
  }, [defaultPrompt]);

  const fetchSessions = useCallback(async () => {
    try {
      const response = await fetch(`${backend}/api/ouroboros/agentic/sessions?limit=40`);
      if (!response.ok) {
        setError(`Kon sessies niet ophalen (${response.status}).`);
        return;
      }
      const data = (await response.json()) as AgenticSessionsResponse;
      const list = data.sessions ?? [];
      setSessions(list);
      setError("");
      setSelectedId((current) => {
        if (current && list.some((session) => session.session_id === current)) return current;
        return list.length > 0 ? list[0].session_id : null;
      });
    } catch (exc) {
      setError(`Sessies fetch faalde: ${(exc as Error).message}`);
    }
  }, [backend]);

  const fetchEvents = useCallback(
    async (sessionId: string) => {
      try {
        const response = await fetch(`${backend}/api/ouroboros/agentic/sessions/${encodeURIComponent(sessionId)}/events?limit=400`);
        if (!response.ok) return;
        const data = (await response.json()) as AgenticEventsResponse;
        setEvents(data.events ?? []);
      } catch {
        // swallow; next poll will retry
      }
    },
    [backend],
  );

  const fetchPolicy = useCallback(async () => {
    try {
      const response = await fetch(`${backend}/api/ouroboros/agentic/policy/commands`);
      if (!response.ok) return;
      const data = (await response.json()) as { policy?: { active_allow_patterns?: string[]; active_deny_patterns?: string[] } };
      const policy = data.policy ?? {};
      setPolicySummary({
        allowCount: (policy.active_allow_patterns ?? []).length,
        denyCount: (policy.active_deny_patterns ?? []).length,
      });
    } catch {
      // ignore
    }
  }, [backend]);

  useEffect(() => {
    fetchSessions();
    fetchPolicy();
    const sessionsTimer = window.setInterval(fetchSessions, 4000);
    return () => window.clearInterval(sessionsTimer);
  }, [fetchSessions, fetchPolicy]);

  useEffect(() => {
    if (!selectedId) {
      setEvents([]);
      return;
    }
    fetchEvents(selectedId);
    const timer = window.setInterval(() => fetchEvents(selectedId), 1800);
    return () => window.clearInterval(timer);
  }, [selectedId, fetchEvents]);

  useEffect(() => {
    if (!timelineRef.current) return;
    timelineRef.current.scrollTop = timelineRef.current.scrollHeight;
  }, [events.length]);

  const selectedSession = useMemo(
    () => sessions.find((session) => session.session_id === selectedId) ?? null,
    [sessions, selectedId],
  );
  const selectedEvent = useMemo(
    () => events.find((event) => event.event_id === selectedEventId) ?? events[events.length - 1] ?? null,
    [events, selectedEventId],
  );

  const memoryStatus = selectedSession?.memory_status;
  const braveEvent = useMemo(
    () => events.find((event) => event.tool === "brave_search"),
    [events],
  );
  const memoryEvent = useMemo(
    () => events.find((event) => event.tool === "memory_search"),
    [events],
  );
  const awaitingApprovalEvent = useMemo(
    () => events.find((event) => event.event_type === "tool_awaiting_approval"),
    [events],
  );

  const sendPrompt = useCallback(async () => {
    const trimmed = prompt.trim();
    if (!trimmed) return;
    const newSessionId = `agentic_workspace_${Date.now()}`;
    setSelectedId(newSessionId);
    try {
      const outcome = await onSubmit({ prompt: trimmed, planMode, sessionId: newSessionId });
      const actualId = outcome?.sessionId || newSessionId;
      setSelectedId(actualId);
      setPrompt("");
      setTimeout(() => {
        fetchSessions();
        fetchEvents(actualId);
      }, 400);
    } catch (exc) {
      setError(`Kon prompt niet sturen: ${(exc as Error).message}`);
    }
  }, [prompt, planMode, onSubmit, fetchSessions, fetchEvents]);

  const cancelSession = useCallback(async () => {
    if (!selectedId) return;
    try {
      await fetch(`${backend}/api/ouroboros/agentic/sessions/${encodeURIComponent(selectedId)}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "cockpit_cancel" }),
      });
      fetchSessions();
      fetchEvents(selectedId);
    } catch (exc) {
      setError(`Cancel faalde: ${(exc as Error).message}`);
    }
  }, [backend, selectedId, fetchEvents, fetchSessions]);

  return (
    <section className="agent-workspace">
      <header className="agent-workspace-header">
        <div className="agent-workspace-title">
          <Bot />
          <div>
            <h2>Agent Workspace</h2>
            <p>
              {provider}/{model || "model"} · {sessions.length} sessies ·{" "}
              policy {policySummary ? `${policySummary.allowCount} allow / ${policySummary.denyCount} deny` : "laadt"}
            </p>
          </div>
        </div>
        <div className="agent-workspace-controls">
          <div className="plan-mode-segmented" role="tablist">
            <button
              type="button"
              className={planMode === "act" ? "active" : ""}
              onClick={() => setPlanMode("act")}
              role="tab"
              aria-selected={planMode === "act"}
            >
              Act
            </button>
            <button
              type="button"
              className={planMode === "plan" ? "active" : ""}
              onClick={() => setPlanMode("plan")}
              role="tab"
              aria-selected={planMode === "plan"}
            >
              Plan
            </button>
          </div>
          <button type="button" className="ghost" onClick={fetchSessions} title="Refresh">
            <RefreshCw size={14} /> Refresh
          </button>
          <button
            type="button"
            className="ghost"
            disabled={!selectedSession || selectedSession.status !== "running"}
            onClick={cancelSession}
            title="Stop"
          >
            <StopCircle size={14} /> Stop
          </button>
        </div>
      </header>

      {error && <div className="agent-workspace-error">{error}</div>}

      <div className="agent-workspace-grid">
        <aside className="agent-session-rail">
          <header>
            <h3>Sessies</h3>
            <span>{sessions.length}</span>
          </header>
          <ul>
            {sessions.length === 0 && <li className="agent-empty">Nog geen agentische sessies.</li>}
            {sessions.map((session) => {
              const tone = statusTone(session.status);
              return (
                <li
                  key={session.session_id}
                  className={`agent-session-card ${classNamesForTone(tone)} ${
                    session.session_id === selectedId ? "active" : ""
                  }`}
                  onClick={() => {
                    setSelectedId(session.session_id);
                    setSelectedEventId(null);
                  }}
                >
                  <div className="agent-session-card-top">
                    <span className={`agent-session-status ${classNamesForTone(tone)}`}>{session.status ?? "?"}</span>
                    <span className="agent-session-mode">{(session.plan_mode || "act").toUpperCase()}</span>
                    <em>{relativeTime(session.updated_at)}</em>
                  </div>
                  <p className="agent-session-goal">{session.goal || "(geen doel)"}</p>
                  <div className="agent-session-meta">
                    <span>{session.provider || "?"}/{session.model || "model"}</span>
                    {session.approval_required && <span className="agent-tone-warn">Akkoord nodig</span>}
                    {session.loop_warning && <span className="agent-tone-warn">loop?</span>}
                    {session.loop_blocked && <span className="agent-tone-block">loop block</span>}
                  </div>
                  <div className="agent-session-tools">
                    {TOOL_SUMMARY_KEYS.map(({ key, label, tone: subTone }) => {
                      const count = Number(session.tool_summary?.[key] ?? 0);
                      if (!count) return null;
                      return (
                        <span key={String(key)} className={`agent-chip ${classNamesForTone(subTone)}`}>
                          {label} {count}
                        </span>
                      );
                    })}
                  </div>
                </li>
              );
            })}
          </ul>
        </aside>

        <section className="agent-timeline-column">
          <div className="agent-timeline-summary">
            {selectedSession ? (
              <>
                <div>
                  <strong>{selectedSession.goal || "(geen doel)"}</strong>
                  <small>
                    {selectedSession.session_id} ·{" "}
                    {selectedSession.duration_seconds != null
                      ? `${selectedSession.duration_seconds.toFixed(2)}s`
                      : "lopend"}
                  </small>
                </div>
                <div className="agent-summary-chips">
                  <span className={`agent-chip ${classNamesForTone(statusTone(selectedSession.status))}`}>
                    {selectedSession.status ?? "?"}
                  </span>
                  <span className="agent-chip agent-tone-neutral">
                    Plan: {(selectedSession.plan_mode || "act").toUpperCase()}
                  </span>
                  <span className="agent-chip agent-tone-info">
                    Memory: {memoryStatus?.status ?? memoryStatus?.collection ?? "—"}
                  </span>
                  <span className="agent-chip agent-tone-neutral">
                    Brave: {braveEvent ? "gebruikt" : "niet gebruikt"}
                  </span>
                  {selectedSession.loop_warning && (
                    <span className="agent-chip agent-tone-warn">loop warning</span>
                  )}
                  {selectedSession.loop_blocked && (
                    <span className="agent-chip agent-tone-block">loop blocked</span>
                  )}
                </div>
              </>
            ) : (
              <p>Selecteer een sessie of stuur een nieuwe prompt om de timeline te zien.</p>
            )}
          </div>

          {awaitingApprovalEvent && (
            <div className="agent-approval-banner">
              <ShieldAlert size={16} />
              <div>
                <strong>Wacht op {approvalPhrase}.</strong>
                <span>
                  Tool {awaitingApprovalEvent.tool ?? "?"} is geblokkeerd. Typ exact <code>{approvalPhrase}</code> en stuur opnieuw.
                </span>
              </div>
              {!approvalReady && (
                <button type="button" onClick={onRequestApproval}>
                  Vul Akkoord
                </button>
              )}
            </div>
          )}

          <div className="agent-timeline" ref={timelineRef}>
            {events.length === 0 && <p className="agent-empty">Geen events nog. Start een agentische run hieronder.</p>}
            {events.map((event) => {
              const meta = EVENT_META[event.event_type || ""] ?? {
                label: event.event_type || "event",
                tone: "neutral",
                icon: <CircleDot size={14} />,
              };
              const tone = meta.tone;
              const isActive = (selectedEvent && selectedEvent.event_id === event.event_id) ? "active" : "";
              return (
                <article
                  key={event.event_id || `${event.session_id}-${event.sequence}`}
                  className={`agent-event ${classNamesForTone(tone)} ${isActive}`}
                  onClick={() => setSelectedEventId(event.event_id ?? null)}
                >
                  <div className="agent-event-head">
                    <span className={`agent-event-icon ${classNamesForTone(tone)}`}>{meta.icon}</span>
                    <strong>{meta.label}</strong>
                    {event.tool && <span className="agent-event-tool">{event.tool}</span>}
                    {event.status && <span className="agent-event-status">{event.status}</span>}
                    <em>
                      <Clock size={12} /> {relativeTime(event.ts)}
                      {event.duration_seconds != null && ` · ${event.duration_seconds.toFixed(2)}s`}
                    </em>
                  </div>
                  <div className="agent-event-body">{safeJson(event.payload)}</div>
                </article>
              );
            })}
          </div>

          <form
            className="agent-prompt-form"
            onSubmit={(event) => {
              event.preventDefault();
              if (!busy) {
                sendPrompt();
              }
            }}
          >
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder={`Schrijf een agentische taak (mode: ${planMode.toUpperCase()})`}
              rows={3}
            />
            <div className="agent-prompt-actions">
              <div className="agent-prompt-hint">
                {planMode === "plan" ? "Plan mode plant alleen — Akkoord nodig om uit te voeren." : "Act mode voert het plan uit."}
              </div>
              <button type="submit" disabled={busy || !prompt.trim()}>
                <Send size={14} /> Verstuur
              </button>
            </div>
          </form>
        </section>

        <aside className="agent-inspector">
          <header>
            <h3>Inspector</h3>
            {selectedEvent && <span>{selectedEvent.event_id}</span>}
          </header>
          {!selectedEvent && <p className="agent-empty">Klik een event aan om details te zien.</p>}
          {selectedEvent && (
            <>
              <dl className="agent-inspector-grid">
                <dt>Type</dt>
                <dd>{selectedEvent.event_type}</dd>
                <dt>Tool</dt>
                <dd>{selectedEvent.tool ?? "—"}</dd>
                <dt>Status</dt>
                <dd>{selectedEvent.status ?? "—"}</dd>
                <dt>Tijdstip</dt>
                <dd>{selectedEvent.ts ?? "—"}</dd>
                <dt>Duur</dt>
                <dd>{selectedEvent.duration_seconds != null ? `${selectedEvent.duration_seconds.toFixed(3)}s` : "—"}</dd>
                <dt>Approval</dt>
                <dd>{selectedEvent.approval_required ? "vereist" : "—"}</dd>
              </dl>
              <h4>Payload</h4>
              <pre>{JSON.stringify(selectedEvent.payload ?? {}, null, 2)}</pre>
            </>
          )}
          {selectedSession && (
            <section className="agent-inspector-extras">
              <h4>Memory</h4>
              <ul>
                <li>status: <em>{memoryStatus?.status ?? "—"}</em></li>
                <li>collection: <em>{memoryStatus?.collection ?? "—"}</em></li>
                <li>item_id: <em>{memoryStatus?.item_id ?? "—"}</em></li>
                {memoryStatus?.fallback_path && (
                  <li className="agent-tone-warn">fallback: <em>{memoryStatus.fallback_path}</em></li>
                )}
                {memoryStatus?.primary_error && (
                  <li className="agent-tone-warn">primary_error: <em>{memoryStatus.primary_error}</em></li>
                )}
              </ul>
              <h4>Evidence</h4>
              <ul>
                <li>Brave Search: <em>{braveEvent ? "gebruikt" : "niet gebruikt"}</em></li>
                <li>Memory Search: <em>{memoryEvent ? "geraadpleegd" : "—"}</em></li>
                <li>Loop warning: <em>{selectedSession.loop_warning ? "ja" : "nee"}</em></li>
                <li>Loop blocked: <em>{selectedSession.loop_blocked ? "ja" : "nee"}</em></li>
              </ul>
              <h4>Blocked tools</h4>
              <ul>
                {(selectedSession.blocked_tools ?? []).length === 0 && <li>geen</li>}
                {(selectedSession.blocked_tools ?? []).map((tool) => (
                  <li key={tool} className="agent-tone-block">{tool}</li>
                ))}
              </ul>
              <h4>Bestanden</h4>
              <ul>
                {(selectedSession.files_touched ?? []).length === 0 && <li>geen</li>}
                {(selectedSession.files_touched ?? []).map((path) => (
                  <li key={path}>{path}</li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>
    </section>
  );
}

function Bot() {
  return (
    <span className="agent-icon-bot" aria-hidden>
      <PauseCircle size={20} />
    </span>
  );
}

export default AgentWorkspace;

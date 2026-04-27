"""Goose-like standalone desktop UI for Resonant Ouroboros Awake Keeper."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
import queue
import threading
import textwrap
from typing import Any
from urllib import error, parse, request

try:
    import customtkinter as ctk
    import tkinter as tk
    from tkinter import messagebox
except ImportError as exc:  # pragma: no cover - exercised by launcher on desktops without Tk.
    raise SystemExit(
        "customtkinter and tkinter are required for the desktop UI. "
        "Install customtkinter with pip and make sure python3-tk is installed."
    ) from exc


API_BASE_URL = os.getenv("AWAKE_KEEPER_API_URL", "http://127.0.0.1:7861").rstrip("/")
POLL_SECONDS = float(os.getenv("AWAKE_KEEPER_UI_POLL_SECONDS", "1.5"))


@dataclass(frozen=True)
class ApiResult:
    ok: bool
    data: dict[str, Any]
    error: str | None = None


def api_request(method: str, path: str, payload: dict[str, Any] | None = None, timeout: float = 90.0) -> ApiResult:
    url = f"{API_BASE_URL}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        req = request.Request(url, data=data, method=method.upper(), headers=headers)
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
        return ApiResult(True, json.loads(body or "{}"))
    except error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"detail": str(exc)}
        return ApiResult(False, body, str(body.get("detail") or exc))
    except Exception as exc:
        return ApiResult(False, {}, str(exc))


def api_get(path: str, params: dict[str, Any] | None = None, timeout: float = 30.0) -> ApiResult:
    query = ""
    if params:
        query = "?" + parse.urlencode(params)
    return api_request("GET", f"{path}{query}", timeout=timeout)


def clamp_text(value: Any, limit: int = 900) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}..."


class GooseLikeApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("Resonant Ouroboros - Awake Keeper")
        self.geometry("1220x780")
        self.minsize(980, 640)

        self.event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.status_vars: dict[str, tk.StringVar] = {}
        self.polling = True
        self.current_status: dict[str, Any] = {}
        self.approval_tokens: dict[str, str] = {}

        self._build_layout()
        self._append_system_message(
            "Safe Mode is active. This UI talks only to the local Awake Keeper API and never runs shell commands."
        )
        self._start_polling()
        self.after(120, self._drain_events)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self) -> None:
        self.configure(fg_color="#101113")
        self.grid_columnconfigure(0, minsize=306, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, fg_color="#17191d", corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(
            sidebar,
            text="Awake Keeper",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#f2f6ff",
        ).grid(row=0, column=0, padx=22, pady=(24, 4), sticky="w")
        ctk.CTkLabel(
            sidebar,
            text="Goose-like Standalone UI",
            font=ctk.CTkFont(size=13),
            text_color="#8f98a8",
        ).grid(row=1, column=0, padx=22, pady=(0, 16), sticky="w")

        safe = ctk.CTkFrame(sidebar, fg_color="#0d2b24", corner_radius=8)
        safe.grid(row=2, column=0, padx=16, pady=(0, 14), sticky="ew")
        safe.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            safe,
            text="SAFE MODE",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#87ffd3",
        ).grid(row=0, column=0, padx=14, pady=(10, 0), sticky="w")
        self.safe_detail = ctk.CTkLabel(
            safe,
            text="Docker-local API",
            font=ctk.CTkFont(size=12),
            text_color="#c9f8e8",
            wraplength=250,
            justify="left",
        )
        self.safe_detail.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="w")

        status_frame = ctk.CTkFrame(sidebar, fg_color="#202329", corner_radius=8)
        status_frame.grid(row=3, column=0, padx=16, pady=(0, 14), sticky="ew")
        status_frame.grid_columnconfigure(1, weight=1)
        status_items = [
            ("Hz", "hz"),
            ("Mood", "mood"),
            ("Iterations", "iterations"),
            ("Topic", "current_topic"),
            ("Last action", "last_action"),
            ("Model", "ollama_model"),
            ("Co-evolution", "co_evolution_score"),
            ("Events", "latest_event"),
            ("Proposals", "pending_proposals"),
            ("Sandbox", "sandbox_status"),
        ]
        for index, (label, key) in enumerate(status_items):
            ctk.CTkLabel(status_frame, text=label, text_color="#8f98a8", font=ctk.CTkFont(size=12)).grid(
                row=index, column=0, padx=(14, 8), pady=7, sticky="w"
            )
            var = tk.StringVar(value="...")
            self.status_vars[key] = var
            ctk.CTkLabel(
                status_frame,
                textvariable=var,
                text_color="#f2f6ff",
                font=ctk.CTkFont(size=12, weight="bold" if index < 2 else "normal"),
                wraplength=166,
                justify="left",
            ).grid(row=index, column=1, padx=(0, 14), pady=7, sticky="w")

        controls = ctk.CTkFrame(sidebar, fg_color="#202329", corner_radius=8)
        controls.grid(row=4, column=0, padx=16, pady=(0, 14), sticky="ew")
        controls.grid_columnconfigure((0, 1), weight=1)
        self._control_button(controls, "Start Awake Mode", "start", 0, 0, "#2d7ff9")
        self._control_button(controls, "Stop", "stop", 0, 1, "#3a404a")
        self._control_button(controls, "Manual PAEU Step", "manual_paeu_step", 1, 0, "#3a404a")
        self._control_button(controls, "Creative Spike", "creative_spike", 1, 1, "#8854ff")
        self._control_button(controls, "View 11D Memory", "memory", 2, 0, "#3a404a")
        self._control_button(controls, "Clear Queue", "clear_queue", 2, 1, "#3a404a")
        self._control_button(controls, "Reflect", "reflect", 3, 0, "#274a43")
        self._control_button(controls, "Evolution", "evolution", 3, 1, "#3a404a")
        self.approvals_button = ctk.CTkButton(
            controls,
            text="Approvals (0)",
            height=38,
            fg_color="#274a43",
            hover_color="#37665c",
            command=self._open_approvals,
        )
        self.approvals_button.grid(row=4, column=0, columnspan=2, padx=8, pady=8, sticky="ew")

        self.connection_label = ctk.CTkLabel(
            sidebar,
            text=f"API: {API_BASE_URL}",
            text_color="#747d8f",
            font=ctk.CTkFont(size=11),
            wraplength=260,
            justify="left",
        )
        self.connection_label.grid(row=6, column=0, padx=18, pady=16, sticky="sw")

        main = ctk.CTkFrame(self, fg_color="#101113", corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(main, fg_color="#101113", corner_radius=0)
        header.grid(row=0, column=0, padx=22, pady=(20, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Live Chat",
            text_color="#f2f6ff",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        self.activity_label = ctk.CTkLabel(
            header,
            text="Polling...",
            text_color="#8f98a8",
            font=ctk.CTkFont(size=12),
        )
        self.activity_label.grid(row=0, column=1, sticky="e")

        self.chat_scroll = ctk.CTkScrollableFrame(main, fg_color="#15171b", corner_radius=8)
        self.chat_scroll.grid(row=1, column=0, padx=22, pady=(0, 12), sticky="nsew")
        self.chat_scroll.grid_columnconfigure(0, weight=1)
        self.chat_row = 0

        bottom = ctk.CTkFrame(main, fg_color="#101113", corner_radius=0)
        bottom.grid(row=2, column=0, padx=22, pady=(0, 18), sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)
        self.input_box = ctk.CTkTextbox(bottom, height=72, fg_color="#202329", border_width=1, border_color="#303641")
        self.input_box.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.input_box.bind("<Control-Return>", lambda _event: self._send_chat())
        self.input_box.bind("<Command-Return>", lambda _event: self._send_chat())
        ctk.CTkButton(
            bottom,
            text="Send",
            width=96,
            height=44,
            fg_color="#2d7ff9",
            command=self._send_chat,
        ).grid(row=0, column=1, sticky="sew")

    def _control_button(
        self,
        parent: ctk.CTkFrame,
        text: str,
        command: str,
        row: int,
        column: int,
        color: str,
    ) -> None:
        if command == "memory":
            action = self._open_memory
        elif command == "reflect":
            action = self._run_reflect
        elif command == "evolution":
            action = self._open_evolution
        else:
            action = lambda cmd=command: self._run_control(cmd)
        ctk.CTkButton(
            parent,
            text=text,
            height=38,
            fg_color=color,
            hover_color="#465060",
            command=action,
        ).grid(row=row, column=column, padx=8, pady=8, sticky="ew")

    def _append_system_message(self, text: str) -> None:
        self._append_message("System", text, accent="#8f98a8", bubble="#1b1e24")

    def _append_user_message(self, text: str) -> None:
        self._append_message("You", text, accent="#a7d8ff", bubble="#16283a")

    def _append_assistant_message(self, payload: dict[str, Any]) -> None:
        answer = payload.get("answer", "")
        meta = f"{float(payload.get('hz') or 0):.2f} Hz / {payload.get('mood') or 'unknown'}"
        frame = self._append_message("Awake Keeper", answer, accent="#c7b9ff", bubble="#202329", meta=meta)
        sources = payload.get("sources") or []
        if sources:
            source_text = "\n".join(
                f"- {clamp_text(source.get('title') or source.get('url'), 90)}"
                for source in sources[:4]
            )
            ctk.CTkLabel(
                frame,
                text=f"Sources\n{source_text}",
                text_color="#9da7b8",
                justify="left",
                wraplength=760,
                font=ctk.CTkFont(size=12),
            ).grid(row=3, column=0, padx=14, pady=(0, 10), sticky="w")

        suggestions = payload.get("suggested_learning_actions") or []
        if suggestions:
            suggestion_frame = ctk.CTkFrame(frame, fg_color="transparent")
            suggestion_frame.grid(row=4, column=0, padx=12, pady=(0, 10), sticky="w")
            for index, suggestion in enumerate(suggestions[:2]):
                prompt = suggestion.get("label") or "Connect this to 11D memory"
                ctk.CTkButton(
                    suggestion_frame,
                    text=clamp_text(prompt, 32),
                    width=190,
                    height=28,
                    fg_color="#3a404a",
                    command=lambda text=prompt: self._send_chat(prefix=f"{text}: "),
                ).grid(row=0, column=index, padx=(0, 8))

        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.grid(row=5, column=0, padx=12, pady=(0, 12), sticky="w")
        ctk.CTkButton(
            actions,
            text="Browse more",
            width=112,
            height=28,
            fg_color="#3a404a",
            command=lambda: self._send_chat(prefix="Browse more with context about: "),
        ).grid(row=0, column=0, padx=(0, 8))
        button_column = 1
        action_proposals = [
            action for action in (payload.get("actions") or []) if action.get("kind") not in {"control"}
        ]
        for action in action_proposals[:2]:
            ctk.CTkButton(
                actions,
                text=clamp_text(action.get("label") or "Approve & Execute", 28),
                width=154,
                height=28,
                fg_color="#274a43",
                command=lambda item=action, msg=payload.get("message_id"): self._create_action_from_chat(
                    item,
                    answer,
                    str(msg or ""),
                ),
            ).grid(row=0, column=button_column, padx=(0, 8))
            button_column += 1
        if not action_proposals and ("```" in str(answer) or "def " in str(answer) or "class " in str(answer)):
            ctk.CTkButton(
                actions,
                text="Approve & Review Code",
                width=166,
                height=28,
                fg_color="#274a43",
                command=lambda: self._create_action_from_chat(
                    {
                        "kind": "apply_code_review",
                        "label": "Approve & Review Code",
                        "payload": {"code": answer, "language": "text"},
                    },
                    answer,
                    str(payload.get("message_id") or ""),
                ),
            ).grid(row=0, column=button_column, padx=(0, 8))

    def _append_message(
        self,
        role: str,
        text: str,
        *,
        accent: str,
        bubble: str,
        meta: str | None = None,
    ) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.chat_scroll, fg_color=bubble, corner_radius=8)
        frame.grid(row=self.chat_row, column=0, padx=10, pady=8, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)
        self.chat_row += 1
        ctk.CTkLabel(
            frame,
            text=role,
            text_color=accent,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, padx=14, pady=(10, 0), sticky="w")
        if meta:
            ctk.CTkLabel(
                frame,
                text=meta,
                text_color="#747d8f",
                font=ctk.CTkFont(size=11),
            ).grid(row=1, column=0, padx=14, pady=(0, 4), sticky="w")
        wrapped = textwrap.dedent(str(text or "")).strip() or "(empty)"
        ctk.CTkLabel(
            frame,
            text=wrapped,
            text_color="#f2f6ff",
            font=ctk.CTkFont(size=13),
            justify="left",
            wraplength=820,
        ).grid(row=2, column=0, padx=14, pady=(6, 12), sticky="w")
        self.after(60, self._scroll_to_bottom)
        return frame

    def _scroll_to_bottom(self) -> None:
        try:
            self.chat_scroll._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _start_polling(self) -> None:
        def poll_loop() -> None:
            while self.polling:
                result = api_get("/status", timeout=20.0)
                self.event_queue.put(("status", result))
                threading.Event().wait(POLL_SECONDS)

        threading.Thread(target=poll_loop, daemon=True).start()

    def _drain_events(self) -> None:
        while True:
            try:
                event, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break
            if event == "status":
                self._handle_status(payload)
            elif event == "chat":
                self._handle_chat(payload)
            elif event == "control":
                self._handle_control(payload)
            elif event == "reflect":
                self._handle_reflect(payload)
            elif event == "memory":
                self._show_memory_window(payload)
            elif event == "evolution":
                self._show_evolution_window(payload)
            elif event == "actions":
                self._show_approvals_window(payload)
            elif event == "action_created":
                self._handle_action_created(payload)
            elif event == "action_update":
                self._handle_action_update(payload)
            elif event == "action_batch_update":
                self._handle_action_batch_update(payload)
        self.after(120, self._drain_events)

    def _handle_status(self, result: ApiResult) -> None:
        if not result.ok:
            self.activity_label.configure(text="API disconnected", text_color="#ff8f8f")
            self.connection_label.configure(text=f"API: {API_BASE_URL}\n{result.error}")
            return
        self.activity_label.configure(text=f"Live {datetime.now().strftime('%H:%M:%S')}", text_color="#87ffd3")
        self.current_status = result.data
        self.safe_detail.configure(text=result.data.get("safe_mode_label") or "Docker-local API")
        values = {
            "hz": f"{float(result.data.get('current_hz') or 0):.2f}",
            "mood": str(result.data.get("vibration_mood") or "..."),
            "iterations": str(result.data.get("iterations") or 0),
            "current_topic": clamp_text(result.data.get("current_topic") or "idle", 80),
            "last_action": clamp_text(result.data.get("last_action") or "none", 80),
            "ollama_model": clamp_text(result.data.get("ollama_model") or "unknown", 80),
            "co_evolution_score": str((result.data.get("co_evolution") or {}).get("score") or 0),
            "latest_event": clamp_text((result.data.get("events") or {}).get("latest_event_id") or "none", 80),
            "pending_proposals": str((result.data.get("proposals") or {}).get("pending_count") or 0),
            "sandbox_status": clamp_text((result.data.get("sandbox") or {}).get("status_label") or "unknown", 80),
        }
        for key, value in values.items():
            self.status_vars[key].set(value)
        actions = result.data.get("actions") or {}
        pending = int(actions.get("pending_count") or 0)
        self.approvals_button.configure(
            text=f"Approvals ({pending})",
            fg_color="#8a6430" if pending else "#274a43",
        )

    def _send_chat(self, prefix: str = "") -> None:
        message = self.input_box.get("1.0", "end").strip()
        if prefix and not message:
            message = clamp_text(self.current_status.get("current_topic") or "current Awake Keeper context", 160)
        message = f"{prefix}{message}".strip()
        if not message:
            return
        self.input_box.delete("1.0", "end")
        self._append_user_message(message)
        self.activity_label.configure(text="Thinking...", text_color="#ffd27d")

        def worker() -> None:
            result = api_request("POST", "/chat", {"message": message}, timeout=180.0)
            self.event_queue.put(("chat", result))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_chat(self, result: ApiResult) -> None:
        if result.ok:
            self._append_assistant_message(result.data)
            self._handle_status(ApiResult(True, result.data.get("status") or {}))
            return
        self._append_system_message(f"Chat failed: {result.error}")
        self.activity_label.configure(text="Chat error", text_color="#ff8f8f")

    def _create_action_from_chat(self, action: dict[str, Any], answer: str, message_id: str) -> None:
        kind = str(action.get("kind") or "apply_code_review")
        payload = dict(action.get("payload") or {})
        if kind == "apply_code_review":
            payload.setdefault("code", answer)
            payload.setdefault("language", "text")
        if message_id:
            payload.setdefault("message_id", message_id)
        body = {
            "kind": kind,
            "label": action.get("label") or "Approve & Execute",
            "summary": action.get("summary") or f"Action proposed from chat message {message_id or '(unknown)'}",
            "payload": payload,
            "source": {"client": "goose_like_ui", "conversation_id": "local-ui-default"},
        }
        self.activity_label.configure(text="Creating action...", text_color="#ffd27d")

        def worker() -> None:
            result = api_request("POST", "/actions", body, timeout=90.0)
            self.event_queue.put(("action_created", result))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_action_created(self, result: ApiResult) -> None:
        if not result.ok:
            self._append_system_message(f"Action proposal failed: {result.error}")
            self.activity_label.configure(text="Action error", text_color="#ff8f8f")
            return
        proposal = result.data.get("proposal") or {}
        token = result.data.get("approval_token")
        if token and proposal.get("id"):
            self.approval_tokens[str(proposal["id"])] = str(token)
        status = proposal.get("status")
        if status == "pending":
            self._append_system_message(
                f"Action queued for approval: {proposal.get('label') or proposal.get('kind')}"
            )
            self._open_approvals()
        elif status == "executed":
            result_text = proposal.get("result") or {}
            feedback = result_text.get("feedback") if isinstance(result_text, dict) else None
            self._append_system_message(
                f"Safe action executed: {proposal.get('label') or proposal.get('kind')}. {feedback or ''}"
            )
        else:
            reasons = "; ".join(str(item) for item in proposal.get("safety_reasons") or [])
            self._append_system_message(f"Action {status}: {reasons or proposal.get('label')}")
        self.activity_label.configure(text="Action updated", text_color="#87ffd3")

    def _run_reflect(self) -> None:
        topic = self.current_status.get("current_topic") or "Fase 4 co-evolution loop"
        self.activity_label.configure(text="Reflecting...", text_color="#ffd27d")

        def worker() -> None:
            result = api_request("POST", "/reflect", {"topic": topic}, timeout=180.0)
            self.event_queue.put(("reflect", result))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_reflect(self, result: ApiResult) -> None:
        if not result.ok:
            self._append_system_message(f"Reflection failed: {result.error}")
            self.activity_label.configure(text="Reflection error", text_color="#ff8f8f")
            return
        safe_action = result.data.get("safe_action") or {}
        token = result.data.get("approval_token")
        if token and safe_action.get("id"):
            self.approval_tokens[str(safe_action["id"])] = str(token)
        self._append_system_message(
            "Reflection proposal created.\n"
            f"{clamp_text(result.data.get('proposal'), 1100)}\n\n"
            f"Approval action: {safe_action.get('id') or 'none'}"
        )
        self._handle_status(ApiResult(True, result.data.get("status") or {}))
        if safe_action.get("status") == "pending":
            self._open_approvals()

    def _run_control(self, command: str) -> None:
        self.activity_label.configure(text=f"{command}...", text_color="#ffd27d")

        def worker() -> None:
            result = api_request("POST", "/control", {"command": command}, timeout=180.0)
            self.event_queue.put(("control", result))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_control(self, result: ApiResult) -> None:
        if result.ok:
            self._append_system_message(str(result.data.get("message") or "Control command completed."))
            self._handle_status(ApiResult(True, result.data.get("status") or {}))
            return
        self._append_system_message(f"Control failed: {result.error}")
        self.activity_label.configure(text="Control error", text_color="#ff8f8f")

    def _open_approvals(self) -> None:
        def worker() -> None:
            result = api_get("/actions", {"status": "pending", "limit": 20}, timeout=45.0)
            self.event_queue.put(("actions", result))

        threading.Thread(target=worker, daemon=True).start()

    def _show_approvals_window(self, result: ApiResult) -> None:
        if not result.ok:
            messagebox.showerror("Approvals", result.error or "Action request failed")
            return
        window = ctk.CTkToplevel(self)
        window.title("Safe Action Approvals")
        window.geometry("900x600")
        window.configure(fg_color="#101113")
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        actions = result.data.get("actions") or []
        selected_vars: dict[str, tk.BooleanVar] = {}
        header = ctk.CTkFrame(window, fg_color="#101113", corner_radius=0)
        header.grid(row=0, column=0, padx=18, pady=16, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text=f"Pending Approvals: {len(actions)}",
            text_color="#f2f6ff",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            header,
            text="Approve Selected",
            width=142,
            height=30,
            fg_color="#2d7ff9",
            command=lambda: self._approve_selected_actions(selected_vars, window),
        ).grid(row=0, column=1, padx=(8, 0), sticky="e")
        ctk.CTkButton(
            header,
            text="Reject Selected",
            width=122,
            height=30,
            fg_color="#3a404a",
            command=lambda: self._reject_selected_actions(selected_vars, window),
        ).grid(row=0, column=2, padx=(8, 0), sticky="e")
        scroll = ctk.CTkScrollableFrame(window, fg_color="#15171b", corner_radius=8)
        scroll.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        if not actions:
            ctk.CTkLabel(
                scroll,
                text="No pending actions.",
                text_color="#8f98a8",
                font=ctk.CTkFont(size=13),
            ).grid(row=0, column=0, padx=14, pady=14, sticky="w")
            return
        for index, action in enumerate(actions):
            item = ctk.CTkFrame(scroll, fg_color="#202329", corner_radius=8)
            item.grid(row=index, column=0, padx=8, pady=8, sticky="ew")
            item.grid_columnconfigure(0, weight=1)
            label = action.get("label") or action.get("kind") or "action"
            reasons = "; ".join(str(reason) for reason in action.get("safety_reasons") or [])
            action_id = str(action.get("id") or "")
            if action_id:
                selected_vars[action_id] = tk.BooleanVar(value=False)
                ctk.CTkCheckBox(
                    item,
                    text="",
                    variable=selected_vars[action_id],
                    width=24,
                    fg_color="#2d7ff9",
                ).grid(row=0, column=1, rowspan=4, padx=10, pady=12, sticky="ne")
            ctk.CTkLabel(
                item,
                text=f"{label} / {action.get('risk')} risk",
                text_color="#c7b9ff",
                font=ctk.CTkFont(size=12, weight="bold"),
            ).grid(row=0, column=0, padx=12, pady=(10, 2), sticky="w")
            ctk.CTkLabel(
                item,
                text=clamp_text(action.get("summary") or reasons or action.get("payload"), 820),
                text_color="#f2f6ff",
                wraplength=780,
                justify="left",
                font=ctk.CTkFont(size=12),
            ).grid(row=1, column=0, padx=12, pady=(0, 8), sticky="w")
            preview = self._action_preview_text(action)
            if preview:
                ctk.CTkLabel(
                    item,
                    text=preview,
                    text_color="#9da7b8",
                    wraplength=780,
                    justify="left",
                    font=ctk.CTkFont(size=11),
                ).grid(row=2, column=0, padx=12, pady=(0, 8), sticky="w")
            buttons = ctk.CTkFrame(item, fg_color="transparent")
            buttons.grid(row=3, column=0, padx=12, pady=(0, 10), sticky="w")
            ctk.CTkButton(
                buttons,
                text="Approve Review" if action.get("kind") in {"evolution_proposal", "safe_evolution_proposal"} else "Approve & Execute",
                width=150,
                height=28,
                fg_color="#2d7ff9",
                command=lambda aid=action_id, win=window: self._approve_action(aid, win),
            ).grid(row=0, column=0, padx=(0, 8))
            ctk.CTkButton(
                buttons,
                text="Reject",
                width=84,
                height=28,
                fg_color="#3a404a",
                command=lambda aid=action_id, win=window: self._reject_action(aid, win),
            ).grid(row=0, column=1, padx=(0, 8))

    def _action_preview_text(self, action: dict[str, Any]) -> str:
        payload = action.get("payload") or {}
        result = action.get("result") or {}
        parts = []
        argv = payload.get("argv") or payload.get("command")
        if argv:
            parts.append(f"command: {argv}")
        target_files = payload.get("target_files")
        if target_files:
            parts.append(f"targets: {', '.join(str(item) for item in target_files[:4])}")
        prepared = result.get("prepared_command") if isinstance(result, dict) else None
        if prepared:
            parts.append(f"prepared: {' '.join(str(item) for item in prepared[:8])}")
        stdout = result.get("stdout_preview") if isinstance(result, dict) else None
        stderr = result.get("stderr_preview") if isinstance(result, dict) else None
        if stdout:
            parts.append(f"stdout: {clamp_text(stdout, 220)}")
        if stderr:
            parts.append(f"stderr: {clamp_text(stderr, 220)}")
        return "\n".join(parts)

    def _selected_action_ids(self, selected_vars: dict[str, tk.BooleanVar]) -> list[str]:
        return [action_id for action_id, var in selected_vars.items() if var.get()]

    def _approve_selected_actions(
        self,
        selected_vars: dict[str, tk.BooleanVar],
        window: ctk.CTkToplevel | None = None,
    ) -> None:
        action_ids = self._selected_action_ids(selected_vars)
        if not action_ids:
            messagebox.showinfo("Batch approval", "Select one or more actions first.")
            return
        missing = [action_id for action_id in action_ids if action_id not in self.approval_tokens]
        if missing:
            messagebox.showwarning(
                "Approval token unavailable",
                "This UI session does not hold every selected one-time approval token. "
                "Recreate missing proposals from chat or approve only actions created in this session.",
            )
            return
        if window:
            window.destroy()
        approvals = [
            {"action_id": action_id, "approval_token": self.approval_tokens[action_id]}
            for action_id in action_ids
        ]

        def worker() -> None:
            result = api_request(
                "POST",
                "/actions/approve-batch",
                {"approvals": approvals, "approved_by": "local_ui"},
                timeout=180.0,
            )
            self.event_queue.put(("action_batch_update", result))

        threading.Thread(target=worker, daemon=True).start()

    def _reject_selected_actions(
        self,
        selected_vars: dict[str, tk.BooleanVar],
        window: ctk.CTkToplevel | None = None,
    ) -> None:
        action_ids = self._selected_action_ids(selected_vars)
        if not action_ids:
            messagebox.showinfo("Batch rejection", "Select one or more actions first.")
            return
        if window:
            window.destroy()

        def worker() -> None:
            result = api_request(
                "POST",
                "/actions/reject-batch",
                {"action_ids": action_ids, "reason": "Rejected in Goose-like UI batch."},
                timeout=120.0,
            )
            self.event_queue.put(("action_batch_update", result))

        threading.Thread(target=worker, daemon=True).start()

    def _approve_action(self, action_id: str, window: ctk.CTkToplevel | None = None) -> None:
        token = self.approval_tokens.get(action_id)
        if not token:
            messagebox.showwarning(
                "Approval token unavailable",
                "This UI session does not hold the one-time approval token. Create the proposal again from chat.",
            )
            return
        if window:
            window.destroy()

        def worker() -> None:
            result = api_request(
                "POST",
                f"/actions/{parse.quote(action_id)}/approve",
                {"approval_token": token, "approved_by": "local_ui"},
                timeout=120.0,
            )
            self.event_queue.put(("action_update", result))

        threading.Thread(target=worker, daemon=True).start()

    def _reject_action(self, action_id: str, window: ctk.CTkToplevel | None = None) -> None:
        if window:
            window.destroy()

        def worker() -> None:
            result = api_request(
                "POST",
                f"/actions/{parse.quote(action_id)}/reject",
                {"reason": "Rejected in Goose-like UI."},
                timeout=60.0,
            )
            self.event_queue.put(("action_update", result))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_action_update(self, result: ApiResult) -> None:
        if not result.ok:
            self._append_system_message(f"Action update failed: {result.error}")
            self.activity_label.configure(text="Action error", text_color="#ff8f8f")
            return
        proposal = result.data.get("proposal") or {}
        if proposal.get("id") in self.approval_tokens and proposal.get("status") != "pending":
            self.approval_tokens.pop(str(proposal.get("id")), None)
        result_text = proposal.get("result") or {}
        message = result_text.get("message") if isinstance(result_text, dict) else None
        stdout = result_text.get("stdout_preview") if isinstance(result_text, dict) else None
        stderr = result_text.get("stderr_preview") if isinstance(result_text, dict) else None
        feedback = result_text.get("feedback") if isinstance(result_text, dict) else None
        details = "\n".join(
            item
            for item in (
                feedback,
                f"stdout: {stdout}" if stdout else "",
                f"stderr: {stderr}" if stderr else "",
            )
            if item
        )
        self._append_system_message(
            f"Action {proposal.get('status')}: {message or proposal.get('label') or proposal.get('kind')}"
            + (f"\n{details}" if details else "")
        )
        self.activity_label.configure(text="Action updated", text_color="#87ffd3")

    def _handle_action_batch_update(self, result: ApiResult) -> None:
        if not result.ok:
            self._append_system_message(f"Batch action update failed: {result.error}")
            self.activity_label.configure(text="Batch action error", text_color="#ff8f8f")
            return
        lines = []
        for item in result.data.get("results") or []:
            proposal = item.get("proposal") or {}
            action_id = str(proposal.get("id") or item.get("action_id") or "")
            if action_id and proposal.get("status") != "pending":
                self.approval_tokens.pop(action_id, None)
            result_text = proposal.get("result") or {}
            feedback = result_text.get("feedback") if isinstance(result_text, dict) else None
            lines.append(
                f"{proposal.get('label') or proposal.get('kind') or action_id}: "
                f"{proposal.get('status') or item.get('message')}"
                + (f" / {feedback}" if feedback else "")
            )
        self._append_system_message("Batch action update:\n" + "\n".join(lines))
        self._handle_status(ApiResult(True, result.data.get("status") or self.current_status))
        self.activity_label.configure(text="Batch action updated", text_color="#87ffd3")

    def _open_memory(self) -> None:
        query = self.input_box.get("1.0", "end").strip()

        def worker() -> None:
            result = api_get("/memory", {"query": query, "limit": 18}, timeout=45.0)
            self.event_queue.put(("memory", result))

        threading.Thread(target=worker, daemon=True).start()

    def _open_evolution(self) -> None:
        def worker() -> None:
            result = api_get("/evolution", {"limit": 24}, timeout=45.0)
            self.event_queue.put(("evolution", result))

        threading.Thread(target=worker, daemon=True).start()

    def _show_evolution_window(self, result: ApiResult) -> None:
        if not result.ok:
            messagebox.showerror("Co-evolution", result.error or "Evolution request failed")
            return
        window = ctk.CTkToplevel(self)
        window.title("Co-evolution Events")
        window.geometry("920x660")
        window.configure(fg_color="#101113")
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        scorecard = result.data.get("scorecard") or {}
        header = (
            f"Score: {scorecard.get('score', result.data.get('score'))} / "
            f"Recent delta: {scorecard.get('recent_delta', 0)} / "
            f"Events: {result.data.get('count')}"
        )
        ctk.CTkLabel(
            window,
            text=header,
            text_color="#f2f6ff",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, padx=18, pady=16, sticky="w")
        scroll = ctk.CTkScrollableFrame(window, fg_color="#15171b", corner_radius=8)
        scroll.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        rows = result.data.get("events") or []
        if not rows:
            ctk.CTkLabel(
                scroll,
                text="No co-evolution events yet.",
                text_color="#8f98a8",
                font=ctk.CTkFont(size=13),
            ).grid(row=0, column=0, padx=14, pady=14, sticky="w")
            return
        for index, row in enumerate(rows):
            item = ctk.CTkFrame(scroll, fg_color="#202329", corner_radius=8)
            item.grid(row=index, column=0, padx=8, pady=8, sticky="ew")
            item.grid_columnconfigure(0, weight=1)
            title = f"{row.get('type')} / {row.get('status')} / +{row.get('score_delta')}"
            body = row.get("proposal") or row.get("output_summary") or row.get("input_summary")
            ctk.CTkLabel(
                item,
                text=clamp_text(title, 160),
                text_color="#c7b9ff",
                font=ctk.CTkFont(size=12, weight="bold"),
            ).grid(row=0, column=0, padx=12, pady=(10, 2), sticky="w")
            ctk.CTkLabel(
                item,
                text=clamp_text(body, 820),
                text_color="#f2f6ff",
                wraplength=800,
                justify="left",
                font=ctk.CTkFont(size=12),
            ).grid(row=1, column=0, padx=12, pady=(0, 6), sticky="w")
            meta = f"id={row.get('id')} / records={', '.join(row.get('record_ids') or [])}"
            ctk.CTkLabel(
                item,
                text=clamp_text(meta, 820),
                text_color="#8f98a8",
                wraplength=800,
                justify="left",
                font=ctk.CTkFont(size=11),
            ).grid(row=2, column=0, padx=12, pady=(0, 10), sticky="w")

    def _show_memory_window(self, result: ApiResult) -> None:
        if not result.ok:
            messagebox.showerror("11D Memory", result.error or "Memory request failed")
            return
        window = ctk.CTkToplevel(self)
        window.title("11D Memory")
        window.geometry("880x620")
        window.configure(fg_color="#101113")
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        summary = f"Records: {result.data.get('count')} / Query: {result.data.get('query') or '(recent)'}"
        ctk.CTkLabel(
            window,
            text=summary,
            text_color="#f2f6ff",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, padx=18, pady=16, sticky="w")
        scroll = ctk.CTkScrollableFrame(window, fg_color="#15171b", corner_radius=8)
        scroll.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        rows = result.data.get("rows") or []
        if not rows:
            rows = result.data.get("knowledge_feed") or []
        for index, row in enumerate(rows):
            item = ctk.CTkFrame(scroll, fg_color="#202329", corner_radius=8)
            item.grid(row=index, column=0, padx=8, pady=8, sticky="ew")
            item.grid_columnconfigure(0, weight=1)
            title = row.get("id") or row.get("record_id") or row.get("title") or "memory"
            metadata = row.get("metadata") or {}
            detail = row.get("text") or row.get("summary") or metadata
            ctk.CTkLabel(
                item,
                text=clamp_text(title, 140),
                text_color="#c7b9ff",
                font=ctk.CTkFont(size=12, weight="bold"),
            ).grid(row=0, column=0, padx=12, pady=(10, 2), sticky="w")
            ctk.CTkLabel(
                item,
                text=clamp_text(detail, 700),
                text_color="#f2f6ff",
                wraplength=780,
                justify="left",
                font=ctk.CTkFont(size=12),
            ).grid(row=1, column=0, padx=12, pady=(0, 10), sticky="w")

    def _on_close(self) -> None:
        self.polling = False
        self.destroy()


def main() -> None:
    app = GooseLikeApp()
    app.mainloop()


if __name__ == "__main__":
    main()

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
        action = self._open_memory if command == "memory" else lambda cmd=command: self._run_control(cmd)
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

        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.grid(row=4, column=0, padx=12, pady=(0, 12), sticky="w")
        ctk.CTkButton(
            actions,
            text="Browse more",
            width=112,
            height=28,
            fg_color="#3a404a",
            command=lambda: self._send_chat(prefix="Browse more with context about: "),
        ).grid(row=0, column=0, padx=(0, 8))
        if "```" in str(answer) or "def " in str(answer) or "class " in str(answer):
            ctk.CTkButton(
                actions,
                text="Apply this code",
                width=124,
                height=28,
                fg_color="#3a404a",
                command=lambda: messagebox.showinfo(
                    "Safe Mode",
                    "Safe Mode blocks automatic code application from chat. Review and apply changes manually.",
                ),
            ).grid(row=0, column=1, padx=(0, 8))

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
            elif event == "memory":
                self._show_memory_window(payload)
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
        }
        for key, value in values.items():
            self.status_vars[key].set(value)

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

    def _open_memory(self) -> None:
        query = self.input_box.get("1.0", "end").strip()

        def worker() -> None:
            result = api_get("/memory", {"query": query, "limit": 18}, timeout=45.0)
            self.event_queue.put(("memory", result))

        threading.Thread(target=worker, daemon=True).start()

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

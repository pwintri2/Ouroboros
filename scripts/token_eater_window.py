#!/usr/bin/env python3
"""Small paste window for feeding Google/Microsoft tokens to Ouroboros.

Purpose:
    Show one local GUI window where Philip can paste notepad text such as
    "Google -->" plus token and "Microsoft -->" plus token, then press OK.
Inputs:
    Pasted text containing Google and/or Microsoft token sections.
Outputs:
    Correct `.secrets/*_token.json` files via scripts/token_eater.py, with
    chmod 0600. Optional backend restart using start_ouroboros_sandbox_allow.sh.
Safety notes:
    Tokens are never printed to stdout or shown in status. The text area is
    cleared after a successful import.
Akkoord requirements:
    This local utility is for tokens Philip explicitly chooses to feed
    Ouroboros.

Why this change:
    A forgiving paste window removes the brittle manual .env/token-file step.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.resolve()
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from scripts.token_eater import eat_pasted_text  # noqa: E402
from scripts.oauth_token_wizard import GOOGLE_403_HELP, run_google_loopback_oauth, run_microsoft_device_oauth  # noqa: E402


class TokenEaterWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Ouroboros Token Eater")
        self.root.geometry("820x620")
        self.root.minsize(700, 520)
        self.root.bind("<Control-Return>", lambda _event: self.on_import())
        self.root.bind("<Alt-o>", lambda _event: self.on_import())

        self.restart_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Plak je Google/Microsoft tekst en druk op OK.")
        self.busy = False

        self._build()

    def _build(self) -> None:
        outer = tk.Frame(self.root, padx=14, pady=14)
        outer.pack(fill=tk.BOTH, expand=True)

        title = tk.Label(outer, text="Ouroboros Token Eater", font=("Sans", 16, "bold"), anchor="w")
        title.pack(fill=tk.X)

        help_text = (
            "Plak bijvoorbeeld:\n\n"
            "Google -->\n"
            "<google token>\n\n"
            "Google secret -->\n"
            "<google client secret indien je die hebt>\n\n"
            "Microsoft -->\n"
            "<microsoft token>\n\n"
            "Klik daarna eventueel op Google login of Microsoft login om echte access tokens op te halen.\n"
            "Tokenwaarden worden niet geprint en worden lokaal in .secrets/ gezet."
        )
        helper = tk.Label(outer, text=help_text, justify=tk.LEFT, anchor="w")
        helper.pack(fill=tk.X, pady=(8, 10))

        top_buttons = tk.Frame(outer)
        top_buttons.pack(fill=tk.X, pady=(0, 10))
        tk.Button(
            top_buttons,
            text="OK",
            command=self.on_import,
            width=18,
            height=2,
            default=tk.ACTIVE,
        ).pack(side=tk.LEFT)
        tk.Button(top_buttons, text="Google login", command=self.on_google_login, width=16, height=2).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(top_buttons, text="Google alles", command=self.on_google_full_login, width=14, height=2).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(top_buttons, text="Microsoft login", command=self.on_microsoft_login, width=16, height=2).pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(top_buttons, text="Sneltoets: Ctrl+Enter", anchor="w").pack(side=tk.LEFT, padx=(12, 0))

        frame = tk.Frame(outer)
        frame.pack(fill=tk.BOTH, expand=True)

        self.text = tk.Text(frame, wrap=tk.WORD, undo=True, height=16)
        scroll = tk.Scrollbar(frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        options = tk.Frame(outer)
        options.pack(fill=tk.X, pady=(10, 0))
        restart = tk.Checkbutton(options, text="Backend daarna herstarten", variable=self.restart_var)
        restart.pack(side=tk.LEFT)

        buttons = tk.Frame(outer)
        buttons.pack(fill=tk.X, pady=(10, 0))
        tk.Button(buttons, text="OK", command=self.on_import, width=18, height=2).pack(side=tk.LEFT)
        tk.Button(buttons, text="Google login", command=self.on_google_login, width=14, height=2).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(buttons, text="Google alles", command=self.on_google_full_login, width=14, height=2).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(buttons, text="Microsoft login", command=self.on_microsoft_login, width=14, height=2).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(buttons, text="Leegmaken", command=self.clear, width=12).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(buttons, text="Google 403 hulp", command=self.on_google_403_help, width=14).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(buttons, text="Sluiten", command=self.root.destroy, width=10).pack(side=tk.RIGHT)

        status = tk.Label(outer, textvariable=self.status_var, anchor="w", justify=tk.LEFT)
        status.pack(fill=tk.X, pady=(10, 0))

    def clear(self) -> None:
        self.text.delete("1.0", tk.END)
        self.status_var.set("Tekstvak leeggemaakt.")

    def on_import(self) -> None:
        if self.busy:
            messagebox.showinfo("Even wachten", "Er loopt al een import of login.")
            return
        pasted = self.text.get("1.0", tk.END).strip()
        if not pasted:
            messagebox.showwarning("Geen tekst", "Plak eerst je Google/Microsoft token tekst.")
            return

        result = eat_pasted_text(workspace=WORKSPACE, pasted_text=pasted)
        imported = int(result.get("imported_count") or 0)
        if imported <= 0:
            self.status_var.set("Geen tokens geimporteerd.")
            messagebox.showerror("Niet gelukt", _safe_result_message(result))
            return

        restart_status = ""
        if self.restart_var.get():
            restart_status = self._restart_backend()

        self.text.delete("1.0", tk.END)
        providers = [item.get("provider") for item in result.get("results", []) if item.get("status") == "success"]
        message = f"Geimporteerd: {', '.join(providers)}. Secrets staan in .secrets/."
        if restart_status:
            message += f" {restart_status}"
        self.status_var.set(message)
        messagebox.showinfo("Klaar", message)

    def on_google_login(self) -> None:
        self._run_login("google", scope_profile="workspace")

    def on_google_full_login(self) -> None:
        self._run_login("google", scope_profile="full")

    def on_microsoft_login(self) -> None:
        self._run_login("microsoft")

    def on_google_403_help(self) -> None:
        messagebox.showinfo("Google 403 hulp", GOOGLE_403_HELP)

    def _run_login(self, provider: str, scope_profile: str = "workspace") -> None:
        if self.busy:
            messagebox.showinfo("Even wachten", "Er loopt al een import of login.")
            return
        self.busy = True
        self.status_var.set(f"{provider.capitalize()} login wordt voorbereid...")

        def status(message: str) -> None:
            self.root.after(0, lambda: self.status_var.set(message))

        def worker() -> None:
            try:
                if provider == "google":
                    result = run_google_loopback_oauth(workspace=WORKSPACE, scope_profile=scope_profile, status=status)
                else:
                    result = run_microsoft_device_oauth(workspace=WORKSPACE, status=status)
                if result.get("status") == "success" and self.restart_var.get():
                    result["restart_status"] = self._restart_backend()
            except Exception as exc:
                result = {"status": "error", "provider": provider, "reason": str(exc), "secrets_returned": False}
            self.root.after(0, lambda: self._finish_login(result))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_login(self, result: dict) -> None:
        self.busy = False
        provider = str(result.get("provider") or "login")
        if result.get("status") != "success":
            message = _safe_result_message(result)
            self.status_var.set(f"{provider.capitalize()} login niet gelukt.")
            messagebox.showerror("Niet gelukt", message)
            return
        scopes = result.get("scopes") or []
        message = f"{provider.capitalize()} login klaar. Scopes: {len(scopes)}."
        if result.get("restart_status"):
            message += f" {result.get('restart_status')}"
        self.status_var.set(message)
        messagebox.showinfo("Klaar", message)

    def _restart_backend(self) -> str:
        script = WORKSPACE / "start_ouroboros_sandbox_allow.sh"
        if not script.exists():
            return "Backend niet herstart: startscript ontbreekt."
        try:
            proc = subprocess.run(
                [str(script)],
                cwd=str(WORKSPACE),
                text=True,
                capture_output=True,
                timeout=15,
            )
        except Exception as exc:
            return f"Backend herstart fout: {exc}"
        if proc.returncode == 0:
            return "Backend herstart."
        return "Backend herstart gaf een fout; check artifacts/backend_sandbox_allow.log."

    def run(self) -> None:
        self.root.mainloop()


def _safe_result_message(result: dict) -> str:
    safe = {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "message": result.get("message"),
        "hint": result.get("hint"),
        "results": [
            {
                "status": item.get("status"),
                "provider": item.get("provider"),
                "reason": item.get("reason"),
                "hint": item.get("hint"),
            }
            for item in result.get("results", [])
        ],
        "secrets_returned": False,
    }
    return json.dumps(safe, indent=2, sort_keys=True)


if __name__ == "__main__":
    TokenEaterWindow().run()

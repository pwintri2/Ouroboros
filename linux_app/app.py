#!/usr/bin/env python3
"""
Wintrip Grok — Native GTK4/libadwaita chat interface voor Linux/Pop!_OS.

Gebruik:
    python linux_app/app.py [--backend http://127.0.0.1:8000]

Vereisten (eenmalig):
    sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
    pip install requests python-dotenv

Het venster communiceert via HTTP met de FastAPI-backend (`controller/main.py`).
Als de backend nog niet draait, start dit script hem automatisch op in de
achtergrond (BACKEND_AUTOSTART=true in .env of standaard aan).
"""

import argparse
import os
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk, Pango  # noqa: E402

try:
    import requests
except ImportError:
    sys.exit("Installeer requests:  pip install requests")

from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("WINTRIP_BACKEND", "http://127.0.0.1:8000")
DEFAULT_MODEL = os.getenv("WINTRIP_DEFAULT_MODEL", "grok")
APP_ID = "nl.wintrip.GrokApp"
APP_VERSION = "1.0.0"
TITLE = "Wintrip — Grok"

# ──────────────────────────────────────────────
# Hulpfuncties
# ──────────────────────────────────────────────

def _start_backend_if_needed():
    """Probeer de backend te bereiken; start hem anders automatisch op."""
    try:
        requests.get(f"{BACKEND_URL}/health", timeout=2)
        return  # backend draait al
    except Exception:
        pass

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cmd = [sys.executable, "-m", "uvicorn", "controller.main:app",
           "--host", "127.0.0.1", "--port", "8000"]
    subprocess.Popen(cmd, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wacht max 10 s op de backend
    for _ in range(20):
        time.sleep(0.5)
        try:
            requests.get(f"{BACKEND_URL}/health", timeout=1)
            return
        except Exception:
            continue


def _post_ask(prompt: str, history: list, model: str, system_prompt: str | None) -> str:
    """Stuur een vraag naar de backend en geef het antwoord terug."""
    payload = {
        "prompt": prompt,
        "model": model,
        "history": history,
        "system_prompt": system_prompt,
    }
    try:
        r = requests.post(f"{BACKEND_URL}/ask", json=payload, timeout=120)
        r.raise_for_status()
        return r.json().get("response", "(geen antwoord)")
    except requests.exceptions.ConnectionError:
        return "⚠️ Backend niet bereikbaar. Controleer of de server draait."
    except Exception as e:
        return f"⚠️ Fout: {e}"


# ──────────────────────────────────────────────
# UI-componenten
# ──────────────────────────────────────────────

def _make_bubble(text: str, is_user: bool) -> Gtk.Box:
    """Maak een chatballon voor gebruiker of assistent."""
    outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    outer.set_margin_top(4)
    outer.set_margin_bottom(4)
    outer.set_margin_start(8)
    outer.set_margin_end(8)

    label = Gtk.Label(label=text)
    label.set_wrap(True)
    label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    label.set_selectable(True)
    label.set_xalign(0)
    label.set_max_width_chars(72)

    frame = Gtk.Frame()
    frame.set_child(label)
    label.set_margin_top(8)
    label.set_margin_bottom(8)
    label.set_margin_start(12)
    label.set_margin_end(12)

    if is_user:
        frame.add_css_class("card")
        outer.set_halign(Gtk.Align.END)
    else:
        frame.add_css_class("view")
        outer.set_halign(Gtk.Align.START)

    outer.append(frame)
    return outer


class WintripWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, backend_url: str, default_model: str):
        super().__init__(application=app)
        self.set_title(TITLE)
        self.set_default_size(780, 620)

        self._backend_url = backend_url
        self._model = default_model
        self._history: list[dict] = []
        self._system_prompt: str | None = None

        self._build_ui()

    # ── UI-opbouw ──────────────────────────────

    def _build_ui(self):
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        # Header
        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        # Model-kiezer
        self._model_combo = Gtk.ComboBoxText()
        for m in ["grok", "grok-3", "grok-3-mini", "ollama"]:
            self._model_combo.append_text(m)
        self._model_combo.set_active(0)
        self._model_combo.connect("changed", self._on_model_changed)
        header.pack_end(self._model_combo)

        # Reset-knop
        reset_btn = Gtk.Button(icon_name="edit-clear-symbolic")
        reset_btn.set_tooltip_text("Gesprek wissen")
        reset_btn.connect("clicked", self._on_reset)
        header.pack_start(reset_btn)

        # Hoofd-inhoud
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.set_vexpand(True)
        toolbar_view.set_content(main_box)

        # Chatscroll
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        main_box.append(scroll)

        self._chat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._chat_box.set_vexpand(True)
        scroll.set_child(self._chat_box)

        # Welkomstbericht
        self._append_bubble("Hoi! Ik ben Wintrip met Grok. Hoe kan ik je helpen? 🦅", is_user=False)

        # Invoer
        input_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_row.set_margin_top(8)
        input_row.set_margin_bottom(8)
        input_row.set_margin_start(12)
        input_row.set_margin_end(12)
        main_box.append(input_row)

        self._entry = Gtk.Entry()
        self._entry.set_hexpand(True)
        self._entry.set_placeholder_text("Typ hier je vraag…  (Enter = verstuur)")
        self._entry.connect("activate", self._on_send)
        input_row.append(self._entry)

        send_btn = Gtk.Button(label="Verstuur")
        send_btn.add_css_class("suggested-action")
        send_btn.connect("clicked", self._on_send)
        input_row.append(send_btn)

        # Statusbalk
        self._status_label = Gtk.Label(label="Klaar")
        self._status_label.add_css_class("caption")
        self._status_label.set_margin_bottom(4)
        main_box.append(self._status_label)

        self._scroll = scroll

    # ── Acties ────────────────────────────────

    def _append_bubble(self, text: str, is_user: bool):
        bubble = _make_bubble(text, is_user=is_user)
        self._chat_box.append(bubble)
        # Scroll naar beneden
        GLib.idle_add(self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        adj = self._scroll.get_vadjustment()
        adj.set_value(adj.get_upper())
        return False

    def _on_model_changed(self, combo):
        self._model = combo.get_active_text() or DEFAULT_MODEL

    def _on_reset(self, _btn):
        self._history.clear()
        for child in list(self._chat_box):
            self._chat_box.remove(child)
        self._append_bubble("Gesprek gewist. Waarmee kan ik je helpen? 🦅", is_user=False)

    def _on_send(self, _widget):
        prompt = self._entry.get_text().strip()
        if not prompt:
            return
        self._entry.set_text("")
        self._append_bubble(prompt, is_user=True)
        self._status_label.set_text("⏳ Grok denkt na…")
        self._entry.set_sensitive(False)

        # Stuur request in aparte thread om UI niet te blokkeren
        threading.Thread(target=self._ask_backend, args=(prompt,), daemon=True).start()

    def _ask_backend(self, prompt: str):
        response = _post_ask(
            prompt=prompt,
            history=self._history,
            model=self._model,
            system_prompt=self._system_prompt,
        )
        # Sla in geschiedenis op
        self._history.append({"role": "user", "content": prompt})
        self._history.append({"role": "assistant", "content": response})

        # Update UI vanuit hoofd-thread
        GLib.idle_add(self._show_response, response)

    def _show_response(self, text: str):
        self._append_bubble(text, is_user=False)
        self._status_label.set_text("Klaar")
        self._entry.set_sensitive(True)
        self._entry.grab_focus()
        return False


# ──────────────────────────────────────────────
# Applicatie-bootstrap
# ──────────────────────────────────────────────

class WintripApp(Adw.Application):
    def __init__(self, backend_url: str, default_model: str):
        super().__init__(application_id=APP_ID)
        self._backend_url = backend_url
        self._default_model = default_model
        self.connect("activate", self._on_activate)

    def _on_activate(self, _app):
        win = WintripWindow(
            app=self,
            backend_url=self._backend_url,
            default_model=self._default_model,
        )
        win.present()


def main():
    parser = argparse.ArgumentParser(description="Wintrip Grok — Native Linux GTK4 app")
    parser.add_argument("--backend", default=BACKEND_URL, help="Backend URL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Standaard AI-model")
    parser.add_argument("--no-autostart", action="store_true",
                        help="Start de backend NIET automatisch op")
    args = parser.parse_args()

    if not args.no_autostart:
        print("🔍 Backend controleren…")
        _start_backend_if_needed()

    app = WintripApp(backend_url=args.backend, default_model=args.model)
    sys.exit(app.run(sys.argv[:1]))


if __name__ == "__main__":
    main()

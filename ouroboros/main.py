"""
main.py – Ouroboros Proto 1  Demo UI

Venster met:
  • Invoerveld voor gebruikersopdrachten
  • "Start Demo"-knop  – activeert schermlezen + overlays
  • "Stop Demo"-knop   – stopt alles netjes
  • "About"-sectie     – info over Ouroboros Proto 1

Afhankelijkheden: customtkinter, de andere ouroboros-modules.
"""

from __future__ import annotations

import queue
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# Zorg dat imports vanuit de ouroboros-map werken wanneer dit bestand
# direct wordt uitgevoerd (bijv. python ouroboros/main.py)
sys.path.insert(0, str(Path(__file__).parent))

import customtkinter as ctk  # type: ignore

import internet_lookup
import nlp_engine
import screen_reader
import visual_overlay

# ---------------------------------------------------------------------------
# Kleuren & constanten
# ---------------------------------------------------------------------------
ACHTERGROND = "#1a1a2e"
ACCENT = "#e94560"
TEKST_KLEUR = "#eaeaea"
KNOP_KLEUR = "#16213e"
KNOP_HOVER = "#0f3460"
ABOUT_TEKST = (
    "Ouroboros Proto 1 – Demo Versie\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "Een autonome Windows-assistent die:\n"
    "  • UI-elementen detecteert via UIA & OCR\n"
    "  • Visuele aanwijzingen toont (rode pijlen)\n"
    "  • Gebruikersintenties herkent met NLP\n"
    "  • Basale vragen beantwoordt via lokale DB\n\n"
    "Platform  : Windows 10 / 11\n"
    "Versie    : Proto 1 (demo)\n"
    "Project   : WintripAI – Ouroboros\n"
)

_LOG_MAX_LINES = 200


class OuroborosApp(ctk.CTk):
    """Hoofd-demo-venster van Ouroboros Proto 1."""

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("Ouroboros Proto 1 – Demo")
        self.geometry("780x640")
        self.resizable(True, True)
        self.configure(fg_color=ACHTERGROND)

        self._demo_actief = False
        self._demo_thread: Optional[threading.Thread] = None
        self._log_queue: queue.Queue[str] = queue.Queue()

        self._bouw_ui()
        self._poll_log()

    # ------------------------------------------------------------------ #
    # UI opbouw                                                            #
    # ------------------------------------------------------------------ #

    def _bouw_ui(self) -> None:
        # Titelbalk
        titel = ctk.CTkLabel(
            self,
            text="🐍  Ouroboros Proto 1",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=ACCENT,
        )
        titel.pack(pady=(20, 4))

        subtitel = ctk.CTkLabel(
            self,
            text="Autonome Windows UI-assistent – Demo Versie",
            font=ctk.CTkFont(size=12),
            text_color="#888",
        )
        subtitel.pack(pady=(0, 16))

        # Invoerveld
        invoer_frame = ctk.CTkFrame(self, fg_color=KNOP_KLEUR, corner_radius=10)
        invoer_frame.pack(fill="x", padx=24, pady=(0, 12))

        ctk.CTkLabel(
            invoer_frame,
            text="Opdracht:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEKST_KLEUR,
        ).pack(anchor="w", padx=12, pady=(8, 0))

        self._invoer = ctk.CTkEntry(
            invoer_frame,
            placeholder_text='Bijv. "Open Kladblok" of "Hoe maak ik een screenshot?"',
            font=ctk.CTkFont(size=12),
            height=38,
        )
        self._invoer.pack(fill="x", padx=12, pady=(4, 12))
        self._invoer.bind("<Return>", lambda _: self._verwerk_opdracht())

        # Knoppen
        knop_frame = ctk.CTkFrame(self, fg_color="transparent")
        knop_frame.pack(pady=(0, 12))

        self._start_knop = ctk.CTkButton(
            knop_frame,
            text="▶  Start Demo",
            width=160,
            height=40,
            fg_color=ACCENT,
            hover_color="#c73652",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._start_demo,
        )
        self._start_knop.grid(row=0, column=0, padx=8)

        self._stop_knop = ctk.CTkButton(
            knop_frame,
            text="■  Stop Demo",
            width=160,
            height=40,
            fg_color="#333",
            hover_color="#555",
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled",
            command=self._stop_demo,
        )
        self._stop_knop.grid(row=0, column=1, padx=8)

        self._verwerk_knop = ctk.CTkButton(
            knop_frame,
            text="⚡  Verwerk Opdracht",
            width=180,
            height=40,
            fg_color=KNOP_HOVER,
            hover_color="#1a4a80",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._verwerk_opdracht,
        )
        self._verwerk_knop.grid(row=0, column=2, padx=8)

        # Log-paneel
        log_frame = ctk.CTkFrame(self, fg_color=KNOP_KLEUR, corner_radius=10)
        log_frame.pack(fill="both", expand=True, padx=24, pady=(0, 12))

        ctk.CTkLabel(
            log_frame,
            text="Activiteitslog",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEKST_KLEUR,
        ).pack(anchor="w", padx=12, pady=(8, 0))

        self._log = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Courier New", size=11),
            wrap="word",
            state="disabled",
        )
        self._log.pack(fill="both", expand=True, padx=12, pady=(4, 12))

        # About sectie (uitklapbaar)
        self._about_zichtbaar = False
        self._about_knop = ctk.CTkButton(
            self,
            text="ℹ  About",
            width=120,
            height=30,
            fg_color="transparent",
            border_color=ACCENT,
            border_width=1,
            text_color=ACCENT,
            hover_color="#2a1a2e",
            font=ctk.CTkFont(size=11),
            command=self._toggle_about,
        )
        self._about_knop.pack(pady=(0, 4))

        self._about_frame = ctk.CTkFrame(self, fg_color=KNOP_KLEUR, corner_radius=10)
        ctk.CTkLabel(
            self._about_frame,
            text=ABOUT_TEKST,
            font=ctk.CTkFont(family="Courier New", size=10),
            text_color=TEKST_KLEUR,
            justify="left",
        ).pack(padx=16, pady=12, anchor="w")

    # ------------------------------------------------------------------ #
    # Demo-logica                                                          #
    # ------------------------------------------------------------------ #

    def _start_demo(self) -> None:
        if self._demo_actief:
            return
        self._demo_actief = True
        self._start_knop.configure(state="disabled")
        self._stop_knop.configure(state="normal")
        self._log_schrijf("▶ Demo gestart – scherm wordt gescand...\n")

        self._demo_thread = threading.Thread(target=self._demo_loop, daemon=True)
        self._demo_thread.start()

    def _stop_demo(self) -> None:
        self._demo_actief = False
        visual_overlay.verberg_overlays()
        self._start_knop.configure(state="normal")
        self._stop_knop.configure(state="disabled")
        self._log_schrijf("■ Demo gestopt.\n")

    def _demo_loop(self) -> None:
        """Achtergrond-lus: scan + toon overlays elke ~3 seconden."""
        while self._demo_actief:
            elementen = screen_reader.lees_scherm()
            self._log_queue.put(
                f"[scan] {len(elementen)} element(en) gevonden "
                f"({sum(1 for e in elementen if e.bron == 'uia')} UIA, "
                f"{sum(1 for e in elementen if e.bron == 'ocr')} OCR, "
                f"{sum(1 for e in elementen if e.bron == 'stub')} stub)\n"
            )
            visual_overlay.toon_overlays(elementen[:8])  # Max 8 overlays

            for elem in elementen[:5]:
                self._log_queue.put(f"  • [{elem.type}] {elem.naam!r}\n")

            for _ in range(30):
                if not self._demo_actief:
                    break
                time.sleep(0.1)

        visual_overlay.verberg_overlays()

    def _verwerk_opdracht(self) -> None:
        tekst = self._invoer.get().strip()
        if not tekst:
            self._log_schrijf("⚠ Voer eerst een opdracht in.\n")
            return

        self._log_schrijf(f"\n─── Opdracht: {tekst!r} ───\n")

        intentie, score = nlp_engine.herken_intentie(tekst)
        self._log_schrijf(f"🧠 Intentie : {intentie} (score={score:.2f})\n")

        resultaat = internet_lookup.zoek(tekst)
        self._log_schrijf(f"🔍 Antwoord : {resultaat['antwoord']}\n")

        if resultaat.get("actie") == "open_app" and resultaat.get("app"):
            app_naam = resultaat["app"]
            self._log_schrijf(f"⚙  Actie   : applicatie openen → {app_naam}\n")
            self._open_app(app_naam)

    # Whitelist van toegestane applicatienamen (ter voorkoming van command injection)
    _APP_WHITELIST: frozenset[str] = frozenset({
        "notepad.exe",
        "explorer.exe",
        "calc.exe",
        "taskmgr.exe",
        "microsoft-edge:",
        "ms-settings:",
    })

    def _open_app(self, app_naam: str) -> None:
        import platform
        if platform.system() != "Windows":
            self._log_schrijf("   (Niet op Windows – app-start overgeslagen)\n")
            return

        if app_naam not in self._APP_WHITELIST:
            self._log_schrijf(f"   ✗ Niet-toegestane applicatie: {app_naam!r}\n")
            return

        import subprocess
        try:
            subprocess.Popen(["cmd", "/c", "start", "", app_naam], shell=False)  # noqa: S603
            self._log_schrijf(f"   ✓ Gestart: {app_naam}\n")
        except Exception as exc:
            self._log_schrijf(f"   ✗ Fout bij starten: {exc}\n")

    # ------------------------------------------------------------------ #
    # Hulpfuncties                                                         #
    # ------------------------------------------------------------------ #

    def _toggle_about(self) -> None:
        self._about_zichtbaar = not self._about_zichtbaar
        if self._about_zichtbaar:
            self._about_frame.pack(fill="x", padx=24, pady=(0, 12))
        else:
            self._about_frame.pack_forget()

    def _log_schrijf(self, tekst: str) -> None:
        """Thread-safe schrijven naar het logveld."""
        self._log_queue.put(tekst)

    def _poll_log(self) -> None:
        """Verwerk wachtende logberichten (draait in de main-thread)."""
        try:
            while True:
                bericht = self._log_queue.get_nowait()
                self._log.configure(state="normal")
                self._log.insert("end", bericht)

                # Trim als het logveld te groot wordt
                inhoud = self._log.get("1.0", "end-1c")
                regels = inhoud.splitlines()
                if len(regels) > _LOG_MAX_LINES:
                    self._log.delete("1.0", f"{len(regels) - _LOG_MAX_LINES}.0")

                self._log.see("end")
                self._log.configure(state="disabled")
        except queue.Empty:
            pass
        finally:
            self.after(200, self._poll_log)

    def on_sluiten(self) -> None:
        self._demo_actief = False
        visual_overlay.verberg_overlays()
        self.destroy()


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    app = OuroborosApp()
    app.protocol("WM_DELETE_WINDOW", app.on_sluiten)
    app.mainloop()


if __name__ == "__main__":
    main()

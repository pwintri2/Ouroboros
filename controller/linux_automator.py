"""Linux computer-access tools — vervangt mac_automator.py op Linux/Pop!_OS.

Biedt:
- open_app       : applicaties starten via xdg-open / gtk-launch
- run_command    : shell-commando uitvoeren en output teruggeven
- list_windows   : actieve vensters opvragen via wmctrl
- focus_window   : venster naar voren brengen
- type_text      : tekst intypen via xdotool
- take_screenshot: schermafbeelding maken via scrot of gnome-screenshot
- read_file      : bestandsinhoud veilig lezen
- write_file     : inhoud naar bestand schrijven (alleen in toegestane paden)
"""

import os
import shutil
import subprocess
import tempfile


ALLOWED_WRITE_DIRS = [
    os.path.expanduser("~/wintrip_output"),
    "/tmp",
    tempfile.gettempdir(),
]


def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str, str]:
    """Voer een subproces uit en geef (returncode, stdout, stderr) terug."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


class LinuxAutomator:
    # ------------------------------------------------------------------
    # Apps & vensters
    # ------------------------------------------------------------------

    @staticmethod
    def open_app(app_name: str) -> str:
        """Open een applicatie met xdg-open, gtk-launch of direct via naam."""
        # Probeer eerst gtk-launch (werkt op .desktop-bestanden)
        if shutil.which("gtk-launch"):
            code, _, _ = _run(["gtk-launch", app_name])
            if code == 0:
                return f"Wintrip: '{app_name}' is geopend."

        # Fallback: probeer de naam direct als commando
        if shutil.which(app_name):
            subprocess.Popen(  # noqa: S603
                [app_name],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return f"Wintrip: '{app_name}' is gestart."

        # Laatste fallback: xdg-open
        if shutil.which("xdg-open"):
            subprocess.Popen(  # noqa: S603
                ["xdg-open", app_name],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return f"Wintrip: Ik heb geprobeerd '{app_name}' te openen via xdg-open."

        return f"Wintrip: Kon '{app_name}' niet openen (gtk-launch en xdg-open niet gevonden)."

    @staticmethod
    def list_windows() -> str:
        """Geef een lijst van actieve vensters terug (via wmctrl)."""
        if not shutil.which("wmctrl"):
            return "wmctrl is niet geïnstalleerd (sudo apt install wmctrl)."
        code, stdout, _ = _run(["wmctrl", "-l"])
        return stdout if code == 0 else "Kon vensterlijst niet ophalen."

    @staticmethod
    def focus_window(window_title: str) -> str:
        """Breng een venster met de gegeven titel naar voren."""
        if not shutil.which("wmctrl"):
            return "wmctrl is niet geïnstalleerd."
        code, _, err = _run(["wmctrl", "-a", window_title])
        if code == 0:
            return f"Venster '{window_title}' is naar voren gebracht."
        return f"Kon venster niet focussen: {err}"

    # ------------------------------------------------------------------
    # Tekst & toetsenbord
    # ------------------------------------------------------------------

    @staticmethod
    def type_text(text: str) -> str:
        """Simuleer toetsaanslagen in het actieve venster via xdotool."""
        if not shutil.which("xdotool"):
            return "xdotool is niet geïnstalleerd (sudo apt install xdotool)."
        code, _, err = _run(["xdotool", "type", "--clearmodifiers", "--", text])
        if code == 0:
            return "Tekst is getypt."
        return f"Fout bij typen: {err}"

    # ------------------------------------------------------------------
    # Shell-commando
    # ------------------------------------------------------------------

    @staticmethod
    def run_command(command: str, timeout: int = 30) -> str:
        """Voer een shell-commando uit en geef de output terug.

        Let op: het commando wordt via de shell uitgevoerd zodat pipelining
        en shell-substitutie werken. Geef alleen vertrouwde invoer mee.
        """
        import shlex

        try:
            # Gebruik een expliciete args-lijst waar mogelijk voor veiligheid
            try:
                args = shlex.split(command)
                result = subprocess.run(  # noqa: S603
                    args,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except ValueError:
                # Fallback voor complexe shell-expressies (pijpen, omleidingen)
                result = subprocess.run(  # noqa: S602
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            output = result.stdout or result.stderr
            return output.strip() if output.strip() else "(geen output)"
        except subprocess.TimeoutExpired:
            return f"Commando heeft de tijdslimiet van {timeout}s overschreden."
        except Exception as e:
            return f"Fout bij uitvoeren commando: {str(e)}"

    # ------------------------------------------------------------------
    # Schermafbeelding
    # ------------------------------------------------------------------

    @staticmethod
    def take_screenshot(save_path: str | None = None) -> str:
        """Maak een schermafbeelding en sla hem op (standaard in /tmp)."""
        if save_path is None:
            save_path = os.path.join(tempfile.gettempdir(), "wintrip_screenshot.png")

        if shutil.which("scrot"):
            code, _, err = _run(["scrot", save_path])
        elif shutil.which("gnome-screenshot"):
            code, _, err = _run(["gnome-screenshot", "-f", save_path])
        elif shutil.which("import"):  # ImageMagick
            code, _, err = _run(["import", "-window", "root", save_path])
        else:
            return "Geen screenshot-tool gevonden (installeer scrot, gnome-screenshot of imagemagick)."

        if code == 0:
            return f"Screenshot opgeslagen: {save_path}"
        return f"Screenshot mislukt: {err}"

    # ------------------------------------------------------------------
    # Bestandsoperaties (veilig)
    # ------------------------------------------------------------------

    @staticmethod
    def read_file(path: str) -> str:
        """Lees een bestand en geef de inhoud terug."""
        expanded = os.path.expanduser(path)
        real = os.path.realpath(expanded)
        if not os.path.isfile(real):
            return f"Bestand niet gevonden: {path}"
        try:
            with open(real, encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception as e:
            return f"Fout bij lezen: {str(e)}"

    @staticmethod
    def write_file(path: str, content: str) -> str:
        """Schrijf inhoud naar een bestand (alleen toegestane mappen)."""
        expanded = os.path.expanduser(path)
        real = os.path.realpath(os.path.abspath(expanded))

        allowed = [os.path.realpath(os.path.expanduser(d)) for d in ALLOWED_WRITE_DIRS]
        if not any(real.startswith(d) for d in allowed):
            return (
                f"Schrijftoegang geweigerd voor '{path}'. "
                f"Toegestane mappen: {ALLOWED_WRITE_DIRS}"
            )

        os.makedirs(os.path.dirname(real), exist_ok=True)
        try:
            with open(real, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Bestand opgeslagen: {real}"
        except Exception as e:
            return f"Fout bij schrijven: {str(e)}"

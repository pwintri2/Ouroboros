"""
screen_reader.py – Schermlezen voor Ouroboros Proto 1 (Windows 10/11).

Detecteert zichtbare UI-elementen via:
  1. Windows UI Automation (pywinauto) – voor vensterhiërarchie & control-info.
  2. OCR via pytesseract + opencv – voor schermtekst die niet via UIA bereikbaar is.

Op niet-Windows-platforms wordt een stub teruggegeven zodat de rest van de
applicatie (inclusief tests) zonder pywinauto/pytesseract kan draaien.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field
from typing import List, Optional

_IS_WINDOWS = platform.system() == "Windows"

# Conditional imports – alleen op Windows
if _IS_WINDOWS:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
        import pytesseract  # type: ignore
        from PIL import ImageGrab  # type: ignore
        from pywinauto import Desktop  # type: ignore
        from pywinauto.application import Application  # type: ignore

        _DEPS_OK = True
    except ImportError as exc:
        print(f"[screen_reader] Waarschuwing: optionele dependency ontbreekt: {exc}", file=sys.stderr)
        _DEPS_OK = False
else:
    _DEPS_OK = False


@dataclass
class UIElement:
    """Gevonden UI-element op het scherm."""

    naam: str
    type: str                    # bijv. "Window", "Button", "Edit"
    rect: tuple[int, int, int, int]  # (left, top, right, bottom)
    tekst: str = ""
    enabled: bool = True
    bron: str = "uia"            # "uia" of "ocr"


def lees_scherm() -> List[UIElement]:
    """Detecteer alle zichtbare UI-elementen op het huidige scherm.

    Returns een lijst van :class:`UIElement` objecten.
    Op niet-Windows-platforms wordt een lege lijst teruggegeven.
    """
    if not _IS_WINDOWS or not _DEPS_OK:
        return _stub_elementen()

    elementen: List[UIElement] = []
    elementen.extend(_lees_via_uia())
    elementen.extend(_lees_via_ocr())
    return elementen


# ---------------------------------------------------------------------------
# Interne helpers
# ---------------------------------------------------------------------------

def _lees_via_uia() -> List[UIElement]:
    """Gebruik Windows UI Automation om vensters en controls te vinden."""
    try:
        desktop = Desktop(backend="uia")
        windows = desktop.windows()
    except Exception:
        return []

    resultaten: List[UIElement] = []
    for win in windows:
        try:
            rect = win.rectangle()
            elem = UIElement(
                naam=win.window_text() or "(geen titel)",
                type="Window",
                rect=(rect.left, rect.top, rect.right, rect.bottom),
                tekst=win.window_text() or "",
                enabled=win.is_enabled(),
                bron="uia",
            )
            resultaten.append(elem)

            # Kinderelements (knoppen, invoervelden)
            for ctrl in win.descendants(control_type="Button"):
                try:
                    crect = ctrl.rectangle()
                    resultaten.append(UIElement(
                        naam=ctrl.window_text() or "Knop",
                        type="Button",
                        rect=(crect.left, crect.top, crect.right, crect.bottom),
                        tekst=ctrl.window_text() or "",
                        enabled=ctrl.is_enabled(),
                        bron="uia",
                    ))
                except Exception:
                    continue
        except Exception:
            continue

    return resultaten


def _lees_via_ocr() -> List[UIElement]:
    """Maak een screenshot en extraheer tekst met pytesseract."""
    try:
        screenshot = ImageGrab.grab()
        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Tesseract OCR met bounding-box data
        data = pytesseract.image_to_data(
            gray,
            lang="nld+eng",
            output_type=pytesseract.Output.DICT,
        )

        resultaten: List[UIElement] = []
        for i, tekst in enumerate(data["text"]):
            if not tekst.strip():
                continue
            if int(data["conf"][i]) < 40:
                continue
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            resultaten.append(UIElement(
                naam=tekst.strip(),
                type="OCRText",
                rect=(x, y, x + w, y + h),
                tekst=tekst.strip(),
                bron="ocr",
            ))
        return resultaten
    except Exception:
        return []


def _stub_elementen() -> List[UIElement]:
    """Stub voor niet-Windows-platforms – geeft voorbeeldelementen terug."""
    return [
        UIElement("Kladblok [Demo]", "Window", (100, 100, 800, 600), "Kladblok", bron="stub"),
        UIElement("Nieuw", "Button", (110, 140, 170, 165), "Nieuw", bron="stub"),
        UIElement("Opslaan", "Button", (180, 140, 260, 165), "Opslaan", bron="stub"),
        UIElement("Teksteditor", "Edit", (100, 180, 800, 580), "", bron="stub"),
    ]


if __name__ == "__main__":
    print("Gevonden UI-elementen:")
    for elem in lees_scherm():
        print(f"  [{elem.type}] {elem.naam!r}  @ {elem.rect}  (bron={elem.bron})")

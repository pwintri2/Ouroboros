"""
visual_overlay.py – Visuele aanwijzingen voor Ouroboros Proto 1.

Toont transparante overlays (rode pijlen + tekstballonnen) boven gevonden
UI-elementen. Elke overlay is een titelbaarloos, klikdoorlatend PyQt5-venster
dat boven alle andere vensters zweeft.

Op niet-Windows-platforms (of als PyQt5 niet beschikbaar is) wordt een
console-stub gebruikt zodat de rest van de app gewoon functioneert.
"""

from __future__ import annotations

import sys
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from screen_reader import UIElement

# ---------------------------------------------------------------------------
# Beschikbaarheidscheck
# ---------------------------------------------------------------------------
try:
    from PyQt5 import QtCore, QtGui, QtWidgets  # type: ignore

    _QT_OK = True
except ImportError:
    _QT_OK = False

_overlays: List[object] = []  # Bijhouden van actieve overlay-vensters
_app: Optional[object] = None  # Gedeelde QApplication


# ---------------------------------------------------------------------------
# Publieke API
# ---------------------------------------------------------------------------

def toon_overlays(elementen: "List[UIElement]") -> None:
    """Toon rode-pijl/tekstballon overlays voor *elementen*.

    Verwijdert eventuele vorige overlays eerst.
    """
    verberg_overlays()

    if not elementen:
        return

    if _QT_OK:
        _toon_qt_overlays(elementen)
    else:
        _toon_console_overlays(elementen)


def verberg_overlays() -> None:
    """Verberg en vernietig alle actieve overlays."""
    global _overlays
    for ov in _overlays:
        try:
            ov.hide()  # type: ignore[union-attr]
            ov.deleteLater()  # type: ignore[union-attr]
        except Exception:
            pass
    _overlays = []


# ---------------------------------------------------------------------------
# Qt-implementatie
# ---------------------------------------------------------------------------

if _QT_OK:
    class _OverlayWindow(QtWidgets.QWidget):  # type: ignore[misc]
        """Transparant, klikdoorlatend overlayvenster met pijl en ballon."""

        def __init__(self, element: "UIElement") -> None:
            super().__init__(None, QtCore.Qt.WindowStaysOnTopHint |
                             QtCore.Qt.FramelessWindowHint |
                             QtCore.Qt.Tool)
            self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
            self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            self.setWindowFlag(QtCore.Qt.WindowTransparentForInput, True)

            l, t, r, b = element.rect
            breedte = max(r - l, 60)
            hoogte = max(b - t, 30)

            # Overlay iets groter dan het element voor de pijl+ballon
            overlay_breedte = breedte + 160
            overlay_hoogte = hoogte + 60
            self.setGeometry(l - 5, t - 50, overlay_breedte, overlay_hoogte)

            self._elem = element
            self._elem_breedte = breedte
            self._elem_hoogte = hoogte
            self.show()

        def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)

            rood = QtGui.QColor(220, 30, 30, 230)
            wit = QtGui.QColor(255, 255, 255, 240)
            zwart = QtGui.QColor(0, 0, 0, 255)

            # --- Tekstballon ---
            ballon_rect = QtCore.QRect(5, 0, min(len(self._elem.naam) * 8 + 20, 280), 34)
            painter.setBrush(QtGui.QBrush(wit))
            painter.setPen(QtGui.QPen(rood, 2))
            painter.drawRoundedRect(ballon_rect, 8, 8)

            painter.setPen(QtGui.QPen(zwart))
            font = QtGui.QFont("Segoe UI", 9)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                ballon_rect.adjusted(6, 2, -6, -2),
                QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                self._elem.naam[:35],
            )

            # --- Pijl (driehoek) naar beneden ---
            pijl_x = ballon_rect.left() + 20
            pijl_y = ballon_rect.bottom()
            pijl = QtGui.QPolygon([
                QtCore.QPoint(pijl_x, pijl_y),
                QtCore.QPoint(pijl_x + 10, pijl_y),
                QtCore.QPoint(pijl_x + 5, pijl_y + 12),
            ])
            painter.setBrush(QtGui.QBrush(rood))
            painter.setPen(QtGui.QPen(rood, 1))
            painter.drawPolygon(pijl)

            # --- Rode rand om het element ---
            elem_rect = QtCore.QRect(5, 46, self._elem_breedte, self._elem_hoogte)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(rood, 2, QtCore.Qt.DashLine))
            painter.drawRect(elem_rect)

            painter.end()


def _toon_qt_overlays(elementen: "List[UIElement]") -> None:
    global _app, _overlays

    if _app is None:
        existing = QtWidgets.QApplication.instance()
        _app = existing if existing else QtWidgets.QApplication(sys.argv)

    for elem in elementen[:15]:  # Maximaal 15 overlays tegelijk
        ov = _OverlayWindow(elem)
        _overlays.append(ov)


# ---------------------------------------------------------------------------
# Console-stub (niet-Windows of geen PyQt5)
# ---------------------------------------------------------------------------

def _toon_console_overlays(elementen: "List[UIElement]") -> None:
    print("[visual_overlay] STUB – Overlays zouden worden getoond voor:")
    for elem in elementen:
        print(f"  → [{elem.type}] {elem.naam!r} @ {elem.rect}")


if __name__ == "__main__":
    # Snelle smoke-test
    from screen_reader import lees_scherm

    gevonden = lees_scherm()
    print(f"Toon overlays voor {len(gevonden)} elementen...")
    toon_overlays(gevonden)

    if _QT_OK and _app is not None:
        import time
        time.sleep(3)
    verberg_overlays()
    print("Klaar.")

"""
test_ouroboros.py – Smoke-tests voor Ouroboros Proto 1 modules.

Draait op alle platforms (inclusief CI). Windows-specifieke
code-paden worden overgeslagen via stubs.
"""

import sys
import unittest
from pathlib import Path

# Zorg dat de ouroboros-map in het pad staat
sys.path.insert(0, str(Path(__file__).parent.parent / "ouroboros"))


class TestInternetLookup(unittest.TestCase):
    def setUp(self) -> None:
        import internet_lookup as il
        self.il = il

    def test_directe_match(self) -> None:
        result = self.il.zoek("kladblok")
        self.assertIn("kladblok", result["antwoord"].lower())

    def test_fuzzy_match(self) -> None:
        result = self.il.zoek("klaadbloek")  # typefout
        self.assertIsInstance(result, dict)
        self.assertIn("antwoord", result)

    def test_fallback(self) -> None:
        result = self.il.zoek("xyzzy_onbestaand_12345")
        self.assertIn("antwoord", result)

    def test_lege_query(self) -> None:
        result = self.il.zoek("")
        self.assertIn("antwoord", result)

    def test_screenshot_query(self) -> None:
        result = self.il.zoek("Hoe maak ik een screenshot?")
        self.assertIn("antwoord", result)
        self.assertEqual(result.get("actie"), "info")


class TestNLPEngine(unittest.TestCase):
    def setUp(self) -> None:
        import nlp_engine as ne
        self.ne = ne

    def test_open_app_intentie(self) -> None:
        intentie, score = self.ne.herken_intentie("Open Kladblok")
        self.assertEqual(intentie, "open_app")

    def test_stop_intentie(self) -> None:
        intentie, _ = self.ne.herken_intentie("Stop de demo")
        self.assertEqual(intentie, "stop")

    def test_info_intentie(self) -> None:
        intentie, _ = self.ne.herken_intentie("Hoe doe ik dit?")
        self.assertEqual(intentie, "info")

    def test_lege_tekst(self) -> None:
        intentie, score = self.ne.herken_intentie("")
        self.assertEqual(intentie, "onbekend")
        self.assertEqual(score, 0.0)

    def test_screenshot_intentie(self) -> None:
        intentie, _ = self.ne.herken_intentie("screenshot maken")
        self.assertEqual(intentie, "screenshot")

    def test_returntype(self) -> None:
        result = self.ne.herken_intentie("test input")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], str)
        self.assertIsInstance(result[1], float)


class TestScreenReader(unittest.TestCase):
    def setUp(self) -> None:
        import screen_reader as sr
        self.sr = sr

    def test_lees_scherm_retourneert_lijst(self) -> None:
        elementen = self.sr.lees_scherm()
        self.assertIsInstance(elementen, list)

    def test_stub_elementen_aanwezig(self) -> None:
        """Op niet-Windows moet de stub-fallback actief zijn."""
        import platform
        if platform.system() != "Windows":
            elementen = self.sr.lees_scherm()
            self.assertGreater(len(elementen), 0)
            self.assertTrue(all(e.bron == "stub" for e in elementen))

    def test_element_attributen(self) -> None:
        elementen = self.sr.lees_scherm()
        for elem in elementen:
            self.assertTrue(hasattr(elem, "naam"))
            self.assertTrue(hasattr(elem, "type"))
            self.assertTrue(hasattr(elem, "rect"))
            self.assertIsInstance(elem.rect, tuple)
            self.assertEqual(len(elem.rect), 4)


class TestVisualOverlay(unittest.TestCase):
    def setUp(self) -> None:
        import visual_overlay as vo
        import screen_reader as sr
        self.vo = vo
        self.sr = sr

    def test_verberg_overlays_geen_fout(self) -> None:
        """verberg_overlays() mag geen fout gooien, ook bij lege lijst."""
        self.vo.verberg_overlays()

    def test_toon_lege_lijst(self) -> None:
        """toon_overlays met lege lijst mag geen fout gooien."""
        self.vo.toon_overlays([])

    def test_toon_stub_elementen(self) -> None:
        """toon_overlays met stub-elementen mag geen fout gooien."""
        elementen = self.sr.lees_scherm()
        self.vo.toon_overlays(elementen)
        self.vo.verberg_overlays()


if __name__ == "__main__":
    unittest.main(verbosity=2)

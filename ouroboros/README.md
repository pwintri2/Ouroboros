# Ouroboros Proto 1 – Demo Versie

**Onderdeel van WintripAI · Windows 10/11 · Python 3.10+**

---

## Overzicht

Ouroboros Proto 1 is een autonome Windows UI-assistent die:

| Functie | Beschrijving | Module |
|---|---|---|
| **Schermlezen** | Detecteert vensters en controls via Windows UI Automation + OCR | `screen_reader.py` |
| **Visuele aanwijzingen** | Toont rode pijlen en tekstballonnen boven UI-elementen | `visual_overlay.py` |
| **NLP** | Herkent gebruikersintenties via transformers (met keyword-fallback) | `nlp_engine.py` |
| **Internet-opzoeking** | Beantwoordt vragen via een lokale mock-database | `internet_lookup.py` |
| **Demo-UI** | customtkinter venster met Start/Stop/About | `main.py` |

---

## Installatie

```bash
# 1. Basisvereisten (alle platforms)
pip install customtkinter Pillow

# 2. Windows-specifiek (schermlezen + overlays)
pip install pywinauto pytesseract opencv-python PyQt5

# 3. NLP-model (optioneel – vereist ~2 GB geheugen)
pip install transformers torch
```

> **Tesseract OCR** moet ook geïnstalleerd zijn:  
> Download van https://github.com/UB-Mannheim/tesseract/wiki  
> Voeg het installatiepad toe aan `PATH`.  
> Installeer ook het **Nederlandse taalpakket** (`nld`):  
> kies tijdens de Tesseract-installatie "Additional language data" → "Dutch".

---

## Gebruik

```bash
cd ouroboros
python main.py
```

Het venster opent met:
- **Invoerveld** – typ een opdracht in het Nederlands
- **▶ Start Demo** – start de automatische scansessie (elke 3 sec)
- **■ Stop Demo** – stopt alle overlays en het scannen
- **⚡ Verwerk Opdracht** – analyseer de getypte opdracht direct
- **ℹ About** – toon projectinformatie

### Voorbeeldopdrachten

| Opdracht | Verwacht gedrag |
|---|---|
| `Open Kladblok` | Intentie `open_app`, start `notepad.exe` |
| `Hoe maak ik een screenshot?` | Intentie `info`, toont uitleg |
| `Stop de demo` | Intentie `stop`, stopt scansessie |
| `volume aanpassen` | Intentie `info`, toont volumebeschrijving |

---

## Bestandsstructuur

```
ouroboros/
├── main.py              # Hoofd-UI (customtkinter)
├── screen_reader.py     # Schermlezen (pywinauto + pytesseract + opencv)
├── visual_overlay.py    # Visuele aanwijzingen (PyQt5)
├── nlp_engine.py        # Intentieherkenning (transformers / keyword-fallback)
├── internet_lookup.py   # Mock internet lookup (lokale JSON)
├── antwoorden.json      # Mock antwoorden-database
├── requirements.txt     # Python-afhankelijkheden
└── README.md            # Deze documentatie
```

---

## Platform-opmerkingen

- **Windows-only** functionaliteiten (pywinauto, pytesseract, PyQt5-overlays) degraderen
  graceful op macOS/Linux: de app start gewoon, maar gebruikt stub-data.
- Het NLP-model wordt bij eerste gebruik automatisch gedownload (~800 MB).  
  Als `transformers` niet geïnstalleerd is, wordt automatisch de keyword-fallback gebruikt.

---

*WintripAI · Ouroboros Proto 1 · Demo Versie*

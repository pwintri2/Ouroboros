```markdown
# Ouroboros Proto 1 - Demo Versie

**Een interactieve Windows-assistent die gebruikers helpt bij het bedienen van hun pc/laptop met visuele aanwijzingen, schermlezen, en natuurlijke taalcommando's.**

---
## 📌 Overzicht
Deze demo-versie van **Ouroboros Proto 1** is bedoeld om de kernfunctionaliteiten te demonstreren:
- **Schermlezen**: UI-elementen detecteren (vensters, knoppen) met OCR en Windows UI Automation.
- **Visuele aanwijzingen**: Rode pijltjes en tekstballonnen tonen om gebruikers te begeleiden.
- **Natuurlijke taal**: Eenvoudige commando's begrijpen (bijv. *"Open Kladblok"*).
- **Mock internet-opzoeking**: Voorbeeldantwoorden tonen voor veelgestelde vragen.

⚠️ **Demo-limitaties**:
- Gebruikt **mock-data** voor internet-opzoeking (geen echte API-calls).
- Werkt het beste met **standaard Windows-applicaties** (Kladblok, Verkenner, Instellingen).

---

## 🚀 Snelle Start

### Vereisten
- **Windows 10/11**
- **Python 3.9+**
- **Afhankelijkheden** (zie [`requirements.txt`](requirements.txt)):
  ```bash
  pip install -r requirements.txt
  ```
- **Tesseract OCR** (voor tekstherkenning):
  - Download en installeer [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki).
  - Voeg Tesseract toe aan je `PATH`.

---

### Installatie
1. Clone de repo en checkout de `demo-ouroboros-proto-1` branche:
   ```bash
   git clone https://github.com/pwintri2/wintripai.git
   cd wintripai
   git checkout demo-ouroboros-proto-1
   ```

2. Installeer afhankelijkheden:
   ```bash
   pip install -r requirements.txt
   ```

3. Start de demo:
   ```bash
   python main.py
   ```

---

## 🎛️ Gebruik
1. **Typ een commando** in het inputveld (bijv. *"Open Kladblok"* of *"Hoe maak ik een screenshot?"*).
2. Klik op **"Start Demo"**:
   - De applicatie detecteert het relevante venster/knop.
   - Een **rood pijltje** en **tekstballon** verschijnen om je te begeleiden.
3. Gebruik **"Stop Demo"** om de overlay te sluiten.

---
## 📂 Bestandsstructuur
```
demo-ouroboros-proto-1/
├── main.py                # Hoofdscript
├── nlp/
│   └── intentieherkenning.py  # NLP-logica
├── ui/
│   ├── overlay.py         # Visuele aanwijzingen (pijltjes/ballonnen)
│   └── demo_ui.py         # Hoofdvenster
├── data/
│   └── antwoorden.json    # Mock-antwoorden voor internet-opzoeking
└── requirements.txt       # Afhankelijkheden
```

---
## 🛠️ Aanpassingen
### 1. **Nieuwe commando's toevoegen**
Voeg regels toe aan `data/antwoorden.json`:
```json
{
  "Hoe verander ik mijn achtergrond": "Klik met rechts op je bureaublad > 'Aanpassen' > Kies een achtergrond.",
  "Open Verkenner": "Verkenner wordt geopend via de taakbalk."
}
```

### 2. **UI aanpassen**
Pas het uiterlijk aan in `ui/demo_ui.py`:
- Gebruik [`customtkinter`](https://customtkinter.tomschimansky.com/) voor thema's (donker/licht).
- Wijzig kleuren/lettertypes in de `Overlay`-klasse (`ui/overlay.py`).

### 3. **Schermlezen verbeteren**
- Pas de **OCR-instellingen** aan in `main.py` (bijv. taal voor Tesseract):
  ```python
  pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'  # Pas pad aan
  ```

---
## ⚠️ Bekende Limitaties
- **OCR-nauwkeurigheid**: Werkt het beste met standaard lettertypes en hoge contrasten.
- **Vensterdetectie**: Sommige moderne apps (bijv. UWP-apps) worden niet altijd herkend.
- **Prestaties**: NLP-model kan traag zijn op oudere machines (val terug op keyword-matching).

---
## 🤝 Bijdragen
Feedback en pull requests zijn welkom! Open een **issue** voor:
- Bugs of crashes.
- Nieuwe functionaliteiten (bijv. spraakherkenning).
- Verbeteringen voor de UI/UX.

---
## 📜 Licentie
Dit project valt onder de **MIT-licentie**. Zie [`LICENSE`](LICENSE) voor details.

---
💡 **Tip**: Voor de beste ervaring, gebruik de demo met **Kladblok**, **Verkenner**, of **Instellingen** open.
```

---
### **Hoe te gebruiken?**
1. Sla dit bestand op als `README.md` in de root van je `demo-ouroboros-proto-1` branche.
2. Pas de **paden** (bijv. Tesseract-installatie) en **voorbeelden** aan waar nodig.

---
### **Extra’s**
- Voeg een **screenshot** toe van de demo in actie (bijv. `docs/demo_screenshot.png`) en link deze in de README.
- Wil je een **korte demo-video** toevoegen? Host deze op YouTube/Loom en voeg de link toe.

Laat me weten als je specifieke onderdelen wilt aanpassen (bijv. meer focus op installatie of aanpassingen)!

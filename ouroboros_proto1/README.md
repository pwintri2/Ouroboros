# Ouroboros proto 1

Ouroboros proto 1 is een native desktop assistent voor Windows 10/11, macOS en Linux.

Features:

- GUI (geen terminal nodig tijdens gebruik)
- Schermcapture en visuele uitleg op screenshot
- Rode pijlen met tekstballonnetjes voor klik-instructies
- Optionele OCR via lokale Tesseract-installatie
- Internetinformatie ophalen via DuckDuckGo Instant Answer API

## Bouwen (compileerbare taal: Rust)

1. Installeer Rust via https://rustup.rs
2. Open deze map in terminal of editor task runner
3. Build:
    - Development: `cargo run`
    - Release: `cargo build --release`

Resultaat:

- Windows binary: `target/release/ouroboros_proto1.exe`
- macOS/Linux binary: `target/release/ouroboros_proto1`

## Zonder terminal gebruiken

- Windows 10/11:
   - Start `OuroborosProto1Setup.exe` en installeer de app.
   - Start daarna via Start Menu: Ouroboros proto 1.
   - De app is gebouwd met `windows_subsystem = "windows"`, dus zonder consolevenster.
- macOS:
   - Pak `OuroborosProto1-macos.zip` uit en open `OuroborosProto1.app` via Finder.
- Linux:
   - Gebruik `OuroborosProto1-x86_64.AppImage` of het desktop pakket.

## Standalone binaries voor alle platforms

Omdat native Windows/macOS binaries vanaf Linux lokaal vaak extra compilers nodig hebben, staat er een workflow klaar die op native runners bouwt:

- Workflow: `.github/workflows/ouroboros_proto1_build.yml`
- Resultaat artifacts:
   - `ouroboros-windows-installer-and-exe`
      - `OuroborosProto1Setup.exe`
      - `ouroboros_proto1.exe`
   - `ouroboros-macos-app`
      - `OuroborosProto1.app`
      - `OuroborosProto1-macos.zip`
   - `ouroboros-linux-appimage-and-desktop`
      - `OuroborosProto1-x86_64.AppImage`
      - `OuroborosProto1-linux-desktop.tar.gz`
      - `ouroboros_proto1`

Gebruik:

1. Push je branch naar GitHub
2. Open Actions tab
3. Start workflow "Build Ouroboros Proto 1" (of laat hem via push triggeren)
4. Download de drie artifacts

## Native packaging scripts per OS

Naast CI kun je op elk platform lokaal packagen met deze scripts:

- Windows (PowerShell): `packaging/windows/build_installer.ps1`
- macOS (bash): `packaging/macos/build_app.sh`
- Linux (bash): `packaging/linux/build_appimage.sh`

Linux script-output:

- `dist/OuroborosProto1-x86_64.AppImage`
- `dist/OuroborosProto1-linux-desktop.tar.gz`

## OCR (optioneel, voor scherm lezen)

Installeer Tesseract en zorg dat `tesseract` op PATH staat.

- Windows: UB Mannheim installer of `winget install tesseract`
- macOS: `brew install tesseract`
- Linux: `sudo apt install tesseract-ocr`

Zonder Tesseract blijft de app werken met screenshot + internet hints.

## Werking

1. Typ je doel in het veld "Wat wil je doen?"
2. Klik op "Analyseer hulp"
3. De app maakt een schermcapture, probeert OCR, haalt internetcontext op
4. Je ziet op de screenshot rode pijlen en tekstballonnen met stappen

## Proto-status

Dit is een prototype (Ouroboros proto 1):

- Kliklocaties zijn heuristisch en doelgericht (op basis van doeltekst + OCR-hints)
- Geen volledige computer vision object detectie in deze versie
- Ontworpen als basis voor verdere uitbreiding (bijv. model-based UI element detection)

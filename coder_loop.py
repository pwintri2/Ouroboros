import os
import subprocess
import sys
import re
import shutil
from datetime import datetime

# ==========================================
# CONFIGURATIE PADEN (Aangepast aan jouw Xcode structuur)
# ==========================================
XCODE_PROJECT_DIR = "/Users/philip/WintripApp/WintripAI/WintripAI"
XCODE_PROJECT_FILE = f"{XCODE_PROJECT_DIR}/WintripAI.xcodeproj"
TARGET_FILE = "/Users/philip/WintripApp/WintripAI/WintripAI/WintripAI/ContentView.swift"

# Veilige variabele voor markdown om chat-hallucinaties te voorkomen!
TRIPLE_BACKTICKS = '```'

def read_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"❌ [Voorzitter]: Bestand niet gevonden op pad: {filepath}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ [Voorzitter]: Fout bij het lezen: {e}")
        sys.exit(1)

def create_backup(filepath):
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.basename(filepath)
    backup_path = os.path.join(backup_dir, f"{filename}.{timestamp}.bak")
    try:
        shutil.copy2(filepath, backup_path)
        print(f"📦 [Voorzitter]: Backup gemaakt: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"❌ [Voorzitter]: Fout bij maken backup: {e}")
        return None

def write_file(filepath, content):
    match = re.search(r'```(?:swift)?\n(.*?)\n```', content, re.DOTALL)
    clean_content = match.group(1).strip() if match else content.strip()
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(clean_content)

def call_gemini(prompt):
    try:
        result = subprocess.run(['gemini', prompt], capture_output=True, text=True, check=True, encoding='utf-8')
        return result.stdout
    except Exception as e:
        print(f"❌ [Voorzitter]: Gemini CLI gaf een fout: {e}")
        return ""

def run_tester():
    print("🛠️  [Tester]: Xcode build wordt gestart op de achtergrond. Momentje...")
    try:
        result = subprocess.run(
            ['xcodebuild', '-project', XCODE_PROJECT_FILE, '-scheme', 'WintripAI', 'build'],
            capture_output=True, text=True, cwd=XCODE_PROJECT_DIR, encoding='utf-8'
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)

def run_coder_loop(task_description):
    print(f"\n" + "="*50)
    print(f"🎤 [Voorzitter]: Wintrip AI Team-overleg is geopend.")
    print(f"Missie: {task_description}")
    print("="*50 + "\n")

    current_code = read_file(TARGET_FILE)

    # --- ROL 2: GENERATOR ---
    print("👨‍💻 [Generator]: Bestudeert de huidige code en schrijft een nieuwe versie...")
    prompt_gen = f"""Je bent de Wintrip SwiftUI Lead Developer.
TAAK: {task_description}

REGELS WAAR JE JE STRIKT AAN HOUDT:
1. GEEN PLACEHOLDERS. Schrijf altijd de volledige, werkende code uit.
2. VERWIJDER NOOIT bestaande logica (zoals NetworkManager aanroepen of de DiffView pop-up).
3. Gebruik NOOIT `let` voor variabelen in een struct die later gewijzigd moeten worden; gebruik `var`.
4. In SwiftData (als je dat gebruikt), gebruik je arrays en voeg je objecten toe met `insert` in de modelContext.

HUIDIGE CODE:
{TRIPLE_BACKTICKS}swift
{current_code}
{TRIPLE_BACKTICKS}
Schrijf de VOLLEDIGE nieuwe code voor dit bestand. Geef uitsluitend het Swift codeblok terug.
"""
    proposed_code = call_gemini(prompt_gen)

    # --- ROL 3: KRITIKUS ---
    print("🧐 [Kritikus]: Beoordeelt de code van de Generator op syntaxfouten...")
    prompt_kritiek = f"""Je bent de Wintrip Lead Architect.
De Generator heeft deze code geschreven. Jouw taak is compiler-fouten voorkomen.
Kijk STRIKT naar:
Zijn er Duplicate Keys in ForEach? (Gebruik \\.self of Identifiable structs).
Ontbreken er sluit-haakjes }}?

VOORGESTELDE CODE:
{TRIPLE_BACKTICKS}swift
{proposed_code}
{TRIPLE_BACKTICKS}
Als je fouten vindt: Los ze op en geef de VOLLEDIGE gecorrigeerde code terug.
Als het perfect is: Geef exact dezelfde code terug. Geef uitsluitend het Swift codeblok.
"""
    final_code = call_gemini(prompt_kritiek)
    
    if not final_code.strip():
        final_code = proposed_code

    # --- ROL 1: VOORZITTER (De Human-in-the-Loop Check) ---
    print("\n" + "-"*40)
    print("👀 [Voorzitter]: HIER IS EEN SNEAK PEEK VAN DE NIEUWE CODE:")
    print("-"*40)

    lines = final_code.strip().split('\n')
    preview_lines = lines[:15] + ["\n... [Code overgeslagen voor overzicht] ...\n"] + lines[-15:] if len(lines) > 30 else lines
    print('\n'.join(preview_lines))
    print("-"*40)

    print(f"\n🎤 [Voorzitter]: Mag ik ContentView.swift overschrijven? (Ik maak eerst een backup!) (j/n)")
    if input("> ").strip().lower() != 'j':
        print("🛑 Afgebroken door Piloot. Er is niets gewijzigd.")
        return

    create_backup(TARGET_FILE)
    write_file(TARGET_FILE, final_code)
    print("✅ [Voorzitter]: Bestand succesvol overschreven.")

    # --- ROL 4: TESTER ---
    success, build_log = run_tester()

    if success:
        print("🎉 [Tester]: SUCCES! De code compileert foutloos.")
        print("🚀 [Voorzitter]: Druk op Cmd+R in Xcode om je nieuwe interface te bekijken!")
    else:
        print("❌ [Tester]: FOUT! De Xcode build is gecrasht. Foutmelding:")
        error_lines = [line for line in build_log.strip().split('\n') if 'error:' in line]
        print('\n'.join(error_lines[-10:]))
        
        print("\n🎤 [Voorzitter]: Wil je dat ik dit teruggeef voor een automatische fix? (j/n)")
        if input("> ").strip().lower() == 'j':
            new_task = f"Je vorige code crashte in Xcode. Fix deze error en geef de volledige, correcte code terug:\n{build_log[-1000:]}"
            run_coder_loop(new_task)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Gebruik: python3 coder_loop.py "Jouw instructie"')
    else:
        run_coder_loop(sys.argv[1])

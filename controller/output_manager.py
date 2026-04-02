import os

def get_output_base():
    """
    Geeft het absolute pad naar de veilige 'output' map.
    Dit is de enige toegestane plek voor bestandscreatie door de AI-agent.
    """
    # We bouwen het pad op vanaf de locatie van dit script naar de parent/output map.
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output"))
    return base_dir

def preview_file_creation(filename: str, content: str) -> dict:
    """
    FASE: ANALYSE & PLAN (Diff)
    Toont een preview van de aanstaande wijziging zonder iets op te slaan.
    Dit wordt ter goedkeuring aan de gebruiker getoond.
    """
    preview_limit = 250
    preview_text = content[:preview_limit] + ("..." if len(content) > preview_limit else "")
    
    return {
        "status": "Aanvraag tot creatie",
        "filename": filename,
        "preview": preview_text,
        "full_length": f"{len(content)} tekens",
        "target_directory": "WintripAI/output/",
        "instruction": "Bevestig met 'Ja' of 'Akkoord' om dit bestand definitief op te slaan."
    }

def save_approved_file(filename: str, content: str) -> str:
    """
    FASE: UITVOEREN
    Slaat het bestand definitief op in de output-map na menselijke goedkeuring.
    VEILIGHEIDSREGEL: Voorkomt Path Traversal door strikte path-validatie.
    """
    base_dir = get_output_base()
    
    # Maak het volledige doelpad en resolve naar een absoluut pad (lost ../ op)
    target_path = os.path.abspath(os.path.join(base_dir, filename))
    
    # VEILIGHEIDSCONTROLE: Mag niet buiten de output-map treden.
    if not target_path.startswith(base_dir):
        return f"[VEILIGHEIDSFOUT] Onveilige bestandslocatie gedetecteerd: '{filename}'. Creatie buiten de WintripAI/output/ map is geblokkeerd."
    
    try:
        # Maak eventuele submappen in de output-map aan (bijv. 'rapporten/v1/')
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return f"✅ SUCCESS: Bestand opgeslagen in: {os.path.relpath(target_path, os.getcwd())}"
    except Exception as e:
        return f"[FOUT] Kon bestand niet opslaan: {str(e)}"

if __name__ == "__main__":
    # Test validatie van de module
    print("--- Start Output Manager Veiligheidstest ---")
    
    demo_content = "Dit is een gegenereerd rapport door Wintrip AI.\n\nLocal-first is de toekomst."
    
    # Test 1: Preview genereren
    print("\n[Preview Test]:")
    print(preview_file_creation("test_rapport.txt", demo_content))
    
    # Test 2: Path Traversal blokkade
    print("\n[Path Traversal Test]:")
    print(save_approved_file("../config_hack.py", "malicious_code = True"))
    
    # Test 3: Correcte opslag (als test_rapport.txt)
    # print("\n[Opslag Test]:")
    # print(save_approved_file("test_rapport.txt", demo_content))

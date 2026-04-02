import os
import sys
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Voeg de project-root toe aan sys.path zodat we modules kunnen importeren
# Dit zorgt ervoor dat we `from controller.router` kunnen doen ongeacht waar we het script starten.
project_root = "/Users/philip/wintripai"
if project_root not in sys.path:
    sys.path.append(project_root)

# Importeer de lokale modules
try:
    from controller.router import AIRouter
    from controller.file_parser import read_local_file
    from controller.output_manager import preview_file_creation, save_approved_file
except ImportError as e:
    print(f"[FOUT] Kon modules niet laden: {e}")
    sys.exit(1)

# Laad omgevingsvariabelen
load_dotenv()

app = FastAPI(title="Wintrip Controller API")
router = AIRouter()

# --- Request Modellen ---

class TaskRequest(BaseModel):
    prompt: str
    tier: int = 3

class FileAnalyzeRequest(BaseModel):
    filename: str
    instruction: str = "Vat dit document samen in 3 bulletpoints."
    tier: int = 3

class SaveRequest(BaseModel):
    filename: str
    content: str

# --- Endpoints ---

@app.get("/status")
async def get_status():
    """
    Geeft de huidige status van de Wintrip Controller weer.
    """
    return {
        "status": "Wintrip Controller Active",
        "tier_3": "Ollama Standby"
    }

@app.post("/process")
async def process_task(request: TaskRequest):
    """
    Verwerkt een prompt via de router op de opgegeven tier.
    """
    try:
        response = router.process_task(request.prompt, request.tier)
        return {
            "response": response, 
            "tier": request.tier,
            "status": "Success"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze_file")
async def analyze_file(request: FileAnalyzeRequest):
    """
    Leest een lokaal bestand veilig in en laat de AI het analyseren.
    Combineert de File Parser (veiligheid) met de AI Router (verwerking).
    """
    # 1. Lees het bestand veilig in via de parser
    content = read_local_file(request.filename)
    
    # 2. Foutafhandeling voor de parser (bijv. Path Traversal of File Not Found)
    if content.startswith("[FOUT]") or content.startswith("[VEILIGHEIDSFOUT]") or content.startswith("[LEESFOUT]"):
        raise HTTPException(status_code=400, detail=content)
    
    # 3. Bouw de prompt voor de AI
    full_prompt = f"{request.instruction}\n\nDocument inhoud:\n{content}"
    
    # 4. Verwerk de samengestelde prompt via de router
    try:
        analysis = router.process_task(full_prompt, request.tier)
        return {
            "filename": request.filename,
            "tier": request.tier,
            "analysis": analysis,
            "status": "Success"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/preview_save")
async def preview_save(request: SaveRequest):
    """
    Genereert een preview van het bestand dat de AI wil aanmaken.
    Onderdeel van de Human-in-the-Loop flow.
    """
    return preview_file_creation(request.filename, request.content)

@app.post("/commit_save")
async def commit_save(request: SaveRequest):
    """
    Schrijft het bestand definitief weg naar de /output/ map.
    Dit is het enige schrijfpunt in de API waar bestanden aangemaakt kunnen worden.
    """
    result = save_approved_file(request.filename, request.content)
    
    if result.startswith("[VEILIGHEIDSFOUT]") or result.startswith("[FOUT]"):
        raise HTTPException(status_code=400, detail=result)
    
    return {"status": "Success", "message": result}

if __name__ == "__main__":
    import uvicorn
    # Start de server lokaal op poort 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)

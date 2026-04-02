import os
import sys
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

# Forceer het juiste pad
project_root = "/Users/philip/wintripai"
if project_root not in sys.path:
    sys.path.append(project_root)

try:
    from controller.ollama_client import OllamaClient
    from controller.router import AIRouter
    from controller.mail_executor import MailExecutor
    from controller.tools import extract_readable_text
    from controller.digestion import digest_text
    from controller.virtual_team import VirtualMeeting
except ImportError:
    from ollama_client import OllamaClient
    from router import AIRouter
    from mail_executor import MailExecutor
    from tools import extract_readable_text
    from digestion import digest_text
    from virtual_team import VirtualMeeting

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ollama = OllamaClient()
router = AIRouter(ollama_client=ollama)
mail_executor = MailExecutor()

# HIER ZIT DE MAGIE: FastAPI accepteert nu FILES in de rugzak!
class URLRequest(BaseModel):
    url: str

class TeamTask(BaseModel):
    task: str

class Query(BaseModel):
    prompt: str
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = None
    files: Optional[List[str]] = None # <--- DIT IS HET PAPIERTJE!

class PlanExecution(BaseModel):
    plan_text: str

@app.get("/status")
@app.get("/health")
async def health():
    return {"status": "online", "agent": "Wintrip"}

@app.get("/models")
async def get_models():
    models = ollama.list_models()
    return {"models": models}

@app.post("/keep-alive")
async def keep_alive():
    return {"status": "alive"}

@app.post("/ask")
@app.post("/process")
async def ask(query: Query):
    print(f"\n--- 🕵️‍♂️ API CALL CHECK ---")
    print(f"Gekozen Persona: {query.system_prompt}")
    print(f"Bestanden in rugzak: {query.files}")
    print(f"--------------------------\n")

    # We geven de files keurig door aan de router
    response = router.route_request(
        query.prompt, 
        model=query.model,
        history=query.history,
        system_prompt=query.system_prompt,
        files=query.files
    )
    return {"response": response, "tier": 3, "status": "Success"}

@app.post("/team/discuss")
async def discuss_task(request: TeamTask):
    meeting = VirtualMeeting(ollama_client=ollama)
    conversation_history = meeting.run_meeting(request.task)
    return conversation_history

@app.post("/execute_plan")
async def execute(request: PlanExecution):
    report = mail_executor.run_action_plan(request.plan_text)
    return {"report": report}

@app.post("/learn/url")
async def learn_url(request: URLRequest):
    try:
        url = request.url
        text = extract_readable_text(url)
        if not text or text.startswith("Error fetching or parsing URL:"):
            raise HTTPException(status_code=400, detail=f"Invalid URL or error fetching text: {text}")

        metadata = {"url": url}
        # In digestion.py, the argument is named source_metadata
        result = digest_text(text, source_metadata=metadata, collection_name="wintrip_knowledge")
        if not result:
            raise HTTPException(status_code=500, detail="Error processing text")

        return {
            "url": url,
            "text_length": len(text),
            "success": True
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
# ^^ WintripAI sys.path fix — added automatically ^^

import os
import sys
import uvicorn
import asyncio
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Dict, Optional
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse

# Forceer het juiste pad
project_root = "/app"
if project_root not in sys.path:
    sys.path.append(project_root)

from controller.knowledge_base import KnowledgeBase
try:
    from controller.ollama_client import OllamaClient
    from controller.router import AIRouter
    from controller.mail_executor import MailExecutor
    from controller.tools import extract_readable_text
    from controller.digestion import digest_text
    from controller.virtual_team import VirtualMeeting
    from controller.orchestrator import WintripOrchestrator
except ImportError:
    from ollama_client import OllamaClient
    from router import AIRouter
    from mail_executor import MailExecutor
    from tools import extract_readable_text
    from digestion import digest_text
    from virtual_team import VirtualMeeting
    from orchestrator import WintripOrchestrator

load_dotenv()

from provider_router import route_gemini, route_claude, route_provider, check_providers
from agent_runtime import get_orchestrator_config, get_agent_configs
import subprocess
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ollama = OllamaClient()
kb = KnowledgeBase()
router = AIRouter(ollama_client=ollama, kb=kb)
mail_executor = MailExecutor()

# Regiekamer / Orchestrator Instantie (Hergebruikt sandbox en reflector uit de router array)
orchestrator = WintripOrchestrator(ollama_client=ollama, sandbox=router.sandbox, reflector=router.reflector, kb=kb)
orchestrator_runtime = get_orchestrator_config()
agent_runtime = get_agent_configs(project_root=os.getenv("WINTRIP_PROJECT_ROOT", "/app"))
orchestrator.active_model = orchestrator_runtime.get("provider", "gemini")

# Expose important objects on app.state for API route modules
app.state.orchestrator = orchestrator
app.state.ollama = ollama
app.state.kb = kb
app.state.orchestrator_runtime = orchestrator_runtime
app.state.agent_runtime = agent_runtime

vergadertafel_state: dict = {}

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


# Backward-compatible Request model used by some endpoints
class QueryRequest(Query):
    provider: Optional[str] = None

class PlanExecution(BaseModel):
    plan_text: str

class OrchestrateRequest(BaseModel):
    task: str
    max_iterations: Optional[int] = 3

class InviteRequest(BaseModel):
    persona_id: str
    table_id: str

class ModelSwitchRequest(BaseModel):
    model: str
    provider: Optional[str] = None

class CommitSaveRequest(BaseModel):
    filename: str
    content: str

class RuntimeActionRequest(BaseModel):
    action: str

@app.get("/status")
@app.get("/health")
async def health():
    return {"status": "online", "agent": "Wintrip"}

@app.get("/models")
async def get_models():
    models = ollama.list_models()
    return {"models": models}

@app.get("/agent/config")
async def get_agent_config():
    return {
        "orchestrator": orchestrator_runtime,
        "agents": {k: vars(v) for k, v in agent_runtime.items()}
    }

@app.post("/keep-alive")
async def keep_alive():
    return {"status": "alive"}

@app.get("/api/search")
async def api_search(q: str, limit: int = 5):
    if not q.strip():
        return {"query": q, "results": []}
    try:
        results = kb.search(q, n_results=max(1, min(limit, 10)))
        return {"query": q, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...), ingest: bool = True):
    uploads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "uploads"))
    os.makedirs(uploads_dir, exist_ok=True)
    filename = os.path.basename(file.filename or "upload.bin")
    target = os.path.join(uploads_dir, filename)
    content = await file.read()
    with open(target, "wb") as fh:
        fh.write(content)

    ingested = False
    if ingest:
        try:
            ingested = kb.ingest_file(target)
        except Exception:
            ingested = False

    return {
        "status": "ok",
        "filename": filename,
        "path": target,
        "size": len(content),
        "ingested": ingested
    }

@app.post("/ask")
@app.post("/process")
async def ask(query: Query):
    print(f"\n--- 🕵️‍♂️ API CALL CHECK ---")
    print(f"Gekozen Persona: {query.system_prompt}")
    print(f"Bestanden in rugzak: {query.files}")
    print(f"Model Override: {query.model}")
    print(f"--------------------------\n")

    # Use active_model from orchestrator state if not specifically requested
    target_model = query.model if query.model else orchestrator.active_model

    # === RAG ENRICHMENT — ChromaDB geheugen in prompt injecteren ===
    rag_results = kb.search(query.prompt, n_results=5)
    enriched_prompt = query.prompt
    if rag_results:
        memory_lines = "\n".join([f"• {r['text']}" for r in rag_results])
        enriched_prompt = f"{query.prompt}\n\n[GEHEUGEN CONTEXT - Wintrip zijn geheugen]\n{memory_lines}"
        print(f"🧠 [RAG]: {len(rag_results)} herinneringen geïnjecteerd in prompt")
    else:
        print("🧠 [RAG]: Geen relevante herinneringen gevonden")
    # === EINDE RAG ENRICHMENT ===

    # We geven de files keurig door aan de router
    response = router.route_request(
        enriched_prompt, 
        model=target_model,
        history=query.history,
        system_prompt=query.system_prompt,
        files=query.files
    )
    return {"response": response, "tier": 3, "status": "Success"}

@app.post("/vergadertafel/invite")
async def invite_persona(req: InviteRequest):
    vergadertafel_state.setdefault(req.table_id, set()).add(req.persona_id)
    return {"status": "ok", "seated": list(vergadertafel_state.get(req.table_id, []))}

@app.post("/vergadertafel/remove")
async def remove_persona(req: InviteRequest):
    vergadertafel_state.get(req.table_id, set()).discard(req.persona_id)
    return {"status": "ok", "seated": list(vergadertafel_state.get(req.table_id, []))}

@app.get("/vergadertafel/{table_id}")
async def get_table_state(table_id: str):
    return {"table_id": table_id, "seated": list(vergadertafel_state.get(table_id, []))}

@app.post("/model/switch")
async def switch_model(req: ModelSwitchRequest):
    provider = (req.provider or "").lower().strip()
    orchestrator.active_model = req.model

    if provider in {"gemini", "groq", "claude", "openai", "codex", "chatgpt"}:
        orchestrator.runtime["provider"] = provider
    elif req.model not in {'chatgpt', 'claude', 'gemini', 'groq'}:
        ollama.model = req.model
        orchestrator.runtime["provider"] = "ollama"

    orchestrator.runtime["model"] = req.model
    app.state.orchestrator_runtime = orchestrator.runtime

    return {
        "status": "ok",
        "active_model": req.model,
        "provider": orchestrator.runtime.get("provider", "ollama")
    }

@app.post("/api/orchestrate")
@app.post("/orchestrate")
async def orchestrate_task(request: OrchestrateRequest):
    print(f"\n--- 🧠 REGIEKAMER API ---")
    print(f"Taak: {request.task}")
    print(f"--------------------------\n")
    
    # Voert autonoom een OODA loop uit tot hij op GREEN staat
    # Optionally explicitly pass active model, but orchestrator currently handles it internally
    result = orchestrator.execute_task(request.task, max_iterations=request.max_iterations)
    
    # We returnen direct de status (Success/Failed) plus eventueel final code.
    return result

@app.get("/api/stream/demo")
async def stream_demo(prompt: str = "Wintrip demo stream"):
    async def event_gen():
        chunks = [
            f"Observer intake: {prompt}",
            "Wintrip Developer onderzoekt backend-impact.",
            "Wintrip UI vertaalt dit naar Mission Control componenten.",
            "Wintrip Voorzitter valideert de sandbox-route.",
            "Voorzitter summary gereed."
        ]
        for idx, chunk in enumerate(chunks):
            yield f"data: {chunk}\n\n"
            await asyncio.sleep(0.45)
        yield "event: done\ndata: complete\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")

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

        # Update digest_text to not break, but ideally use kb singleton
        # the simplest is to just rely on digest_text doing what it does or calling kb.ingest directly
        # if the file doesn't have an ingest raw text function we will keep digest text logic but default to the right collection 
        metadata = {"url": url}
        from controller.knowledge_base import CHROMA_COLLECTION_NAME
        result = digest_text(text, source_metadata=metadata, collection_name=CHROMA_COLLECTION_NAME)
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

@app.post("/commit_save")
async def commit_save(req: CommitSaveRequest):
    from controller.output_manager import save_approved_file
    result = save_approved_file(req.filename, req.content)
    if "✅ SUCCESS" in result:
        return {"status": "Success", "message": result}
    else:
        return {"status": "Error", "detail": result}

@app.post("/commit_preview")
async def commit_preview(req: CommitSaveRequest):
    from controller.output_manager import preview_file_creation
    return preview_file_creation(req.filename, req.content)

@app.get("/runtime/status")
async def runtime_status():
    providers = check_providers()
    sandbox_ok = bool(getattr(router, 'sandbox', None) and getattr(router.sandbox, 'client', None))
    return {
        "status": "ok",
        "orchestrator": orchestrator.runtime,
        "providers": providers,
        "sandbox": {"available": sandbox_ok},
        "docker_socket": os.path.exists('/var/run/docker.sock')
    }

@app.post("/runtime/action")
async def runtime_action(req: RuntimeActionRequest):
    action = (req.action or '').strip().lower()
    if action == 'docker_ps':
        try:
            r = subprocess.run(['docker', 'ps', '--format', '{{.Names}}|{{.Status}}'], capture_output=True, text=True, timeout=10)
            lines = [line for line in r.stdout.splitlines() if line.strip()]
            return {"status": "ok", "action": action, "output": lines}
        except Exception as e:
            return {"status": "error", "action": action, "detail": str(e)}
    return {"status": "error", "action": action, "detail": "Unsupported runtime action"}


@app.post("/vergadertafel/chat")
async def vergadertafel_chat(query: QueryRequest):
    """Vergadertafel chat met provider-routing (OpenAI/Gemini/Claude/Ollama)."""
    provider = (getattr(query, "provider", None) or "ollama").lower()
    model    = getattr(query, "model", None) or ""
    sys_p    = getattr(query, "system_prompt", None)
    if provider in {"openai", "codex", "chatgpt", "gemini", "claude", "antigravity"}:
        resp = route_provider(provider, query.prompt, model or ("gpt-5.4" if provider in {"openai", "codex", "chatgpt"} else ""), system_prompt=sys_p)
    else:
        resp = router.route_request(query.prompt, model=model or "gemma4:latest", history=getattr(query, "history", []) or [])
    return {"response": resp, "provider": provider}

@app.get("/providers")
async def get_providers():
    from provider_router import check_providers
    return check_providers()


# Mount the preferred frontend (webui/dist if built, otherwise regiekamer) and serve SPA root
try:
    regiekamer_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "regiekamer"))
    webui_dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "webui", "dist"))
    webui_assets_dir = os.path.join(webui_dist_dir, "assets")

    if os.path.isdir(regiekamer_dir):
        app.mount("/static", StaticFiles(directory=regiekamer_dir), name="static")

    if os.path.isdir(webui_assets_dir):
        app.mount("/assets", StaticFiles(directory=webui_assets_dir), name="webui-assets")

    @app.get("/")
    async def serve_ui():
        webui_index = os.path.join(webui_dist_dir, "index.html")
        regiekamer_index = os.path.join(regiekamer_dir, "index.html")
        if os.path.exists(webui_index):
            return FileResponse(webui_index)
        if os.path.exists(regiekamer_index):
            return FileResponse(regiekamer_index)
        return {"status": "no-ui", "message": "No frontend found"}
except Exception as _e:
    print("[Frontend] mounting failed:", _e)


@app.get("/api/health")
async def api_health():
    return {"status": "ok", "service": "wintrip-ai", "phase": "7.X"}

# Try to auto-register optional API route modules (chat/models/persona)
try:
    from controller.api import chat_routes, model_routes, persona_routes
    if hasattr(chat_routes, "init_chat"):
        chat_routes.init_chat(app)
    if hasattr(model_routes, "init_models"):
        model_routes.init_models(app)
    if hasattr(persona_routes, "init_personas"):
        persona_routes.init_personas(app)
except Exception:
    # not fatal — these modules may not exist yet while developing
    pass

if __name__ == "__main__":
    # When running directly with `python controller/main.py` bind to 0.0.0.0
    # so the container publishes the port to the host correctly.
    uvicorn.run(app, host="0.0.0.0", port=8000)

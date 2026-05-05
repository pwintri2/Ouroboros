import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
# ^^ WintripAI sys.path fix — added automatically ^^

import os
import sys
import asyncio
import json
import math
import re
import threading
import time
import requests
import uvicorn
from types import SimpleNamespace
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, List, Dict, Optional
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

# Forceer het juiste pad zonder laptop/container-pad hard te coderen.
project_root = os.getenv("WINTRIP_PROJECT_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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

try:
    from controller.provider_router import route_gemini, route_claude, check_providers
except ImportError:
    from provider_router import route_gemini, route_claude, check_providers

try:
    from controller.ollama_router import allowed_available_models, ollama_router_status
except Exception:
    def allowed_available_models(models=None) -> tuple[str, ...]:
        return tuple(str(model) for model in (models or ()) if model)

    def ollama_router_status(list_models=None) -> dict[str, Any]:
        return {
            "allowed_models": [],
            "available_models": [],
            "roles": {},
            "default_model": "llama3.2:latest",
        }

try:
    from controller.ouroboros_status import compose_ouroboros_status
except Exception:
    compose_ouroboros_status = None

try:
    from controller.agent_tools import AgentToolRegistry
except Exception:
    AgentToolRegistry = None

try:
    from controller.self_training import self_training_step
except ImportError:
    self_training_step = None

try:
    from controller.multi_api_router import MultiAPIRouter
except ImportError:
    MultiAPIRouter = None

try:
    from controller.api_key_store import (
        delete_provider_api_key,
        load_provider_api_keys,
        provider_key_status,
        save_provider_api_key,
    )
except Exception:
    delete_provider_api_key = None
    load_provider_api_keys = None
    provider_key_status = None
    save_provider_api_key = None

try:
    from controller.ouroboros_self_context import (
        build_chat_context,
        get_self_context_status,
        record_chat_turn,
    )
except Exception:
    def build_chat_context(
        prompt: str,
        provider: str,
        model: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        conversation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        return {
            "conversation_id": conversation_id or f"cockpit:{provider}:{model}",
            "prompt": prompt,
            "system_prompt": system_prompt,
            "history": history or [],
            "self_context": {"enabled": False, "reason": "ouroboros_self_context unavailable"},
        }

    def get_self_context_status() -> dict[str, Any]:
        return {"status": "unavailable", "enabled": False, "fake_success": False}

    def record_chat_turn(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"status": "unavailable", "stored": False, "fake_success": False}

try:
    from controller.slash_agent_router import handle_slash_command, slash_command_catalog
except Exception:
    def handle_slash_command(*_args: Any, **_kwargs: Any) -> dict[str, Any] | None:
        return None

    def slash_command_catalog() -> dict[str, Any]:
        return {"status": "unavailable", "commands": {}, "fake_success": False}

try:
    from controller.api.browser_routes import init_browser_research
except Exception:
    def init_browser_research(app: Any) -> None:
        app.state.browser_research_routes_unavailable = True

try:
    from controller.ouroboros_model import build_model_runtime_pocket
    from controller.ouroboros_model import MODEL_NAME as OUROBOROS_MODEL_NAME
    from controller.ouroboros_model import prepare_ouroboros_create
except Exception:
    build_model_runtime_pocket = None
    OUROBOROS_MODEL_NAME = "ouroboros"
    prepare_ouroboros_create = None

try:
    from controller.api.training_routes import (
        BrowserTrainingRequest,
        init_training,
        _preview_payload,
        _remember_event,
        _safe_total_count,
        _store_training_snapshot,
        _training_collection,
    )
except Exception:
    BrowserTrainingRequest = None
    _preview_payload = None
    _remember_event = None
    _safe_total_count = None
    _store_training_snapshot = None
    _training_collection = None

    def init_training(app: Any, storage: Any) -> None:
        app.state.training_storage = storage
        app.state.training_events = []

try:
    from controller.api.trainer_pipeline_routes import init_trainer_pipeline
except Exception:
    def init_trainer_pipeline(app: Any) -> None:
        app.state.trainer_pipeline_routes_unavailable = True

try:
    from controller.api.agent_runtime_routes import init_agent_runtime
except Exception:
    def init_agent_runtime(app: Any) -> None:
        app.state.agent_runtime_routes_unavailable = True

try:
    from controller.api.ouroboros_esoteric_routes import init_ouroboros_esoteric
except Exception:
    def init_ouroboros_esoteric(app: Any) -> None:
        app.state.ouroboros_esoteric_routes_unavailable = True

try:
    from controller.api.world_agent_routes import init_world_agent
    from controller.world_agent import GROK_URL, ask_grok_via_world_agent, detect_world_intent, grok_frontend_url, search_world_memory, world_agent_status
except Exception:
    GROK_URL = "https://grok.com/"

    def init_world_agent(app: Any) -> None:
        app.state.world_agent_routes_unavailable = True

    def detect_world_intent(_prompt: object) -> Any:
        return None

    def ask_grok_via_world_agent(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"status": "unavailable", "route": "world_agent", "reason": "WorldAgent niet beschikbaar.", "fake_success": False}

    def search_world_memory(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"status": "unavailable", "route": "world_agent", "reason": "WorldAgent niet beschikbaar.", "matches": [], "fake_success": False}

    def world_agent_status() -> dict[str, Any]:
        return {"status": "unavailable", "reason": "WorldAgent niet beschikbaar.", "fake_success": False}

    def grok_frontend_url(_question: object = "") -> str:
        return GROK_URL

try:
    from controller.brave_search import brave_search_status, search_brave_llm_context, search_brave_web
except Exception:
    def brave_search_status() -> dict[str, Any]:
        return {"status": "unavailable", "provider": "brave", "configured": False, "fake_success": False}

    def search_brave_llm_context(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"status": "unavailable", "provider": "brave", "document": "", "fake_success": False}

    def search_brave_web(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"status": "unavailable", "provider": "brave", "matches": [], "fake_success": False}

try:
    from controller.fase8_agent import Fase8ToolDispatcher, get_fase8_runner
    from controller.external_capabilities import external_capabilities_status
except Exception:
    Fase8ToolDispatcher = None

    def get_fase8_runner(*_args: Any, **_kwargs: Any) -> Any:
        return None

    def external_capabilities_status() -> dict[str, Any]:
        return {"status": "unavailable", "capabilities": {}, "reason": "Fase8 capabilities niet beschikbaar.", "fake_success": False}

try:
    from controller.safe_shell import run_safe_shell
except Exception:
    def run_safe_shell(command: str, approval: str = "", timeout: int = 20) -> dict[str, Any]:
        return {
            "status": "error",
            "command": command,
            "stdout": "",
            "stderr": "safe_shell module niet beschikbaar",
            "reason": "safe_shell module niet beschikbaar",
            "exit_code": None,
        }

try:
    from controller.stream.storage import StreamStorage
except Exception:
    class StreamStorage:
        def __init__(self, collection: Any):
            self._collection = collection


class _UnavailableAgentTools:
    def __init__(self, *args: Any, **kwargs: Any):
        self.last_tool_result = None

    def status(self) -> dict[str, Any]:
        return {
            "status": "offline",
            "available_tools": [],
            "last_tool_result": self.last_tool_result,
            "autonomy": {"level": "offline", "label": "Agent tools niet beschikbaar"},
        }

    def run_tool(self, tool_name: str, args: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        self.last_tool_result = {
            "tool_name": tool_name,
            "status": "error",
            "result": {},
            "stdout": "",
            "stderr": "Agent tools module niet beschikbaar",
            "error": "Agent tools module niet beschikbaar",
            "stored_to_memory": False,
        }
        return self.last_tool_result


AgentToolRegistryClass = AgentToolRegistry or _UnavailableAgentTools
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
stream_storage = StreamStorage(collection=kb.collection)
init_training(app, storage=stream_storage)
init_browser_research(app)
init_trainer_pipeline(app)
init_agent_runtime(app)
init_ouroboros_esoteric(app)
init_world_agent(app)
app.state.self_modification_pipeline = {
    "status": "online",
    "approval_required": True,
    "stages": [
        {"name": "roo_tools", "status": "online"},
        {"name": "context", "status": "online"},
        {"name": "trainer_pipeline", "status": "online"},
        {"name": "preview_apply_test", "status": "approval_gated"},
    ],
    "last_run": None,
    "fake_success": False,
}
agent_tools = AgentToolRegistryClass(kb=kb, storage=stream_storage, app=app)

# Regiekamer / Orchestrator Instantie (Hergebruikt sandbox en reflector uit de router array)
orchestrator = WintripOrchestrator(ollama_client=ollama, sandbox=router.sandbox, reflector=router.reflector, kb=kb, agent_tools=agent_tools)
orchestrator.active_model = "ollama"
try:
    from controller.tool_bridge import run_tool_bridge

    orchestrator.configure_living_tools(
        agent_tools=agent_tools,
        world_ask=ask_grok_via_world_agent,
        world_search=search_world_memory,
        tool_bridge_runner=run_tool_bridge,
    )
except Exception:
    pass

vergadertafel_state: dict = {}

# HIER ZIT DE MAGIE: FastAPI accepteert nu FILES in de rugzak!
class URLRequest(BaseModel):
    url: str

class TeamTask(BaseModel):
    task: Optional[str] = None
    message: Optional[str] = None
    model: Optional[str] = None
    members: Optional[List[str]] = None
    training_context: Optional[str] = None

class Query(BaseModel):
    prompt: str
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = None
    files: Optional[List[str]] = None # <--- DIT IS HET PAPIERTJE!

class QueryRequest(Query):
    provider: Optional[str] = None

class CockpitChatRequest(BaseModel):
    prompt: str
    provider: Optional[str] = "ollama"
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    conversation_id: Optional[str] = None
    approval: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = None
    files: Optional[List[str]] = None
    include_tools: Optional[bool] = False
    include_tool_schemas: Optional[bool] = False
    tools: Optional[Any] = None
    role: Optional[str] = None

class ProviderApiKeyRequest(BaseModel):
    provider: str
    api_key: Optional[str] = None
    approval: Optional[str] = None
    delete: Optional[bool] = False

class OuroborosLoopStartRequest(BaseModel):
    prompt: Optional[str] = None
    browser_text: Optional[str] = None
    url: Optional[str] = "https://teachablemachine.withgoogle.com/train"
    target_hz: Optional[float] = None
    approval: Optional[str] = None
    test_selector: Optional[str] = None
    run_tests: Optional[bool] = False
    trigger_step: Optional[bool] = True

class PlanExecution(BaseModel):
    plan_text: str

class OrchestrateRequest(BaseModel):
    task: str
    max_iterations: Optional[int] = 3

class LivingActionRequest(BaseModel):
    prompt: str
    approval: Optional[str] = None
    max_iterations: Optional[int] = 3

class InviteRequest(BaseModel):
    persona_id: str
    table_id: str

class ModelSwitchRequest(BaseModel):
    model: str

class ShellCommandRequest(BaseModel):
    command: str
    approval: Optional[str] = None
    timeout: Optional[int] = 20

class AgentToolRequest(BaseModel):
    tool_name: str
    args: Optional[Dict[str, object]] = None

class TrainCycleRequest(BaseModel):
    text: str
    target_hz: Optional[float] = None
    approval: Optional[str] = None
    url: Optional[str] = "https://teachablemachine.withgoogle.com/train"
    test_selector: Optional[str] = None

class OuroborosModelRequest(BaseModel):
    base_model: Optional[str] = None
    force_refresh: Optional[bool] = False
    approval: Optional[str] = None
    execute: Optional[bool] = False

class BrowserResearchRequest(BaseModel):
    query: str
    url: Optional[str] = "https://teachablemachine.withgoogle.com/train"
    browser_text: Optional[str] = None
    target_hz: Optional[float] = None
    limit: Optional[int] = 5
    approval: Optional[str] = None

class BraveSearchRequest(BaseModel):
    query: str
    approval: Optional[str] = None
    limit: Optional[int] = 8
    llm_context: Optional[bool] = True

class PromptUnderstandingRequest(BaseModel):
    prompt: str
    context: Optional[str] = None
    model: Optional[str] = None

class TrainingIngestRequest(BaseModel):
    url: Optional[str] = "https://teachablemachine.withgoogle.com/train"
    browser_text: str
    title: Optional[str] = "Ouroboros Phase 1 ingest"
    approval: Optional[str] = None
    target_hz: Optional[float] = None

class SelfTrainingStepRequest(BaseModel):
    prompt: Optional[str] = None
    browser_text: Optional[str] = None
    url: Optional[str] = "https://teachablemachine.withgoogle.com/train"
    target_hz: Optional[float] = None
    approval: Optional[str] = None
    test_selector: Optional[str] = None
    run_tests: Optional[bool] = False

class InspectHippocampusRequest(BaseModel):
    limit: Optional[int] = 7

class BrowserChatGPTRequest(BaseModel):
    prompt: Optional[str] = None
    question: Optional[str] = None
    approval: Optional[str] = None
    conversation_id: Optional[str] = None
    store_question: Optional[bool] = True

class Fase8RunRequest(BaseModel):
    goal: str
    approval: Optional[str] = None
    max_iterations: Optional[int] = None
    continuous: Optional[bool] = False

class Fase8PlanRequest(BaseModel):
    goal: str

class Fase8ToolDispatchRequest(BaseModel):
    tool: Optional[str] = None
    args: Optional[Dict[str, object]] = None
    prompt: Optional[str] = None
    approval: Optional[str] = None

class CommitSaveRequest(BaseModel):
    filename: str
    content: str

@app.get("/status")
@app.get("/health")
async def health():
    try:
        memories = kb.collection.count()
    except Exception:
        memories = 0
    return {"status": "online", "agent": "Wintrip", "memories": memories, "training": "online"}

@app.get("/models")
async def get_models():
    raw_models = _raw_model_names()
    models = _safe_model_names(raw_models)
    ignored = [model for model in raw_models if model not in set(models)]
    return {"models": models, "local": models, "ignored_disallowed_models": ignored}

@app.post("/keep-alive")
async def keep_alive():
    return {"status": "alive"}

@app.post("/sandbox/shell")
async def sandbox_shell(req: ShellCommandRequest):
    return run_safe_shell(req.command, approval=req.approval or "", timeout=req.timeout or 20)

@app.get("/agent/status")
async def agent_status():
    return agent_tools.status()

@app.post("/agent/tool")
async def agent_tool(req: AgentToolRequest):
    return agent_tools.run_tool(req.tool_name, dict(req.args or {}))

@app.post("/agent/train-cycle")
async def agent_train_cycle(req: TrainCycleRequest):
    return agent_tools.run_tool(
        "training_ingest",
        {
            "text": req.text,
            "target_hz": req.target_hz,
            "approval": req.approval or "",
            "url": req.url or "https://teachablemachine.withgoogle.com/train",
            "test_selector": req.test_selector,
        },
    )

@app.get("/api/ouroboros/status")
@app.get("/api/ouroboros/model/status")
async def ouroboros_status():
    return _ouroboros_status_payload()

@app.post("/api/ouroboros/model/create")
@app.post("/api/ouroboros/model/create-flow")
async def ouroboros_model_create(req: OuroborosModelRequest):
    return _ouroboros_create_flow(req)

@app.post("/api/ouroboros/research/browser")
@app.post("/api/ouroboros/browser/research")
async def ouroboros_browser_research(req: BrowserResearchRequest):
    return _browser_research_payload(req)

@app.get("/api/ouroboros/search/brave/status")
async def ouroboros_brave_search_status():
    return brave_search_status()

@app.post("/api/ouroboros/search/brave")
async def ouroboros_brave_search(req: BraveSearchRequest):
    return _brave_search_payload(req)

@app.post("/api/ouroboros/prompt/understand")
async def ouroboros_prompt_understanding(req: PromptUnderstandingRequest):
    return _prompt_understanding_payload(req.prompt, context=req.context, model=req.model)

@app.post("/api/ouroboros/self-training/step")
async def ouroboros_self_training_step(req: SelfTrainingStepRequest):
    return _self_training_step_payload(req)

@app.post("/api/ouroboros/loop/start")
async def ouroboros_loop_start(req: OuroborosLoopStartRequest):
    return _ouroboros_loop_start_payload(req)

@app.post("/api/ouroboros/loop/pause")
async def ouroboros_loop_pause():
    return _ouroboros_loop_control_payload("paused")

@app.post("/api/ouroboros/loop/abort")
async def ouroboros_loop_abort():
    return _ouroboros_loop_control_payload("aborted")

@app.get("/api/ouroboros/loop/status")
async def ouroboros_loop_status():
    return _ouroboros_loop_status_payload()

@app.get("/api/fase8/status")
async def fase8_status():
    return _fase8_runner().status()

@app.get("/orchestrator/status")
@app.get("/api/orchestrator/status")
async def fase8_orchestrator_status():
    return _fase8_runner().status()

@app.get("/orchestrator/status/{task_id}")
@app.get("/api/orchestrator/status/{task_id}")
async def fase8_orchestrator_task_status(task_id: str):
    return _fase8_runner().get(task_id)

@app.post("/orchestrator/run")
@app.post("/api/orchestrator/run")
async def fase8_orchestrator_run(req: Fase8RunRequest):
    return _fase8_runner().run(
        req.goal,
        approval=req.approval or "",
        max_iterations=req.max_iterations,
        continuous=bool(req.continuous),
    )

@app.post("/orchestrator/stop/{task_id}")
@app.post("/api/orchestrator/stop/{task_id}")
async def fase8_orchestrator_stop(task_id: str):
    return _fase8_runner().stop(task_id)

@app.post("/api/fase8/plan")
async def fase8_plan(req: Fase8PlanRequest):
    return _fase8_runner().create_plan(req.goal)

@app.post("/api/fase8/tools/dispatch")
async def fase8_tool_dispatch(req: Fase8ToolDispatchRequest):
    dispatcher = _fase8_runner().dispatcher
    if req.tool:
        return dispatcher.dispatch(req.tool, dict(req.args or {}))
    choice = dispatcher.choose(req.prompt or "", approval=req.approval or "")
    result = dispatcher.dispatch(choice["tool"], dict(choice.get("args") or {}))
    return {"status": result.get("status", "unknown"), "choice": choice, "result": result, "fake_success": False}

@app.get("/api/fase8/external-capabilities")
async def fase8_external_capabilities():
    return external_capabilities_status()

@app.post("/api/ouroboros/training/ingest")
async def ouroboros_training_ingest(req: TrainingIngestRequest):
    return _training_ingest_payload(req)

@app.post("/api/ouroboros/hippocampus/inspect")
async def ouroboros_inspect_hippocampus(req: InspectHippocampusRequest):
    return _inspect_hippocampus_payload(limit=req.limit or 7)

@app.post("/api/ouroboros/chatgpt/browser")
async def ouroboros_ask_chatgpt_in_browser(req: BrowserChatGPTRequest):
    question = _normalize_chatgpt_question(req.question or req.prompt or "")
    if not question:
        raise HTTPException(status_code=400, detail="prompt of question is verplicht")
    understanding = _chatgpt_question_understanding(question, original_prompt=req.prompt or req.question or "")
    try:
        from controller.browser_research import chatgpt_browser_ask

        response = chatgpt_browser_ask(question=question, approval=req.approval)
        status = response.get("status", "error")
        self_context = _store_chatgpt_question_context(
            question=question,
            browser_response=response,
            understanding=understanding,
            conversation_id=req.conversation_id,
            enabled=bool(req.store_question),
        )
        stdout = json.dumps(
            {
                "question": question,
                "understanding": understanding,
                "browser": response,
                "self_context": self_context,
            },
            ensure_ascii=False,
            indent=2,
        )
        return {
            "status": status,
            "question": question,
            "understanding": understanding,
            "browser": response,
            "self_context": self_context,
            "diff_view": response.get("diff_view", ""),
            "flags": response.get("blocked_patterns", []),
            "stdout": stdout,
            "stderr": "" if status == "success" else (response.get("reason") or stdout),
            "learned": "ChatGPT vraag is begrepen en opgeslagen; browserantwoord is als UNTRUSTED browsercontent behandeld en gescrubd." if status == "success" else "ChatGPT vraag is begrepen; browseractie is veilig geblokkeerd of niet beschikbaar.",
            "mentor": "Self-context bewaart alleen de vraag en actie-samenvatting; browsercontent blijft buiten durable context tot expliciete ingest-review.",
            "next_action": "Preview Ingest" if status == "success" else response.get("next_action", "Vul Akkoord in en probeer opnieuw."),
        }
    except Exception as exc:
        self_context = _store_chatgpt_question_context(
            question=question,
            browser_response={"status": "error", "reason": str(exc), "browser_action_performed": False},
            understanding=understanding,
            conversation_id=req.conversation_id,
            enabled=bool(req.store_question),
        )
        return {
            "status": "error",
            "question": question,
            "understanding": understanding,
            "self_context": self_context,
            "stdout": json.dumps({"question": question, "understanding": understanding, "self_context": self_context}, ensure_ascii=False, indent=2),
            "stderr": str(exc),
            "learned": "ChatGPT browser automation faalde veilig.",
            "mentor": "Controleer of de ChatGPT-app lokaal beschikbaar is.",
            "next_action": "Gebruik Research Missing Knowledge of plak browsertekst handmatig.",
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
    orchestrator.active_model = req.model
    # Also update ollama instance default if it's an ollama model
    if req.model != 'chatgpt' and req.model != 'claude' and req.model != 'gemini' and req.model != 'groq':
        ollama.model = req.model
    return {"status": "ok", "active_model": req.model}

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

@app.post("/api/orchestrator/living-action")
@app.post("/orchestrator/living-action")
async def orchestrator_living_action(request: LivingActionRequest):
    method = getattr(orchestrator, "levendige_actie", None)
    if not callable(method):
        raise HTTPException(status_code=503, detail="Levendige Actie is niet beschikbaar op deze orchestrator")
    return await asyncio.to_thread(
        method,
        request.prompt,
        approval=request.approval or "",
        max_iterations=request.max_iterations or 3,
    )

@app.post("/team/discuss")
async def discuss_task(request: TeamTask):
    task = request.task or request.message
    if not task:
        raise HTTPException(status_code=400, detail="Field required: task or message")
    training_context = request.training_context or _current_training_context()
    meeting = VirtualMeeting(
        ollama_client=ollama,
        training_context=training_context,
        requested_model=request.model,
        tools=agent_tools,
    )
    conversation_history = meeting.run_meeting(task)
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


@app.post("/vergadertafel/chat")
async def vergadertafel_chat(query: QueryRequest):
    """Vergadertafel chat met provider-routing (Gemini/Claude/Ollama)."""
    provider = (getattr(query, "provider", None) or "ollama").lower()
    model    = getattr(query, "model", None) or ""
    sys_p    = getattr(query, "system_prompt", None)
    if provider == "gemini":
        resp = route_gemini(query.prompt, model=model or "gemini-2.5-pro", system_prompt=sys_p)
    elif provider == "claude":
        resp = route_claude(query.prompt, model=model or "claude-opus-4-6", system_prompt=sys_p)
    else:
        resp = router.route_request(query.prompt, model=model or "llama3.1:latest", history=getattr(query, "history", []) or [])
    return {"response": resp, "provider": provider}

@app.get("/providers")
async def get_providers():
    result = check_providers()
    try:
        models = ollama.list_models()
        result["ollama"] = {"available": bool(models), "models": models}
    except Exception:
        result["ollama"] = {"available": False, "models": []}
    return result

@app.get("/api/cockpit/config")
async def cockpit_config():
    return _cockpit_config_payload()

@app.post("/api/cockpit/chat")
async def cockpit_chat(req: CockpitChatRequest):
    return await _cockpit_chat_payload(req)

@app.get("/api/ouroboros/self-context/status")
async def ouroboros_self_context_status():
    return _self_context_status_payload()

@app.get("/api/cockpit/api-keys")
async def cockpit_api_keys():
    return _api_key_status_payload()

@app.post("/api/cockpit/api-keys")
async def cockpit_save_api_key(req: ProviderApiKeyRequest):
    return _save_api_key_payload(req)


def _ouroboros_capabilities() -> dict[str, dict[str, str]]:
    return {
        "model_status": {"method": "GET", "path": "/api/ouroboros/status"},
        "create_or_refresh_model": {"method": "POST", "path": "/api/ouroboros/model/create-flow"},
        "browser_research": {"method": "POST", "path": "/api/ouroboros/research/browser"},
        "brave_search": {"method": "POST", "path": "/api/ouroboros/search/brave"},
        "brave_search_status": {"method": "GET", "path": "/api/ouroboros/search/brave/status"},
        "ask_chatgpt_browser": {"method": "POST", "path": "/api/ouroboros/chatgpt/browser"},
        "prompt_understanding": {"method": "POST", "path": "/api/ouroboros/prompt/understand"},
        "training_ingest": {"method": "POST", "path": "/api/ouroboros/training/ingest"},
        "safe_shell": {"method": "POST", "path": "/sandbox/shell"},
        "run_tests": {"method": "POST", "path": "/agent/tool", "tool_name": "run_tests"},
        "inspect_hippocampus": {"method": "POST", "path": "/api/ouroboros/hippocampus/inspect"},
        "self_training_step": {"method": "POST", "path": "/api/ouroboros/self-training/step"},
        "self_context": {"method": "GET", "path": "/api/ouroboros/self-context/status"},
        "esoteric_status": {"method": "GET", "path": "/api/ouroboros/esoteric/status"},
        "akashic_recent": {"method": "GET", "path": "/api/ouroboros/esoteric/akashic/recent"},
        "living_ouroboros_status": {"method": "GET", "path": "/api/ouroboros/esoteric/living/status"},
        "living_ouroboros_tick": {"method": "POST", "path": "/api/ouroboros/esoteric/living/tick"},
        "living_ouroboros_memory": {"method": "GET", "path": "/api/ouroboros/esoteric/living/memory"},
        "quantum_nexus_status": {"method": "GET", "path": "/api/agent-runtime/nexus/status"},
        "world_agent_status": {"method": "GET", "path": "/api/world-agent/status"},
        "world_agent_grok_ask": {"method": "POST", "path": "/api/world-agent/grok/ask"},
        "world_agent_memory_search": {"method": "POST", "path": "/api/world-agent/memory/search"},
        "world_agent_recent_actions": {"method": "GET", "path": "/api/world-agent/actions/recent"},
        "tool_bridge_run": {"method": "POST", "path": "/api/agent-runtime/tools/run"},
        "fase8_status": {"method": "GET", "path": "/api/fase8/status"},
        "fase8_plan": {"method": "POST", "path": "/api/fase8/plan"},
        "fase8_tool_dispatch": {"method": "POST", "path": "/api/fase8/tools/dispatch"},
        "external_capabilities": {"method": "GET", "path": "/api/fase8/external-capabilities"},
        "living_action": {"method": "POST", "path": "/api/orchestrator/living-action"},
        "orchestrator_run": {"method": "POST", "path": "/orchestrator/run"},
        "orchestrator_status": {"method": "GET", "path": "/orchestrator/status/{task_id}"},
        "orchestrator_stop": {"method": "POST", "path": "/orchestrator/stop/{task_id}"},
        "slash_agents": {"method": "POST", "path": "/api/cockpit/chat", "prefix": "/"},
    }


APPROVAL_PHRASE = "Akkoord"
MULTI_API_PROVIDER_MODELS: dict[str, list[str]] = {
    "openai": ["gpt-4.1", "gpt-4.1-mini"],
    "anthropic": ["claude-opus-4-6", "claude-sonnet-4-6"],
    "google": ["gemini-2.5-flash", "gemini-2.5-pro"],
    "xai": ["grok-3", "grok-3-mini"],
    "mistral": ["mistral-large-latest", "mistral-small-latest"],
}
MULTI_API_KEY_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "xai": "XAI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}
PROVIDER_ALIASES: dict[str, str] = {
    "local": "ollama",
    "ollama": "ollama",
    "chatgpt": "openai",
    "claude": "anthropic",
    "anthropic": "anthropic",
    "gemini": "google",
    "google": "google",
    "grok": "xai",
    "xai": "xai",
}


def _safe_check_providers() -> dict[str, dict[str, Any]]:
    try:
        return check_providers()
    except Exception as exc:
        return {"provider_router": {"status": "error", "available": False, "reason": str(exc)}}


def _backend_status_payload(models: Optional[list[str]] = None) -> dict[str, Any]:
    try:
        memories = kb.collection.count()
    except Exception:
        memories = 0
    return {
        "status": "online",
        "agent": "Wintrip",
        "memories": memories,
        "training": "online",
        "models_available": len(models or []),
        "loop": _loop_summary(),
    }


def _provider_options_payload(models: Optional[list[str]] = None) -> dict[str, dict[str, Any]]:
    inventory_models = models or []
    models = _local_model_choices(inventory_models)
    inventory_online = bool(inventory_models)
    key_status = _api_key_status_payload().get("providers", {})
    options: dict[str, dict[str, Any]] = {
        "ollama": {
            "provider": "ollama",
            "label": "Local Ollama",
            "available": inventory_online,
            "enabled": bool(models),
            "local_only": True,
            "models": models,
            "default_model": _active_base(models),
            "status": "online" if inventory_online else "inventory_unavailable",
            "reason": (
                "Ollama model-inventaris is leeg of tijdelijk onbereikbaar; het lokale fallbackmodel blijft selecteerbaar."
                if not inventory_online
                else ""
            ),
            "inventory_models_available": len(inventory_models),
            "fallback_model": models[0] if models else "",
        }
    }
    for provider, model_options in MULTI_API_PROVIDER_MODELS.items():
        env_name = MULTI_API_KEY_ENV.get(provider, "")
        store_status = key_status.get(provider, {})
        configured = bool(os.getenv(env_name) or store_status.get("configured"))
        options[provider] = {
            "provider": provider,
            "label": provider.title(),
            "available": bool(MultiAPIRouter is not None and configured),
            "enabled": bool(MultiAPIRouter is not None and configured),
            "configured": configured,
            "key_source": store_status.get("source", "missing"),
            "masked_key": store_status.get("masked", ""),
            "local_only": False,
            "models": model_options,
            "default_model": model_options[0] if model_options else "",
            "status": "configured" if configured else "missing_api_key",
            "router_available": MultiAPIRouter is not None,
        }
    for provider, status in _safe_check_providers().items():
        if provider not in options:
            options[provider] = dict(status)
            options[provider].setdefault("provider", provider)
            options[provider].setdefault("models", status.get("models", []))
    return options


def _cockpit_config_payload() -> dict[str, Any]:
    raw_models = _raw_model_names()
    inventory_models = _safe_model_names(raw_models)
    models = _local_model_choices(inventory_models)
    ignored = [model for model in raw_models if model not in set(inventory_models)]
    provider_options = _provider_options_payload(inventory_models)
    return {
        "status": "online",
        "backend": _backend_status_payload(inventory_models),
        "providers": provider_options,
        "provider_options": provider_options,
        "available_models": {
            "ollama": models,
            "local": models,
            "ollama_inventory": inventory_models,
            "raw_local": raw_models,
            "ignored_disallowed_models": ignored,
            "multi_api": {provider: details.get("models", []) for provider, details in provider_options.items() if provider != "ollama"},
        },
        "models": models,
        "required_approval_phrase": APPROVAL_PHRASE,
        "approval": {"required_phrase": APPROVAL_PHRASE, "case_sensitive": True},
        "api_keys": _api_key_status_payload(),
        "self_context": _self_context_status_payload(),
        "slash_agents": slash_command_catalog(),
        "tool_schemas_available": callable(getattr(agent_tools, "get_tool_schemas", None)),
        "capabilities": {
            "cockpit_chat": {"method": "POST", "path": "/api/cockpit/chat"},
            "loop_start": {"method": "POST", "path": "/api/ouroboros/loop/start"},
            "loop_pause": {"method": "POST", "path": "/api/ouroboros/loop/pause"},
            "loop_abort": {"method": "POST", "path": "/api/ouroboros/loop/abort"},
            "loop_status": {"method": "GET", "path": "/api/ouroboros/loop/status"},
            "fase8_status": {"method": "GET", "path": "/api/fase8/status"},
            "fase8_plan": {"method": "POST", "path": "/api/fase8/plan"},
            "fase8_tool_dispatch": {"method": "POST", "path": "/api/fase8/tools/dispatch"},
            "fase8_external_capabilities": {"method": "GET", "path": "/api/fase8/external-capabilities"},
            "living_action": {"method": "POST", "path": "/api/orchestrator/living-action"},
            "orchestrator_run": {"method": "POST", "path": "/orchestrator/run"},
            "orchestrator_status": {"method": "GET", "path": "/orchestrator/status/{task_id}"},
            "orchestrator_stop": {"method": "POST", "path": "/orchestrator/stop/{task_id}"},
            **_ouroboros_capabilities(),
        },
    }


def _normalize_cockpit_provider(provider: Optional[str]) -> tuple[str, str]:
    requested = str(provider or "ollama").strip().lower() or "ollama"
    return requested, PROVIDER_ALIASES.get(requested, requested)


def _default_cockpit_model(provider: str, requested_model: Optional[str] = None) -> str:
    if requested_model:
        return requested_model
    if provider == "ollama":
        return _active_base(_safe_model_names())
    options = MULTI_API_PROVIDER_MODELS.get(provider) or []
    return options[0] if options else ""


def _agent_tool_schemas(provider: str = "openai") -> list[dict[str, Any]]:
    getter = getattr(agent_tools, "get_tool_schemas", None)
    if not callable(getter):
        base_schemas: list[dict[str, Any]] = []
    else:
        try:
            schemas = getter(provider=provider)
        except TypeError:
            schemas = getter()
        except Exception:
            schemas = []
        base_schemas = list(schemas or [])
    runner = _fase8_runner(allow_unavailable=True)
    if runner is not None:
        try:
            base_schemas.extend(runner.dispatcher.schemas())
        except Exception:
            pass
    return base_schemas


def _fase8_runner(allow_unavailable: bool = False) -> Any:
    try:
        runner = get_fase8_runner(agent_tools=agent_tools)
    except Exception:
        runner = None
    if runner is None and not allow_unavailable:
        raise HTTPException(status_code=503, detail="Fase 8 runner niet beschikbaar")
    return runner


def _requested_tool_payload(req: CockpitChatRequest, provider: str) -> list[dict[str, Any]]:
    if isinstance(req.tools, list):
        return [tool for tool in req.tools if isinstance(tool, dict)]
    wants_registry_tools = bool(req.include_tools or req.include_tool_schemas or req.tools is True)
    schema_provider = "openai" if provider in MULTI_API_PROVIDER_MODELS else provider
    return _agent_tool_schemas(provider=schema_provider) if wants_registry_tools else []


def _should_return_tool_schemas(req: CockpitChatRequest) -> bool:
    return bool(req.include_tools or req.include_tool_schemas or req.tools is True or isinstance(req.tools, list))


def _multi_api_router_instance() -> Any:
    key_map = _stored_api_keys()
    key_version = tuple(sorted((key, value[-8:]) for key, value in key_map.items()))
    existing = getattr(app.state, "multi_api_router", None)
    existing_version = getattr(app.state, "multi_api_router_key_version", None)
    if existing is not None and callable(getattr(existing, "route_chat", None)) and existing_version is None:
        return existing
    if existing is not None and callable(getattr(existing, "route_chat", None)) and existing_version == key_version:
        return existing
    if MultiAPIRouter is None:
        return None
    try:
        instance = MultiAPIRouter(api_keys=key_map)
        app.state.multi_api_router = instance
        app.state.multi_api_router_key_version = key_version
        return instance
    except Exception:
        return None


def _stored_api_keys() -> dict[str, str]:
    if callable(load_provider_api_keys):
        try:
            return load_provider_api_keys()
        except Exception:
            return {}
    return {}


def _api_key_status_payload() -> dict[str, Any]:
    if not callable(provider_key_status):
        return {
            "status": "unavailable",
            "providers": {},
            "error": "controller.api_key_store is niet beschikbaar",
            "secrets_returned": False,
        }
    try:
        return {
            "status": "online",
            "providers": provider_key_status(),
            "secrets_returned": False,
            "approval_required": True,
            "required_approval_phrase": APPROVAL_PHRASE,
        }
    except Exception as exc:
        return {
            "status": "error",
            "providers": {},
            "error": str(exc),
            "secrets_returned": False,
        }


def _self_context_status_payload() -> dict[str, Any]:
    try:
        return get_self_context_status()
    except Exception as exc:
        return {
            "status": "error",
            "enabled": False,
            "reason": str(exc),
            "fake_success": False,
        }


def _save_api_key_payload(req: ProviderApiKeyRequest) -> dict[str, Any]:
    if (req.approval or "").strip() != APPROVAL_PHRASE:
        return {
            "status": "blocked",
            "provider": req.provider,
            "stderr": f"API key opslag wacht op exact {APPROVAL_PHRASE}.",
            "secrets_returned": False,
        }
    try:
        if bool(req.delete):
            if not callable(delete_provider_api_key):
                raise RuntimeError("delete_provider_api_key unavailable")
            provider_status = delete_provider_api_key(req.provider)
            action = "deleted"
        else:
            if not callable(save_provider_api_key):
                raise RuntimeError("save_provider_api_key unavailable")
            provider_status = save_provider_api_key(req.provider, req.api_key or "")
            action = "saved"
        app.state.multi_api_router = None
        app.state.multi_api_router_key_version = None
        return {
            "status": "success",
            "action": action,
            "provider": provider_status.get("provider", req.provider),
            "key_status": provider_status,
            "secrets_returned": False,
            "next_action": "Kies de provider in de cockpit en stuur een testprompt.",
        }
    except Exception as exc:
        return {
            "status": "error",
            "provider": req.provider,
            "stderr": str(exc),
            "secrets_returned": False,
        }


def _disabled_chat_payload(req: CockpitChatRequest, provider: str, model: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "disabled",
        "provider": provider,
        "model": model,
        "response": "",
        "tool_schemas": tools if _should_return_tool_schemas(req) else [],
        "tool_schema_count": len(tools),
        "error": "MultiAPIRouter niet beschikbaar; no external API call was made.",
        "reason": "Externe provider-routing is disabled/unavailable in deze backend.",
        "local_only": True,
        "next_action": "Kies provider 'ollama' of configureer MultiAPIRouter met een expliciete API key.",
    }


def _slash_agent_timeout_seconds() -> int:
    try:
        return max(10, min(int(os.getenv("WINTRIP_SLASH_AGENT_TIMEOUT_SECONDS", "240")), 600))
    except ValueError:
        return 240


def _cockpit_chat_timeout_seconds() -> float:
    try:
        return max(3.0, min(float(os.getenv("WINTRIP_COCKPIT_CHAT_TIMEOUT_SECONDS", "75")), 85.0))
    except ValueError:
        return 75.0


def _cockpit_slash_dispatch_timeout_seconds() -> float:
    try:
        configured = float(os.getenv("WINTRIP_COCKPIT_SLASH_DISPATCH_TIMEOUT_SECONDS", "24"))
    except ValueError:
        configured = 24.0
    return max(3.0, min(configured, _cockpit_chat_timeout_seconds(), 28.0))


def _should_route_living_action(prompt: object) -> bool:
    method = getattr(orchestrator, "levendige_actie", None)
    if not callable(method):
        return False
    text = str(prompt or "").strip().lower()
    if not text or text.startswith("/"):
        return False
    if "grok.com" in text and "interessant" in text and any(marker in text for marker in ("denk", "reflect", "bewustzijn")):
        return True
    if text.startswith(("denk na", "reflecteer", "levendige actie")) and any(marker in text for marker in ("tool", "browser", "grok", "geheugen")):
        return True
    return False


async def _cockpit_chat_payload(req: CockpitChatRequest) -> dict[str, Any]:
    requested_provider, provider = _normalize_cockpit_provider(req.provider)
    model = _default_cockpit_model(provider, req.model)
    tools = _requested_tool_payload(req, provider)
    timeout_seconds = _cockpit_chat_timeout_seconds()
    slash_timeout_seconds = _cockpit_slash_dispatch_timeout_seconds()
    chat_context = build_chat_context(
        prompt=req.prompt,
        provider=provider,
        model=model,
        system_prompt=req.system_prompt,
        history=req.history or [],
        conversation_id=req.conversation_id,
    )
    try:
        slash_result = await asyncio.wait_for(
            asyncio.to_thread(
                handle_slash_command,
                req.prompt,
                approval=req.approval or "",
                timeout_seconds=_slash_agent_timeout_seconds(),
            ),
            timeout=slash_timeout_seconds,
        )
    except asyncio.TimeoutError:
        return _with_cockpit_self_context(
            _chat_timeout_payload(
                requested_provider=requested_provider,
                provider="slash",
                model=model,
                route="slash_agent",
                timeout_seconds=slash_timeout_seconds,
                local_only=True,
                tools=tools,
                return_tools=_should_return_tool_schemas(req),
            ),
            chat_context,
            provider,
            model,
        )
    if slash_result is not None:
        slash_result.setdefault("status", "success")
        slash_result.setdefault("provider", "slash")
        slash_result.setdefault("requested_provider", requested_provider)
        slash_result.setdefault("model", slash_result.get("agent", "slash"))
        slash_result.setdefault("route", "slash_agent")
        slash_result.setdefault("local_only", True)
        slash_result.setdefault("tool_schemas", [])
        slash_result.setdefault("tool_schema_count", 0)
        slash_result.setdefault("response", str(slash_result.get("message") or slash_result.get("reason") or ""))
        return _with_cockpit_self_context(slash_result, chat_context, provider, model, include_living_echo=False)

    if _should_route_living_action(req.prompt):
        method = getattr(orchestrator, "levendige_actie", None)
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    method,
                    req.prompt,
                    approval=req.approval or "",
                    max_iterations=3,
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            return _with_cockpit_self_context(
                _chat_timeout_payload(
                    requested_provider=requested_provider,
                    provider="ouroboros",
                    model="living-ooda-world",
                    route="living_action",
                    timeout_seconds=timeout_seconds,
                    local_only=False,
                    tools=tools,
                    return_tools=_should_return_tool_schemas(req),
                ),
                chat_context,
                provider,
                model,
            )
        if not isinstance(result, dict):
            result = {"status": "success", "response": str(result)}
        result.setdefault("status", "success")
        result.setdefault("provider", "ouroboros")
        result.setdefault("requested_provider", requested_provider)
        result.setdefault("model", "living-ooda-world")
        result.setdefault("route", "living_action")
        result.setdefault("local_only", False)
        result.setdefault("tool_schemas", tools if _should_return_tool_schemas(req) else [])
        result.setdefault("tool_schema_count", len(tools) if _should_return_tool_schemas(req) else 0)
        return _with_cockpit_self_context(result, chat_context, provider, model)

    world_intent = detect_world_intent(req.prompt)
    if world_intent is not None:
        world_action = str(getattr(world_intent, "action", "") or "")
        is_grok_intent = world_action.startswith("grok")
        grok_frontend_allowed = is_grok_intent and (req.approval or "").strip() == APPROVAL_PHRASE
        try:
            if world_action == "memory_search":
                result = await asyncio.wait_for(
                    asyncio.to_thread(search_world_memory, getattr(world_intent, "query", ""), limit=5),
                    timeout=min(timeout_seconds, 30.0),
                )
            else:
                grok_question = getattr(world_intent, "query", "") or "Open grok.com"
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        ask_grok_via_world_agent,
                        grok_question,
                        approval=req.approval or "",
                        open_tab=False,
                        submit=world_action != "grok_open",
                    ),
                    timeout=timeout_seconds,
                )
        except asyncio.TimeoutError:
            timeout_payload = _chat_timeout_payload(
                requested_provider=requested_provider,
                provider="world_agent",
                model="grok.com",
                route="world_agent",
                timeout_seconds=timeout_seconds,
                local_only=False,
                tools=tools,
                return_tools=_should_return_tool_schemas(req),
            )
            if grok_frontend_allowed:
                timeout_payload["frontend_action"] = _grok_frontend_action(question=getattr(world_intent, "query", ""))
                timeout_payload["frontend_note"] = (
                    "Cockpit opent de zichtbare Grok-tab ook als de host-bridge/Playwright ask vertraagt of timeout."
                )
            timeout_payload["world_intent"] = world_intent.to_dict() if callable(getattr(world_intent, "to_dict", None)) else {
                "action": world_action,
                "query": getattr(world_intent, "query", ""),
                "target": getattr(world_intent, "target", ""),
            }
            return _with_cockpit_self_context(
                timeout_payload,
                chat_context,
                provider,
                model,
            )
        if not isinstance(result, dict):
            result = {"status": "success", "response": str(result)}
        result.setdefault("status", "success")
        result.setdefault("provider", "world_agent")
        result.setdefault("requested_provider", requested_provider)
        result.setdefault("model", "grok.com")
        result.setdefault("route", "world_agent")
        result.setdefault("local_only", world_action == "memory_search")
        result.setdefault("tool_schemas", [])
        result.setdefault("tool_schema_count", 0)
        if grok_frontend_allowed:
            result.setdefault("frontend_action", _grok_frontend_action(result.get("action_id"), question=getattr(world_intent, "query", "")))
            result.setdefault(
                "frontend_note",
                "Cockpit opent de zichtbare Grok-tab; de host-bridge probeert de vraag apart via Playwright te stellen.",
            )
        result["world_intent"] = world_intent.to_dict() if callable(getattr(world_intent, "to_dict", None)) else {
            "action": getattr(world_intent, "action", ""),
            "query": getattr(world_intent, "query", ""),
            "target": getattr(world_intent, "target", ""),
        }
        return _with_cockpit_self_context(result, chat_context, provider, model)

    if provider == "ollama":
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    router.route_request,
                    chat_context.get("prompt") or req.prompt,
                    model=model,
                    history=chat_context.get("history") or [],
                    system_prompt=chat_context.get("system_prompt"),
                    files=req.files,
                ),
                timeout=timeout_seconds,
            )
            result = {
                "status": "success",
                "provider": "ollama",
                "requested_provider": requested_provider,
                "model": model,
                "response": response,
                "route": "local",
                "local_only": True,
                "tool_schemas": tools if _should_return_tool_schemas(req) else [],
                "tool_schema_count": len(tools),
            }
            return _with_cockpit_self_context(result, chat_context, provider, model)
        except asyncio.TimeoutError:
            return _with_cockpit_self_context(
                _chat_timeout_payload(
                    requested_provider=requested_provider,
                    provider="ollama",
                    model=model,
                    route="local",
                    timeout_seconds=timeout_seconds,
                    local_only=True,
                    tools=tools,
                    return_tools=_should_return_tool_schemas(req),
                ),
                chat_context,
                provider,
                model,
            )
        except Exception as exc:
            return {
                "status": "error",
                "provider": "ollama",
                "requested_provider": requested_provider,
                "model": model,
                "response": "",
                "route": "local",
                "local_only": True,
                "conversation_id": chat_context.get("conversation_id"),
                "self_context": chat_context.get("self_context") or {},
                "tool_schemas": tools if _should_return_tool_schemas(req) else [],
                "tool_schema_count": len(tools),
                "error": str(exc),
            }

    multi_router = _multi_api_router_instance()
    if multi_router is None:
        return _disabled_chat_payload(req, provider, model, tools)

    try:
        result = await asyncio.wait_for(
            multi_router.route_chat(
                provider=provider,
                model=model,
                prompt=chat_context.get("prompt") or req.prompt,
                system_prompt=chat_context.get("system_prompt"),
                tools=tools or None,
                history=chat_context.get("history") or [],
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        return _with_cockpit_self_context(
            _chat_timeout_payload(
                requested_provider=requested_provider,
                provider=provider,
                model=model,
                route="multi_api",
                timeout_seconds=timeout_seconds,
                local_only=False,
                tools=tools,
                return_tools=_should_return_tool_schemas(req),
            ),
            chat_context,
            provider,
            model,
        )
    if not isinstance(result, dict):
        result = {"status": "success", "response": str(result)}
    result.setdefault("status", "success")
    result.setdefault("response", result.get("message", ""))
    result["provider"] = result.get("provider") or provider
    result["requested_provider"] = requested_provider
    result["model"] = result.get("model") or model
    result["route"] = "multi_api"
    result["local_only"] = False
    result["tool_schemas"] = tools if _should_return_tool_schemas(req) else []
    result["tool_schema_count"] = len(tools)
    return _with_cockpit_self_context(result, chat_context, provider, model)


def _chat_timeout_payload(
    *,
    requested_provider: str,
    provider: str,
    model: str,
    route: str,
    timeout_seconds: float,
    local_only: bool,
    tools: list[dict[str, Any]],
    return_tools: bool,
) -> dict[str, Any]:
    seconds = int(round(timeout_seconds))
    reason = f"Chat provider exceeded backend timeout after {seconds}s."
    return {
        "status": "timeout",
        "provider": provider,
        "requested_provider": requested_provider,
        "model": model,
        "response": "",
        "route": route,
        "local_only": local_only,
        "error": reason,
        "reason": reason,
        "tool_schemas": tools if return_tools else [],
        "tool_schema_count": len(tools),
        "next_action": "Kies een sneller model of probeer opnieuw met een kortere prompt.",
        "fake_success": False,
    }


def _grok_frontend_action(action_id: object = None, question: object = "") -> dict[str, Any]:
    clean_question = str(question or "").strip()
    return {
        "type": "open_url",
        "url": grok_frontend_url(clean_question),
        "base_url": GROK_URL,
        "target": "_blank",
        "agent": "world_agent",
        "action_id": str(action_id or f"world_{int(time.time())}"),
        "question": clean_question,
        "auto_submit_hint": bool(clean_question),
    }


def _with_cockpit_self_context(
    result: dict[str, Any],
    chat_context: dict[str, Any],
    provider: str,
    model: str,
    *,
    include_living_echo: bool | None = None,
) -> dict[str, Any]:
    response = str(result.get("response") or result.get("message") or "")
    status = str(result.get("status") or "")
    self_context = dict(chat_context.get("self_context") or {})
    route = str(result.get("route") or "")
    attach_living_echo = route != "slash_agent" if include_living_echo is None else bool(include_living_echo)
    living_echo = _living_chat_echo() if attach_living_echo else {}
    if living_echo:
        result["living_echo"] = living_echo
    result["conversation_id"] = chat_context.get("conversation_id")
    if status == "success" and response.strip():
        try:
            self_context["last_store"] = record_chat_turn(
                prompt=str(chat_context.get("prompt") or ""),
                response=response,
                provider=provider,
                model=model,
                conversation_id=str(chat_context.get("conversation_id") or ""),
                status=status,
            )
        except Exception as exc:
            self_context["last_store"] = {"status": "error", "reason": str(exc), "fake_success": False}
    result["self_context"] = self_context
    return result


def _living_chat_echo() -> dict[str, Any]:
    try:
        from ouroboros_esoteric.ouroboros_consciousness_loop import living_status

        status = living_status(limit=8)
    except Exception:
        return {}
    thought = str(status.get("current_thought") or "").strip()
    whisper = str(status.get("last_whisper") or "").strip()
    if not thought and not whisper:
        return {}
    return {
        "current_thought": thought,
        "last_whisper": whisper,
        "running": bool(status.get("running")),
        "status": status.get("status", "unknown"),
        "memory_entry_count": (status.get("memory") or {}).get("entry_count", 0),
        "fake_success": False,
    }


def _raw_model_names() -> list[str]:
    try:
        raw = ollama.list_models() or []
    except Exception:
        raw = []
    names: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            name = item.get("name") or item.get("id") or item.get("model")
        else:
            name = item
        if name:
            names.append(str(name))
    return names


def _safe_model_names(raw_models: Optional[list[str]] = None) -> list[str]:
    raw = raw_models if raw_models is not None else _raw_model_names()
    return list(allowed_available_models(raw))


def _local_model_choices(models: Optional[list[str]] = None) -> list[str]:
    choices = list(models or [])
    if choices:
        return choices
    fallback = _active_base(choices)
    return [fallback] if fallback else []


def _active_base(models: Optional[list[str]] = None) -> str:
    models = models or []
    provider_ids = {
        "ollama",
        "chatgpt",
        "claude",
        "gemini",
        "groq",
        "openai",
        "anthropic",
        "google",
        "xai",
        "mistral",
    }
    current = str(getattr(orchestrator, "active_model", "") or "")
    if not current or current in provider_ids:
        current = str(getattr(ollama, "model", "") or "")
    elif not allowed_available_models([current]):
        current = ""
    if not current and models:
        current = models[0]
    return current or "llama3.2:latest"


def _ensure_ouroboros_model_state(models: Optional[list[str]] = None) -> dict[str, Any]:
    models = models or []
    model_exists = OUROBOROS_MODEL_NAME in models
    state = getattr(app.state, "ouroboros_model", None)
    if not isinstance(state, dict):
        state = {
            "created": model_exists,
            "online": model_exists,
            "active_base": _active_base(models),
            "updated_at": None,
            "create_flow": {
                "status": "idle",
                "created": model_exists,
                "flags": [],
                "next_action": "Create/Refresh Ouroboros Model",
            },
        }
        app.state.ouroboros_model = state
    else:
        state["created"] = model_exists
        state["online"] = model_exists
    return state


def _roo_adapter_status_payload(registry_status: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    if isinstance(registry_status, dict) and isinstance(registry_status.get("roo_adapter"), dict):
        return registry_status["roo_adapter"]
    state_value = getattr(app.state, "roo_adapter", None)
    if isinstance(state_value, dict):
        return state_value
    try:
        from controller.roo_tools import roo_tools_status

        return roo_tools_status()
    except Exception as exc:
        return {
            "status": "unavailable",
            "available": False,
            "reason": str(exc),
            "fake_success": False,
        }


def _ouroboros_status_payload(extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    models = _safe_model_names()
    model_state = _ensure_ouroboros_model_state(models)
    active_base = model_state.get("active_base") or _active_base(models)
    records = _hippocampus_records(limit=3)
    model_runtime = _model_runtime_pocket(active_base=active_base, records=records)
    last_tool = getattr(agent_tools, "last_tool_result", None) or {}
    research = getattr(app.state, "ouroboros_browser_research", None) or {
        "status": "idle",
        "last_query": "",
        "last_url": "",
        "flags": [],
    }
    router_status = ollama_router_status(list_models=lambda: models)
    try:
        registry_status = agent_tools.status()
    except Exception:
        registry_status = {}
    roo_adapter = _roo_adapter_status_payload(registry_status)
    self_modification = getattr(app.state, "self_modification_pipeline", None)
    selected_by_role = dict(router_status.get("selected_by_role") or {})
    role_overrides = {
        "Developer": selected_by_role.get("self_modification") or selected_by_role.get("code") or "",
        "Researcher": selected_by_role.get("research") or "",
        "Critic": selected_by_role.get("critic") or "",
        "Trainer": selected_by_role.get("default") or "",
        "Tester": selected_by_role.get("test") or "",
    }
    if compose_ouroboros_status is not None:
        ecosystem_extra = _ecosystem_status_extra()
        payload = compose_ouroboros_status(
            model_name=OUROBOROS_MODEL_NAME,
            available_models=models,
            active_base=active_base,
            role_model_overrides=role_overrides,
            provider_status=check_providers,
            agent_tools=agent_tools,
            last_tool_result=last_tool,
            records=records,
            geometry_11d=_geometry_11d(records=records),
            browser_research=research,
            model_state=model_state,
            capabilities=_ouroboros_capabilities(),
            roo_adapter=roo_adapter,
            self_modification_pipeline=self_modification,
            training_events=getattr(app.state, "training_events", []),
            extra={"ollama_router": router_status, "self_context": _self_context_status_payload(), **ecosystem_extra},
        )
        payload["fase8"] = _fase8_status_summary()
        payload["model_runtime"] = model_runtime
        if extra:
            payload.update(extra)
        return payload

    model_online = OUROBOROS_MODEL_NAME in models
    payload = {
        "status": "online",
        "model": {
            "name": OUROBOROS_MODEL_NAME,
            "online": model_online,
            "status": "online" if model_online else "offline",
            "active_base": active_base,
            "available_bases": models,
            "ollama_online": bool(models),
            "create_flow": model_state.get("create_flow", {}),
        },
        "active_base": active_base,
        "browser_research": research,
        "geometry_11d": _geometry_11d(records=records),
        "records": records,
        "model_runtime": model_runtime,
        "stdout": str(last_tool.get("stdout", "")),
        "stderr": str(last_tool.get("stderr") or last_tool.get("error") or ""),
        "ollama_router": router_status,
        "external_providers": check_providers(),
        "blocked_external_providers": list(check_providers().keys()),
        "roo_adapter": roo_adapter or {"status": "unavailable", "available": False},
        "self_context": _self_context_status_payload(),
        "last_tool_call": last_tool or {"status": "not_run"},
        "self_modification_pipeline": self_modification or {"status": "not_configured", "approval_required": True},
        "fase8": _fase8_status_summary(),
        "integrity": {"fake_fine_tune_success": False, "fake_tool_success": False},
        "learned": "Status gelezen: model, research, 11D geometry en Hippocampus records zijn beschikbaar.",
        "mentor": "Backend-first: gebruik Preview Ingest voordat iets in 11D Memory wordt opgeslagen.",
        "next_action": "Create/Refresh Ouroboros Model" if not model_online else "Research Missing Knowledge",
        "capabilities": _ouroboros_capabilities(),
        **_ecosystem_status_extra(),
    }
    if extra:
        payload.update(extra)
    return payload


def _model_runtime_pocket(active_base: str = "", records: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    record_count = 0
    if isinstance(records, dict):
        record_count = int(records.get("total_count") or records.get("training_collection_count") or 0)
    if callable(build_model_runtime_pocket):
        try:
            return build_model_runtime_pocket(
                "Ouroboros cockpit status",
                active_base=active_base,
                record_count=record_count,
            )
        except Exception as exc:
            return {"status": "error", "reason": str(exc), "dimension_count": 11, "fake_success": False}
    return {"status": "unavailable", "dimension_count": 11, "fake_success": False}


def _fase8_status_summary() -> dict[str, Any]:
    runner = _fase8_runner(allow_unavailable=True)
    if runner is None:
        return {"status": "unavailable", "fake_success": False}
    try:
        status = runner.status()
        return {
            "status": status.get("status", "unknown"),
            "task_count": status.get("task_count", 0),
            "tool_schema_count": status.get("tool_schema_count", 0),
            "external_capabilities": status.get("external_capabilities", {}),
            "fake_success": False,
        }
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "fake_success": False}


def _ecosystem_status_extra() -> dict[str, Any]:
    """Attach ecosystem adapter status without triggering live API calls."""
    try:
        from controller.ecosystem_status import get_ecosystem_status

        ecosystem = get_ecosystem_status()
        return {
            "ecosystem_adapters": ecosystem.get("ecosystem_adapters", {}),
            "crawl_stats": ecosystem.get("crawl_stats", {}),
            "program_inventory": ecosystem.get("program_inventory", {}),
            "host_sensory": ecosystem.get("host_sensory", {}),
            "ecosystem_knowledge": ecosystem.get("ecosystem_knowledge", {}),
            "brave_search": brave_search_status(),
        }
    except Exception as exc:
        return {
            "ecosystem_adapters": {},
            "crawl_stats": {"status": "unavailable", "reason": str(exc), "fake_success": False},
            "program_inventory": {"status": "unavailable", "reason": str(exc), "fake_success": False},
            "host_sensory": {"status": "unavailable", "reason": str(exc), "fake_success": False},
            "ecosystem_knowledge": {"status": "unavailable", "reason": str(exc), "fake_success": False},
            "brave_search": brave_search_status(),
        }


def _loop_summary() -> dict[str, Any]:
    state = _ensure_ouroboros_loop_state()
    return {
        "status": state.get("status", "idle"),
        "running": bool(state.get("running")),
        "queued": bool(state.get("queued")),
        "iteration": int(state.get("iteration", 0) or 0),
        "last_step_status": (state.get("last_step") or {}).get("status") if isinstance(state.get("last_step"), dict) else None,
        "updated_at": state.get("updated_at"),
    }


def _ensure_ouroboros_loop_state() -> dict[str, Any]:
    state = getattr(app.state, "ouroboros_loop", None)
    if not isinstance(state, dict):
        state = {
            "status": "idle",
            "running": False,
            "queued": False,
            "abort_requested": False,
            "pause_requested": False,
            "iteration": 0,
            "prompt": "",
            "last_step": None,
            "last_error": "",
            "started_at": None,
            "updated_at": None,
            "paused_at": None,
            "aborted_at": None,
        }
        app.state.ouroboros_loop = state
    return state


def _ensure_ouroboros_loop_lock() -> Any:
    lock = getattr(app.state, "ouroboros_loop_lock", None)
    if not (hasattr(lock, "acquire") and hasattr(lock, "release")):
        lock = threading.RLock()
        app.state.ouroboros_loop_lock = lock
    return lock


def _ouroboros_loop_status_payload(extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    state = dict(_ensure_ouroboros_loop_state())
    payload = {
        "status": state.get("status", "idle"),
        "loop": state,
        "running": bool(state.get("running")),
        "queued": bool(state.get("queued")),
        "iteration": int(state.get("iteration", 0) or 0),
        "last_step": state.get("last_step"),
        "required_approval_phrase": APPROVAL_PHRASE,
        "next_action": state.get("next_action") or "Start Loop",
    }
    if extra:
        payload.update(extra)
    return payload


def _ouroboros_loop_start_payload(req: OuroborosLoopStartRequest) -> dict[str, Any]:
    now = time.time()
    prompt = req.prompt or req.browser_text or "Ouroboros self-training loop"
    step_request = SelfTrainingStepRequest(
        prompt=prompt,
        browser_text=req.browser_text,
        url=req.url,
        target_hz=req.target_hz,
        approval=req.approval,
        test_selector=req.test_selector,
        run_tests=req.run_tests,
    )

    with _ensure_ouroboros_loop_lock():
        state = _ensure_ouroboros_loop_state()
        if state.get("running"):
            state.update(
                {
                    "status": "queued",
                    "queued": True,
                    "queued_prompt": prompt,
                    "updated_at": now,
                    "next_action": "Wacht tot de huidige self-training stap klaar is.",
                }
            )
            return _ouroboros_loop_status_payload({"message": "Loop is al bezig; startverzoek staat queued."})

        state.update(
            {
                "status": "running" if req.trigger_step else "queued",
                "running": bool(req.trigger_step),
                "queued": not bool(req.trigger_step),
                "abort_requested": False,
                "pause_requested": False,
                "prompt": prompt,
                "last_step": None,
                "last_error": "",
                "started_at": now,
                "updated_at": now,
                "next_action": "Self-training step draait op de achtergrond." if req.trigger_step else "Queued tot de cockpit de volgende stap start.",
            }
        )
        payload = _ouroboros_loop_status_payload(
            {
                "message": "Self-training stap is gestart op de achtergrond; poll /api/ouroboros/loop/status voor de uitkomst."
                if req.trigger_step
                else "Loop startverzoek staat queued; geen background loop gestart.",
                "background": bool(req.trigger_step),
            }
        )

    if req.trigger_step:
        _start_ouroboros_loop_worker(step_request)
    return payload


def _start_ouroboros_loop_worker(step_request: SelfTrainingStepRequest) -> None:
    thread = threading.Thread(
        target=_run_ouroboros_loop_step,
        args=(step_request,),
        name="ouroboros-loop-step",
        daemon=True,
    )
    app.state.ouroboros_loop_thread = thread
    thread.start()


def _run_ouroboros_loop_step(step_request: SelfTrainingStepRequest) -> None:
    state = _ensure_ouroboros_loop_state()
    try:
        step = _self_training_step_payload(step_request)
        step_status = str(step.get("status") or "success")
        if step_status == "blocked":
            loop_status = "blocked"
        elif step_status == "error":
            loop_status = "error"
        else:
            loop_status = "completed"
        with _ensure_ouroboros_loop_lock():
            if state.get("abort_requested"):
                loop_status = "aborted"
            elif state.get("pause_requested"):
                loop_status = "paused"
            state.update(
                {
                    "status": loop_status,
                    "running": False,
                    "queued": False,
                    "iteration": int(state.get("iteration", 0) or 0) + 1,
                    "last_step": step,
                    "last_error": str(step.get("stderr") or step.get("error") or "") if loop_status == "error" else "",
                    "updated_at": time.time(),
                    "next_action": step.get("next_action") or "Inspect Loop Status",
                }
            )
    except Exception as exc:
        with _ensure_ouroboros_loop_lock():
            state.update(
                {
                    "status": "error",
                    "running": False,
                    "queued": False,
                    "last_error": str(exc),
                    "updated_at": time.time(),
                    "next_action": "Inspect failing self-training step.",
                }
            )


def _ouroboros_loop_control_payload(action: str) -> dict[str, Any]:
    state = _ensure_ouroboros_loop_state()
    now = time.time()
    if action == "aborted":
        state.update(
            {
                "status": "aborted",
                "running": False,
                "queued": False,
                "abort_requested": True,
                "pause_requested": False,
                "last_step": None,
                "last_error": "",
                "aborted_at": now,
                "updated_at": now,
                "next_action": "Start Loop",
            }
        )
    else:
        state.update(
            {
                "status": "paused",
                "running": False,
                "queued": False,
                "pause_requested": True,
                "paused_at": now,
                "updated_at": now,
                "next_action": "Resume via Start Loop",
            }
        )
    return _ouroboros_loop_status_payload()


def _ouroboros_create_flow(req: OuroborosModelRequest) -> dict[str, Any]:
    models = _safe_model_names()
    active_base = req.base_model or _active_base(models)
    flags: list[str] = []
    if not models:
        flags.append("ollama_models_unavailable")
    elif active_base not in models:
        flags.append("active_base_not_in_ollama_list")

    plan_dict: dict[str, Any] = {
        "model_name": OUROBOROS_MODEL_NAME,
        "base_model": active_base,
        "execution_status": "prepare_unavailable",
        "valid": False,
        "validation_errors": ["controller.ouroboros_model niet beschikbaar"],
    }
    if prepare_ouroboros_create is not None:
        try:
            plan = prepare_ouroboros_create(
                root=project_root,
                available_models=models or [active_base],
                write_modelfile=True,
            )
            plan_dict = plan.as_dict()
            active_base = plan.base_model
        except Exception as exc:
            flags.append("modelfile_prepare_failed")
            plan_dict["validation_errors"] = [str(exc)]

    execution_result = None
    approved = (req.approval or "").strip() == APPROVAL_PHRASE
    if bool(req.execute):
        if not approved:
            flags.append("approval_required")
            execution_result = {
                "status": "blocked",
                "stdout": "",
                "stderr": "Ollama create wacht op Philip approval phrase: Akkoord.",
            }
        elif not plan_dict.get("valid"):
            flags.append("invalid_modelfile")
            execution_result = {
                "status": "blocked",
                "stdout": "",
                "stderr": "Modelfile validatie faalde; create is niet uitgevoerd.",
            }
        else:
            execution_result = _execute_ouroboros_create_via_ollama_api(plan_dict)
            if execution_result.get("status") != "success":
                flags.append("ollama_create_failed")

    refreshed_models = _safe_model_names()
    created = OUROBOROS_MODEL_NAME in refreshed_models
    flow = {
        "status": "online" if created else ("prepared" if not req.execute else "create_attempted"),
        "created": created,
        "online": created,
        "base_model": active_base,
        "model_name": OUROBOROS_MODEL_NAME,
        "modelfile_path": plan_dict.get("modelfile_path"),
        "command_text": plan_dict.get("command_text"),
        "valid": bool(plan_dict.get("valid")),
        "validation_errors": plan_dict.get("validation_errors", []),
        "execution_status": (execution_result or {}).get("status") or plan_dict.get("execution_status"),
        "execution_result": execution_result,
        "flags": flags,
        "updated_at": time.time(),
        "next_action": "Research Missing Knowledge" if created else "Typ Akkoord en Create/Refresh om het model via Ollama API aan te maken.",
    }
    app.state.ouroboros_model = {
        "created": created,
        "online": created,
        "active_base": active_base,
        "updated_at": flow["updated_at"],
        "create_flow": flow,
    }
    return _ouroboros_status_payload(
        {
            "create_flow": flow,
            "learned": f"Ouroboros Modelfile is voorbereid op basis {active_base}; online betekent pas: Ollama rapporteert model '{OUROBOROS_MODEL_NAME}'.",
            "mentor": "Dit is modelidentiteit, geen fine-tune. Weights worden niet gefaket; latere LoRA/dataset-flow blijft apart.",
            "next_action": flow["next_action"],
        }
    )


def _execute_ouroboros_create_via_ollama_api(plan: dict[str, Any]) -> dict[str, str]:
    """Create the local Ollama identity through Ollama's HTTP API after approval."""

    modelfile_path = str(plan.get("modelfile_path") or "")
    try:
        with open(modelfile_path, "r", encoding="utf-8") as handle:
            modelfile = handle.read()
    except Exception as exc:
        return {"status": "error", "stdout": "", "stderr": f"Modelfile niet leesbaar: {exc}"}

    create_payload = _ollama_create_payload_from_modelfile(plan, modelfile)

    base_url = str(getattr(ollama, "base_url", "") or os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
    if base_url.endswith("/api"):
        base_url = base_url[:-4]
    try:
        response = requests.post(
            f"{base_url}/api/create",
            json=create_payload,
            timeout=180,
        )
        text = response.text[-12000:]
        if response.ok:
            return {"status": "success", "stdout": text or f"Ollama model '{OUROBOROS_MODEL_NAME}' aangemaakt.", "stderr": ""}
        return {"status": "error", "stdout": "", "stderr": text or f"Ollama create status {response.status_code}"}
    except Exception as exc:
        return {"status": "error", "stdout": "", "stderr": f"Ollama create API mislukt: {exc}"}


def _ollama_create_payload_from_modelfile(plan: dict[str, Any], modelfile: str) -> dict[str, Any]:
    """Convert the prepared Modelfile into Ollama's current /api/create payload."""

    base_model = str(plan.get("base_model") or "").strip()
    system_lines: list[str] = []
    parameters: dict[str, Any] = {}
    in_system = False

    for raw_line in modelfile.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("FROM ") and not base_model:
            base_model = line.removeprefix("FROM ").strip()
            continue
        if line.startswith("PARAMETER "):
            parts = line.split(maxsplit=2)
            if len(parts) == 3:
                parameters[parts[1]] = _coerce_ollama_parameter(parts[2])
            continue
        if line == 'SYSTEM """':
            in_system = True
            continue
        if in_system and line == '"""':
            in_system = False
            continue
        if in_system:
            system_lines.append(raw_line)

    payload: dict[str, Any] = {
        "model": OUROBOROS_MODEL_NAME,
        "from": base_model or "llama3.2:latest",
        "stream": False,
    }
    if system_lines:
        payload["system"] = "\n".join(system_lines).strip()
    if parameters:
        payload["parameters"] = parameters
    return payload


def _coerce_ollama_parameter(value: str) -> Any:
    text = str(value or "").strip()
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def _geometry_11d(records: Optional[dict[str, Any]] = None, dream_hz: Optional[float] = None) -> dict[str, float | int]:
    hz = dream_hz
    if hz is None:
        try:
            events = getattr(app.state, "training_events", [])
            hz = float((events[-1] or {}).get("dream_hz")) if events else 422.0
        except Exception:
            hz = 422.0
    hz = max(418.0, min(432.0, float(hz or 422.0)))
    try:
        from controller.stream.geometry_11d import measure_geometry_11d

        measured = measure_geometry_11d(hz)
    except Exception:
        measured = {"dimension_count": 11, "radius": 1.0, "volume": 0.0, "oppervlakte": 0.0}
    return {
        "dimension_count": int(measured.get("dimension_count", 11)),
        "dream_hz": round(hz, 6),
        "radius": round(float(measured.get("radius", 0.0)), 6),
        "volume": round(float(measured.get("volume", 0.0)), 6),
        "oppervlakte": round(float(measured.get("oppervlakte", 0.0)), 6),
        "surface_area": round(float(measured.get("oppervlakte", 0.0)), 6),
        "record_count": int((records or {}).get("total_count", 0)),
    }


def _hippocampus_records(limit: int = 7) -> dict[str, Any]:
    limit = max(1, min(int(limit or 7), 20))
    main_count = 0
    try:
        main_count = int(kb.collection.count())
    except Exception:
        main_count = 0

    training_count = 0
    ids: list[str] = []
    metadatas: list[dict[str, Any]] = []
    documents: list[str] = []
    if _training_collection is not None:
        try:
            collection = _training_collection()
            training_count = int(collection.count())
            recent = collection.get(limit=limit, include=["documents", "metadatas"])
            ids = list(recent.get("ids", []) or [])
            metadatas = list(recent.get("metadatas", []) or [])
            documents = [str(doc)[:600] for doc in (recent.get("documents", []) or [])]
        except Exception:
            training_count = 0
    return {
        "main_collection_count": main_count,
        "training_collection_count": training_count,
        "total_count": main_count + training_count,
        "recent_training_ids": ids,
        "recent_training_metadatas": metadatas,
        "recent_training_documents": documents,
    }


def _inspect_hippocampus_payload(limit: int = 7) -> dict[str, Any]:
    records = _hippocampus_records(limit=limit)
    return {
        "status": "success",
        "records": records,
        "geometry_11d": _geometry_11d(records=records),
        "stdout": json.dumps(records, ensure_ascii=False, indent=2),
        "stderr": "",
        "learned": f"Hippocampus bevat {records['total_count']} records over hoofd- en trainingcollecties.",
        "mentor": "Inspectie is read-only en schrijft geen extra herinnering weg.",
        "next_action": "Preview Ingest" if records["training_collection_count"] == 0 else "Self-Training Step",
    }


def _training_request_proxy() -> Any:
    if not hasattr(app.state, "training_storage"):
        app.state.training_storage = stream_storage
    if not hasattr(app.state, "training_events"):
        app.state.training_events = []
    return SimpleNamespace(app=app)


def _training_ingest_payload(req: TrainingIngestRequest) -> dict[str, Any]:
    if BrowserTrainingRequest is None or _preview_payload is None:
        return {
            "status": "error",
            "diff_view": "",
            "flags": ["training_routes_unavailable"],
            "stdout": "",
            "stderr": "training_routes module niet beschikbaar",
            "records": _hippocampus_records(),
            "learned": "Training ingest kon niet starten.",
            "mentor": "Laad controller.api.training_routes voordat je deze knop activeert.",
            "next_action": "Controleer backend imports.",
        }
    try:
        approved = (req.approval or "").strip() == APPROVAL_PHRASE
        body = BrowserTrainingRequest(
            url=req.url or "https://teachablemachine.withgoogle.com/train",
            browser_text=req.browser_text,
            title=req.title or "Ouroboros Phase 1 ingest",
            approval=req.approval if approved else None,
            target_hz=req.target_hz,
        )
        request_proxy = _training_request_proxy()
        payload = _preview_payload(body, approval=req.approval if approved else None, request=request_proxy)
        flags = list(payload.get("blocked_patterns", [])) + list(payload.get("missing_11d_layers", []))
        stored = None
        if approved and payload.get("approval_status") == "approved" and _store_training_snapshot is not None:
            stored = _store_training_snapshot(payload)
            try:
                collection_count = _safe_total_count(stream_storage) if _safe_total_count else _hippocampus_records()["total_count"]
            except Exception:
                collection_count = _hippocampus_records()["total_count"]
            payload.update(
                {
                    "stored": stored.get("stored", False),
                    "approval_required": False,
                    "item_id": stored.get("item_id"),
                    "reason": stored.get("reason"),
                    "storage_target": stored.get("storage_target"),
                    "collection_count": collection_count,
                }
            )
            if _remember_event is not None:
                _remember_event(request_proxy, "ouroboros_ingest_stored", payload)
            try:
                from controller.trainer_continuous import notify_browser_training_record

                notify_browser_training_record(item_id=stored.get("item_id"), source_url=payload.get("source_url"))
            except Exception:
                pass
        else:
            payload.update(
                {
                    "stored": False,
                    "approval_required": bool(payload.get("requires_approval")),
                    "reason": "Preview klaar; opslag wacht op Akkoord.",
                }
            )
            if payload.get("approval_required") and not approved:
                flags.append("approval_required")
            if _remember_event is not None:
                _remember_event(request_proxy, "ouroboros_ingest_preview", payload)

        records = _hippocampus_records(limit=5)
        status = "stored" if payload.get("stored") else "preview"
        return {
            "status": status,
            "ingest": payload,
            "stored": bool(payload.get("stored")),
            "diff_view": payload.get("diff_view", ""),
            "flags": flags,
            "records": records,
            "geometry_11d": _geometry_11d(records=records, dream_hz=payload.get("dreamcycle", {}).get("dream_hz")),
            "stdout": stored.get("reason", "Preview klaar.") if stored else "Preview klaar; nog niet opgeslagen.",
            "stderr": "",
            "learned": "Browsertekst is gescrubd en 11D metadata is compleet." if not flags or flags == ["approval_required"] else "Browsertekst bevat flags die zichtbaar blijven in de diffview.",
            "mentor": "Alle externe browserkennis blijft untrusted tot Akkoord.",
            "next_action": "Inspect Hippocampus" if payload.get("stored") else "Akkoord + Store in 11D Memory",
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _prompt_understanding_payload(prompt: str, context: Optional[str] = None, model: Optional[str] = None) -> dict[str, Any]:
    text = str(prompt or "")
    lowered = text.lower()
    flags: list[str] = []
    if any(marker in lowered for marker in ("ignore previous", "system prompt", "developer message", "api key", "password")):
        flags.append("prompt_safety_review")
    if len(text) > 4000:
        flags.append("long_prompt")

    intent = "general"
    if any(word in lowered for word in ("research", "zoek", "missing knowledge", "ontbrekende kennis")):
        intent = "browser_research"
    elif any(word in lowered for word in ("train", "ingest", "memory", "hippocampus", "11d")):
        intent = "training_ingest"
    elif any(word in lowered for word in ("test", "unittest", "pytest")):
        intent = "run_tests"
    elif any(word in lowered for word in ("status", "model", "ouroboros")):
        intent = "model_status"

    missing_knowledge = []
    if "?" in text or intent == "browser_research":
        missing_knowledge.append("external_or_recent_context")
    if "browser" in lowered or "chatgpt" in lowered:
        missing_knowledge.append("browser_observation")

    next_action = {
        "browser_research": "Research Missing Knowledge",
        "training_ingest": "Preview Ingest",
        "run_tests": "Run Tests",
        "model_status": "Create/Refresh Ouroboros Model",
    }.get(intent, "Self-Training Step")
    return {
        "status": "success",
        "intent": intent,
        "model": model or _active_base(_safe_model_names()),
        "summary": text[:240],
        "context_used": bool(context),
        "missing_knowledge": missing_knowledge,
        "flags": flags,
        "stdout": json.dumps({"intent": intent, "missing_knowledge": missing_knowledge}, ensure_ascii=False),
        "stderr": "",
        "learned": f"Prompt begrepen als intent: {intent}.",
        "mentor": "Gebruik de intent alleen als routevoorstel; preview blijft verplicht voor opslag.",
        "next_action": next_action,
    }


_CHATGPT_QUESTION_PREFIXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?is)^\s*(?:vraag|ask|stel)\s+(?:aan\s+)?(?:chatgpt|openai|gpt)\s*:?\s*"),
    re.compile(r"(?is)^\s*(?:open|start|lanceer)\s+(?:chatgpt|openai|gpt)\s+(?:en\s+)?(?:vraag|ask|stel)(?:\s+(?:de\s+)?vraag)?\s*:?\s*"),
    re.compile(r"(?is)^\s*(?:chatgpt|openai|gpt)\s*[:\-]\s*"),
)


def _normalize_chatgpt_question(value: object) -> str:
    question = str(value or "").replace("\x00", " ").strip()
    for pattern in _CHATGPT_QUESTION_PREFIXES:
        extracted = pattern.sub("", question, count=1).strip()
        if extracted != question:
            question = extracted
            break
    return question[:4000]


def _chatgpt_question_understanding(question: str, original_prompt: object = "") -> dict[str, Any]:
    understanding = _prompt_understanding_payload(question)
    original = str(original_prompt or "").strip()
    flags = list(understanding.get("flags") or [])
    if original and original != question:
        flags.append("chatgpt_question_extracted")
    understanding.update(
        {
            "intent": "chatgpt_browser_ask",
            "summary": question[:240],
            "question_chars": len(question),
            "requires_approval": True,
            "approval_phrase": APPROVAL_PHRASE,
            "flags": list(dict.fromkeys(flags)),
            "stdout": json.dumps(
                {
                    "intent": "chatgpt_browser_ask",
                    "question_chars": len(question),
                    "flags": list(dict.fromkeys(flags)),
                },
                ensure_ascii=False,
            ),
            "learned": "Prompt begrepen als ChatGPT-browservraag.",
            "mentor": "De browseractie blijft approval-gated; self-context bewaart alleen vraag en actie-samenvatting.",
            "next_action": "Akkoord + Ask ChatGPT Browser",
        }
    )
    missing = list(understanding.get("missing_knowledge") or [])
    if "browser_observation" not in missing:
        missing.append("browser_observation")
    understanding["missing_knowledge"] = missing
    return understanding


def _store_chatgpt_question_context(
    question: str,
    browser_response: dict[str, Any],
    understanding: dict[str, Any],
    conversation_id: Optional[str],
    enabled: bool = True,
) -> dict[str, Any]:
    if not enabled:
        return {"enabled": False, "status": "skipped", "reason": "store_question=false", "fake_success": False}

    status = str(browser_response.get("status") or "unknown")
    safe_summary = {
        "tool": "chatgpt_browser_ask",
        "status": status,
        "intent": understanding.get("intent") or "chatgpt_browser_ask",
        "browser_action_performed": bool(browser_response.get("browser_action_performed")),
        "approval_required": bool(browser_response.get("approval_required", status == "approval_required")),
        "approval_status": browser_response.get("approval_status") or ("pending_philip_akkoord" if status == "approval_required" else ""),
        "source_url": browser_response.get("source_url") or browser_response.get("url") or "",
        "diff_hash": browser_response.get("diff_hash") or "",
        "blocked_patterns": list(browser_response.get("blocked_patterns") or []),
        "untrusted_browser_content_saved": False,
        "note": "ChatGPT browsercontent blijft UNTRUSTED; self-context bewaart alleen vraag en actie-samenvatting.",
    }
    try:
        return {
            "enabled": True,
            "last_store": record_chat_turn(
                prompt=f"ChatGPT vraag: {question}",
                response=json.dumps(safe_summary, ensure_ascii=False, sort_keys=True),
                provider="chatgpt_browser",
                model="chatgpt.com",
                conversation_id=conversation_id or "chatgpt-browser",
                status=status,
            ),
            "stored_question": True,
            "stored_browser_content": False,
            "fake_success": False,
        }
    except Exception as exc:
        return {"enabled": True, "status": "error", "reason": str(exc), "stored_question": False, "fake_success": False}


def _brave_search_payload(req: BraveSearchRequest) -> dict[str, Any]:
    query = str(req.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is verplicht")
    if (req.approval or "").strip() != APPROVAL_PHRASE:
        return {
            "status": "blocked",
            "provider": "brave",
            "approval_required": True,
            "required_approval_phrase": APPROVAL_PHRASE,
            "reason": "Brave Search API-call wacht op Akkoord.",
            "fake_success": False,
        }
    if req.llm_context is not False:
        result = search_brave_llm_context(query, maximum_number_of_urls=max(1, min(req.limit or 8, 50)))
    else:
        result = search_brave_web(query, count=max(1, min(req.limit or 8, 20)))
    result.setdefault("provider", "brave")
    result.setdefault("route", "brave_search")
    result.setdefault("fake_success", False)
    return result


def _browser_research_payload(req: BrowserResearchRequest) -> dict[str, Any]:
    query = str(req.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is verplicht")
    understanding = _prompt_understanding_payload(query)
    memory = agent_tools.run_tool("memory_search", {"query": query, "limit": req.limit or 5})
    brave_result = _brave_companion_search(query, approval=req.approval or "", limit=req.limit or 5)
    ingest = None
    browser_result = None
    flags = list(understanding.get("flags", []))
    status = "needs_browser_capture"
    brave_status = str(brave_result.get("status") or "")
    if brave_status and brave_status not in {"success", "blocked"}:
        flags.append(f"brave_{brave_status}")
    if req.browser_text:
        ingest = _training_ingest_payload(
            TrainingIngestRequest(
                url=req.url or "https://teachablemachine.withgoogle.com/train",
                browser_text=req.browser_text,
                title=f"Browser research: {query[:80]}",
                target_hz=req.target_hz,
            )
        )
        flags.extend(ingest.get("flags", []))
        status = "preview"
    else:
        try:
            from controller.browser_research import browser_research

            browser_result = browser_research(query=query, url=req.url, approval=req.approval, include_brave=False)
            flags.extend(browser_result.get("blocked_patterns", []))
            if browser_result.get("status") == "success":
                status = "browser_observed"
            else:
                status = browser_result.get("status", "browser_unavailable")
                flags.append(status)
        except Exception as exc:
            browser_result = {
                "status": "error",
                "reason": str(exc),
                "next_action": "Gebruik handmatige browsertekst en Preview Ingest.",
            }
            status = "error"
            flags.append("browser_research_error")

    if status not in {"browser_observed", "preview"} and brave_result.get("status") == "success":
        status = "brave_observed"

    research = {
        "status": status,
        "last_query": query,
        "last_url": (browser_result or {}).get("url") or (browser_result or {}).get("source_url") or req.url or "",
        "flags": flags,
        "matches": (memory.get("result") or {}).get("count", 0),
        "brave_status": brave_result.get("status"),
        "brave_matches": int(brave_result.get("count") or len(brave_result.get("matches") or brave_result.get("source_urls") or []) or 0),
        "browser_action_performed": bool((browser_result or {}).get("browser_action_performed")),
        "updated_at": time.time(),
    }
    app.state.ouroboros_browser_research = research
    return {
        "status": status,
        "query": query,
        "browser_research": research,
        "understanding": understanding,
        "memory": memory.get("result", {}),
        "brave": brave_result,
        "browser": browser_result,
        "ingest": ingest,
        "diff_view": (ingest or {}).get("diff_view", "") or (browser_result or {}).get("diff_view", ""),
        "flags": flags,
        "stdout": json.dumps({"memory": memory.get("result", {}), "brave": brave_result, "browser": browser_result}, ensure_ascii=False, indent=2, default=str),
        "stderr": memory.get("stderr") or memory.get("error", "") or ((browser_result or {}).get("reason") if status not in {"preview", "browser_observed", "brave_observed"} else ""),
        "learned": _browser_research_learned(req, brave_result=brave_result),
        "mentor": "Onderzoek leest eerst lokaal geheugen en slaat externe tekst pas op na Akkoord.",
        "next_action": "Preview Ingest" if not req.browser_text else "Akkoord + Store in 11D Memory",
    }


def _brave_companion_search(query: str, *, approval: str = "", limit: int = 5) -> dict[str, Any]:
    if (approval or "").strip() != APPROVAL_PHRASE:
        return {
            "status": "blocked",
            "provider": "brave",
            "approval_required": True,
            "reason": "Brave companion search wacht op Akkoord.",
            "fake_success": False,
        }
    try:
        result = search_brave_llm_context(query, maximum_number_of_urls=max(1, min(int(limit or 5), 20)))
        result.setdefault("provider", "brave")
        result.setdefault("route", "brave_companion_search")
        result.setdefault("fake_success", False)
        return result
    except Exception as exc:
        return {"status": "error", "provider": "brave", "reason": str(exc), "fake_success": False}


def _browser_research_learned(req: BrowserResearchRequest, *, brave_result: dict[str, Any]) -> str:
    if req.browser_text:
        return "Browser research staat klaar als gescrubde ingest-preview; Brave-context is als companion meegegeven wanneer Akkoord aanwezig was."
    if brave_result.get("status") == "success":
        return "Ontbrekende kennis is vergeleken met lokaal geheugen, Brave Search LLM Context en de bestaande browserobservatie."
    return "Ontbrekende kennis is vergeleken met lokaal geheugen en via een enkele browserobservatie gescrubd."


def _self_training_step_payload(req: SelfTrainingStepRequest) -> dict[str, Any]:
    prompt = req.prompt or req.browser_text or "Ouroboros self-training step"
    approval = (req.approval or "").strip()

    # Als we de echte self_training_step hebben, gebruik die dan!
    if self_training_step is not None and not (req.run_tests and approval != APPROVAL_PHRASE):
        try:
            # We voeren de stap uit via de registry
            result = self_training_step(
                philip_opdracht=prompt,
                registry=agent_tools,
                approval=approval,
                action="run_tests" if req.run_tests else None,
                action_args={"test_selector": req.test_selector} if req.test_selector else None
            )

            # Verrijk het resultaat met UI-vriendelijke velden indien nodig
            result["records"] = _hippocampus_records(limit=5)
            result["geometry_11d"] = _geometry_11d(records=result["records"])
            if req.run_tests and "test_result" not in result:
                result["test_result"] = result.get("action_result")

            # Zorg dat de status 'success' is als de reflectie dat zegt
            if result.get("status") == "blocked" and approval == "Akkoord":
                # Soms blokkeert een sub-tool maar de loop zelf mag doorgaan als de eind-reflectie positief is
                pass

            return result
        except Exception as exc:
            return {
                "status": "error",
                "stderr": str(exc),
                "learned": "Echte agent-loop faalde.",
                "mentor": "Check controller/self_training.py voor logicafouten.",
                "next_action": "Repareer de agent-loop."
            }

    # Fallback (legacy/passive mode)
    understanding = _prompt_understanding_payload(prompt)
    ingest = None
    if req.browser_text:
        ingest = _training_ingest_payload(
            TrainingIngestRequest(
                url=req.url or "https://teachablemachine.withgoogle.com/train",
                browser_text=req.browser_text,
                title="Ouroboros self-training step",
                approval=req.approval,
                target_hz=req.target_hz,
            )
        )
    records = _hippocampus_records(limit=5)
    test_result = None
    if req.run_tests:
        if approval == APPROVAL_PHRASE:
            test_result = agent_tools.run_tool(
                "run_tests",
                {
                    "test_selector": req.test_selector or "sandbox_tests.test_api_ouroboros_phase1",
                    "approval": req.approval or "",
                },
            )
        else:
            test_result = {
                "tool_name": "run_tests",
                "status": "blocked",
                "stdout": "",
                "stderr": f"Run Tests wacht op {APPROVAL_PHRASE}.",
                "error": f"Run Tests wacht op {APPROVAL_PHRASE}.",
            }
    stdout_parts = [understanding.get("stdout", "")]
    if ingest:
        stdout_parts.append(ingest.get("stdout", ""))
    if test_result:
        stdout_parts.append(test_result.get("stdout", ""))
    stderr_parts = []
    if ingest and ingest.get("stderr"):
        stderr_parts.append(ingest.get("stderr", ""))
    if test_result and (test_result.get("stderr") or test_result.get("error")):
        stderr_parts.append(test_result.get("stderr") or test_result.get("error"))
    return {
        "status": "success" if not stderr_parts else "blocked",
        "understanding": understanding,
        "ingest": ingest,
        "test_result": test_result,
        "records": records,
        "geometry_11d": _geometry_11d(records=records),
        "flags": (understanding.get("flags", []) + ((ingest or {}).get("flags", []))),
        "stdout": "\n".join(part for part in stdout_parts if part),
        "stderr": "\n".join(part for part in stderr_parts if part),
        "learned": "Self-training stap heeft promptbegrip, optionele ingest en records samengebracht.",
        "mentor": f"Volgende stap blijft klein: inspecteer resultaat of geef {APPROVAL_PHRASE} voor opslag/tests.",
        "next_action": "Inspect Hippocampus" if ingest and ingest.get("stored") else "Preview Ingest",
    }


def _current_training_context() -> str:
    events = getattr(app.state, "training_events", [])
    if not events:
        return "Nog geen recente trainingsgebeurtenissen."
    lines = []
    for event in events[-5:]:
        lines.append(
            " | ".join(
                [
                    f"event={event.get('kind')}",
                    f"host={event.get('source_host')}",
                    f"stored={event.get('stored')}",
                    f"hz={event.get('dream_hz')}",
                    f"resonance={event.get('resonance_score')}",
                    f"count={event.get('collection_count')}",
                ]
            )
        )
    return "\n".join(lines)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

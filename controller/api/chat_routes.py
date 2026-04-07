from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
import json
import uuid

chat_router = APIRouter()


class Message(BaseModel):
    sender: str
    text: str
    model: Optional[str] = None


def _data_dir():
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
    chats = os.path.join(base, "chats")
    os.makedirs(chats, exist_ok=True)
    return chats


@chat_router.get("/api/chats")
async def list_chats():
    d = _data_dir()
    files = [f for f in os.listdir(d) if f.endswith('.json')]
    chats = []
    for f in files:
        p = os.path.join(d, f)
        try:
            with open(p, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            chats.append({"id": data.get('id', f.replace('.json','')), "title": data.get('title','Chat'), "last_modified": os.path.getmtime(p)})
        except Exception:
            continue
    chats.sort(key=lambda x: x['last_modified'], reverse=True)
    return {"chats": chats}


@chat_router.post("/api/chats")
async def create_chat():
    d = _data_dir()
    chat_id = str(uuid.uuid4())
    p = os.path.join(d, chat_id + ".json")
    data = {"id": chat_id, "title": "Nieuwe Chat", "messages": []}
    with open(p, 'w', encoding='utf-8') as fh:
        json.dump(data, fh)
    return {"id": chat_id}


@chat_router.get("/api/chats/{chat_id}")
async def get_chat(chat_id: str):
    p = os.path.join(_data_dir(), f"{chat_id}.json")
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="Chat not found")
    with open(p, 'r', encoding='utf-8') as fh:
        return json.load(fh)


@chat_router.post("/api/chat")
async def post_message(request: Request, payload: Message):
    """Send a message into a chat. Optional query param: chat_id"""
    chat_id = request.query_params.get('chat_id')
    d = _data_dir()
    if chat_id:
        p = os.path.join(d, f"{chat_id}.json")
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as fh:
                chat = json.load(fh)
        else:
            chat = {"id": chat_id, "title": "Chat", "messages": []}
    else:
        # ephemeral chat
        chat_id = str(uuid.uuid4())
        p = os.path.join(d, f"{chat_id}.json")
        chat = {"id": chat_id, "title": "Temp Chat", "messages": []}

    chat['messages'].append({"sender": payload.sender, "text": payload.text})

    # persist
    with open(p, 'w', encoding='utf-8') as fh:
        json.dump(chat, fh)

    # Use orchestrator if available to produce a response
    orch = getattr(request.app.state, 'orchestrator', None)
    if orch:
        try:
            resp = orch.route_request(payload.text, model=payload.model or orch.active_model)
        except Exception as e:
            resp = f"[orchestrator error] {e}"
    else:
        resp = "[no orchestrator configured]"

    chat['messages'].append({"sender": "assistant", "text": resp})
    with open(p, 'w', encoding='utf-8') as fh:
        json.dump(chat, fh)

    return {"chat_id": chat_id, "response": resp}


def init_chat(app):
    app.include_router(chat_router)

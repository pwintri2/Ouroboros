from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
import json
import uuid

persona_router = APIRouter()


class Persona(BaseModel):
    name: str
    description: Optional[str] = ""


def _persona_dir():
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
    pdir = os.path.join(base, "personas")
    os.makedirs(pdir, exist_ok=True)
    return pdir


@persona_router.get('/api/personas')
async def list_personas():
    d = _persona_dir()
    items = []
    for f in os.listdir(d):
        if not f.endswith('.json'):
            continue
        with open(os.path.join(d, f), 'r', encoding='utf-8') as fh:
            try:
                items.append(json.load(fh))
            except Exception:
                continue
    return {"personas": items}


@persona_router.post('/api/personas')
async def create_persona(p: Persona):
    d = _persona_dir()
    pid = str(uuid.uuid4())
    obj = {"id": pid, "name": p.name, "description": p.description, "photo": None}
    with open(os.path.join(d, f"{pid}.json"), 'w', encoding='utf-8') as fh:
        json.dump(obj, fh)
    return obj


@persona_router.put('/api/personas/{persona_id}')
async def update_persona(persona_id: str, p: Persona):
    d = _persona_dir()
    meta_path = os.path.join(d, f"{persona_id}.json")
    if not os.path.exists(meta_path):
        raise HTTPException(status_code=404, detail='persona not found')
    with open(meta_path, 'r', encoding='utf-8') as fh:
        meta = json.load(fh)
    meta['name'] = p.name
    meta['description'] = p.description
    with open(meta_path, 'w', encoding='utf-8') as fh:
        json.dump(meta, fh)
    return meta


@persona_router.delete('/api/personas/{persona_id}')
async def delete_persona(persona_id: str):
    d = _persona_dir()
    meta_path = os.path.join(d, f"{persona_id}.json")
    if not os.path.exists(meta_path):
        raise HTTPException(status_code=404, detail='persona not found')
    with open(meta_path, 'r', encoding='utf-8') as fh:
        meta = json.load(fh)
    photo_path = meta.get('photo')
    if photo_path:
        abs_photo = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', photo_path))
        if os.path.exists(abs_photo):
            try:
                os.remove(abs_photo)
            except Exception:
                pass
    os.remove(meta_path)
    return {"status": "ok", "deleted": persona_id}


@persona_router.post('/api/personas/{persona_id}/photo')
async def upload_photo(persona_id: str, file: UploadFile = File(...)):
    d = _persona_dir()
    meta_path = os.path.join(d, f"{persona_id}.json")
    if not os.path.exists(meta_path):
        raise HTTPException(status_code=404, detail='persona not found')
    images_dir = os.path.join(d, 'images')
    os.makedirs(images_dir, exist_ok=True)
    ext = os.path.splitext(file.filename)[1]
    dest = os.path.join(images_dir, f"{persona_id}{ext}")
    with open(dest, 'wb') as out:
        out.write(await file.read())
    # update metadata
    with open(meta_path, 'r', encoding='utf-8') as fh:
        meta = json.load(fh)
    meta['photo'] = os.path.relpath(dest, start=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    with open(meta_path, 'w', encoding='utf-8') as fh:
        json.dump(meta, fh)
    return {"status": "ok", "photo": meta['photo']}


def init_personas(app):
    app.include_router(persona_router)

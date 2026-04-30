# controller/api/browser_routes.py
# FastAPI routes for the browser research perimeter.

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from controller.browser_research import (
    browser_research,
    chatgpt_browser_ask,
    read_visible_text,
    scrub_browser_content,
)


browser_router = APIRouter(prefix="/browser", tags=["browser"])


class BrowserResearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    url: Optional[str] = Field(default=None, max_length=2048)
    approval: Optional[str] = Field(default=None, max_length=64)


class ChatGPTBrowserAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    approval: Optional[str] = Field(default=None, max_length=64)


class ReadVisibleTextRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    approval: Optional[str] = Field(default=None, max_length=64)


class ScrubBrowserContentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=64000)


@browser_router.post("/research")
async def post_browser_research(body: BrowserResearchRequest) -> dict[str, Any]:
    return browser_research(query=body.query, url=body.url, approval=body.approval)


@browser_router.post("/chatgpt/ask")
async def post_chatgpt_browser_ask(body: ChatGPTBrowserAskRequest) -> dict[str, Any]:
    return chatgpt_browser_ask(question=body.question, approval=body.approval)


@browser_router.post("/read-visible-text")
async def post_read_visible_text(body: ReadVisibleTextRequest) -> dict[str, Any]:
    return read_visible_text(url=body.url, approval=body.approval)


@browser_router.post("/scrub")
async def post_scrub_browser_content(body: ScrubBrowserContentRequest) -> dict[str, Any]:
    return scrub_browser_content(content=body.content)


def init_browser_research(app: Any) -> None:
    app.include_router(browser_router)

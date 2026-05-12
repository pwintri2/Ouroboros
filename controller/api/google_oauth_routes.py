"""FastAPI routes for the Google connector OAuth setup flow."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from controller.google_oauth_setup import (
    DEFAULT_GOOGLE_REDIRECT_URI,
    DEFAULT_GOOGLE_SCOPES,
    exchange_google_oauth_code,
    google_oauth_callback_page,
    google_oauth_status,
    store_google_oauth_callback_code,
    start_google_oauth_flow,
)


google_oauth_router = APIRouter(prefix="/api/cockpit/connectors/google/oauth", tags=["google-oauth-setup"])


class GoogleOAuthStartRequest(BaseModel):
    client_id: str = Field(default="", max_length=500)
    client_secret: str = Field(default="", max_length=1000)
    client_json: str = Field(default="", max_length=12000)
    redirect_uri: str = Field(default=DEFAULT_GOOGLE_REDIRECT_URI, max_length=1000)
    scopes: list[str] = Field(default_factory=lambda: list(DEFAULT_GOOGLE_SCOPES))
    approval: str = Field(default="", max_length=128)


class GoogleOAuthExchangeRequest(BaseModel):
    code: str = Field(default="", max_length=4000)
    client_id: str = Field(default="", max_length=500)
    client_secret: str = Field(default="", max_length=1000)
    client_json: str = Field(default="", max_length=12000)
    redirect_uri: str = Field(default="", max_length=1000)
    use_pending_code: bool = Field(default=False)
    approval: str = Field(default="", max_length=128)


def init_google_oauth_routes(app: Any) -> None:
    app.include_router(google_oauth_router)


@google_oauth_router.get("/status")
async def google_oauth_setup_status() -> dict[str, Any]:
    return google_oauth_status()


@google_oauth_router.post("/start")
async def google_oauth_start(request: GoogleOAuthStartRequest) -> dict[str, Any]:
    return start_google_oauth_flow(
        client_id=request.client_id,
        client_secret=request.client_secret,
        client_json=request.client_json,
        redirect_uri=request.redirect_uri,
        scopes=request.scopes,
        approval=request.approval,
    )


@google_oauth_router.post("/exchange")
async def google_oauth_exchange(request: GoogleOAuthExchangeRequest) -> dict[str, Any]:
    return exchange_google_oauth_code(
        code=request.code,
        client_id=request.client_id,
        client_secret=request.client_secret,
        client_json=request.client_json,
        redirect_uri=request.redirect_uri,
        use_pending_code=bool(request.use_pending_code),
        approval=request.approval,
    )


@google_oauth_router.get("/callback", response_class=HTMLResponse)
async def google_oauth_callback(code: str = "", error: str = "") -> HTMLResponse:
    stored = store_google_oauth_callback_code(code=code, error=error)
    return HTMLResponse(google_oauth_callback_page(code_present=bool(code), error=error, stored=bool(stored.get("stored"))))

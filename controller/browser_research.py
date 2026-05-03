# controller/browser_research.py
# Browser research perimeter: real Playwright actions when available, no fake success.

from __future__ import annotations

import os
import re
import asyncio
import concurrent.futures
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus, urlparse

from controller.stream.browser_scrubber import (
    DEFAULT_APPROVAL_PHRASE,
    TEACHABLE_MACHINE_HOST,
    ScrubbedBrowserContent,
    prepare_browser_ingest,
    prepare_teachablemachine_ingest,
)


CHATGPT_URL = "https://chatgpt.com/"
PROVIDED_CONTENT_URL = "https://browser-content.invalid/provided"
SEARCH_URL_TEMPLATE = "https://duckduckgo.com/?q={query}"

MAX_URL_LENGTH = 2048
MAX_QUERY_LENGTH = 500
MAX_CHATGPT_QUESTION_LENGTH = 4000
MAX_BROWSER_TEXT_CHARS = 64_000

_DEFAULT_TIMEOUT_MS = 12_000
_LOGIN_OR_CAPTCHA_RE = re.compile(
    r"(?i)\b("
    r"captcha|verify you are human|verify you're human|cloudflare|"
    r"log in|login|sign in|signin|create account|enter your password|password required|two-factor|2fa"
    r")\b"
)


@dataclass(frozen=True)
class BrowserActionResult:
    status: str
    url: str = ""
    visible_text: str = ""
    title: str = ""
    reason: str = ""
    next_action: str = ""
    backend: str = "playwright"
    browser_action_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "url": self.url,
            "title": self.title,
            "reason": self.reason,
            "next_action": self.next_action,
            "backend": self.backend,
            "browser_action_performed": self.browser_action_performed,
        }


def browser_research(query: str, url: str | None = None, approval: object = None) -> dict[str, Any]:
    """
    Read exactly one browser page for a research query.

    If url is provided, the browser reads that page. Without url, it navigates to
    a single search-results page for the query. It does not click result links.
    """
    clean_query = _clean_text(query, max_len=MAX_QUERY_LENGTH)
    if not clean_query:
        return _blocked_result(
            tool_name="browser_research",
            action="browser_research",
            reason="Query ontbreekt.",
            next_action="Geef een korte research query op.",
        )

    target_url = url.strip() if isinstance(url, str) and url.strip() else _search_url(clean_query)
    result = read_visible_text(target_url, approval=approval)
    result.update(
        {
            "tool_name": "browser_research",
            "action": "browser_research",
            "query": clean_query,
            "target_url": target_url,
            "page_limit": 1,
            "bulk_scraping": False,
        }
    )
    return result


def chatgpt_browser_ask(question: str, approval: object = None) -> dict[str, Any]:
    """
    Ask ChatGPT through a browser only after exact Philip approval.

    This function may type and submit text in a browser, so approval must be the
    exact phrase "Akkoord". Without that phrase no browser session is opened.
    """
    clean_question = _clean_text(question, max_len=MAX_CHATGPT_QUESTION_LENGTH)
    if not clean_question:
        blocked = _blocked_result(
            tool_name="chatgpt_browser_ask",
            action="chatgpt_browser_ask",
            reason="Vraag ontbreekt.",
            next_action="Geef een vraag op voordat de browser wordt geopend.",
        )
        blocked.update({"question": "", "question_chars": 0})
        return blocked
    if not _has_exact_approval(approval):
        return {
            "tool_name": "chatgpt_browser_ask",
            "action": "chatgpt_browser_ask",
            "status": "approval_required",
            "question": clean_question,
            "question_chars": len(clean_question),
            "approval_required": True,
            "approval_phrase": DEFAULT_APPROVAL_PHRASE,
            "reason": "ChatGPT ask typt en submit tekst in de browser en vereist exact Akkoord.",
            "next_action": "Roep opnieuw aan met approval='Akkoord' als Philip deze browseractie wil uitvoeren.",
            "backend": "playwright",
            "browser_action_performed": False,
            "blocked_actions": ["type", "submit"],
        }

    action = _run_chatgpt_ask_with_playwright(clean_question)
    payload = _browser_action_to_scrubbed_payload(
        tool_name="chatgpt_browser_ask",
        action="chatgpt_browser_ask",
        action_result=action,
        approval=approval,
        fallback_url=CHATGPT_URL,
        title="ChatGPT browser ask",
    )
    payload.update({"question": clean_question, "question_chars": len(clean_question)})
    return payload


def read_visible_text(url: str, approval: object = None) -> dict[str, Any]:
    """Read visible text from one http(s) page through Playwright, then scrub it."""
    validation = _validate_single_http_url(url)
    if validation is not None:
        return validation

    action = _run_read_with_playwright(url.strip())
    return _browser_action_to_scrubbed_payload(
        tool_name="read_visible_text",
        action="read_visible_text",
        action_result=action,
        approval=approval,
        fallback_url=url.strip(),
        title="Browser visible text",
    )


def scrub_browser_content(content: str) -> dict[str, Any]:
    """
    Scrub already-provided browser content without claiming a browser action.

    The synthetic .invalid URL is only a source label for the existing browser
    ingest scrubber; browser_action_performed stays false.
    """
    text = _clean_text(content, max_len=MAX_BROWSER_TEXT_CHARS)
    scrubbed = _prepare_scrubbed(
        url=PROVIDED_CONTENT_URL,
        content=text,
        approval=None,
        title="Provided browser content",
    )
    payload = _scrubbed_to_payload(scrubbed)
    payload.update(
        {
            "tool_name": "scrub_browser_content",
            "action": "scrub_browser_content",
            "status": "success",
            "source_kind": "provided_browser_content",
            "browser_action_performed": False,
            "next_action": "Review DiffView; gebruik de inhoud pas verder na expliciete Akkoord-gate.",
        }
    )
    return payload


def _browser_action_to_scrubbed_payload(
    tool_name: str,
    action: str,
    action_result: BrowserActionResult,
    approval: object,
    fallback_url: str,
    title: str,
) -> dict[str, Any]:
    if action_result.status in {"unavailable", "failed"} and not action_result.visible_text:
        payload = action_result.to_dict()
        if not payload.get("url"):
            payload["url"] = fallback_url
        payload.update({"tool_name": tool_name, "action": action})
        return payload

    source_url = action_result.url or fallback_url
    visible_text = _clean_text(action_result.visible_text, max_len=MAX_BROWSER_TEXT_CHARS)
    scrubbed = _prepare_scrubbed(
        url=source_url,
        content=visible_text,
        approval=approval if _has_exact_approval(approval) else None,
        title=title,
    )
    payload = _scrubbed_to_payload(scrubbed)
    payload.update(action_result.to_dict())
    payload.update(
        {
            "tool_name": tool_name,
            "action": action,
            "url": source_url,
            "browser_action_performed": action_result.browser_action_performed,
            "visible_text_chars": len(visible_text),
        }
    )

    if _looks_like_login_or_captcha(visible_text):
        payload.update(
            {
                "status": "blocked",
                "reason": "Login/CAPTCHA/interactieve verificatie gedetecteerd; er is geen bypass uitgevoerd.",
                "next_action": "Open deze pagina handmatig in een gewone browser of kies een publiek toegankelijke bron.",
            }
        )
    return payload


def _prepare_scrubbed(url: str, content: str, approval: object, title: str) -> ScrubbedBrowserContent:
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() == TEACHABLE_MACHINE_HOST:
        return prepare_teachablemachine_ingest(
            url=url,
            browser_text=content,
            approval=approval,
            title=title,
        )
    return prepare_browser_ingest(
        url=url,
        browser_text=content,
        approval=approval,
        title=title,
    )


def _scrubbed_to_payload(scrubbed: ScrubbedBrowserContent) -> dict[str, Any]:
    return {
        "source_url": scrubbed.source_url,
        "source_host": scrubbed.source_host,
        "taint": scrubbed.taint,
        "trust_level": "external_web_scrubbed",
        "approval_status": scrubbed.approval_status,
        "approval_required": scrubbed.approval_status != "approved",
        "approval_phrase": scrubbed.approval_phrase,
        "blocked_patterns": list(scrubbed.blocked_patterns),
        "allowed_actions": list(scrubbed.allowed_actions),
        "blocked_actions": list(scrubbed.blocked_actions),
        "scrubbed_text": scrubbed.scrubbed_text,
        "diff_view": scrubbed.diff_view,
        "diff_hash": scrubbed.diff_hash,
        "scrubber_version": scrubbed.scrubber_version,
        "scrubbed_at": scrubbed.scrubbed_at,
    }


def _run_read_with_playwright(url: str) -> BrowserActionResult:
    if _inside_running_asyncio_loop():
        return _run_blocking_browser_action(_run_read_with_playwright_blocking, url)
    return _run_read_with_playwright_blocking(url)


def _run_read_with_playwright_blocking(url: str) -> BrowserActionResult:
    loaded = _load_playwright()
    if loaded is not None:
        return loaded

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return _playwright_unavailable(exc)

    timeout_ms = _timeout_ms()
    browser_action_started = False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=_headless())
            browser_action_started = True
            try:
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                _safe_network_idle(page, timeout_ms=min(timeout_ms, 5_000))
                title = _safe_page_title(page)
                text = _safe_body_text(page)
            finally:
                browser.close()
    except PlaywrightTimeoutError as exc:
        return BrowserActionResult(
            status="failed",
            url=url,
            reason=f"Browser timeout: {exc}",
            next_action="Probeer later opnieuw of gebruik een lichtere, publiek toegankelijke pagina.",
            browser_action_performed=True,
        )
    except PlaywrightError as exc:
        if _is_missing_browser_error(exc):
            return _playwright_unavailable(exc)
        return BrowserActionResult(
            status="failed",
            url=url,
            reason=f"Playwright fout: {exc}",
            next_action="Controleer of de pagina publiek toegankelijk is en geen interactieve blokkade vereist.",
            browser_action_performed=browser_action_started,
        )
    except Exception as exc:
        return BrowserActionResult(
            status="failed",
            url=url,
            reason=f"Browseractie mislukt: {exc}",
            next_action="Controleer URL en browserinstallatie; er wordt geen resultaat gefaket.",
            browser_action_performed=browser_action_started,
        )

    return BrowserActionResult(
        status="success",
        url=url,
        title=title,
        visible_text=text,
        next_action="Review DiffView voordat deze browserinhoud verder gebruikt wordt.",
        browser_action_performed=True,
    )


def _run_chatgpt_ask_with_playwright(question: str) -> BrowserActionResult:
    if _inside_running_asyncio_loop():
        return _run_blocking_browser_action(_run_chatgpt_ask_with_playwright_blocking, question)
    return _run_chatgpt_ask_with_playwright_blocking(question)


def _run_chatgpt_ask_with_playwright_blocking(question: str) -> BrowserActionResult:
    loaded = _load_playwright()
    if loaded is not None:
        return loaded

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return _playwright_unavailable(exc)

    timeout_ms = _timeout_ms()
    browser_action_started = False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=_headless())
            browser_action_started = True
            try:
                page = browser.new_page()
                page.goto(CHATGPT_URL, wait_until="domcontentloaded", timeout=timeout_ms)
                _safe_network_idle(page, timeout_ms=min(timeout_ms, 5_000))
                visible_before = _safe_body_text(page)
                if _looks_like_login_or_captcha(visible_before):
                    return BrowserActionResult(
                        status="blocked",
                        url=CHATGPT_URL,
                        title=_safe_page_title(page),
                        visible_text=visible_before,
                        reason="ChatGPT toont login/CAPTCHA/interactieve verificatie; er is geen bypass uitgevoerd.",
                        next_action="Log handmatig in of gebruik de officiele API buiten deze browserperimeter.",
                        browser_action_performed=True,
                    )

                prompt = _first_visible_locator(
                    page,
                    [
                        '[data-testid="prompt-textarea"]',
                        "#prompt-textarea",
                        'textarea[placeholder*="Message"]',
                        'textarea',
                        'div[contenteditable="true"]',
                    ],
                )
                if prompt is None:
                    return BrowserActionResult(
                        status="blocked",
                        url=CHATGPT_URL,
                        title=_safe_page_title(page),
                        visible_text=visible_before,
                        reason="Geen ChatGPT promptveld gevonden; er is niets getypt of gesubmit.",
                        next_action="Controleer handmatig of ChatGPT publiek bereikbaar en ingelogd is.",
                        browser_action_performed=True,
                    )

                prompt.click(timeout=2_000)
                try:
                    prompt.fill(question, timeout=3_000)
                except Exception:
                    prompt.type(question, timeout=5_000)
                page.keyboard.press("Enter")
                page.wait_for_timeout(6_000)
                text = _safe_body_text(page)
                title = _safe_page_title(page)
            finally:
                browser.close()
    except PlaywrightTimeoutError as exc:
        return BrowserActionResult(
            status="failed",
            url=CHATGPT_URL,
            reason=f"ChatGPT browser timeout: {exc}",
            next_action="Probeer later opnieuw; er wordt geen antwoord gefaket.",
            browser_action_performed=True,
        )
    except PlaywrightError as exc:
        if _is_missing_browser_error(exc):
            return _playwright_unavailable(exc)
        return BrowserActionResult(
            status="failed",
            url=CHATGPT_URL,
            reason=f"Playwright fout tijdens ChatGPT ask: {exc}",
            next_action="Controleer browserinstallatie en ChatGPT bereikbaarheid.",
            browser_action_performed=browser_action_started,
        )
    except Exception as exc:
        return BrowserActionResult(
            status="failed",
            url=CHATGPT_URL,
            reason=f"ChatGPT browseractie mislukt: {exc}",
            next_action="Geen mock-response gemaakt; controleer handmatig of Playwright/ChatGPT werkt.",
            browser_action_performed=browser_action_started,
        )

    return BrowserActionResult(
        status="success",
        url=CHATGPT_URL,
        title=title,
        visible_text=text,
        next_action="Review DiffView; behandel de ChatGPT-pagina als UNTRUSTED browsercontent.",
        browser_action_performed=True,
    )


def _inside_running_asyncio_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def _run_blocking_browser_action(fn: Any, *args: Any) -> BrowserActionResult:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(fn, *args).result()


def _load_playwright() -> BrowserActionResult | None:
    try:
        import playwright.sync_api  # noqa: F401
    except Exception as exc:
        return _playwright_unavailable(exc)
    return None


def _playwright_unavailable(exc: BaseException) -> BrowserActionResult:
    return BrowserActionResult(
        status="unavailable",
        reason=f"Playwright backend/browser niet beschikbaar: {exc}",
        next_action="Installeer optioneel: pip install playwright && python -m playwright install chromium.",
        browser_action_performed=False,
    )


def _validate_single_http_url(url: str) -> dict[str, Any] | None:
    raw = str(url or "").strip()
    if not raw:
        return _blocked_result("read_visible_text", "read_visible_text", "URL ontbreekt.", "Geef een http(s)-URL op.")
    if len(raw) > MAX_URL_LENGTH or any(ch in raw for ch in "\r\n\t"):
        return _blocked_result(
            "read_visible_text",
            "read_visible_text",
            "URL is ongeldig of lijkt meerdere doelen te bevatten.",
            "Gebruik exact een enkele http(s)-URL.",
        )

    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return _blocked_result(
            "read_visible_text",
            "read_visible_text",
            "Alleen http(s)-URL's met host zijn toegestaan.",
            "Gebruik een publiek toegankelijke http(s)-pagina.",
        )
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return _blocked_result(
            "read_visible_text",
            "read_visible_text",
            "Lokale of interne browserdoelen zijn geblokkeerd.",
            "Gebruik een publiek webadres; deze perimeter doet geen lokale service-inspectie.",
        )
    return None


def _blocked_result(tool_name: str, action: str, reason: str, next_action: str) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "action": action,
        "status": "blocked",
        "reason": reason,
        "next_action": next_action,
        "browser_action_performed": False,
    }


def _search_url(query: str) -> str:
    return SEARCH_URL_TEMPLATE.format(query=quote_plus(query[:MAX_QUERY_LENGTH]))


def _clean_text(value: object, max_len: int) -> str:
    text = str(value or "").replace("\x00", " ").strip()
    if len(text) > max_len:
        return text[:max_len]
    return text


def _has_exact_approval(value: object) -> bool:
    return str(value or "").strip() == DEFAULT_APPROVAL_PHRASE


def _looks_like_login_or_captcha(text: str) -> bool:
    return bool(_LOGIN_OR_CAPTCHA_RE.search(text or ""))


def _timeout_ms() -> int:
    try:
        return max(2_000, min(60_000, int(os.getenv("WINTRIP_BROWSER_TIMEOUT_MS", str(_DEFAULT_TIMEOUT_MS)))))
    except ValueError:
        return _DEFAULT_TIMEOUT_MS


def _headless() -> bool:
    return os.getenv("WINTRIP_BROWSER_HEADLESS", "1").strip().lower() not in {"0", "false", "no"}


def _is_missing_browser_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "executable doesn't exist" in message or "playwright install" in message or "browser executable" in message


def _safe_page_title(page: Any) -> str:
    try:
        return str(page.title() or "")[:256]
    except Exception:
        return ""


def _safe_body_text(page: Any) -> str:
    try:
        return str(page.locator("body").inner_text(timeout=3_000) or "")
    except Exception:
        try:
            return str(page.content() or "")
        except Exception:
            return ""


def _safe_network_idle(page: Any, timeout_ms: int) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        return


def _first_visible_locator(page: Any, selectors: list[str]) -> Any | None:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=1_000):
                return locator
        except Exception:
            continue
    return None

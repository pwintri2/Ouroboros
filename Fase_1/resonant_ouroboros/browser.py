"""Human-like Playwright browser engine driven by Hertz state."""

from __future__ import annotations

import asyncio
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .oscillator import BrowserBehavior
from .safety import evaluate_url, sanitize_query
from .vision import VisionAnalyzer, VisionObservation


@dataclass(frozen=True)
class BrowserSnapshot:
    url: str
    title: str
    visible_text: str
    screenshot_path: str | None
    vision: VisionObservation
    links: list[str]


@dataclass(frozen=True)
class BrowserAction:
    action_type: str
    target: str
    rationale: str


class HumanBrowserEngine:
    """Real Playwright browser wrapper with human-style action primitives."""

    def __init__(
        self,
        screenshot_dir: str | Path = "/workspace/data/screenshots",
        headless: bool | None = None,
        allow_private_hosts: bool = False,
        vision: VisionAnalyzer | None = None,
    ):
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.headless = _env_bool("BROWSER_HEADLESS", True) if headless is None else headless
        self.allow_private_hosts = allow_private_hosts
        self.vision = vision or VisionAnalyzer()
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None

    async def __aenter__(self) -> "HumanBrowserEngine":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def start(self) -> None:
        try:
            from playwright.async_api import async_playwright  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "playwright is required for the human browser engine. "
                "Use Docker or install requirements.txt."
            ) from exc

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._page = await self._browser.new_page(viewport={"width": 1440, "height": 1000})

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = None
        self._browser = None
        self._playwright = None

    async def navigate(self, url: str, behavior: BrowserBehavior) -> BrowserSnapshot:
        self._require_page()
        decision = evaluate_url(url, allow_private_hosts=self.allow_private_hosts)
        if not decision.allowed:
            raise ValueError(decision.reason)
        await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(min(behavior.dwell_seconds, 3.0))
        return await self.read(behavior)

    async def click(self, selector: str, behavior: BrowserBehavior) -> BrowserSnapshot:
        self._require_page()
        await self._page.click(selector, timeout=10000)
        await asyncio.sleep(min(behavior.dwell_seconds, 2.0))
        return await self.read(behavior)

    async def type(self, selector: str, text: str, behavior: BrowserBehavior) -> BrowserSnapshot:
        self._require_page()
        await self._page.fill(selector, "")
        await self._page.type(selector, text, delay=int(25 + (100 * (1.0 - behavior.curiosity))))
        await asyncio.sleep(0.2)
        return await self.read(behavior)

    async def scroll(self, behavior: BrowserBehavior, direction: str = "down") -> BrowserSnapshot:
        self._require_page()
        pixels = behavior.scroll_pixels * (-1 if direction == "up" else 1)
        await self._page.mouse.wheel(0, pixels)
        await asyncio.sleep(min(behavior.dwell_seconds, 2.0))
        return await self.read(behavior)

    async def read(self, behavior: BrowserBehavior) -> BrowserSnapshot:
        self._require_page()
        title = await self._page.title()
        url = self._page.url
        visible_text = await self._page.locator("body").inner_text(timeout=10000)
        links = await self._extract_links(behavior.max_links_to_scan)
        screenshot_path = await self._capture_screenshot()
        vision = self.vision.analyze(screenshot_path, visible_text)
        return BrowserSnapshot(
            url=url,
            title=title,
            visible_text=visible_text,
            screenshot_path=screenshot_path,
            vision=vision,
            links=links,
        )

    async def propose_next_action(
        self,
        topic: str,
        snapshot: BrowserSnapshot | None,
        behavior: BrowserBehavior,
    ) -> BrowserAction:
        if snapshot is None:
            query = sanitize_query(topic)
            return BrowserAction(
                action_type="navigate",
                target=f"https://duckduckgo.com/?q={query.replace(' ', '+')}",
                rationale=f"start human web search for seed topic at mood {behavior.mood}",
            )

        if snapshot.links and random.random() < behavior.link_jump_probability:
            target = random.choice(snapshot.links[: behavior.max_links_to_scan])
            return BrowserAction("navigate", target, "high frequency exploratory link jump")

        return BrowserAction("scroll", "down", "low frequency deep reading scroll")

    async def _extract_links(self, limit: int) -> list[str]:
        anchors = await self._page.locator("a[href]").evaluate_all(
            """els => els.map(a => a.href).filter(Boolean)"""
        )
        safe_links = []
        for href in anchors:
            decision = evaluate_url(href, allow_private_hosts=self.allow_private_hosts)
            if decision.allowed and href not in safe_links:
                safe_links.append(href)
            if len(safe_links) >= limit:
                break
        return safe_links

    async def _capture_screenshot(self) -> str | None:
        if not self._page:
            return None
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.screenshot_dir / "current_browser_view.png"
        await self._page.screenshot(path=str(path), full_page=False)
        return str(path)

    def _require_page(self) -> None:
        if not self._page:
            raise RuntimeError("browser engine is not started")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

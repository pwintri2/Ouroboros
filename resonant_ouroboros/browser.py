"""Human-like Playwright browser engine driven by Hertz state."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import random
from typing import Any
from urllib.parse import quote_plus

from .oscillator import BrowserBehavior
from .safety import evaluate_url, sanitize_query
from .vision import VisionAnalyzer, VisionObservation


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "ja", "on"}


@dataclass(frozen=True)
class BrowserSnapshot:
    url: str
    title: str
    visible_text: str
    screenshot_path: str | None
    vision: VisionObservation
    links: list[str]
    quality_score: float = 1.0
    quality_reason: str = "accepted"

    @property
    def accepted(self) -> bool:
        return self.quality_score >= 0.45 and self.quality_reason != "rejected"


@dataclass(frozen=True)
class BrowserAction:
    action_type: str
    target: str
    rationale: str


@dataclass(frozen=True)
class BrowserToolkitAction:
    action_type: str
    description: str


class HumanBrowserEngine:
    """Real Playwright browser wrapper with human-style action primitives."""

    def __init__(
        self,
        screenshot_dir: str | Path | None = None,
        headless: bool | None = None,
        allow_private_hosts: bool = False,
        vision: VisionAnalyzer | None = None,
        rng: random.Random | None = None,
    ):
        default_dir = Path("/workspace/data/screenshots")
        if not default_dir.exists():
            default_dir = Path("./data/screenshots")
        self.screenshot_dir = Path(screenshot_dir) if screenshot_dir else default_dir
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.headless = _env_bool("BROWSER_HEADLESS", True) if headless is None else headless
        self.allow_private_hosts = allow_private_hosts
        self.vision = vision or VisionAnalyzer()
        self.rng = rng or random.Random()
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._page: Any | None = None

    async def __aenter__(self) -> "HumanBrowserEngine":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def start(self) -> None:
        if self._page is not None:
            return
        try:
            from playwright.async_api import async_playwright  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "playwright is required for the human browser engine. Use Docker or install requirements.txt."
            ) from exc

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await self._browser.new_context(
            viewport={"width": 1366, "height": 820},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        self._page = await context.new_page()

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None
        self._page = None

    async def wait_human_delay(
        self,
        minimum_seconds: float,
        maximum_seconds: float,
        behavior: BrowserBehavior | None = None,
    ) -> None:
        dwell = behavior.dwell_seconds if behavior else 0.5
        delay = self.rng.uniform(minimum_seconds, maximum_seconds) + min(dwell, 2.5) * 0.15
        await asyncio.sleep(max(0.0, delay))

    async def navigate(self, url: str, behavior: BrowserBehavior) -> BrowserSnapshot:
        decision = evaluate_url(url, allow_private_hosts=self.allow_private_hosts)
        if not decision.allowed:
            raise RuntimeError(decision.reason)
        await self.start()
        await self._page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await self.wait_human_delay(0.25, 0.75, behavior)
        return await self.read(behavior)

    async def scroll(
        self,
        behavior: BrowserBehavior,
        direction: str = "down",
        steps: int = 5,
    ) -> BrowserSnapshot:
        await self.start()
        pixels = behavior.scroll_pixels if direction == "down" else -behavior.scroll_pixels
        for _ in range(max(1, steps)):
            await self._page.mouse.wheel(0, pixels)
            await self.wait_human_delay(0.05, 0.18, behavior)
        return await self.read(behavior)

    async def click(self, selector: str, behavior: BrowserBehavior) -> BrowserSnapshot:
        await self.start()
        await self._page.locator(selector).first.click(timeout=5000)
        await self.wait_human_delay(0.25, 0.75, behavior)
        return await self.read(behavior)

    async def type(self, selector: str, text: str, behavior: BrowserBehavior) -> BrowserSnapshot:
        await self.start()
        locator = self._page.locator(selector).first
        await locator.fill("")
        for character in text:
            await locator.type(character, delay=self.rng.randint(15, 80))
        await self.wait_human_delay(0.2, 0.6, behavior)
        return await self.read(behavior)

    async def read(self, behavior: BrowserBehavior) -> BrowserSnapshot:
        await self.start()
        title = await self._page.title()
        url = self._page.url
        visible_text = ""
        try:
            visible_text = await self._page.locator("body").inner_text(timeout=5000)
        except Exception:
            visible_text = ""

        links = await self._collect_links(behavior)
        screenshot_path = str(self.screenshot_dir / "current_browser_view.png")
        try:
            await self._page.screenshot(path=screenshot_path, full_page=False)
        except Exception:
            screenshot_path = None

        vision = self.vision.analyze(screenshot_path, visible_text)
        provisional = BrowserSnapshot(
            url=url,
            title=title,
            visible_text=visible_text,
            screenshot_path=screenshot_path,
            vision=vision,
            links=links,
        )
        score, reason = self.evaluate_quality(provisional)
        return BrowserSnapshot(
            url=url,
            title=title,
            visible_text=visible_text,
            screenshot_path=screenshot_path,
            vision=vision,
            links=links,
            quality_score=score,
            quality_reason=reason,
        )

    async def _collect_links(self, behavior: BrowserBehavior) -> list[str]:
        try:
            hrefs = await self._page.locator("a[href]").evaluate_all(
                "(nodes) => nodes.map((node) => node.href).filter(Boolean)"
            )
        except Exception:
            return []
        safe_links: list[str] = []
        for href in hrefs:
            decision = evaluate_url(str(href), allow_private_hosts=self.allow_private_hosts)
            if decision.allowed and href not in safe_links:
                safe_links.append(str(href))
            if len(safe_links) >= max(1, behavior.max_links_to_scan):
                break
        return safe_links

    def evaluate_quality(self, snapshot: BrowserSnapshot) -> tuple[float, str]:
        text_length = len((snapshot.visible_text or "").strip())
        if text_length < 120:
            return 0.25, "rejected: visible text too short"
        if "captcha" in snapshot.visible_text.lower():
            return 0.2, "rejected: captcha detected"
        if snapshot.title.strip().lower() in {"", "about:blank"}:
            return 0.35, "rejected: blank title"
        return min(1.0, 0.55 + (text_length / 3000.0)), "accepted"

    def propose_next_action(
        self,
        topic: str,
        snapshot: BrowserSnapshot | None,
        behavior: BrowserBehavior,
    ) -> BrowserAction:
        if snapshot is None:
            query = quote_plus(sanitize_query(topic))
            return BrowserAction(
                "navigate",
                f"https://en.wikipedia.org/w/index.php?search={query}",
                "initial safe public knowledge search",
            )

        if behavior.mood == "creative_spike" and snapshot.links:
            target = self.rng.choice(snapshot.links[: max(1, behavior.max_links_to_scan)])
            return BrowserAction("navigate", target, "creative spike link exploration")

        if behavior.mood == "deep_read":
            return BrowserAction("scroll", "down", "low Hz deep reading")

        if snapshot.links and self.rng.random() < behavior.link_jump_probability:
            target = self.rng.choice(snapshot.links[: max(1, behavior.max_links_to_scan)])
            return BrowserAction("navigate", target, "curious related-topic exploration")

        return BrowserAction("scroll", "down", "continue reading current page")

    def langgraph_toolkit_manifest(self) -> list[BrowserToolkitAction]:
        return [
            BrowserToolkitAction("navigate", "Open a public http/https URL in a real Playwright browser."),
            BrowserToolkitAction("scroll", "Scroll the visible page with human-like dwell timing."),
            BrowserToolkitAction("click", "Click a visible element selected by a safe Playwright selector."),
            BrowserToolkitAction("type", "Type text into a visible field with human-like timing."),
            BrowserToolkitAction("read", "Read visible page state and capture screenshot provenance."),
        ]

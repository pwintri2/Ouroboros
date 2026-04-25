"""Human-like Playwright browser engine driven by Hertz state."""

from __future__ import annotations

import asyncio
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

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
    quality_score: float = 1.0
    quality_reason: str = "accepted"


@dataclass(frozen=True)
class BrowserAction:
    action_type: str
    target: str
    rationale: str


class HumanBrowserEngine:
    """Real Playwright browser wrapper with human-style action primitives."""

    def __init__(
        self,
        screenshot_dir: str | Path | None = None,
        headless: bool | None = None,
        allow_private_hosts: bool = False,
        vision: VisionAnalyzer | None = None,
    ):
        # Prefer project-relative data dir if /workspace not found
        default_dir = Path("/workspace/data/screenshots") if os.path.exists("/workspace") else Path("./data/screenshots")
        self.screenshot_dir = Path(screenshot_dir) if screenshot_dir else default_dir
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
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        # Set a realistic user agent
        self._page = await self._browser.new_page(
            viewport={"width": 1440, "height": 1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        )

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
        
        # Human-like delay before navigation
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Wait for some content to load if it's a slow SPA
        try:
            await self._page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        await asyncio.sleep(min(behavior.dwell_seconds, 3.0))
        return await self.read(behavior)

    async def click(self, selector: str, behavior: BrowserBehavior) -> BrowserSnapshot:
        self._require_page()
        
        # Hover before clicking
        try:
            element = self._page.locator(selector).first
            await element.hover(timeout=5000)
            await asyncio.sleep(random.uniform(0.2, 0.7))
            await element.click(timeout=5000)
        except Exception:
            # Fallback if hover fails
            await self._page.click(selector, timeout=10000)
            
        await asyncio.sleep(min(behavior.dwell_seconds, 2.0))
        return await self.read(behavior)

    async def type(self, selector: str, text: str, behavior: BrowserBehavior) -> BrowserSnapshot:
        self._require_page()
        await self._page.fill(selector, "")
        # Human-like typing delay
        delay = int(40 + (120 * (1.0 - behavior.curiosity)))
        await self._page.type(selector, text, delay=delay)
        await asyncio.sleep(0.5)
        # Press enter
        await self._page.keyboard.press("Enter")
        await asyncio.sleep(1.5)
        return await self.read(behavior)

    async def scroll(
        self, behavior: BrowserBehavior, direction: str = "down", steps: int = 5
    ) -> BrowserSnapshot:
        self._require_page()
        total_pixels = behavior.scroll_pixels * (-1 if direction == "up" else 1)
        
        # Multi-step smooth scrolling
        pixels_per_step = total_pixels // steps
        for _ in range(steps):
            await self._page.mouse.wheel(0, pixels_per_step)
            await asyncio.sleep(random.uniform(0.1, 0.3))
            
        await asyncio.sleep(min(behavior.dwell_seconds, 1.5))
        return await self.read(behavior)

    async def read(self, behavior: BrowserBehavior) -> BrowserSnapshot:
        self._require_page()
        title = await self._page.title()
        url = self._page.url
        visible_text = await self._page.locator("body").inner_text(timeout=10000)
        links = await self._extract_links(behavior.max_links_to_scan)
        screenshot_path = await self._capture_screenshot()
        vision = self.vision.analyze(screenshot_path, visible_text)
        
        # Temporary snapshot to evaluate quality
        temp_snapshot = BrowserSnapshot(
            url=url,
            title=title,
            visible_text=visible_text,
            screenshot_path=screenshot_path,
            vision=vision,
            links=links,
        )
        
        quality_score, quality_reason = self.evaluate_quality(temp_snapshot)
        
        return BrowserSnapshot(
            url=url,
            title=title,
            visible_text=visible_text,
            screenshot_path=screenshot_path,
            vision=vision,
            links=links,
            quality_score=quality_score,
            quality_reason=quality_reason,
        )

    def evaluate_quality(self, snapshot: BrowserSnapshot) -> tuple[float, str]:
        """Reject bot-challenges, low-content, or navigation-heavy pages."""
        text = snapshot.visible_text.lower()
        
        # 1. Bot challenges / Captchas - removed length check as DDG footer is long
        bot_markers = [
            "captcha", "verify you are human", "blocked", "security check", 
            "robot", "checking your browser", "access denied", "unfortunately, bots use"
        ]
        if any(marker in text for marker in bot_markers):
            return 0.0, "bot_challenge_detected"
            
        # 2. Low content
        if len(text) < 300:
            return 0.2, "low_content"
            
        # 3. Cookie walls
        cookie_markers = ["cookie policy", "accept all cookies", "manage cookies", "privacy settings", "we use cookies"]
        if all(marker in text for marker in cookie_markers[:2]) and len(text) < 1200:
            return 0.3, "cookie_wall"

        # 4. Error pages
        error_markers = ["404 not found", "access denied", "site maintenance", "internal server error"]
        if any(marker in text for marker in error_markers):
            return 0.0, "error_page"

        return 1.0, "accepted"

    async def propose_next_action(
        self,
        topic: str,
        snapshot: BrowserSnapshot | None,
        behavior: BrowserBehavior,
    ) -> BrowserAction:
        if snapshot is None:
            query = sanitize_query(topic)
            # Prefer Wikipedia for educational seed topics
            search_base = os.getenv(
                "HUMAN_SEARCH_BASE_URL",
                "https://en.wikipedia.org/w/index.php?search=",
            )
            return BrowserAction(
                action_type="navigate",
                target=f"{search_base}{quote_plus(query)}",
                rationale=f"start human web research for seed topic at mood {behavior.mood}",
            )

        # Prefer educational/encyclopedic links if available
        edu_keywords = ["wikipedia.org", ".edu", "britannica.com", "plato.stanford.edu", "scholarpedia.org"]
        edu_links = [l for l in snapshot.links if any(kw in l for kw in edu_keywords)]
        
        if edu_links and random.random() < (behavior.link_jump_probability + 0.2):
            target = random.choice(edu_links[:behavior.max_links_to_scan])
            return BrowserAction("navigate", target, "preferential educational link jump")

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

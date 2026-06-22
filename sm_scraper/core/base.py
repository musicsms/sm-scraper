"""Base scraper class — all platform scrapers inherit from this."""

import asyncio
import json
import random
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from .auth import load_cookies, COOKIE_DIR
from .stealth import human_scroll, delay, long_delay, check_blocked, Backoff, RateLimiter
from .stealth import human_scroll, delay, long_delay, check_blocked, Backoff, RateLimiter
from .utils import (
    ensure_output_dir, save_json, save_media_urls,
    make_timestamp, timestamp_iso, summary_stats, OUTPUT_DIR
)


class BaseScraper(ABC):
    """
    Abstract base class for all social media scrapers.
    
    Usage:
        class FacebookScraper(BaseScraper):
            @property
            def platform(self) -> str: return "facebook"
            
            async def scrape_profile(self, username: str) -> dict: ...
            async def scrape_posts(self, username: str, limit: int) -> list: ...
            async def scrape_photos(self, username: str) -> list: ...
    """

    @property
    @abstractmethod
    def platform(self) -> str:
        """Platform name (used for cookie file, output dir)."""
        ...

    @property
    def base_url(self) -> str:
        """Base URL for this platform."""
        raise NotImplementedError

    def __init__(self, headless: bool = True, humanize: bool = True):
        self.headless = headless
        self.humanize = humanize
        self._browser = None
        self._context = None
        self._cookies_loaded = False

    # ── Browser lifecycle ──────────────────────────────────

    async def _start_browser(self):
        """Initialize CloakBrowser with saved cookies."""
        import cloakbrowser

        self._browser = await cloakbrowser.launch_async(
            headless=self.headless,
            proxy=self.proxy if hasattr(self, "proxy") and self.proxy else None,
            humanize=self.humanize,
        )
        self._context = await self._browser.new_context()

        # Load cookies if available
        cookies = load_cookies(self.platform)
        if cookies:
            for c in cookies:
                await self._context.add_cookies([c])
            self._cookies_loaded = True

        return self._browser

    async def _new_page(self):
        """Create a new page with the current context."""
        if not self._browser:
            await self._start_browser()
        return await self._context.new_page()

    async def close(self):
        """Clean up browser resources."""
        if self._browser:
            await self._browser.close()

    async def __aenter__(self):
        await self._start_browser()
        return self

    async def __aexit__(self, *args):
        await self.close()

    # ── Generic helpers ────────────────────────────────────

    def _user_dir(self, username: str) -> Path:
        return ensure_output_dir(self.platform, username)

    def _save_metadata(self, username: str, data: dict, suffix: str = "profile") -> Path:
        """Save scraped data as JSON with timestamp."""
        d = self._user_dir(username)
        fname = f"{suffix}_{username}_{make_timestamp()}.json"
        return save_json(data, d / fname)

    def _scroll_page(self, page, times: int = 3, delay: float = 2.0):
        """Scroll page down multiple times to load lazy content."""
        async def _scroller():
            for i in range(times):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(delay * 1000)
                print(f"  [scroll] {i+1}/{times}")
        return asyncio.ensure_future(_scroller())

    # ── Abstract scraping methods ───────────────────────────

    @abstractmethod
    async def scrape_profile(self, username: str) -> dict:
        """Scrape all available profile information."""
        ...

    @abstractmethod
    async def scrape_posts(self, username: str, limit: int = 10) -> list:
        """Scrape recent posts/threads."""
        ...

    @abstractmethod
    async def scrape_photos(self, username: str, limit: int = 20) -> list:
        """Scrape photo/album URLs."""
        ...

    # ── Virtual: can override ──────────────────────────────

    async def scrape_friends(self, username: str) -> list:
        """Scrape friends/followers list (optional)."""
        return []

    async def scrape_stories(self, username: str) -> list:
        """Scrape current stories (optional)."""
        return []

    async def scrape_all(self, username: str, include: Optional[list] = None) -> dict:
        """
        Scrape EVERYTHING available for a user.
        include: ['profile', 'posts', 'photos', 'friends', 'stories']
                 None = all available
        """
        results = {}

        if include is None:
            include = ["profile", "posts", "photos", "friends", "stories"]

        if "profile" in include:
            results["profile"] = await self.scrape_profile(username)
            self._save_metadata(username, results["profile"], "profile")

        if "posts" in include:
            results["posts"] = await self.scrape_posts(username)
            if results["posts"]:
                self._save_metadata(username, {"posts": results["posts"]}, "posts")
            print(f"  → Posts scraped: {len(results.get('posts', []))}")

        if "photos" in include:
            results["photos"] = await self.scrape_photos(username)
            if results["photos"]:
                self._save_metadata(username, {"photos": results["photos"]}, "photos")
            print(f"  → Photos scraped: {len(results.get('photos', []))}")

        if "friends" in include:
            results["friends"] = await self.scrape_friends(username)

        if "stories" in include:
            results["stories"] = await self.scrape_stories(username)

        # Summary
        summary_stats(
            {k: len(v) if isinstance(v, list) else "done" for k, v in results.items()},
            f"{self.platform.upper()} — {username}"
        )

        return results

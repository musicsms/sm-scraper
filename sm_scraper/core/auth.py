"""Universal authentication module — handles login & cookie persistence for any platform."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

from .utils import make_timestamp, timestamp_iso

COOKIE_DIR = Path.home() / ".sm_scraper_cookies"

PLATFORM_LOGIN_URLS = {
    "facebook": "https://www.facebook.com/login",
    "instagram": "https://www.instagram.com/accounts/login/",
    "threads": "https://www.threads.net/login",
    "tiktok": "https://www.tiktok.com/login",
    "linkedin": "https://www.linkedin.com/login",
    "x": "https://x.com/login",
    "reddit": "https://www.reddit.com/login",
    "telegram": "https://my.telegram.org/auth",
}


def _get_cookie_path(platform: str) -> Path:
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    return COOKIE_DIR / f"{platform}_cookies.json"


def save_cookies(context, platform: str) -> list:
    """Extract + save all cookies for a platform."""
    cookies = asyncio.run(context.cookies())
    path = _get_cookie_path(platform)
    path.write_text(json.dumps(cookies, indent=2))
    print(f"  ✓ Cookies saved ({len(cookies)} items): {path}")
    return cookies


def load_cookies(platform: str) -> Optional[list]:
    """Load saved cookies for a platform."""
    path = _get_cookie_path(platform)
    if path.exists():
        cookies = json.loads(path.read_text())
        print(f"  ✓ Loaded {len(cookies)} cookies for {platform}")
        return cookies
    print(f"  ✗ No saved cookies for {platform}")
    return None


async def _manual_login(platform: str, headless: bool = False):
    """
    1. Opens the platform login page in CloakBrowser
    2. User logs in manually 
    3. Press Enter to save cookies
    """
    from cloakbrowser import cloakbrowser

    url = PLATFORM_LOGIN_URLS.get(platform)
    if not url:
        raise ValueError(f"Unknown platform: {platform}. Supported: {list(PLATFORM_LOGIN_URLS.keys())}")

    print(f"\n{'═'*50}")
    print(f"🔐 {platform.upper()} — Manual Login")
    print(f"{'═'*50}")
    print(f"  1. Browser will open → {url}")
    print(f"  2. Log in MANUALLY (no rush)")
    print(f"  3. After login, come back to this terminal")
    print(f"  4. Press Enter to save cookies & close")
    print(f"{'═'*50}\n")

    async with cloakbrowser() as cb:
        browser = await cb.start()
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        print(f"  [*] Browser opened. Waiting for you to log in...")

        # Wait for user to press Enter
        await asyncio.get_event_loop().run_in_executor(None, input)

        # Save cookies
        cookies = await page.context.cookies()
        save_cookies(page.context, platform)

        # Additional token detection per platform
        if platform == "facebook":
            c_user = await page.evaluate(
                """() => { try { return document.cookie.match(/c_user=([^;]+)/)?.[1] || null; } catch(e) { return null; } }"""
            )
            if c_user:
                print(f"  ✓ Facebook user ID (c_user): {c_user}")

    print(f"  ✓ Login complete! Cookies ready for {platform}.\n")


def login(platform: str, headless: bool = False):
    """Synchronous entry point for manual login."""
    asyncio.run(_manual_login(platform, headless))


async def _validate_session(platform: str) -> bool:
    """Check if saved cookies still work."""
    from cloakbrowser import cloakbrowser

    cookies = load_cookies(platform)
    if not cookies:
        return False

    url = PLATFORM_LOGIN_URLS.get(platform, f"https://{platform}.com")

    async with cloakbrowser() as cb:
        browser = await cb.start(headless=True)
        context = await browser.new_context()
        for c in cookies:
            context.add_cookies([c])

        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        title = await page.title()
        # Check if login page (contains "log in" or "login")
        is_logged_in = "log in" not in title.lower() and "login" not in title.lower()
        
        if is_logged_in:
            print(f"  ✓ Session valid: {title}")
            return True
        else:
            print(f"  ✗ Session expired (detected login page)")
            return False


def validate(platform: str) -> bool:
    """Check session validity."""
    return asyncio.run(_validate_session(platform))

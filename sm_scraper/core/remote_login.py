"""
Remote Login Helper — VPS-friendly interactive login.
Dùng CloakBrowser headless + screenshot để login không cần màn hình thật.

Cách hoạt động:
  1. CloakBrowser mở login page (headless)
  2. Chụp screenshot → hiển thị trong dashboard
  3. User gõ email/pass vào ô input
  4. Script tự fill form + submit
  5. Nếu có 2FA → screenshot lại → user nhập code
  6. Login xong → save cookies
"""

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from datetime import datetime

LOGIN_URLS = {
    "facebook": "https://www.facebook.com/login",
    "instagram": "https://www.instagram.com/accounts/login/",
    "threads": "https://www.threads.net/login",
    "tiktok": "https://www.tiktok.com/login",
    "linkedin": "https://www.linkedin.com/login",
    "x": "https://x.com/login",
    "reddit": "https://www.reddit.com/login",
    "youtube": "https://accounts.google.com/ServiceLogin",  # Google account
}

COOKIE_DIR = Path.home() / ".sm_scraper_cookies"


class RemoteLogin:
    """Quản lý phiên login từ xa qua dashboard."""

    def __init__(self, platform: str):
        self.platform = platform
        self.browser = None
        self.context = None
        self.page = None
        self.status = "idle"
        self.screenshot_path = None
        self.page_text = ""
        self.page_title = ""
        self.login_url = LOGIN_URLS.get(platform, f"https://{platform}.com/login")

    async def open_login_page(self):
        """Mở browser + login page, chụp screenshot đầu tiên."""
        import cloakbrowser

        self.status = "starting"
        
        self.browser = await cloakbrowser.launch_async(
            headless=True,
            humanize=True,
        )
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()

        # Đi đến login page
        await self.page.goto(self.login_url, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(3000)

        # Chụp screenshot
        await self._capture_screenshot()

        # Lấy text trên page để biết cần field gì
        self.page_text = await self.page.evaluate("document.body.innerText")
        self.page_title = await self.page.title()

        self.status = "waiting_credentials"
        return self.status

    async def fill_form(self, field_type: str, value: str):
        """Điền thông tin vào form login."""
        if not self.page:
            return {"error": "Browser not started"}

        try:
            field_selectors = {
                "email": [
                    'input[name="email"]',
                    'input[name="login"]',
                    'input[type="email"]',
                    'input[name="username"]',
                    'input[autocomplete="username"]',
                    'input[placeholder*="email" i]',
                    'input[placeholder*="phone" i]',
                    'input[placeholder*="user" i]',
                    '#email',
                    'input[data-testid*="email"]',
                    'input[data-testid*="username"]',
                ],
                "password": [
                    'input[name="pass"]',
                    'input[type="password"]',
                    'input[name="password"]',
                    'input[autocomplete="current-password"]',
                    '#pass',
                    'input[data-testid*="password"]',
                ],
            }

            selectors = field_selectors.get(field_type, [])
            filled = False

            for selector in selectors:
                try:
                    el = await self.page.query_selector(selector)
                    if el:
                        await el.fill(value)
                        filled = True
                        print(f"  ✓ Filled {field_type} using: {selector}")
                        break
                except:
                    continue

            if not filled:
                # Fallback: tìm input trống đầu tiên
                inputs = await self.page.query_selector_all('input:not([type="hidden"]):not([type="submit"])')
                for inp in inputs:
                    try:
                        placeholder = await inp.get_attribute("placeholder") or ""
                        input_type = await inp.get_attribute("type") or ""
                        if field_type == "email" and ("email" in placeholder.lower() or "phone" in placeholder.lower() or input_type == "email"):
                            await inp.fill(value)
                            filled = True
                            break
                        elif field_type == "password" and input_type == "password":
                            await inp.fill(value)
                            filled = True
                            break
                    except:
                        continue

            await self._capture_screenshot()
            return {"success": filled, "field": field_type}

        except Exception as e:
            return {"error": str(e)}

    async def submit_login(self):
        """Submit form login."""
        if not self.page:
            return {"error": "Browser not started"}

        try:
            # Try multiple submit methods
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Log In")',
                'button:has-text("Login")',
                'button:has-text("Sign In")',
                'button:has-text("Sign in")',
                'button:has-text("Continue")',
                'button:has-text("Next")',
                'div[role="button"]:has-text("Log In")',
                '#loginbutton',
                'button[name="login"]',
                'button[data-testid*="login"]',
                'button[data-testid*="signin"]',
                # Facebook specific
                'button[data-testid="royal_login_button"]',
                # Instagram specific
                'button[type="submit"]:has-text("Log in")',
            ]

            submitted = False
            for selector in submit_selectors:
                try:
                    btn = await self.page.query_selector(selector)
                    if btn:
                        await btn.click()
                        submitted = True
                        print(f"  ✓ Clicked submit: {selector}")
                        break
                except:
                    continue

            if not submitted:
                # Press Enter
                await self.page.keyboard.press("Enter")
                submitted = True

            await self.page.wait_for_timeout(5000)
            await self._capture_screenshot()

            # Check login result
            self.page_text = await self.page.evaluate("document.body.innerText")
            self.page_title = await self.page.title()

            is_logged_in = not any(w in self.page_title.lower() for w in ["log in", "login", "sign in"])

            return {
                "success": is_logged_in,
                "submitted": submitted,
                "title": self.page_title,
                "page_text_snippet": self.page_text[:1000],
            }

        except Exception as e:
            return {"error": str(e)}

    async def check_2fa(self) -> bool:
        """Kiểm tra có đang ở màn hình 2FA không."""
        text = self.page_text.lower()
        # Common 2FA indicators
        keywords = [
            "two-factor", "2fa", "authentication code", "verification code",
            "confirm your identity", "approve from your phone", "security code",
            "enter the code", "authenticator", "text message", "sms code",
            "code sent", "checkpoint", "enter code",
        ]
        return any(k in text for k in keywords)

    async def enter_2fa_code(self, code: str):
        """Nhập mã 2FA."""
        if not self.page:
            return {"error": "Browser not started"}

        try:
            code_selectors = [
                'input[name="approvals_code"]',
                'input[name="code"]',
                'input[placeholder*="code" i]',
                'input[inputmode="numeric"]',
                'input[type="text"]',
            ]

            filled = False
            for selector in code_selectors:
                try:
                    el = await self.page.query_selector(selector)
                    if el:
                        await el.fill(code)
                        filled = True
                        break
                except:
                    continue

            if filled:
                # Submit code
                await self.page.keyboard.press("Enter")
                await self.page.wait_for_timeout(5000)
                await self._capture_screenshot()
                self.page_text = await self.page.evaluate("document.body.innerText")
                self.page_title = await self.page.title()

            return {"success": filled}

        except Exception as e:
            return {"error": str(e)}

    async def save_cookies(self):
        """Lưu cookies sau khi login thành công."""
        if not self.context:
            return {"error": "No context"}

        cookies = await self.context.cookies()
        cookie_path = COOKIE_DIR / f"{self.platform}_cookies.json"
        cookie_path.parent.mkdir(parents=True, exist_ok=True)
        cookie_path.write_text(json.dumps(cookies, indent=2))

        self.status = "logged_in"
        return {"success": True, "count": len(cookies), "path": str(cookie_path)}

    async def _capture_screenshot(self):
        """Chụp screenshot của page hiện tại."""
        if not self.page:
            return
        try:
            # Save to a known temp path
            self.screenshot_path = f"/tmp/sm_scraper_login_{self.platform}.png"
            await self.page.screenshot(path=self.screenshot_path, full_page=False)
        except Exception as e:
            print(f"  ! Screenshot error: {e}")

    async def close(self):
        """Dọn dẹp."""
        if self.browser:
            await self.browser.close()
        self.status = "closed"


# ── Synchronous wrappers for Streamlit ──

def run_open_login(platform: str) -> dict:
    """Mở login page (sync wrapper)."""
    async def _run():
        rl = RemoteLogin(platform)
        status = await rl.open_login_page()
        return {
            "status": status,
            "screenshot": rl.screenshot_path,
            "title": rl.page_title,
            "text_snippet": rl.page_text[:500],
            "_instance": rl,
        }
    return asyncio.run(_run())


def run_fill_form(instance, field_type: str, value: str) -> dict:
    """Điền field (sync wrapper)."""
    async def _run():
        result = await instance.fill_form(field_type, value)
        result["screenshot"] = instance.screenshot_path
        return result
    return asyncio.run(_run())


def run_submit(instance) -> dict:
    """Submit form (sync wrapper)."""
    async def _run():
        result = await instance.submit_login()
        result["screenshot"] = instance.screenshot_path
        return result
    return asyncio.run(_run())


def run_check_2fa(instance) -> bool:
    """Check 2FA (sync wrapper)."""
    async def _run():
        return await instance.check_2fa()
    return asyncio.run(_run())


def run_enter_2fa(instance, code: str) -> dict:
    """Enter 2FA code (sync wrapper)."""
    async def _run():
        result = await instance.enter_2fa_code(code)
        result["screenshot"] = instance.screenshot_path
        return result
    return asyncio.run(_run())


def run_save_cookies(instance) -> dict:
    """Save cookies (sync wrapper)."""
    async def _run():
        return await instance.save_cookies()
    return asyncio.run(_run())


def run_close(instance):
    """Close browser (sync wrapper)."""
    async def _run():
        await instance.close()
    return asyncio.run(_run())

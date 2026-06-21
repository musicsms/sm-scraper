"""
Telegram scraper — extracts channel/group information:
  • Channel (name, description, member count, avatar)
  • Messages (text, media, dates, forwarded from)
  • Can use Telethon if configured for full access

TWO MODES:
  1. Web (default) — scrapes public t.me pages via CloakBrowser, no auth needed
  2. Telethon — if ~/.sm_scraper_telegram.json exists with api_id + api_hash

Usage:
    python -m sm_scraper telegram channel <channel>       # t.me/<channel>
    python -m sm_scraper telegram messages <channel>       # t.me/s/<channel> or Telethon
    python -m sm_scraper telegram all <channel>
    
    # For Telethon: create ~/.sm_scraper_telegram.json
    # {"api_id": 12345, "api_hash": "abc...", "phone": "84868609591"}
"""

import json
import re
from pathlib import Path
from ..core.base import BaseScraper

TELETHON_CONFIG = Path.home() / ".sm_scraper_telegram.json"


class TelegramScraper(BaseScraper):

    @property
    def platform(self) -> str:
        return "telegram"

    @property
    def base_url(self) -> str:
        return "https://t.me"

    def __init__(self, headless=True, humanize=True):
        super().__init__(headless, humanize)
        self._use_telethon = TELETHON_CONFIG.exists()
        self._telethon_config = None
        if self._use_telethon:
            self._telethon_config = json.loads(TELETHON_CONFIG.read_text())

    # ═══════════════════════════════════════════════════════
    # CHANNEL INFO (web)
    # ═══════════════════════════════════════════════════════

    async def scrape_profile(self, username: str) -> dict:
        """Extract channel info from t.me web page."""
        result = {
            "url": f"{self.base_url}/{username}",
            "channel": username,
            "scraped_at": self._ts(),
            "title": None,
            "description": None,
            "avatar_url": None,
            "member_count": None,
            "has_web_preview": False,
            "type": "unknown",  # channel, group, bot
        }

        # ── Via Telethon (if configured) ──
        if self._use_telethon:
            try:
                tele_data = await self._scrape_via_telethon(username)
                if tele_data:
                    result.update(tele_data)
                    result["source"] = "telethon"
                    self._save_metadata(username, result, "channel")
                    return result
            except Exception as e:
                print(f"  ! Telethon failed: {e}, falling back to web")

        # ── Via web (t.me) ──
        page = await self._new_page()
        await page.goto(f"{self.base_url}/{username}", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        # ── Meta ──
        meta = await page.evaluate("""() => {
            const m = {};
            document.querySelectorAll('meta[property], meta[name]').forEach(el => {
                m[el.getAttribute('property') || el.getAttribute('name')] = el.getAttribute('content');
            });
            return m;
        }""")
        result["meta"] = {"og": meta}
        result["avatar_url"] = meta.get("og:image")
        result["title"] = meta.get("og:title", meta.get("twitter:title"))

        # ── Body text ──
        text = await page.evaluate("document.body.innerText")
        result["meta"]["raw_text_snippet"] = text[:5000]
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # ── Parse ──
        for line in lines:
            # Description / subtitle
            if 'subscriber' in line.lower() or 'member' in line.lower():
                result["member_count"] = line
            elif 'bot' in line.lower() and len(line) < 30:
                result["type"] = "bot"
            elif line.startswith('@') and line[1:] == username:
                result["type"] = "channel"

        # ── Description (often after title in meta) ──
        og_desc = meta.get("og:description", meta.get("description", ""))
        if og_desc and len(og_desc) > 10:
            result["description"] = og_desc[:2000]

        # ── Try s/ page for web preview ──
        try:
            await page.goto(f"{self.base_url}/s/{username}", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            preview_text = await page.evaluate("document.body.innerText")
            if len(preview_text) > 100:
                result["has_web_preview"] = True
                result["meta"]["web_preview_snippet"] = preview_text[:5000]
                print("  ✓ Web preview available (t.me/s/...)")
        except:
            pass

        result["source"] = "web"
        self._save_metadata(username, result, "channel")
        return result

    # ═══════════════════════════════════════════════════════
    # MESSAGES (web preview or Telethon)
    # ═══════════════════════════════════════════════════════

    async def scrape_posts(self, username: str, limit: int = 30) -> list:
        """Scrape recent messages from the channel."""

        # ── Telethon (full access) ──
        if self._use_telethon:
            try:
                messages = await self._scrape_messages_telethon(username, limit)
                if messages:
                    print(f"  → Messages via Telethon: {len(messages)}")
                    self._save_metadata(username, {"messages": messages}, "messages")
                    return messages
            except Exception as e:
                print(f"  ! Telethon failed: {e}")

        # ── Web fallback ──
        page = await self._new_page()
        url = f"{self.base_url}/s/{username}"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        # Scroll for older messages
        for i in range(min(limit // 5 + 1, 4)):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)
            print(f"  [scroll] {i+1}")

        messages = await page.evaluate(f"""() => {{
            const items = [];
            // Telegram web messages
            const containers = document.querySelectorAll('.tgme_widget_message_wrap, .tgme_widget_message, div[class*="message"]');
            
            containers.forEach(c => {{
                const text = c.innerText.trim();
                if (text.length < 2) return;
                
                // Text content
                const body = c.querySelector('.tgme_widget_message_text, div[class*="text"]');
                
                // Author (for groups)
                const author = c.querySelector('.tgme_widget_message_from_author, a[class*="author"]');
                
                // Date
                const time = c.querySelector('time, .tgme_widget_message_date, a[class*="date"]');
                
                // Media
                const imgs = Array.from(c.querySelectorAll('img'))
                    .map(i => i.src)
                    .filter(s => s && !s.includes('telegram.org/img/') && !s.includes('t.me/i/'));
                
                // Forwarded from
                const forward = c.querySelector('.tgme_widget_message_forwarded_from, div[class*="forward"]');
                
                items.push({{
                    text: text.slice(0, 3000),
                    body: body ? body.innerText.trim().slice(0, 2000) : null,
                    author: author ? author.innerText.trim() : null,
                    timestamp: time ? (time.getAttribute('datetime') || time.innerText) : null,
                    images: imgs.slice(0, 5),
                    forwarded_from: forward ? forward.innerText.trim() : null,
                }});
            }});
            
            return items.slice(0, {limit});
        }}""")

        print(f"  → Messages (web): {len(messages)}")
        if messages:
            self._save_metadata(username, {"messages": messages}, "messages")
        return messages

    # ═══════════════════════════════════════════════════════
    # TELETHON BACKEND
    # ═══════════════════════════════════════════════════════

    async def _scrape_via_telethon(self, username: str) -> dict:
        """Get full channel info via Telethon."""
        import asyncio
        from telethon import TelegramClient

        cfg = self._telethon_config
        client = TelegramClient("sm_scraper_session", cfg["api_id"], cfg["api_hash"])

        try:
            await client.start(phone=cfg.get("phone"))
            entity = await client.get_entity(username)

            result = {
                "title": entity.title if hasattr(entity, 'title') else None,
                "description": getattr(entity, 'about', None),
                "member_count": getattr(entity, 'participants_count', None) or getattr(entity, 'members_count', None),
                "type": "channel" if hasattr(entity, 'broadcast') and entity.broadcast else
                        "group" if hasattr(entity, 'megagroup') and entity.megagroup else "unknown",
                "is_verified": getattr(entity, 'verified', False),
                "is_scam": getattr(entity, 'scam', False),
                "is_fake": getattr(entity, 'fake', False),
                "username": getattr(entity, 'username', username),
                "source": "telethon",
            }

            if hasattr(entity, 'photo'):
                # Photo URL construction
                result["avatar_url"] = f"https://t.me/i/userpic/320/{username}.jpg"

            return result
        finally:
            await client.disconnect()

    async def _scrape_messages_telethon(self, username: str, limit: int) -> list:
        """Get full message history via Telethon."""
        from telethon import TelegramClient

        cfg = self._telethon_config
        client = TelegramClient("sm_scraper_session", cfg["api_id"], cfg["api_hash"])

        try:
            await client.start(phone=cfg.get("phone"))
            messages = []
            async for msg in client.iter_messages(username, limit=limit):
                m = {
                    "id": msg.id,
                    "date": msg.date.isoformat() if msg.date else None,
                    "text": (msg.text or msg.message or "")[:3000],
                    "sender_id": msg.sender_id,
                    "has_media": bool(msg.media),
                    "media_type": type(msg.media).__name__ if msg.media else None,
                    "views": getattr(msg, 'views', None),
                    "forwards": getattr(msg, 'forwards', None),
                    "reply_to": msg.reply_to_msg_id,
                }

                # Media URLs
                if hasattr(msg, 'photo') and msg.photo:
                    m["media_url"] = f"https://t.me/{username}/{msg.id}"
                if hasattr(msg, 'video') and msg.video:
                    m["has_video"] = True

                # Grouped messages (albums)
                if hasattr(msg, 'grouped_id') and msg.grouped_id:
                    m["grouped_id"] = msg.grouped_id

                messages.append(m)

            return messages
        finally:
            await client.disconnect()

    # ═══════════════════════════════════════════════════════
    # OVERRIDE scrape_all — supports messages too
    # ═══════════════════════════════════════════════════════

    async def scrape_all(self, username: str, include=None) -> dict:
        if include is None:
            include = ["profile", "messages"]
        return await super().scrape_all(username, include)

    # ═══════════════════════════════════════════════════════
    # PHOTOS — not meaningful for Telegram
    # ═══════════════════════════════════════════════════════

    async def scrape_photos(self, username: str, limit: int = 10) -> list:
        """Extract images from messages."""
        messages = await self.scrape_posts(username, limit)
        photos = []
        for m in messages:
            if m.get("images"):
                photos.extend(m["images"])
        return photos[:limit]

    def _ts(self):
        from ..core.utils import timestamp_iso
        return timestamp_iso()

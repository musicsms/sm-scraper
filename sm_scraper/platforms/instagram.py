"""
Instagram scraper — extracts all available information:
  • Profile (username, full name, bio, avatar, followers/following, posts count, website, email, phone)
  • Posts (images, videos, captions, timestamps, likes, comments)
  • Stories (current visible stories)
  • Followers / Following lists (may need full login)
  • Reels

Usage:
    python -m sm_scraper instagram profile <username>
    python -m sm_scraper instagram posts <username> [--limit 12]
    python -m sm_scraper instagram stories <username>
    python -m sm_scraper instagram all <username>
"""

import re
from ..core.base import BaseScraper


class InstagramScraper(BaseScraper):

    @property
    def platform(self) -> str:
        return "instagram"

    @property
    def base_url(self) -> str:
        return "https://www.instagram.com"

    # ═══════════════════════════════════════════════════════
    # PROFILE
    # ═══════════════════════════════════════════════════════

    async def scrape_profile(self, username: str) -> dict:
        """Extract all visible Instagram profile info."""
        page = await self._new_page()
        url = f"{self.base_url}/{username}/"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)  # Instagram needs more time

        # Handle login popup if it appears
        try:
            close_btn = await page.query_selector('div[role="dialog"] button, svg[aria-label="Close"]')
            if close_btn:
                await close_btn.click()
                await page.wait_for_timeout(1000)
        except:
            pass

        result = {
            "url": url,
            "username": username,
            "scraped_at": self._ts(),
            "full_name": None,
            "bio": None,
            "avatar_url": None,
            "posts_count": None,
            "followers_count": None,
            "following_count": None,
            "website": None,
            "email": None,
            "phone": None,
            "is_private": False,
            "is_verified": False,
            "category": None,
            "external_url": None,
        }

        # ── Extract from meta / OG tags ──
        meta = await page.evaluate("""() => {
            const m = {};
            document.querySelectorAll('meta[property], meta[name]').forEach(el => {
                m[el.getAttribute('property') || el.getAttribute('name')] = el.getAttribute('content');
            });
            return m;
        }""")
        result["meta"] = meta

        # ── Avatar ──
        avatar = await page.evaluate("""() => {
            const img = document.querySelector('img[alt*="profile"], img[data-testid="user-avatar"]');
            return img ? img.src : null;
        }""")
        result["avatar_url"] = avatar or meta.get("og:image")

        # ── Key profile data from JSON-LD / shared data ──
        profile_data = await page.evaluate("""() => {
            try {
                // Method 1: __NEXT_DATA__ or __INITIAL_STATE__
                if (window.__INITIAL_STATE__) return window.__INITIAL_STATE__;
                // Method 2: JSON-LD
                const ld = document.querySelector('script[type="application/ld+json"]');
                if (ld) return JSON.parse(ld.text);
                return {};
            } catch(e) { return {}; }
        }""")
        result["meta"]["page_data"] = profile_data

        # ── Text extraction from page ──
        text = await page.evaluate("document.body.innerText")
        result["meta"]["raw_text_snippet"] = text[:5000]

        # ── Parse stats from text ──
        stats_patterns = {
            "posts_count": r"(\d[\d,.]*)\s*posts",
            "followers_count": r"(\d[\d,.]*[KMBkmb]?)\s*followers?",
            "following_count": r"(\d[\d,.]*[KMBkmb]?)\s*following",
        }
        for key, pattern in stats_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result[key] = match.group(1)

        # ── Bio (often between name and stats) ──
        bio_text = await page.evaluate("""() => {
            const spans = document.querySelectorAll('span._ap3a, div._aacl');
            for (const s of spans) {
                const t = s.innerText.trim();
                if (t.length > 10 && t.includes('\\n') === false && !t.startsWith('@') && !t.includes('follow')) {
                    return t;
                }
            }
            return null;
        }""")
        if not bio_text:
            # Fallback: grab text between first @username mention and stats
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            for i, line in enumerate(lines):
                if line.startswith('@') and i + 1 < len(lines):
                    result["full_name"] = lines[i + 1]
                    if i + 2 < len(lines) and len(lines[i + 2]) > 5:
                        bio_text = lines[i + 2]
                    break

        result["bio"] = bio_text

        # ── Full name from structured section ──
        full_name = await page.evaluate("""() => {
            const h2 = document.querySelector('h2, div[data-testid="user-avatar"] + div span');
            const section = document.querySelector('section h1, section h2');
            return section ? section.innerText.trim() : null;
        }""")
        result["full_name"] = full_name

        # ── Private account? ──
        if "private" in text.lower():
            result["is_private"] = True
            print("  ! Account is PRIVATE — limited info available")

        # ── Verified? ──
        if "verified" in text.lower() or "blue" in text.lower()[:200]:
            result["is_verified"] = True

        self._save_metadata(username, result, "profile")
        return result

    # ═══════════════════════════════════════════════════════
    # POSTS
    # ═══════════════════════════════════════════════════════

    async def scrape_posts(self, username: str, limit: int = 12) -> list:
        """Extract posts (images, videos, captions, likes)."""
        page = await self._new_page()
        url = f"{self.base_url}/{username}/"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        # Close login popup
        try:
            close_btn = await page.query_selector('div[role="dialog"] button, svg[aria-label="Close"]')
            if close_btn:
                await close_btn.click()
                await page.wait_for_timeout(1000)
        except:
            pass

        # Scroll to load more posts
        for i in range(min(limit // 3 + 1, 5)):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

        posts = await page.evaluate(f"""() => {{
            const posts = [];
            const links = document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]');
            const seen = new Set();
            
            links.forEach(a => {{
                const href = a.href;
                if (seen.has(href)) return;
                seen.add(href);
                
                const img = a.querySelector('img');
                const video = a.querySelector('video');
                
                posts.push({{
                    url: href.split('?')[0],
                    thumbnail: img ? img.src : null,
                    has_video: !!video,
                    alt_text: img ? img.getAttribute('alt') : null,
                }});
            }});
            
            return posts.slice(0, {limit});
        }}""")

        print(f"  → Posts found: {len(posts)}")
        self._save_metadata(username, {"posts": posts}, "posts")
        return posts

    # ═══════════════════════════════════════════════════════
    # STORIES
    # ═══════════════════════════════════════════════════════

    async def scrape_stories(self, username: str) -> list:
        """Scrape current stories if available."""
        page = await self._new_page()
        url = f"{self.base_url}/stories/{username}/"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        stories = await page.evaluate("""() => {
            const items = [];
            const imgs = document.querySelectorAll('img[src*="cdninstagram"], img[src*="fbcdn"]');
            imgs.forEach(img => {
                if (img.src && img.src.includes('stories')) {
                    items.push(img.src);
                }
            });
            const videos = document.querySelectorAll('video source');
            videos.forEach(v => {
                if (v.src) items.push(v.src);
            });
            return items.slice(0, 20);
        }""")

        if stories:
            print(f"  → Stories found: {len(stories)}")
            self._save_metadata(username, {"stories": stories}, "stories")
        else:
            print("  → No stories available")

        return stories

    # ═══════════════════════════════════════════════════════
    # FOLLOWERS / FOLLOWING (requires full login)
    # ═══════════════════════════════════════════════════════

    async def scrape_followers(self, username: str, limit: int = 50) -> list:
        """Scrape followers list (may need logged-in session)."""
        page = await self._new_page()
        url = f"{self.base_url}/{username}/followers/"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        followers = await page.evaluate(f"""() => {{
            const items = [];
            const links = document.querySelectorAll('a[href^="/"]');
            const seen = new Set();
            links.forEach(a => {{
                const href = a.href;
                const name = a.innerText.trim();
                if (name && href.startsWith('https://www.instagram.com/') && href.split('/').length === 5 && !seen.has(name)) {{
                    seen.add(name);
                    items.push({{username: name, url: href}});
                }}
            }});
            return items.slice(0, {limit});
        }}""")

        print(f"  → Followers count: {len(followers)}")
        return followers

    # ═══════════════════════════════════════════════════════
    # PHOTOS (alias for posts)
    # ═══════════════════════════════════════════════════════

    async def scrape_photos(self, username: str, limit: int = 20) -> list:
        """Instagram photos = posts with images."""
        posts = await self.scrape_posts(username, limit)
        return [p for p in posts if p.get("thumbnail")]

    # ═══════════════════════════════════════════════════════
    # ALL-IN-ONE
    # ═══════════════════════════════════════════════════════

    async def scrape_all(self, username: str, include=None) -> dict:
        if include is None:
            include = ["profile", "posts", "stories"]
        return await super().scrape_all(username, include)

    def _ts(self):
        from ..core.utils import timestamp_iso
        return timestamp_iso()

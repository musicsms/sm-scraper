"""
Threads scraper — extracts all available information:
  • Profile (username, full name, bio, avatar, followers/following, threads count)
  • Threads (text, images, replies, reposts, likes)
  • Replies

Usage:
    python -m sm_scraper threads profile <username>
    python -m sm_scraper threads posts <username> [--limit 20]
    python -m sm_scraper threads all <username>
"""

import re
from ..core.base import BaseScraper


class ThreadsScraper(BaseScraper):

    @property
    def platform(self) -> str:
        return "threads"

    @property
    def base_url(self) -> str:
        return "https://www.threads.net"

    # ═══════════════════════════════════════════════════════
    # PROFILE
    # ═══════════════════════════════════════════════════════

    async def scrape_profile(self, username: str) -> dict:
        """Extract all visible Threads profile info."""
        page = await self._new_page()
        url = f"{self.base_url}/@{username}"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)  # Threads is React-heavy, needs time

        # Handle login popup
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
            "followers_count": None,
            "following_count": None,
            "threads_count": None,
            "is_verified": False,
            "link_in_bio": None,
        }

        # ── Meta tags ──
        meta = await page.evaluate("""() => {
            const m = {};
            document.querySelectorAll('meta[property], meta[name]').forEach(el => {
                m[el.getAttribute('property') || el.getAttribute('name')] = el.getAttribute('content');
            });
            return m;
        }""")
        result["meta"] = meta
        result["avatar_url"] = meta.get("og:image")
        result["full_name"] = meta.get("og:title", "").replace(" (@' + username + ') • Threads, Say more", "").replace(" (@' + username + ') • Threads", "").strip() or None

        # ── Avatar via image selector ──
        if not result["avatar_url"]:
            avatar = await page.evaluate("""() => {
                const img = document.querySelector('img[draggable="true"]');
                return img ? img.src : null;
            }""")
            result["avatar_url"] = avatar

        # ── Text extraction ──
        text = await page.evaluate("document.body.innerText")
        result["meta"]["raw_text_snippet"] = text[:5000]

        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # ── Parse profile info from page text ──
        for i, line in enumerate(lines):
            # Full name (right after @username)
            if line.startswith('@') and i + 1 < len(lines):
                result["full_name"] = lines[i + 1]
                # Bio often follows
                if i + 2 < len(lines) and not lines[i + 2].endswith('followers') and not lines[i + 2].endswith('following'):
                    result["bio"] = lines[i + 2]
                    # Link in bio often on the next line after bio
                    if i + 3 < len(lines) and 'http' in lines[i + 3]:
                        result["link_in_bio"] = lines[i + 3]

            # Stats
            if 'followers' in line or 'following' in line:
                if not result["followers_count"]:
                    match = re.search(r'([\d,.]+[KMBkmb]?)\s*followers?', line)
                    if match:
                        result["followers_count"] = match.group(1)
                if not result["following_count"]:
                    match = re.search(r'([\d,.]+[KMBkmb]?)\s*following', line)
                    if match:
                        result["following_count"] = match.group(1)

        # ── Verified check ──
        if 'verified' in text.lower()[:1000]:
            result["is_verified"] = True

        self._save_metadata(username, result, "profile")
        return result

    # ═══════════════════════════════════════════════════════
    # THREADS (posts)
    # ═══════════════════════════════════════════════════════

    async def scrape_posts(self, username: str, limit: int = 20) -> list:
        """Scrape threads (text posts, images, replies, likes)."""
        page = await self._new_page()
        url = f"{self.base_url}/@{username}"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        # Close popup
        try:
            close_btn = await page.query_selector('div[role="dialog"] button, svg[aria-label="Close"]')
            if close_btn:
                await close_btn.click()
                await page.wait_for_timeout(1000)
        except:
            pass

        # Scroll to load threads
        for i in range(min(limit // 5 + 1, 5)):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2500)
            print(f"  [scroll] {i+1}")

        threads = await page.evaluate(f"""() => {{
            const items = [];
            const articles = document.querySelectorAll('article, div[role="article"]');
            
            articles.forEach((article) => {{
                const text = article.innerText.trim();
                if (text.length < 5) return;
                
                // Author
                const author = article.querySelector('a[href*="/@"]');
                
                // Images
                const imgs = Array.from(article.querySelectorAll('img'))
                    .map(i => i.src)
                    .filter(s => s && s.length > 20);
                
                // Text content (first meaningful paragraph)
                const spans = article.querySelectorAll('span');
                let content = '';
                spans.forEach(s => {{
                    const t = s.innerText.trim();
                    if (t.length > 10 && !t.startsWith('@') && !t.includes('·')) {{
                        content = t;
                    }}
                }});
                
                // Timestamp
                const time = article.querySelector('time');
                
                // Stats
                const stats = article.innerText.match(/(\\d+[KMBkmb]?)\\s*(like|reply|repost)/gi) || [];
                
                items.push({{
                    text: content.slice(0, 1000) || text.slice(0, 300),
                    author: author ? author.innerText.trim() : null,
                    author_url: author ? author.href.split('?')[0] : null,
                    images: imgs.slice(0, 4),
                    timestamp: time ? (time.getAttribute('datetime') || time.innerText) : null,
                    stats: stats,
                }});
            }});
            
            return items.slice(0, {limit});
        }}""")

        print(f"  → Threads found: {len(threads)}")
        self._save_metadata(username, {"threads": threads}, "posts")
        return threads

    # ═══════════════════════════════════════════════════════
    # PHOTOS (images from threads)
    # ═══════════════════════════════════════════════════════

    async def scrape_photos(self, username: str, limit: int = 20) -> list:
        """Extract images from threads."""
        threads = await self.scrape_posts(username, limit)
        photos = []
        for t in threads:
            if t.get("images"):
                photos.extend(t["images"])

        print(f"  → Photos extracted: {len(photos)}")
        if photos:
            self._save_metadata(username, {"photo_urls": photos}, "photos")
        return photos[:limit]

    # ═══════════════════════════════════════════════════════
    # ALL-IN-ONE
    # ═══════════════════════════════════════════════════════

    async def scrape_all(self, username: str, include=None) -> dict:
        if include is None:
            include = ["profile", "posts", "photos"]
        return await super().scrape_all(username, include)

    def _ts(self):
        from ..core.utils import timestamp_iso
        return timestamp_iso()

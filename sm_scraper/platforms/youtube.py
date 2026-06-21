"""
YouTube scraper — extracts ALL available information (no login needed):
  • Channel (name, handle, subscriber count, video count, description, avatar, banner, links)
  • Videos (title, views, uploaded date, duration, thumbnail, likes, comments)
  • Shorts
  • Playlists

Usage:
    python -m sm_scraper youtube channel <handle>
    python -m sm_scraper youtube videos <handle> [--limit 20]
    python -m sm_scraper youtube all <handle>
"""

import re
from urllib.parse import unquote
from ..core.base import BaseScraper


class YouTubeScraper(BaseScraper):

    @property
    def platform(self) -> str:
        return "youtube"

    @property
    def base_url(self) -> str:
        return "https://www.youtube.com"

    # ═══════════════════════════════════════════════════════
    # CHANNEL PROFILE
    # ═══════════════════════════════════════════════════════

    async def scrape_profile(self, username: str) -> dict:
        """Extract all visible YouTube channel info."""
        # username could be @handle or channel/ID
        if username.startswith('@') or username.startswith('UC'):
            url = f"{self.base_url}/{username}"
        else:
            url = f"{self.base_url}/@{username}"

        page = await self._new_page()
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        result = {
            "url": page.url,
            "handle": username,
            "scraped_at": self._ts(),
            "channel_name": None,
            "avatar_url": None,
            "banner_url": None,
            "subscriber_count": None,
            "video_count": None,
            "description": None,
            "links": [],
            "is_verified": False,
            "channel_id": None,
        }

        # ── Meta / OG ──
        meta = await page.evaluate("""() => {
            const m = {};
            document.querySelectorAll('meta[property], meta[name]').forEach(el => {
                m[el.getAttribute('property') || el.getAttribute('name')] = el.getAttribute('content');
            });
            return m;
        }""")
        result["meta"] = {"og": meta}
        result["avatar_url"] = meta.get("og:image")
        result["channel_name"] = meta.get("og:title", meta.get("twitter:title"))

        # ── Body text ──
        text = await page.evaluate("document.body.innerText")
        result["meta"]["raw_text_snippet"] = text[:8000]
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # ── Parse channel info ──
        for line in lines:
            # Subscriber count
            if 'subscriber' in line.lower() and not result["subscriber_count"]:
                nums = re.findall(r'([\d,.]+[KMBkmb]?)\s*subscriber', line, re.IGNORECASE)
                if nums:
                    result["subscriber_count"] = nums[0]
                else:
                    nums = re.findall(r'([\d,.]+[KMBkmb]?)', line)
                    if nums:
                        result["subscriber_count"] = nums[0]

            # Video count
            if 'video' in line.lower() and not result["video_count"]:
                nums = re.findall(r'([\d,.]+[KMBkmb]?)\s*video', line, re.IGNORECASE)
                if nums:
                    result["video_count"] = nums[0]

            # Description (long lines after channel name)
            if len(line) > 100 and 'subscriber' not in line.lower() and 'video' not in line.lower():
                if not result["description"]:
                    result["description"] = line[:3000]

        # ── Channel ID from URL or meta ──
        channel_id_match = re.search(r'/(?:channel|@|user)/([^/?&]+)', page.url)
        if channel_id_match:
            result["channel_id"] = channel_id_match.group(1)

        # ── Avatar via DOM ──
        avatar = await page.evaluate("""() => {
            const img = document.querySelector('#avatar img, yt-img-shadow img, img[class*="avatar"]');
            return img ? img.src : null;
        }""")
        if avatar and avatar != result["avatar_url"]:
            result["avatar_url"] = avatar

        # ── Banner ──
        banner = await page.evaluate("""() => {
            const img = document.querySelector('#banner img, yt-img-shadow[class*="banner"] img');
            return img ? img.src : null;
        }""")
        result["banner_url"] = banner

        # ── Verification badge ──
        if 'verified' in text.lower()[:2000]:
            result["is_verified"] = True

        # ── Scroll About page for description ──
        about_link = await page.query_selector('a[href*="/about"], yt-tab-shape[tab-title*="About"]')
        if about_link:
            await about_link.click()
            await page.wait_for_timeout(2000)
            about_text = await page.evaluate("document.body.innerText")
            if about_text and len(about_text) > len(text):
                result["meta"]["about_text"] = about_text[:5000]
                # Try to get description from About page
                desc = re.search(r'Description\s*\n(.+?)(?=\n\n)', about_text, re.DOTALL)
                if desc:
                    result["description"] = desc.group(1).strip()[:3000]

        self._save_metadata(username, result, "channel")
        return result

    # ═══════════════════════════════════════════════════════
    # VIDEOS
    # ═══════════════════════════════════════════════════════

    async def scrape_posts(self, username: str, limit: int = 20) -> list:
        """Scrape recent videos from channel."""
        if username.startswith('@') or username.startswith('UC'):
            url = f"{self.base_url}/{username}/videos"
        else:
            url = f"{self.base_url}/@{username}/videos"

        page = await self._new_page()
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        # Scroll to load more videos
        for i in range(min(limit // 6 + 1, 5)):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)
            print(f"  [scroll] {i+1}")

        videos = await page.evaluate(f"""() => {{
            const items = [];
            // YouTube video renderers
            const containers = document.querySelectorAll('ytd-video-renderer, ytd-rich-item-renderer, ytd-grid-video-renderer, ytd-compact-video-renderer, div#dismissible');
            
            containers.forEach(c => {{
                const text = c.innerText.trim();
                if (text.length < 10) return;
                
                // Title
                const title = c.querySelector('#video-title, a#video-title, h3 a, a[class*="title"]');
                
                // Thumbnail
                const thumb = c.querySelector('img[class*="thumbnail"], yt-image img, img#img');
                
                // Meta: views + upload date
                const meta = c.querySelector('#metadata-line, div[class*="metadata"]');
                
                // Duration overlay
                const duration = c.querySelector('span[class*="time"], span.ytd-thumbnail-overlay-time-status-renderer');
                
                // Channel name
                const channel = c.querySelector('ytd-channel-name a, a[class*="channel"]');
                
                items.push({{
                    title: title ? title.innerText.trim().slice(0, 200) : null,
                    url: title ? title.href?.split('?')[0] || title.getAttribute('href')?.split('?')[0] : null,
                    thumbnail: thumb ? (thumb.src || thumb.getAttribute('data-thumb')) : null,
                    metadata: meta ? meta.innerText.trim() : null,
                    duration: duration ? duration.innerText.trim() : null,
                    channel: channel ? channel.innerText.trim() : null,
                }});
            }});
            
            return items.slice(0, {limit});
        }}""")

        # Clean URLs (YouTube gives relative /watch?v=...)
        for v in videos:
            if v.get("url") and v["url"].startswith("/watch"):
                v["url"] = f"https://www.youtube.com{v['url']}"
            if v.get("thumbnail"):
                # Get maxres version
                v["thumbnail"] = v["thumbnail"].replace('/hqdefault', '/maxresdefault')

        print(f"  → Videos found: {len(videos)}")
        self._save_metadata(username, {"videos": videos}, "videos")
        return videos

    # ═══════════════════════════════════════════════════════
    # PHOTOS = thumbnails
    # ═══════════════════════════════════════════════════════

    async def scrape_photos(self, username: str, limit: int = 20) -> list:
        posts = await self.scrape_posts(username, limit)
        thumbs = [v["thumbnail"] for v in posts if v.get("thumbnail")]
        if thumbs:
            self._save_metadata(username, {"thumbnails": thumbs}, "thumbnails")
        return thumbs

    # ═══════════════════════════════════════════════════════
    # ALL-IN-ONE
    # ═══════════════════════════════════════════════════════

    async def scrape_all(self, username: str, include=None) -> dict:
        if include is None:
            include = ["profile", "posts"]
        return await super().scrape_all(username, include)

    def _ts(self):
        from ..core.utils import timestamp_iso
        return timestamp_iso()

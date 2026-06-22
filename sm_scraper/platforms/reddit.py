"""
Reddit scraper — dùng old.reddit.com (HTML thuần, 0 bot detection).
  • Profile (username, avatar, cake day, post/comment karma, bio)
  • Posts (title, text, subreddit, upvotes, comments, timestamp, url)
  • Comments (text, subreddit, upvotes, timestamp)

Usage:
    sm-scraper reddit profile <username>
    sm-scraper reddit posts <username> [--limit 20]
    sm-scraper reddit comments <username> [--limit 30]
    sm-scraper reddit all <username>
"""

import asyncio
import random
import re
from ..core.base import BaseScraper
from ..core.stealth import human_scroll


class RedditScraper(BaseScraper):

    @property
    def platform(self) -> str:
        return "reddit"

    @property
    def base_url(self) -> str:
        return "https://old.reddit.com"

    # ── Parse helpers ──

    def _parse_posts(self, html: str, limit: int) -> list:
        posts = []
        blocks = re.split(r'<div\s+id="thing_', html)
        for block in blocks[1:]:
            p = {}
            m = re.search(r'<a\s+class="[^"]*may-blank[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            if m:
                href = m.group(1)
                p['url'] = 'https://old.reddit.com' + href if href.startswith('/') else href
                p['title'] = m.group(2).strip()
            m = re.search(r'<a[^>]*href="/(r/[^"/]+)"', block)
            if m: p['subreddit'] = m.group(1)
            m = re.search(r'<div\s+class="score[^"]*"[^>]*>\s*([^<]+)\s*</div>', block)
            if m: p['upvotes'] = m.group(1).strip()
            m = re.search(r'<a[^>]*class="[^"]*comments[^"]*"[^>]*>\s*(\d+)\s*(?:comment|&nbsp;)</a>', block, re.I)
            if m: p['comments'] = m.group(1)
            m = re.search(r'<time[^>]*datetime="([^"]+)"', block)
            if m: p['timestamp'] = m.group(1)
            m = re.search(r'<a\s+class="[^"]*thumbnail[^"]*"[^>]*>\s*<img\s+src="([^"]+)"', block)
            if m and 'self' not in m.group(1) and 'default' not in m.group(1):
                p['thumbnail'] = m.group(1)
            if p.get('title'):
                posts.append(p)
            if len(posts) >= limit:
                break
        return posts

    def _parse_comments(self, html: str, limit: int) -> list:
        comments = []
        blocks = re.split(r'<div\s+class="[^"]*entry[^"]*"[^>]*>', html)
        for block in blocks[1:]:
            c = {}
            m = re.search(r'<a[^>]*class="[^"]*author[^"]*"[^>]*>([^<]+)</a>', block)
            if m: c['author'] = m.group(1).strip()
            m = re.search(r'<span\s+class="[^"]*score[^"]*"[^>]*>\s*([^<]+)\s*</span>', block)
            if m: c['upvotes'] = m.group(1).strip()
            m = re.search(r'<time[^>]*datetime="([^"]+)"', block)
            if m: c['timestamp'] = m.group(1)
            m = re.search(r'<div\s+class="[^"]*md[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>', block, re.DOTALL)
            if m:
                body = re.sub(r'<[^>]+>', '', m.group(1)).strip()
                c['text'] = body[:2000]
            m = re.search(r'<a[^>]*href="/(r/[^"/]+)"', block)
            if m: c['subreddit'] = m.group(1)
            if c.get('text'):
                comments.append(c)
            if len(comments) >= limit:
                break
        return comments

    # ═══════════════════════════════════════════════════════
    # PROFILE
    # ═══════════════════════════════════════════════════════

    async def scrape_profile(self, username: str) -> dict:
        """Extract profile via old.reddit — JS-free, 0 detection."""
        page = await self._new_page()
        url = f"{self.base_url}/user/{username}"

        # Human delay before loading
        await asyncio.sleep(random.uniform(2.0, 5.0))
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        result = {
            "url": page.url,
            "username": username,
            "scraped_at": self._ts(),
            "display_name": None, "avatar_url": None,
            "cake_day": None, "post_karma": None, "comment_karma": None,
            "total_karma": None, "bio": None, "is_mod": False,
            "active_subreddits": [],
        }

        text = await page.evaluate('document.body.innerText')
        html = await page.content()

        # Display name
        m = re.search(r'<span\s+class="[^"]*user[^"]*"[^>]*>\s*([^<]+)', html)
        if m: result['display_name'] = m.group(1).strip()

        # Karma from sidebar
        m = re.search(r'([\d,.]+)\s*post\s*karma', text, re.I)
        if m: result['post_karma'] = m.group(1)
        m = re.search(r'([\d,.]+)\s*comment\s*karma', text, re.I)
        if m: result['comment_karma'] = m.group(1)
        m = re.search(r'^([\d,.]+)\s+karma', text, re.M)
        if m: result['total_karma'] = m.group(1)

        # Cake day
        m = re.search(r'(redditor for|member since).+', text, re.I)
        if m: result['cake_day'] = m.group(0)

        # Bio / description
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        for l in lines:
            if len(l) > 20 and 'karma' not in l.lower() and 'redditor' not in l.lower():
                result['bio'] = l[:300]
                break

        # Mod status
        if '[m]' in text or 'moderator' in text.lower():
            result['is_mod'] = True

        # Subreddits
        subs = re.findall(r'/(r/\w+)', text)
        if subs:
            result['active_subreddits'] = list(set(subs))[:20]

        self._save_metadata(username, result, 'profile')
        return result

    # ═══════════════════════════════════════════════════════
    # POSTS
    # ═══════════════════════════════════════════════════════

    async def scrape_posts(self, username: str, limit: int = 15) -> list:
        """Scrape posts via old.reddit."""
        page = await self._new_page()
        await page.goto(f'{self.base_url}/user/{username}/submitted', wait_until='domcontentloaded')
        await page.wait_for_timeout(3000)
        await human_scroll(page, times=min(limit // 5 + 1, 3))

        posts = self._parse_posts(await page.content(), limit)
        print(f'  → Posts: {len(posts)}')
        if posts:
            self._save_metadata(username, {'posts': posts}, 'posts')
        return posts

    # ═══════════════════════════════════════════════════════
    # COMMENTS
    # ═══════════════════════════════════════════════════════

    async def scrape_comments(self, username: str, limit: int = 20) -> list:
        """Scrape comments via old.reddit."""
        page = await self._new_page()
        await page.goto(f'{self.base_url}/user/{username}/comments', wait_until='domcontentloaded')
        await page.wait_for_timeout(3000)
        await human_scroll(page, times=min(limit // 5 + 1, 3))

        comments = self._parse_comments(await page.content(), limit)
        print(f'  → Comments: {len(comments)}')
        if comments:
            self._save_metadata(username, {'comments': comments}, 'comments')
        return comments

    # ═══════════════════════════════════════════════════════
    # PHOTOS
    # ═══════════════════════════════════════════════════════

    async def scrape_photos(self, username: str, limit: int = 20) -> list:
        posts = await self.scrape_posts(username, limit)
        return [p.get('thumbnail') for p in posts if p.get('thumbnail')][:limit]

    # ═══════════════════════════════════════════════════════
    # ALL-IN-ONE
    # ═══════════════════════════════════════════════════════

    async def scrape_all(self, username: str, include=None) -> dict:
        if include is None:
            include = ['profile', 'posts', 'comments']
        return await super().scrape_all(username, include)

    def _ts(self):
        from ..core.utils import timestamp_iso
        return timestamp_iso()

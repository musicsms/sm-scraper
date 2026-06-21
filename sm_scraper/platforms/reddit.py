"""
Reddit scraper — extracts all available information:
  • Profile (username, avatar, cake day, karma, bio)
  • Posts (title, text, images, subreddit, upvotes, comments, awards)
  • Comments (text, subreddit, upvotes, timestamps)
  • Active subreddits

Usage:
    python -m sm_scraper reddit profile <username>
    python -m sm_scraper reddit posts <username> [--limit 20]
    python -m sm_scraper reddit all <username>
"""

import re
from ..core.base import BaseScraper


class RedditScraper(BaseScraper):

    @property
    def platform(self) -> str:
        return "reddit"

    @property
    def base_url(self) -> str:
        return "https://www.reddit.com"

    # ═══════════════════════════════════════════════════════
    # PROFILE
    # ═══════════════════════════════════════════════════════

    async def scrape_profile(self, username: str) -> dict:
        """Extract all visible Reddit profile info — no login needed."""
        page = await self._new_page()
        url = f"{self.base_url}/user/{username}"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        result = {
            "url": url,
            "username": username,
            "scraped_at": self._ts(),
            "display_name": None,
            "avatar_url": None,
            "banner_url": None,
            "cake_day": None,
            "post_karma": None,
            "comment_karma": None,
            "total_karma": None,
            "bio": None,
            "is_nsfw": False,
            "is_mod": False,
            "active_subreddits": [],
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

        # ── Body text ──
        text = await page.evaluate("document.body.innerText")
        result["meta"]["raw_text_snippet"] = text[:8000]
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # ── Parse Reddit profile ──
        for i, line in enumerate(lines):
            # Username line: u/username
            if line.startswith('u/') and username.lower() in line.lower():
                result["display_name"] = line

            # Karma: "X post karma" "Y comment karma"
            karma_match = re.search(r'([\d,.]+)\s*post\s*karma', line, re.IGNORECASE)
            if karma_match:
                result["post_karma"] = karma_match.group(1)
            karma_match = re.search(r'([\d,.]+)\s*comment\s*karma', line, re.IGNORECASE)
            if karma_match:
                result["comment_karma"] = karma_match.group(1)

            # Total karma
            karma_match = re.search(r'^([\d,.]+)\s*karma$', line, re.IGNORECASE)
            if karma_match:
                result["total_karma"] = karma_match.group(1)
            
            if 'karma' in line.lower() and not result["total_karma"]:
                nums = re.findall(r'([\d,.]+)', line)
                if nums:
                    result["total_karma"] = nums[0]

            # Cake day
            if 'cake day' in line.lower():
                result["cake_day"] = line

            # Bio/description — often after the header
            if 'About' in line and i + 1 < len(lines):
                candidate = lines[i + 1]
                if not candidate.startswith('u/') and 'karma' not in candidate.lower() and len(candidate) > 5:
                    result["bio"] = candidate

            # NSFW
            if 'nsfw' in line.lower():
                result["is_nsfw"] = True

            # Moderator
            if 'moderator' in line.lower():
                result["is_mod"] = True

        # ── Also try JSON via old.reddit (more structured) ──
        old_data = await page.evaluate("""() => {
            // Try to get structured data from the page
            const scripts = document.querySelectorAll('script[type="text/javascript"], script[id*="data"]');
            for (const s of scripts) {
                try {
                    const text = s.text || s.innerText;
                    if (text.includes('user') && text.includes('karma')) {
                        return text.slice(0, 5000);
                    }
                } catch(e) {}
            }
            return null;
        }""")
        if old_data:
            result["meta"]["json_data_snippet"] = old_data[:3000]

        # ── Avatar fallback ──
        if not result["avatar_url"]:
            avatar = await page.evaluate("""() => {
                const img = document.querySelector('img[alt*="avatar"], img[alt*="profile"], img[class*="avatar"]');
                return img ? img.src : null;
            }""")
            result["avatar_url"] = avatar

        self._save_metadata(username, result, "profile")
        return result

    # ═══════════════════════════════════════════════════════
    # POSTS / SUBMISSIONS
    # ═══════════════════════════════════════════════════════

    async def scrape_posts(self, username: str, limit: int = 15) -> list:
        """Scrape recent submissions."""
        page = await self._new_page()
        url = f"{self.base_url}/user/{username}/submitted"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        # Scroll
        for i in range(min(limit // 5 + 1, 4)):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)
            print(f"  [scroll] {i+1}")

        posts = await page.evaluate(f"""() => {{
            const items = [];
            // Reddit posts (shreddit-app or classic)
            const containers = document.querySelectorAll('shreddit-post, div[data-testid="post-container"], div.Post, div[class*="post"]');
            
            containers.forEach(c => {{
                const text = c.innerText.trim();
                if (text.length < 10) return;
                
                // Title
                const title = c.querySelector('h1, h2, h3, a[data-testid="post-title"], a[class*="title"]');
                
                // Subreddit
                const sub = c.querySelector('a[href*="/r/"]');
                
                // Content
                const body = c.querySelector('[data-testid="post-content"], div[class*="text-body"], div.md');
                
                // Images
                const imgs = Array.from(c.querySelectorAll('img'))
                    .map(i => i.src)
                    .filter(s => s && !s.includes('redditstatic') && !s.includes('thumbs.redditmedia'));
                
                // Video
                const video = c.querySelector('video');
                
                // Stats
                const votes = c.querySelector('[data-testid="upvote-count"], div[class*="vote"], span[class*="score"]');
                const commentCount = c.querySelector('[data-testid="comment-count"], a[class*="comments"], span[class*="comments"]');
                
                // Timestamp
                const time = c.querySelector('time');
                
                items.push({{
                    title: title ? title.innerText.trim().slice(0, 300) : null,
                    subreddit: sub ? sub.innerText.trim() : null,
                    subreddit_url: sub ? sub.href.split('?')[0] : null,
                    text: body ? body.innerText.trim().slice(0, 2000) : text.slice(0, 500),
                    images: imgs.slice(0, 5),
                    has_video: !!video,
                    votes: votes ? votes.innerText.trim() : null,
                    comments: commentCount ? commentCount.innerText.trim() : null,
                    timestamp: time ? (time.getAttribute('datetime') || time.innerText) : null,
                }});
            }});
            
            return items.slice(0, {limit});
        }}""")

        print(f"  → Posts found: {len(posts)}")
        self._save_metadata(username, {"posts": posts}, "posts")
        return posts

    # ═══════════════════════════════════════════════════════
    # COMMENTS
    # ═══════════════════════════════════════════════════════

    async def scrape_comments(self, username: str, limit: int = 20) -> list:
        """Scrape recent comments."""
        page = await self._new_page()
        url = f"{self.base_url}/user/{username}/comments"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        # Scroll
        for i in range(min(limit // 5 + 1, 4)):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

        comments = await page.evaluate(f"""() => {{
            const items = [];
            const containers = document.querySelectorAll('shreddit-comment, div[data-testid="comment"], div[class*="comment"], div.Entry');
            
            containers.forEach(c => {{
                const text = c.innerText.trim();
                if (text.length < 5) return;
                
                const sub = c.querySelector('a[href*="/r/"]');
                const votes = c.querySelector('[data-testid="upvote-count"], span[class*="score"]');
                const time = c.querySelector('time');
                const parent = c.querySelector('a[href*="/comments/"]');
                
                items.push({{
                    text: text.slice(0, 2000),
                    subreddit: sub ? sub.innerText.trim() : null,
                    votes: votes ? votes.innerText.trim() : null,
                    timestamp: time ? (time.getAttribute('datetime') || time.innerText) : null,
                    parent_post: parent ? parent.innerText.trim().slice(0, 200) : null,
                }});
            }});
            
            return items.slice(0, {limit});
        }}""")

        print(f"  → Comments found: {len(comments)}")
        self._save_metadata(username, {"comments": comments}, "comments")
        return comments

    # ═══════════════════════════════════════════════════════
    # PHOTOS
    # ═══════════════════════════════════════════════════════

    async def scrape_photos(self, username: str, limit: int = 20) -> list:
        posts = await self.scrape_posts(username, limit)
        photos = []
        for p in posts:
            photos.extend(p.get("images", []))
        if photos:
            self._save_metadata(username, {"photos": photos}, "photos")
        return photos[:limit]

    # ═══════════════════════════════════════════════════════
    # ALL-IN-ONE
    # ═══════════════════════════════════════════════════════

    async def scrape_all(self, username: str, include=None) -> dict:
        if include is None:
            include = ["profile", "posts", "comments"]
        return await super().scrape_all(username, include)

    def _ts(self):
        from ..core.utils import timestamp_iso
        return timestamp_iso()

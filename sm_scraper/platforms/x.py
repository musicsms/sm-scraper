"""
X (Twitter) scraper — extracts all available information:
  • Profile (name, username, bio, avatar, banner, follower/following counts, joined date, location, website)
  • Timeline (tweets, retweets, replies)
  • Media (images, videos)

Usage:
    python -m sm_scraper x profile <username>
    python -m sm_scraper x posts <username> [--limit 20]
    python -m sm_scraper x all <username>
"""

import re
from ..core.base import BaseScraper


class XScraper(BaseScraper):

    @property
    def platform(self) -> str:
        return "x"

    @property
    def base_url(self) -> str:
        return "https://x.com"

    # ═══════════════════════════════════════════════════════
    # PROFILE
    # ═══════════════════════════════════════════════════════

    async def scrape_profile(self, username: str) -> dict:
        """Extract all visible X/Twitter profile info."""
        page = await self._new_page()
        url = f"{self.base_url}/{username}"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        result = {
            "url": page.url,
            "username": username,
            "scraped_at": self._ts(),
            "display_name": None,
            "bio": None,
            "avatar_url": None,
            "banner_url": None,
            "location": None,
            "website": None,
            "joined_date": None,
            "followers_count": None,
            "following_count": None,
            "posts_count": None,
            "is_verified": False,
            "is_private": False,
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
        result["meta"]["description"] = meta.get("description", meta.get("og:description"))

        # ── Body text ──
        text = await page.evaluate("document.body.innerText")
        result["meta"]["raw_text_snippet"] = text[:8000]
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # ── Parse X profile layout: name @handle bio location website joined stats ──
        for i, line in enumerate(lines):
            # Display name (before @username)
            if line.startswith('@') and i > 0 and not lines[i - 1].startswith('@'):
                result["display_name"] = lines[i - 1]
            
            # Bio: after the handle line
            if line.startswith('@') and i + 1 < len(lines):
                candidate = lines[i + 1]
                if not candidate.startswith('@') and 'following' not in candidate.lower() and 'follower' not in candidate.lower() and not candidate.startswith('http'):
                    result["bio"] = candidate

            # Location: often has 📍 or contains a city
            if '📍' in line or ('location' in line.lower() and len(line) < 50):
                loc = line.replace('📍', '').strip()
                if loc != line:  # had the emoji
                    result["location"] = loc
            
            # Website / link in bio
            if line.startswith('http') and result.get("bio") and 't.co' not in line:
                result["website"] = line.split('?')[0]

            # Joined date
            if 'Joined' in line or 'joined' in line.lower():
                result["joined_date"] = line.replace('Joined', '').replace('joined', '').strip()

            # Stats
            if 'following' in line.lower() and not result["following_count"]:
                nums = re.findall(r'([\d,.]+[KMBkmb]?)', line)
                if nums:
                    result["following_count"] = nums[0]
            if 'follower' in line.lower() and not result["followers_count"]:
                nums = re.findall(r'([\d,.]+[KMBkmb]?)', line)
                if nums:
                    result["followers_count"] = nums[0]
            if 'posts' in line.lower() or 'tweet' in line.lower():
                nums = re.findall(r'([\d,.]+[KMBkmb]?)', line)
                if nums:
                    result["posts_count"] = nums[0]

        # ── Avatar fallback via OG ──
        og_image = meta.get("og:image", "")
        if og_image and og_image != result["avatar_url"]:
            if not result["avatar_url"]:
                result["avatar_url"] = og_image

        # ── Banner ──
        banner = await page.evaluate("""() => {
            const divs = document.querySelectorAll('div[style*="background"]');
            for (const d of divs) {
                const match = d.getAttribute('style')?.match(/url\\(['"](.+?)['"]\\)/);
                if (match && match[1].includes('twimg')) return match[1];
            }
            return null;
        }""")
        result["banner_url"] = banner

        # ── Verified? ──
        if meta.get("description", "").startswith("@"):
            result["display_name"] = result["display_name"] or meta.get("og:title", "").replace(" (@" + username + ")", "")

        self._save_metadata(username, result, "profile")
        return result

    # ═══════════════════════════════════════════════════════
    # TWEETS
    # ═══════════════════════════════════════════════════════

    async def scrape_posts(self, username: str, limit: int = 20) -> list:
        """Scrape recent tweets/retweets."""
        page = await self._new_page()
        url = f"{self.base_url}/{username}"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        # Scroll
        for i in range(min(limit // 5 + 1, 5)):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2500)
            print(f"  [scroll] {i+1}")

        tweets = await page.evaluate(f"""() => {{
            const items = [];
            const articles = document.querySelectorAll('article[data-testid="tweet"], div[data-testid="cellInnerDiv"]');
            
            articles.forEach(article => {{
                const text = article.innerText.trim();
                if (text.length < 5) return;
                
                // Tweet text
                const tweetText = article.querySelector('[data-testid="tweetText"]');
                const content = tweetText ? tweetText.innerText.trim() : text.slice(0, 500);
                
                // Author
                const author = article.querySelector('[data-testid="User-Name"]');
                
                // Images
                const imgs = Array.from(article.querySelectorAll('img[src*="twimg.com/media/"], img[src*="pbs.twimg.com"]'))
                    .map(i => i.src.replace('&name=small', '&name=large').replace('&name=thumb', '&name=large'));
                
                // Video
                const video = article.querySelector('video');
                
                // Timestamp
                const time = article.querySelector('time');
                
                // Stats directly visible
                const reply = article.querySelector('[data-testid="reply"]');
                const retweet = article.querySelector('[data-testid="retweet"]');
                const like = article.querySelector('[data-testid="like"]');
                
                items.push({{
                    text: content.slice(0, 2000),
                    author_text: author ? author.innerText.trim() : null,
                    images: [...new Set(imgs)].slice(0, 4),
                    video: video ? true : false,
                    timestamp: time ? (time.getAttribute('datetime') || time.innerText) : null,
                    reply_count: null,
                    retweet_count: null,
                    like_count: null,
                }});
            }});
            
            return items.slice(0, {limit});
        }}""")

        print(f"  → Tweets found: {len(tweets)}")
        self._save_metadata(username, {"tweets": tweets}, "tweets")
        return tweets

    # ═══════════════════════════════════════════════════════
    # PHOTOS = media from tweets
    # ═══════════════════════════════════════════════════════

    async def scrape_photos(self, username: str, limit: int = 30) -> list:
        tweets = await self.scrape_posts(username, limit)
        photos = []
        for t in tweets:
            photos.extend(t.get("images", []))
        if photos:
            self._save_metadata(username, {"photos": photos}, "photos")
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

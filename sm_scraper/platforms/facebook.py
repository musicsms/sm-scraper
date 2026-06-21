"""
Facebook scraper — extracts ALL available information:
  • Profile (name, bio, avatar, cover, location, work, education, contact, stats)
  • About page (detailed personal info)
  • Posts (text, images, videos, reactions, comments, shares, timestamps)
  • Photos (albums, all image URLs)
  • Friends list (visible)
  • Groups member list
  • Pages liked

Usage:
    python -m sm_scraper facebook profile <username>
    python -m sm_scraper facebook posts <username> [--limit 20]
    python -m sm_scraper facebook photos <username>
    python -m sm_scraper facebook all <username>
"""

import re
from urllib.parse import urljoin

from ..core.base import BaseScraper
from ..core.utils import save_media_urls


class FacebookScraper(BaseScraper):

    @property
    def platform(self) -> str:
        return "facebook"

    @property
    def base_url(self) -> str:
        return "https://www.facebook.com"

    # ═══════════════════════════════════════════════════════
    # PROFILE — complete extraction
    # ═══════════════════════════════════════════════════════

    async def scrape_profile(self, username: str) -> dict:
        """Extract ALL visible profile information."""
        page = await self._new_page()
        url = f"{self.base_url}/{username}"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        result = {
            "url": url,
            "username": username,
            "scraped_at": self._ts(),
            "name": None,
            "bio": None,
            "avatar_url": None,
            "cover_url": None,
            "location": None,
            "workplace": None,
            "education": None,
            "relationship": None,
            "followers": None,
            "following": None,
            "website": None,
            "contact_info": None,
            "meta": {},
        }

        # ── Page title & meta ──
        result["meta"]["title"] = await page.title()
        result["meta"]["url"] = page.url

        # ── Extract structured data from meta tags ──
        meta_info = await page.evaluate("""() => {
            const meta = {};
            document.querySelectorAll('meta[property]').forEach(m => {
                meta[m.getAttribute('property')] = m.getAttribute('content');
            });
            document.querySelectorAll('meta[name]').forEach(m => {
                meta[m.getAttribute('name')] = m.getAttribute('content');
            });
            return meta;
        }""")
        result["meta"]["og"] = meta_info

        # ── Avatar image ──
        avatar = await page.evaluate("""() => {
            const img = document.querySelector('img[data-imgperflogname="profilePhotoXlarge"]')
                     || document.querySelector('img[alt*="profile"]')
                     || document.querySelector('image[xlink\\:href]')
                     || document.querySelector('img[referrerpolicy="no-referrer"]');
            return img ? img.src : null;
        }""")
        if avatar:
            result["avatar_url"] = avatar
            result["meta"]["avatar_alt"] = avatar

        # ── Cover image ──
        cover = await page.evaluate("""() => {
            const img = document.querySelector('[data-pagelet="ProfileCover"] img')
                     || document.querySelector('img[alt*="cover"]');
            return img ? img.src : null;
        }""")
        result["cover_url"] = cover

        # ── Full name ──
        name = await page.evaluate("""() => {
            const h1 = document.querySelector('h1');
            return h1 ? h1.innerText.trim() : null;
        }""")
        result["name"] = name

        # ── Bio / Intro ──
        bio = await page.evaluate("""() => {
            const spans = document.querySelectorAll('div[data-pagelet="ProfileBio"] span, span[dir="auto"]');
            for (const s of spans) {
                const t = s.innerText.trim();
                if (t.length > 20 && t.length < 500) return t;
            }
            return null;
        }""")
        result["bio"] = bio

        # ── Profile stats (followers, friends, etc.) ──
        stats = await page.evaluate("""() => {
            const links = document.querySelectorAll('a[href*="friends"], a[href*="followers"], a[href*="following"]');
            const res = {};
            links.forEach(a => res[a.innerText.trim()] = a.href);
            return res;
        }""")
        result["meta"]["nav_stats"] = stats

        # ── Extract avatar URL via OG tags ──
        og_image = meta_info.get("og:image", "")
        if og_image and not result["avatar_url"]:
            result["avatar_url"] = og_image

        # ── Full body text for manual extraction reference ──
        result["meta"]["body_snippet"] = (await page.evaluate("document.body.innerText"))[:8000]

        # ── Now scroll a bit for lazy content ──
        await page.evaluate("window.scrollTo(0, 300)")
        await page.wait_for_timeout(1500)

        return result

    # ═══════════════════════════════════════════════════════
    # POSTS — latest posts with all metadata
    # ═══════════════════════════════════════════════════════

    async def scrape_posts(self, username: str, limit: int = 10) -> list:
        """Scrape user's latest posts with text, images, reactions."""
        page = await self._new_page()
        url = f"{self.base_url}/{username}"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Scroll to load posts
        for i in range(min(limit, 10)):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

        posts = await page.evaluate(f"""() => {{
            const posts = [];
            const containers = document.querySelectorAll('[data-pagelet*="Feed"], [role="article"], div[data-ad-preview*="article"]');

            containers.forEach((c, idx) => {{
                // Reject tiny containers
                const text = c.innerText.trim();
                if (text.length < 20) return;

                // Author
                const author = c.querySelector('h4, strong, a[role="link"]');
                const authorName = author ? author.innerText.trim() : null;

                // Timestamp
                const time = c.querySelector('time, a[href*="/posts/"], a[href*="story.php"]');
                const timestamp = time ? (time.getAttribute('datetime') || time.getAttribute('title') || time.innerText.trim()) : null;

                // Post body
                const body = c.querySelector('[data-ad-preview="message"], div[dir="auto"]');
                const bodyText = body ? body.innerText.trim() : text.slice(0, 500);

                // Images
                const imgs = Array.from(c.querySelectorAll('img')).map(img => img.src).filter(s => s && s.length > 50);

                // Video
                const video = c.querySelector('video');
                const videoUrl = video ? video.getAttribute('src') : null;

                // Reaction buttons
                const reactions = c.innerText.match(/(\\d+[KMB]?)\\s*(Like|Love|Wow|Sad|Angry|Haha)/gi);

                // Comments count
                const commentsMatch = c.innerText.match(/(\\d+[KMB]?)\\s*comment/i);

                // Shares count
                const sharesMatch = c.innerText.match(/(\\d+[KMB]?)\\s*share/i);

                posts.push({{
                    idx,
                    author: authorName,
                    timestamp,
                    text: bodyText.slice(0, 2000),
                    image_count: imgs.length,
                    images: imgs.slice(0, 10),
                    video_url: videoUrl,
                    reactions_text: reactions || [],
                    comments: commentsMatch ? commentsMatch[0] : null,
                    shares: sharesMatch ? sharesMatch[0] : null,
                }});
            }});

            return posts.slice(0, {limit});
        }}""")

        return posts

    # ═══════════════════════════════════════════════════════
    # PHOTOS — all visible photos
    # ═══════════════════════════════════════════════════════

    async def scrape_photos(self, username: str, limit: int = 50) -> list:
        """Extract all visible photo URLs from the profile."""
        page = await self._new_page()
        url = f"{self.base_url}/{username}/photos"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Scroll for lazy load
        for i in range(5):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

        photos = await page.evaluate(r"""() => {
            const urls = new Set();
            const imgs = document.querySelectorAll('img');
            imgs.forEach(img => {
                const src = img.getAttribute('src') || img.getAttribute('data-src');
                if (src && 
                    (src.includes('.fbcdn.net') || src.includes('facebook.com')) &&
                    (src.includes('_n.jpg') || src.includes('_o.jpg') || src.includes('_a.jpg'))
                ) {
                    // Try to get the largest version
                    const bigSrc = src.replace(/\/[pq]_/, '/n_').replace(/_[sqptn]_/, '_n_');
                    urls.add(bigSrc);
                }
            });
            return Array.from(urls);
        }""")

        # Save media URLs to file
        if photos:
            self._save_metadata(username, {"photo_urls": photos}, "photos")

        return photos[:limit]

    # ═══════════════════════════════════════════════════════
    # ABOUT — detailed personal info
    # ═══════════════════════════════════════════════════════

    async def scrape_about(self, username: str) -> dict:
        """Scrape the About page for detailed info."""
        page = await self._new_page()
        url = f"{self.base_url}/{username}/about"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        about = await page.evaluate("""() => {
            const res = {overview: {}, work: [], education: [], places: [], contact: {}};
            
            // Grab all section headings and their content
            const sections = document.querySelectorAll('[data-pagelet="ProfileTabs"], div[role="tabpanel"]');
            
            // Fallback: grab all visible text
            res['raw_text'] = document.body.innerText.slice(0, 10000);
            
            return res;
        }""")
        about["url"] = page.url
        about["username"] = username

        self._save_metadata(username, about, "about")
        return about

    # ═══════════════════════════════════════════════════════
    # GROUPS — joined groups
    # ═══════════════════════════════════════════════════════

    async def scrape_groups(self, username: str) -> list:
        """Scrape visible groups."""
        page = await self._new_page()
        url = f"{self.base_url}/{username}/groups"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        groups = await page.evaluate("""() => {
            const items = [];
            const links = document.querySelectorAll('a[href*="/groups/"]');
            const seen = new Set();
            links.forEach(a => {
                const name = a.innerText.trim();
                const href = a.href;
                if (name && href && !seen.has(href) && !href.includes('?__')) {
                    seen.add(href);
                    items.push({name, url: href.split('?')[0]});
                }
            });
            return items.slice(0, 50);
        }""")

        print(f"  → Groups found: {len(groups)}")
        self._save_metadata(username, {"groups": groups}, "groups")
        return groups

    # ═══════════════════════════════════════════════════════
    # FRIENDS (visible list)
    # ═══════════════════════════════════════════════════════

    async def scrape_friends(self, username: str) -> list:
        """Scrape visible friends list."""
        page = await self._new_page()
        url = f"{self.base_url}/{username}/friends"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Scroll for lazy load
        for i in range(3):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

        friends = await page.evaluate("""() => {
            const items = [];
            const links = document.querySelectorAll('a[href*="/user/"], a[href*="?id="]');
            const seen = new Set();
            links.forEach(a => {
                const name = a.getAttribute('aria-label') || a.innerText.trim();
                const href = a.href;
                if (name && href && !seen.has(href) && name.length > 0 && name.length < 100) {
                    seen.add(href);
                    items.push({name, url: href.split('?')[0]});
                }
            });
            // Also grab friend names from the page
            const text = document.body.innerText;
            return items.slice(0, 200);
        }""")

        print(f"  → Friends found: {len(friends)}")
        self._save_metadata(username, {"friends": friends}, "friends")
        return friends

    # ═══════════════════════════════════════════════════════
    # ALL-IN-ONE
    # ═══════════════════════════════════════════════════════

    async def scrape_all(self, username: str, include=None) -> dict:
        if include is None:
            include = ["profile", "posts", "photos", "friends", "about", "groups"]
        return await super().scrape_all(username, include)

    # ── Helpers ──
    def _ts(self):
        from ..core.utils import timestamp_iso
        return timestamp_iso()

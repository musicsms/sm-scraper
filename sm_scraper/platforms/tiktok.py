"""
TikTok scraper — extracts all available information:
  • Profile (username, full name, bio, avatar, followers/following/likes counts)
  • Videos (thumbnails, URLs, descriptions, stats)
  • Liked videos (if visible)

Usage:
    python -m sm_scraper tiktok profile <username>
    python -m sm_scraper tiktok videos <username> [--limit 20]
    python -m sm_scraper tiktok all <username>
"""

import re
from ..core.base import BaseScraper


class TikTokScraper(BaseScraper):

    @property
    def platform(self) -> str:
        return "tiktok"

    @property
    def base_url(self) -> str:
        return "https://www.tiktok.com"

    # ═══════════════════════════════════════════════════════
    # PROFILE
    # ═══════════════════════════════════════════════════════

    async def scrape_profile(self, username: str) -> dict:
        """Extract all visible TikTok profile info."""
        page = await self._new_page()
        url = f"{self.base_url}/@{username}"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)  # TikTok is heavy

        result = {
            "url": url,
            "username": username,
            "scraped_at": self._ts(),
            "full_name": None,
            "bio": None,
            "avatar_url": None,
            "followers_count": None,
            "following_count": None,
            "likes_count": None,
            "videos_count": None,
            "is_verified": False,
            "is_private": False,
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

        # ── Body text ──
        text = await page.evaluate("document.body.innerText")
        result["meta"]["raw_text_snippet"] = text[:5000]
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # ── Parse TikTok profile structure ──
        # TikTok profile layout: @username | name | bio | stats
        for i, line in enumerate(lines):
            # Find username line
            if line.startswith('@') and len(line) < 50:
                result["meta"]["handle_line"] = line
                # Next line should be full name or bio
                if i + 1 < len(lines) and not lines[i + 1].replace(' ', '').isdigit():
                    result["full_name"] = lines[i + 1]
                # Next meaningful line after that is bio
                for j in range(i + 2, min(i + 5, len(lines))):
                    if not lines[j].replace(' ', '').isdigit() and lines[j] != lines[i + 1]:
                        if len(lines[j]) > 3 and 'following' not in lines[j].lower():
                            result["bio"] = lines[j]
                            break

            # Stats: TikTok shows "Following Followers Likes"
            if 'following' in line.lower():
                nums = re.findall(r'([\d,.]+[KMBkmb]?)', line)
                if len(nums) >= 1:
                    result["following_count"] = nums[0]
            if 'follower' in line.lower():
                nums = re.findall(r'([\d,.]+[KMBkmb]?)', line)
                if len(nums) >= 1:
                    result["followers_count"] = nums[0]
            if 'like' in line.lower() and not 'liked' in line.lower():
                nums = re.findall(r'([\d,.]+[KMBkmb]?)', line)
                if len(nums) >= 1:
                    result["likes_count"] = nums[0]

        # ── Extract from JSON-LD / sigi state ──
        user_data = await page.evaluate("""() => {
            try {
                // SIGI_STATE contains user data
                if (window.__SIGI_STATE__) {
                    const state = window.__SIGI_STATE__;
                    const uid = Object.keys(state?.UserModule?.users || {})[0];
                    if (uid) return state.UserModule.users[uid];
                    return state;
                }
                return {note: 'no __SIGI_STATE__'};
            } catch(e) { return {}; }
        }""")
        result["meta"]["sigi_state"] = user_data

        if isinstance(user_data, dict) and "avatarLarger" in user_data:
            result["avatar_url"] = result["avatar_url"] or user_data.get("avatarLarger")
            result["full_name"] = result["full_name"] or user_data.get("nickname")
            result["bio"] = result["bio"] or user_data.get("signature")
            result["is_verified"] = user_data.get("verified", False)
            result["is_private"] = user_data.get("privateAccount", False)

        # ── Private check ──
        if "private" in text.lower()[:200]:
            result["is_private"] = True
            print("  ! Account is PRIVATE")

        self._save_metadata(username, result, "profile")
        return result

    # ═══════════════════════════════════════════════════════
    # VIDEOS
    # ═══════════════════════════════════════════════════════

    async def scrape_posts(self, username: str, limit: int = 15) -> list:
        """Scrape videos from user profile."""
        page = await self._new_page()
        url = f"{self.base_url}/@{username}"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        # Scroll to load more videos
        for i in range(min(limit // 5 + 1, 4)):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2500)
            print(f"  [scroll] {i+1}")

        videos = await page.evaluate(f"""() => {{
            const items = [];
            const links = document.querySelectorAll('a[href*="/video/"]');
            const seen = new Set();

            links.forEach(a => {{
                const href = a.href.split('?')[0];
                if (seen.has(href)) return;
                seen.add(href);

                const img = a.querySelector('img');
                const desc = a.querySelector('[data-e2e="video-desc"], div[class*="caption"]');
                
                items.push({{
                    url: href,
                    thumbnail: img ? img.src : null,
                    description: desc ? desc.innerText.trim().slice(0, 300) : null,
                }});
            }});

            return items.slice(0, {limit});
        }}""")

        print(f"  → Videos found: {len(videos)}")
        self._save_metadata(username, {"videos": videos}, "videos")
        return videos

    # ═══════════════════════════════════════════════════════
    # PHOTOS = thumbnails from videos
    # ═══════════════════════════════════════════════════════

    async def scrape_photos(self, username: str, limit: int = 20) -> list:
        videos = await self.scrape_posts(username, limit)
        thumbnails = [v["thumbnail"] for v in videos if v.get("thumbnail")]
        if thumbnails:
            self._save_metadata(username, {"thumbnails": thumbnails}, "thumbnails")
        return thumbnails

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

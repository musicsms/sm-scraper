"""
LinkedIn scraper — extracts all available information:
  • Profile (name, headline, location, about, experience, education, skills, certifications)
  • Posts (text, images, reactions, comments, shares)
  
NOTE: LinkedIn BLOCKS most profile data without login.
Run login first: python -m sm_scraper auth --platform linkedin --login

Usage:
    python -m sm_scraper linkedin profile <username>
    python -m sm_scraper linkedin posts <username> [--limit 10]
    python -m sm_scraper linkedin all <username>
"""

import re
from ..core.base import BaseScraper


class LinkedInScraper(BaseScraper):

    @property
    def platform(self) -> str:
        return "linkedin"

    @property
    def base_url(self) -> str:
        return "https://www.linkedin.com"

    # ═══════════════════════════════════════════════════════
    # PROFILE — FULL extraction
    # ═══════════════════════════════════════════════════════

    async def scrape_profile(self, username: str) -> dict:
        """Extract ALL visible LinkedIn profile info (requires login)."""
        page = await self._new_page()
        url = f"{self.base_url}/in/{username}/"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        result = {
            "url": page.url,
            "username": username,
            "scraped_at": self._ts(),
            "name": None,
            "headline": None,
            "location": None,
            "about": None,
            "avatar_url": None,
            "background_url": None,
            "experience": [],
            "education": [],
            "skills": [],
            "certifications": [],
            "languages": [],
            "connections_count": None,
            "is_open_to_work": False,
        }

        # ── Check if logged in ──
        title = await page.title()
        if "login" in title.lower() or "sign in" in title.lower():
            print("  ! NOT LOGGED IN. Run: sm-scraper auth --platform linkedin --login")
            print("  ! Limited public profile data only")
            result["meta"] = {"note": "not logged in - limited data"}
            text = await page.evaluate("document.body.innerText")
            result["meta"]["public_text"] = text[:3000]
            self._save_metadata(username, result, "profile")
            return result

        result["meta"] = {"page_title": title}

        # ── Meta / OG tags ──
        meta = await page.evaluate("""() => {
            const m = {};
            document.querySelectorAll('meta[property], meta[name]').forEach(el => {
                m[el.getAttribute('property') || el.getAttribute('name')] = el.getAttribute('content');
            });
            return m;
        }""")
        result["meta"]["og"] = meta

        # ── Avatar ──
        avatar = await page.evaluate("""() => {
            const img = document.querySelector('img[data-ghost-class*="profile"]')
                     || document.querySelector('img[alt*="photo"]')
                     || document.querySelector('.profile-photo-edit__preview img');
            return img ? img.src : null;
        }""")
        result["avatar_url"] = avatar or meta.get("og:image")

        # ── Name ──
        name = await page.evaluate("""() => {
            const h1 = document.querySelector('h1');
            return h1 ? h1.innerText.trim() : null;
        }""")
        result["name"] = name

        # ── Full page text for extraction ──
        text = await page.evaluate("document.body.innerText")
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        result["meta"]["raw_text_snippet"] = text[:8000]

        # ── Headline (usually right after name) ──
        if name:
            for i, line in enumerate(lines):
                if name == line and i + 1 < len(lines):
                    result["headline"] = lines[i + 1]
                    break

        # ── Location ──
        for line in lines:
            if line and not line.startswith('http') and ',' in line and len(line) < 100:
                # Catch "San Francisco, CA" or "Vietnam" but not sentences
                words = line.replace(',', '').split()
                if len(words) < 8 and any(c.isupper() for c in line[:3]):
                    if 'about' not in line.lower() and 'experience' not in line.lower():
                        result["location"] = line
                        break

        # ── About section ──
        about_match = re.search(r'(?:About|Summary)[\s\n]+(.+?)(?=\n\n[A-Z]|\n(?:Experience|Education|Skills|Certifications))', text, re.DOTALL)
        if about_match:
            result["about"] = about_match.group(1).strip()[:2000]

        # ── Connections count ──
        conn_match = re.search(r'([\d,.]+)\s*connections?', text, re.IGNORECASE)
        if conn_match:
            result["connections_count"] = conn_match.group(1)

        # ── Open to work? ──
        if "open to work" in text.lower() or "#opentowork" in text.lower():
            result["is_open_to_work"] = True

        # ── Experience sections ──
        exp_block = re.search(r'(?:Experience|Employment)(.+?)(?=\n\n(?:Education|Skills|Certifications|Languages|Recommendations))', text, re.DOTALL)
        if exp_block:
            exp_lines = [l.strip() for l in exp_block.group(1).split('\n') if l.strip() and len(l.strip()) > 3]
            result["experience"] = exp_lines[:30]

        # ── Education ──
        edu_block = re.search(r'Education(.+?)(?=\n\n(?:Skills|Certifications|Languages|Recommendations|Volunteer))', text, re.DOTALL)
        if edu_block:
            edu_lines = [l.strip() for l in edu_block.group(1).split('\n') if l.strip() and len(l.strip()) > 3]
            result["education"] = edu_lines[:20]

        # ── Skills ──
        skills_block = re.search(r'(?:Skills|Top Skills)(.+?)(?=\n\n(?:Certifications|Languages|Recommendations|Volunteer))', text, re.DOTALL)
        if skills_block:
            skills_lines = [l.strip() for l in skills_block.group(1).split('\n') if l.strip() and len(l.strip()) > 2 and 'endors' not in l.lower()]
            result["skills"] = skills_lines[:30]

        # ── Languages ──
        lang_block = re.search(r'Languages(.+?)(?=\n\n(?:Certifications|Recommendations|Volunteer|Education|Skills))', text, re.DOTALL)
        if lang_block:
            lang_lines = [l.strip() for l in lang_block.group(1).split('\n') if l.strip() and len(l.strip()) > 2]
            result["languages"] = lang_lines[:10]

        # ── Scroll for lazy content ──
        await page.evaluate("window.scrollTo(0, 500)")
        await page.wait_for_timeout(1500)

        self._save_metadata(username, result, "profile")
        return result

    # ═══════════════════════════════════════════════════════
    # POSTS
    # ═══════════════════════════════════════════════════════

    async def scrape_posts(self, username: str, limit: int = 10) -> list:
        """Scrape recent posts from activity section."""
        page = await self._new_page()
        url = f"{self.base_url}/in/{username}/recent-activity/"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        # Scroll
        for i in range(min(limit // 3 + 1, 4)):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

        posts = await page.evaluate(f"""() => {{
            const items = [];
            // LinkedIn posts use specific selectors
            const containers = document.querySelectorAll('.feed-shared-update-v2, .occludable-update, article');
            
            containers.forEach(c => {{
                const text = c.innerText.trim();
                if (text.length < 30) return;
                
                const imgs = Array.from(c.querySelectorAll('img'))
                    .map(i => i.src)
                    .filter(s => s && s.startsWith('http') && !s.includes('sharing'));
                
                const time = c.querySelector('time');
                
                const stats = c.innerText.match(/(\\d+[KMBkmb]?)\\s*(reactions?|comments?|reposts?|likes?)/gi) || [];
                
                items.push({{
                    text: text.slice(0, 2000),
                    images: imgs.slice(0, 5),
                    timestamp: time ? (time.getAttribute('datetime') || time.innerText) : null,
                    stats: stats,
                }});
            }});
            
            return items.slice(0, {limit});
        }}""")

        print(f"  → Posts found: {len(posts)}")
        self._save_metadata(username, {"posts": posts}, "posts")
        return posts

    # ═══════════════════════════════════════════════════════
    # PHOTOS (from posts)
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
            include = ["profile", "posts", "photos"]
        return await super().scrape_all(username, include)

    def _ts(self):
        from ..core.utils import timestamp_iso
        return timestamp_iso()

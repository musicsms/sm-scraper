"""
sm-scraper — Social Media Scraper CLI
Multi-platform, powered by CloakBrowser.

Usage:
    sm-scraper auth --platform facebook --login
    sm-scraper auth --platform instagram --validate
    
    sm-scraper facebook profile <username>
    sm-scraper facebook posts <username> [--limit 20]
    sm-scraper facebook photos <username>
    sm-scraper facebook friends <username>
    sm-scraper facebook groups <username>
    sm-scraper facebook about <username>
    sm-scraper facebook all <username>
    
    sm-scraper instagram profile <username>
    sm-scraper instagram posts <username> [--limit 12]
    sm-scraper instagram stories <username>
    sm-scraper instagram all <username>
    
    sm-scraper threads profile <username>
    sm-scraper threads posts <username> [--limit 20]
    sm-scraper threads all <username>
    
    sm-scraper tiktok profile <username>
    sm-scraper tiktok videos <username> [--limit 20]
    sm-scraper tiktok all <username>
    
    sm-scraper linkedin profile <username>
    sm-scraper linkedin posts <username> [--limit 10]
    sm-scraper linkedin all <username>
    
    sm-scraper x profile <username>
    sm-scraper x posts <username> [--limit 20]
    sm-scraper x all <username>
    
    sm-scraper reddit profile <username>
    sm-scraper reddit posts <username> [--limit 20]
    sm-scraper reddit comments <username>
    sm-scraper reddit all <username>
    
    sm-scraper youtube channel <handle>
    sm-scraper youtube videos <handle> [--limit 20]
    sm-scraper youtube all <handle>
    
    sm-scraper telegram channel <channel>
    sm-scraper telegram messages <channel> [--limit 30]
    sm-scraper telegram all <channel>
"""

import asyncio
import sys
from pathlib import Path

# Ensure package root is in path
PACKAGE_ROOT = Path(__file__).parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from sm_scraper.core.auth import login, validate
from sm_scraper.platforms.facebook import FacebookScraper
from sm_scraper.platforms.instagram import InstagramScraper
from sm_scraper.platforms.threads import ThreadsScraper
from sm_scraper.platforms.tiktok import TikTokScraper
from sm_scraper.platforms.linkedin import LinkedInScraper
from sm_scraper.platforms.x import XScraper
from sm_scraper.platforms.reddit import RedditScraper
from sm_scraper.platforms.youtube import YouTubeScraper
from sm_scraper.platforms.telegram import TelegramScraper


PLATFORMS = {
    "facebook": FacebookScraper,
    "instagram": InstagramScraper,
    "threads": ThreadsScraper,
    "tiktok": TikTokScraper,
    "linkedin": LinkedInScraper,
    "x": XScraper,
    "reddit": RedditScraper,
    "youtube": YouTubeScraper,
    "telegram": TelegramScraper,
}


def print_help():
    print(__doc__)


async def run_scrape(platform_cls, action: str, username: str, limit: int = 10):
    """Run a scrape action with the given platform scraper."""
    async with platform_cls(headless=True, humanize=True) as scraper:
        actions = {
            "profile": scraper.scrape_profile,
            "posts": lambda u: scraper.scrape_posts(u, limit=limit),
            "photos": lambda u: scraper.scrape_photos(u, limit=limit),
            "friends": scraper.scrape_friends if hasattr(scraper, 'scrape_friends') else None,
            "groups": scraper.scrape_groups if hasattr(scraper, 'scrape_groups') else None,
            "about": scraper.scrape_about if hasattr(scraper, 'scrape_about') else None,
            "stories": scraper.scrape_stories if hasattr(scraper, 'scrape_stories') else None,
            "all": lambda u: scraper.scrape_all(u),
        }

        fn = actions.get(action)
        if not fn:
            print(f"  ✗ Action '{action}' not supported for {scraper.platform}")
            print(f"  ✓ Supported: {', '.join(k for k, v in actions.items() if v)}")
            return

        result = await fn(username)

        # Print summary
        if isinstance(result, list):
            print(f"\n  → {len(result)} items")
        elif isinstance(result, dict):
            print(f"\n  → Scraped {len(result)} data fields")

        return result


def main():
    if len(sys.argv) < 2:
        print_help()
        return

    cmd = sys.argv[1]

    # ── Auth commands ──
    if cmd == "auth":
        platform = None
        do_login = False
        do_validate = False

        for i, arg in enumerate(sys.argv[2:]):
            if arg == "--platform" and i + 1 < len(sys.argv[2:]):
                platform = sys.argv[2:][i + 1]
            elif arg == "--login":
                do_login = True
            elif arg == "--validate":
                do_validate = True

        if not platform:
            print("  ✗ Specify platform: --platform facebook|instagram|threads")
            return

        if do_login:
            login(platform)
        elif do_validate:
            validate(platform)
        else:
            print("  Specify --login or --validate")
        return

    # ── Scrape commands: <platform> <action> <username> --limit N ──
    if cmd in PLATFORMS:
        if len(sys.argv) < 4:
            print(f"Usage: sm-scraper {cmd} <action> <username> [--limit N]")
            print(f"Actions: profile, posts, photos, all")
            return

        action = sys.argv[2]
        username = sys.argv[3]
        limit = 10

        # Parse --limit
        for i, arg in enumerate(sys.argv[4:]):
            if arg == "--limit" and i + 1 < len(sys.argv[4:]):
                try:
                    limit = int(sys.argv[4:][i + 1])
                except:
                    pass

        scraper_cls = PLATFORMS[cmd]
        asyncio.run(run_scrape(scraper_cls, action, username, limit))
        return

    print_help()


if __name__ == "__main__":
    main()

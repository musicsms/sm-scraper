"""
Stealth utilities — anti-detection & human-like behavior for all scrapers.
"""

import asyncio
import random
import time


# ── Random delays ──

def delay(short: bool = True) -> float:
    """Human-like random delay in seconds."""
    if short:
        return random.uniform(0.8, 2.5)
    return random.uniform(2.0, 5.0)


def long_delay() -> float:
    """Longer delay (between scrape batches)."""
    return random.uniform(4.0, 8.0)


async def sleep(seconds: float = None):
    """Smart sleep — random if no arg given."""
    await asyncio.sleep(seconds or delay())


# ── Human-like scrolling ──

async def human_scroll(page, times: int = 3, max_px: int = None):
    """
    Scroll like a human — random amounts, random pauses, not always to bottom.
    """
    for i in range(times):
        if max_px:
            scroll_by = random.randint(200, min(800, max_px))
            await page.evaluate('window.scrollBy(0, %d)' % scroll_by)
        else:
            amount = random.randint(300, 900)
            js = 'window.scrollTo(0, Math.min(document.body.scrollHeight - window.innerHeight, window.scrollY + %d))' % amount
            await page.evaluate(js)

        await asyncio.sleep(random.uniform(0.5, 2.5))

        if random.random() < 0.2:
            await asyncio.sleep(random.uniform(2.0, 4.0))

    return times


# ── Rate limiter ──

class RateLimiter:
    """Rate limiter — max N actions per window seconds."""

    def __init__(self, max_actions: int = 10, window: int = 60):
        self.max_actions = max_actions
        self.window = window
        self.timestamps = []

    async def wait_if_needed(self):
        """Wait if we have exceeded rate limit."""
        now = time.time()
        self.timestamps = [t for t in self.timestamps if now - t < self.window]

        if len(self.timestamps) >= self.max_actions:
            wait_time = self.timestamps[0] + self.window - now + random.uniform(1, 3)
            print(f"  [rate] waiting {wait_time:.0f}s...")
            await asyncio.sleep(wait_time)

        self.timestamps.append(time.time())


# ── Blocked page detection ──

BLOCKED_KEYWORDS = [
    "please confirm you are a human",
    "please verify you are a human",
    "automated requests",
    "unusual traffic",
    "too many requests",
    "rate limit",
    "blocked",
    "access denied",
    "challenge",
    "sorry, you have been blocked",
    "you are temporarily blocked",
    "unusual activity",
    "confirm your identity",
    "security check",
    "unusual login",
    "suspicious activity",
]


async def check_blocked(page) -> tuple:
    """
    Check if current page shows a block/challenge.
    Returns (is_blocked, reason).
    """
    try:
        text = await page.evaluate('document.body.innerText')
        text_lower = text.lower()

        for keyword in BLOCKED_KEYWORDS:
            if keyword in text_lower:
                title = await page.title()
                return True, f'{keyword} (title: {title})'

        # Check for CAPTCHA
        captcha_js = '''() => {
            return document.querySelector('iframe[src*="recaptcha"], iframe[src*="captcha"], div[class*="captcha"]') !== null;
        }'''
        has_captcha = await page.evaluate(captcha_js)
        if has_captcha:
            return True, 'captcha detected'

        return False, ''
    except Exception as e:
        return True, f'page error: {e}'


# ── Backoff strategy ──

class Backoff:
    """Exponential backoff with jitter."""

    def __init__(self, base_delay: float = 30.0, max_delay: float = 600.0):
        self.base = base_delay
        self.max = max_delay
        self.attempt = 0

    async def wait(self):
        """Wait with exponential backoff + jitter."""
        delay = min(self.max, self.base * (2 ** self.attempt))
        jitter = random.uniform(0, delay * 0.3)
        total = delay + jitter
        print(f'  [backoff] waiting {total:.0f}s (attempt {self.attempt + 1})...')
        await asyncio.sleep(total)
        self.attempt += 1

    def reset(self):
        self.attempt = 0

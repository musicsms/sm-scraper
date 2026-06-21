# sm-scraper

Multi-platform Social Media Scraper — 9 platforms, VPS-friendly.

## 🚀 Quick Start

```bash
# Clone
git clone https://github.com/musicsms/sm-scraper.git
cd sm-scraper

# Setup
bash setup_vps.sh

# Web Dashboard
sm-dashboard     # → http://localhost:8501

# CLI
sm-scraper facebook profile zuck
sm-scraper tiktok videos therock --limit 20
sm-scraper youtube channel @mkbhd
```

## 🌐 Platforms

| Platform | Auth | Data |
|---|---|---|
| Facebook | Optional | profile, posts, photos, friends, groups, about |
| Instagram | Optional | profile, posts, stories |
| Threads | ✗ | profile, threads |
| TikTok | ✗ | profile, videos |
| LinkedIn | Required | profile (experience, education, skills), posts |
| X/Twitter | ✗ | profile, tweets, media |
| Reddit | ✗ | profile, posts, comments |
| YouTube | ✗ | channel, videos |
| Telegram | Optional | channel, messages (Telethon = full) |

## 🔐 Auth (VPS friendly)

3 cách đăng nhập trên VPS headless:

1. **Login từ xa** — Dashboard gõ tk/mk, auto fill form + screenshot
2. **Upload Cookies** — Export từ local browser → upload JSON
3. **Manual** — Có màn hình thật hoặc VNC

## 📦 Structure

```
sm-scraper/
├── sm_dashboard.py          # Web UI (Streamlit)
├── setup_vps.sh             # One-click VPS setup
├── start.sh                 # Dashboard launcher
└── sm_scraper/
    ├── core/
    │   ├── auth.py          # Cookie persistence
    │   ├── base.py          # BaseScraper abstract class
    │   ├── utils.py         # Helpers (save JSON, media)
    │   └── remote_login.py  # Interactive VPS login
    └── platforms/
        ├── facebook.py      # 361 lines
        ├── instagram.py     # 293 lines
        ├── threads.py       # 219 lines
        ├── tiktok.py        # 195 lines
        ├── linkedin.py      # 238 lines
        ├── x.py             # 227 lines
        ├── reddit.py        # 281 lines
        ├── youtube.py       # 232 lines
        └── telegram.py      # 302 lines
```

## 🔧 Requirements

- Python 3.10+
- CloakBrowser (`pipx install cloakbrowser`)
- Streamlit (`pipx install streamlit`) — for dashboard
- Playwright browsers (auto-installed by CloakBrowser)

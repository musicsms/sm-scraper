"""
sm-scraper Dashboard — Web UI for VPS & server use.
Runs fully headless. Login via cookie upload or Xvfb remote browser.

Usage:
    streamlit run sm_dashboard.py
    # Then open http://localhost:8501
"""

import asyncio
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

import streamlit as st

st.set_page_config(page_title="SM Scraper", page_icon="🌐", layout="wide", initial_sidebar_state="expanded")

# ── Styling ──
st.markdown("""
<style>
    .main > div { padding: 0 1rem; }
    .stApp { background-color: #0e1117; }
    h1, h2, h3 { color: #f0f2f6 !important; }
    .stButton button {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white; font-weight: 600; border: none; border-radius: 8px;
        padding: 0.5rem 1.5rem;
    }
    .stButton button:hover { background: linear-gradient(90deg, #764ba2 0%, #667eea 100%); }
    .result-card { background: #1a1d27; border-radius: 12px; padding: 1.2rem; margin: 0.5rem 0; border-left: 4px solid #667eea; }
    .stat-box { background: #1e2130; border-radius: 10px; padding: 1rem; text-align: center; border: 1px solid #2e3140; }
    .stat-value { font-size: 1.8rem; font-weight: 700; color: #667eea; }
    .stat-label { font-size: 0.8rem; color: #8b8fa3; }
    .auth-badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.7rem; font-weight: 600; }
    .badge-ok { background: #1a3a2a; color: #4ade80; }
    .badge-no { background: #3a1a1a; color: #f87171; }
    .badge-warn { background: #3a2a1a; color: #fbbf24; }
    .data-card { background: #161a25; border-radius: 8px; padding: 0.8rem; margin: 0.3rem 0; font-size: 0.85rem; }
    .vps-tip { background: #1a2332; border: 1px solid #2563eb; border-radius: 10px; padding: 1rem; margin: 0.5rem 0; }
    .step-box { background: #111827; border-radius: 8px; padding: 0.8rem 1rem; margin: 0.3rem 0; border-left: 3px solid #667eea; }
    footer { display: none; }
</style>
""", unsafe_allow_html=True)

if "scrape_results" not in st.session_state:
    st.session_state.scrape_results = None

PLATFORMS = {
    "facebook": {"icon": "📘", "color": "#1877F2", "actions": ["profile", "posts", "photos", "friends", "groups", "about", "all"]},
    "instagram": {"icon": "📸", "color": "#E4405F", "actions": ["profile", "posts", "stories", "all"]},
    "threads": {"icon": "🧵", "color": "#000000", "actions": ["profile", "posts", "all"]},
    "tiktok": {"icon": "🎵", "color": "#FF004F", "actions": ["profile", "videos", "all"]},
    "linkedin": {"icon": "💼", "color": "#0A66C2", "actions": ["profile", "posts", "all"]},
    "x": {"icon": "🐦", "color": "#000000", "actions": ["profile", "posts", "all"]},
    "reddit": {"icon": "🤖", "color": "#FF4500", "actions": ["profile", "posts", "comments", "all"]},
    "youtube": {"icon": "▶️", "color": "#FF0000", "actions": ["channel", "videos", "all"]},
    "telegram": {"icon": "✈️", "color": "#0088CC", "actions": ["channel", "messages", "all"]},
}

ACTIONS_DISPLAY = {
    "profile": "👤 Profile", "posts": "📝 Posts", "photos": "🖼️ Photos",
    "videos": "🎬 Videos", "channel": "📺 Channel", "messages": "💬 Messages",
    "friends": "👥 Friends", "groups": "📋 Groups", "about": "ℹ️ About",
    "stories": "📱 Stories", "comments": "💭 Comments", "all": "⚡ All Data",
}

# ── Sidebar ──
with st.sidebar:
    st.markdown("## 🌐 **SM Scraper**")
    st.caption("Multi-platform Social Media Scraper")
    st.divider()
    
    # VPS notice
    st.markdown(
        '<div class="vps-tip">'
        '🖥️ **VPS Mode**<br>'
        '<span style="font-size:0.8rem;color:#93c5fd">'
        'Login qua cookie upload từ local<br>'
        'hoặc Xvfb remote browser'
        '</span></div>',
        unsafe_allow_html=True,
    )
    st.divider()
    
    mode = st.radio("**Mode**", ["🔍 Scrape", "🔐 Auth", "📂 History"], label_visibility="collapsed")
    
    output_dir = Path.home() / "sm_scraped_data"
    if output_dir.exists():
        total_files = sum(1 for f in output_dir.rglob("*.json"))
        st.caption(f"📁 `{total_files}` data files saved")
    st.divider()
    st.caption("Powered by CloakBrowser 🛡️")

# ── Import helper ──
SCRAPER_CLASSES = {}
def get_scraper_class(platform):
    if platform not in SCRAPER_CLASSES:
        try:
            mod = __import__(f"sm_scraper.platforms.{platform}", fromlist=[""])
            class_name = {
                "facebook":"FacebookScraper","instagram":"InstagramScraper","threads":"ThreadsScraper",
                "tiktok":"TikTokScraper","linkedin":"LinkedInScraper","x":"XScraper",
                "reddit":"RedditScraper","youtube":"YouTubeScraper","telegram":"TelegramScraper",
            }[platform]
            SCRAPER_CLASSES[platform] = getattr(mod, class_name)
        except Exception as e:
            st.error(f"❌ Cannot load {platform}: {e}")
            return None
    return SCRAPER_CLASSES[platform]


# ═══════════════════════════════════════════════════════
# SCRAPE MODE
# ═══════════════════════════════════════════════════════

if mode == "🔍 Scrape":
    st.title("🔍 Social Media Scraper")
    st.caption("Select platform → enter username → scrape. VPS-friendly (headless).")

    cols = st.columns([1, 1, 2])
    with cols[0]:
        platform = st.selectbox("**Platform**", list(PLATFORMS.keys()), format_func=lambda p: f"{PLATFORMS[p]['icon']} {p.capitalize()}")
    with cols[1]:
        action = st.selectbox("**Action**", PLATFORMS[platform]["actions"], format_func=lambda a: ACTIONS_DISPLAY.get(a, a.capitalize()))
    with cols[2]:
        username = st.text_input("**Username / Handle / Channel**", placeholder="e.g. zuck, natgeo, @mkbhd...").strip()

    limit = st.slider("**Limit**", 5, 50, 10) if action in ("posts","photos","videos","messages","comments","all") else 10

    if st.button(f"🚀 Scrape {platform.capitalize()}", disabled=not username, use_container_width=True, type="primary"):
        if username:
            scraper_cls = get_scraper_class(platform)
            if scraper_cls:
                with st.spinner(f"⏳ Scraping {platform}/{username}..."):
                    async def do_scrape():
                        async with scraper_cls(headless=True, humanize=True) as scraper:
                            if action == "all": return await scraper.scrape_all(username)
                            elif action in ("videos","messages"): return await scraper.scrape_posts(username, limit)
                            elif action == "channel": return await scraper.scrape_profile(username)
                            elif action == "stories": return await scraper.scrape_stories(username)
                            elif action == "friends": return await scraper.scrape_friends(username)
                            elif action == "groups": return await scraper.scrape_groups(username)
                            elif action == "about": return await scraper.scrape_about(username)
                            elif action == "comments": return await scraper.scrape_comments(username)
                            elif action == "profile": return await scraper.scrape_profile(username)
                            elif action == "posts": return await scraper.scrape_posts(username, limit)
                            elif action == "photos": return await scraper.scrape_photos(username, limit)
                            else: return await scraper.scrape_profile(username)
                    try:
                        result = asyncio.run(do_scrape())
                        st.session_state.scrape_results = {"platform": platform, "username": username, "action": action, "data": result, "time": datetime.now().isoformat()}
                        st.success(f"✅ Done! Data saved to `~/sm_scraped_data/{platform}/{username}/`")
                    except Exception as e:
                        st.error(f"❌ Error: {e}")

    # ── Results ──
    if st.session_state.scrape_results and st.session_state.scrape_results.get("platform") == platform:
        r = st.session_state.scrape_results
        data = r["data"]
        uname = r["username"]
        st.divider()
        st.subheader(f"📊 Results — {platform.capitalize()}: {uname}")

        if isinstance(data, list):
            st.metric("Total Items", len(data))
            if data and isinstance(data[0], dict):
                st.dataframe(data, use_container_width=True)
                st.download_button("💾 Download JSON", json.dumps(data, indent=2, ensure_ascii=False),
                    file_name=f"{platform}_{uname}_{action}_{datetime.now().strftime('%Y%m%d')}.json", mime="application/json")
        elif isinstance(data, dict):
            stat_cols = st.columns(5)
            si = 0
            for k, v in list(data.items())[:10]:
                if isinstance(v, (str, int, float, bool, type(None))) and len(str(v)) < 60:
                    with stat_cols[si % 5]:
                        st.markdown(f'<div class="stat-box"><div class="stat-label">{k.replace("_"," ").title()}</div><div class="stat-value" style="font-size:1rem">{v if v is not None else "—"}</div></div>', unsafe_allow_html=True)
                    si += 1
            st.divider()
            for section in ["profile","posts","photos","tweets","videos","messages","threads"]:
                if section in data and data[section]:
                    if isinstance(data[section], list) and len(data[section]) > 0:
                        with st.expander(f"📂 {section.capitalize()} ({len(data[section])} items)", expanded=True):
                            for item in data[section][:10]:
                                if isinstance(item, dict):
                                    display_text = item.get("title") or item.get("text") or item.get("name") or json.dumps(item, ensure_ascii=False)[:200]
                                    st.markdown(f'<div class="data-card"><b>{str(display_text)[:150]}</b>'
                                        + (f'<br><small>URL: {str(item.get("url",item.get("thumbnail","")))[:100]}</small>' if item.get("url") or item.get("thumbnail") else '')
                                        + (f'<br><small>Stats: {item.get("stats", item.get("metadata", ""))}</small>' if item.get("stats") or item.get("metadata") else '')
                                        + '</div>', unsafe_allow_html=True)
            with st.expander("📄 Raw JSON"):
                st.json(data)
            st.download_button("💾 Download JSON", json.dumps(data, indent=2, ensure_ascii=False, default=str),
                file_name=f"{platform}_{uname}_{action}_{datetime.now().strftime('%Y%m%d')}.json", mime="application/json")


# ═══════════════════════════════════════════════════════
# AUTH MODE — VPS-FRIENDLY
# ═══════════════════════════════════════════════════════

elif mode == "🔐 Auth":
    st.title("🔐 Authentication")
    st.caption("VPS headless? Dùng cookie upload từ local hoặc Xvfb remote browser.")
    
    tab_auth, tab_cookie, tab_xvfb = st.tabs(["🔑 Login + Status", "📤 Upload Cookies (VPS)", "🖥️ Login từ xa"])

    # ── Tab 1: Login + Status ──
    with tab_auth:
        col_left, col_right = st.columns([1, 1])
        
        with col_left:
            auth_platform = st.selectbox("**Platform**", list(PLATFORMS.keys()),
                format_func=lambda p: f"{PLATFORMS[p]['icon']} {p.capitalize()}", key="auth_platform")
            
            # Chú ý VPS
            st.info("💡 **VPS tip:** Dùng tab **Upload Cookies** bên cạnh.\nLogin manual cần màn hình — chỉ dùng được khi có Xvfb.")
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("🔑 Login (manual)", use_container_width=True):
                    from sm_scraper.core.auth import login
                    with st.spinner(f"⏳ Opening {auth_platform} login..."):
                        try:
                            login(auth_platform)
                            st.success(f"✅ Login complete!")
                        except Exception as e:
                            st.error(f"❌ {e}")
            with col_b:
                if st.button("✅ Validate", use_container_width=True):
                    from sm_scraper.core.auth import validate
                    with st.spinner(f"⏳ Checking..."):
                        try:
                            ok = validate(auth_platform)
                            st.success(f"✅ Session valid!") if ok else st.warning("⚠️ Session expired")
                        except Exception as e:
                            st.error(f"❌ {e}")
        
        with col_right:
            st.markdown("### 📋 Session Status")
            for p in list(PLATFORMS.keys()):
                cf = Path.home() / ".sm_scraper_cookies" / f"{p}_cookies.json"
                if cf.exists():
                    sz = len(cf.read_text())
                    st.markdown(f'<div class="data-card"><span class="auth-badge badge-ok">✓</span> <b>{PLATFORMS[p]["icon"]} {p.capitalize()}</b> <span style="float:right;color:#8b8fa3;font-size:0.8rem">{sz//100} cookies</span></div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="data-card" style="opacity:0.5"><span class="auth-badge badge-no">✗</span> <b>{PLATFORMS[p]["icon"]} {p.capitalize()}</b> <span style="float:right;color:#8b8fa3;font-size:0.8rem">no session</span></div>', unsafe_allow_html=True)
            
            # Telethon
            st.divider()
            tc = Path.home() / ".sm_scraper_telegram.json"
            if tc.exists():
                st.markdown(f'<div class="data-card"><span class="auth-badge badge-ok">✓</span> <b>✈️ Telegram (Telethon)</b> <span style="float:right;color:#8b8fa3;font-size:0.8rem">configured</span></div>', unsafe_allow_html=True)
            else:
                with st.expander("⚙️ Configure Telethon"):
                    c1, c2 = st.columns(2)
                    with c1:
                        aid = st.text_input("API ID", placeholder="12345", type="password")
                    with c2:
                        ah = st.text_input("API Hash", placeholder="abc...", type="password")
                    ph = st.text_input("Phone", placeholder="84868609591")
                    if st.button("Save"):
                        cfg = {"api_id": int(aid) if aid else 0, "api_hash": ah, "phone": ph}
                        if cfg["api_id"] and cfg["api_hash"]:
                            tc.write_text(json.dumps(cfg, indent=2))
                            st.success("✅ Saved!")

    # ── Tab 2: Upload Cookies (VPS method) ──
    with tab_cookie:
        st.markdown("### 📤 Upload Cookies từ Local Machine")
        st.markdown(
            '<div class="vps-tip">'
            '🖥️ **VPS workflow:**<br>'
            '1️⃣ Mở browser trên **máy local** của bạn<br>'
            '2️⃣ Login vào platform (Facebook, Insta, etc.)<br>'
            '3️⃣ Dùng extension **Cookie-Editor** hoặc **EditThisCookie** export cookies<br>'
            '4️⃣ Upload file JSON cookies lên đây<br>'
            '5️⃣ Scraper tự động dùng cookies này'
            '</div>',
            unsafe_allow_html=True,
        )
        
        st.divider()
        st.markdown("#### Bước 1: Chọn platform")
        cookie_platform = st.selectbox("", list(PLATFORMS.keys()),
            format_func=lambda p: f"{PLATFORMS[p]['icon']} {p.capitalize()}", key="cookie_platform", label_visibility="collapsed")
        
        st.markdown("#### Bước 2: Upload file cookies")
        uploaded = st.file_uploader("Upload cookies.json (export từ browser)", type=["json"], key="cookie_upload")
        
        if uploaded:
            try:
                cookies = json.loads(uploaded.read())
                if isinstance(cookies, list) and len(cookies) > 0:
                    # Save to the correct cookie path
                    cookie_path = Path.home() / ".sm_scraper_cookies" / f"{cookie_platform}_cookies.json"
                    cookie_path.parent.mkdir(parents=True, exist_ok=True)
                    cookie_path.write_text(json.dumps(cookies, indent=2))
                    st.success(f"✅ Saved {len(cookies)} cookies to `{cookie_path}`")
                    st.caption(f"Sample: {json.dumps(cookies[0], indent=2)[:200]}...")
                else:
                    st.error("❌ Invalid cookie format. Must be an array of cookie objects.")
            except Exception as e:
                st.error(f"❌ Error: {e}")
        
        st.divider()
        st.markdown("#### 🔧 Cách export cookies từ browser:")
        
        steps = [
            ("Chrome/Edge", "Cài extension **Cookie-Editor** (từ Chrome Web Store)"),
            ("Facebook", "Login → mở extension → click **Export** → Save as JSON"),
            ("Instagram", "Login → export cookies tương tự"),
            ("LinkedIn", "Login → export cookies → upload lên đây"),
        ]
        for title, desc in steps:
            st.markdown(f'<div class="step-box"><b>{title}</b><br><span style="color:#93c5fd;font-size:0.85rem">{desc}</span></div>', unsafe_allow_html=True)
        
        st.divider()
        st.markdown("#### 📋 Cookie status sau upload:")
        for p in list(PLATFORMS.keys()):
            cf = Path.home() / ".sm_scraper_cookies" / f"{p}_cookies.json"
            if cf.exists():
                sz = len(cf.read_text())
                st.markdown(f'<div class="data-card"><span class="auth-badge badge-ok">✓</span> <b>{PLATFORMS[p]["icon"]} {p.capitalize()}</b> <span style="float:right;color:#8b8fa3;font-size:0.8rem">{sz//100} cookies</span></div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="data-card" style="opacity:0.5"><span class="auth-badge badge-no">✗</span> <b>{PLATFORMS[p]["icon"]} {p.capitalize()}</b> <span style="float:right;color:#8b8fa3;font-size:0.8rem">no session</span></div>', unsafe_allow_html=True)

    # ── Tab 3: Remote Browser Login (VPS-friendly) ──
    with tab_xvfb:
        st.markdown("### 🖥️ Login từ xa (Remote Browser)")
        st.markdown(
            '<div class="vps-tip">'
            'Không cần Xvfb, không cần export cookies. '
            'CloakBrowser chạy headless trên VPS — bạn xem ảnh và gõ thông tin qua dashboard.<br><br>'
            '<b>Cách dùng:</b><br>'
            '1️⃣ Chọn platform → bấm "Mở Login Page"<br>'
            '2️⃣ Xem ảnh màn hình login trong dashboard<br>'
            '3️⃣ Gõ email và password vào ô bên dưới<br>'
            '4️⃣ Dashboard tự động fill form + submit<br>'
            '5️⃣ Nếu có 2FA → nhập code → xong!<br>'
            '6️⃣ Cookies tự động lưu ✅'
            '</div>',
            unsafe_allow_html=True,
        )
        
        # Session state for remote login
        if "rl_instance" not in st.session_state:
            st.session_state.rl_instance = None
        if "rl_step" not in st.session_state:
            st.session_state.rl_step = "idle"
        if "rl_screenshot" not in st.session_state:
            st.session_state.rl_screenshot = None
        
        browser_running = st.session_state.rl_step not in ("idle", "closed", "logged_in")
        
        rl_platform = st.selectbox(
            "**Platform**",
            ["facebook","instagram","linkedin","tiktok","x","reddit","threads"],
            format_func=lambda p: f"{PLATFORMS[p]['icon']} {p.capitalize()}",
            key="remote_platform",
            disabled=browser_running,
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 1. Mở Login Page", disabled=browser_running, use_container_width=True):
                with st.spinner("⏳ Starting browser..."):
                    from sm_scraper.core.remote_login import run_open_login
                    result = run_open_login(rl_platform)
                    st.session_state.rl_instance = result["_instance"]
                    st.session_state.rl_step = "waiting_credentials"
                    st.session_state.rl_screenshot = result.get("screenshot")
                    st.rerun()
        with col2:
            if st.button("❌ Đóng Browser", disabled=not browser_running, use_container_width=True):
                from sm_scraper.core.remote_login import run_close
                if st.session_state.rl_instance:
                    run_close(st.session_state.rl_instance)
                st.session_state.rl_instance = None
                st.session_state.rl_step = "idle"
                st.session_state.rl_screenshot = None
                st.rerun()
        
        # Show screenshot
        if st.session_state.rl_screenshot and Path(st.session_state.rl_screenshot).exists():
            st.divider()
            st.markdown(f"**📸 Màn hình login — {rl_platform.capitalize()}**")
            st.image(st.session_state.rl_screenshot, use_container_width=True)
            
            step_labels = {
                "waiting_credentials": "⏳ Đang chờ nhập thông tin...",
                "submitting": "🔄 Đang submit...",
                "2fa": "🔐 Nhập mã xác thực 2FA",
                "logged_in": "✅ Đã login thành công!",
            }
            st.caption(step_labels.get(st.session_state.rl_step, st.session_state.rl_step))
        
        st.divider()
        
        # Form based on step
        if st.session_state.rl_step == "waiting_credentials" and st.session_state.rl_instance:
            st.markdown("**✏️ Nhập thông tin đăng nhập**")
            ca, cb = st.columns(2)
            with ca:
                email_val = st.text_input("📧 Email / Username", placeholder="your@email.com", key="rl_email")
            with cb:
                pass_val = st.text_input("🔑 Password", type="password", placeholder="********", key="rl_pass")
            
            if st.button("▶️ 2. Điền & Login", use_container_width=True):
                if email_val:
                    from sm_scraper.core.remote_login import run_fill_form
                    r = run_fill_form(st.session_state.rl_instance, "email", email_val)
                    if r.get("screenshot"): st.session_state.rl_screenshot = r["screenshot"]
                if pass_val:
                    from sm_scraper.core.remote_login import run_fill_form
                    r = run_fill_form(st.session_state.rl_instance, "password", pass_val)
                    if r.get("screenshot"): st.session_state.rl_screenshot = r["screenshot"]
                
                from sm_scraper.core.remote_login import run_submit, run_check_2fa, run_save_cookies
                result = run_submit(st.session_state.rl_instance)
                if result.get("screenshot"): st.session_state.rl_screenshot = result["screenshot"]
                
                if result.get("success"):
                    save_r = run_save_cookies(st.session_state.rl_instance)
                    st.session_state.rl_step = "logged_in"
                    if save_r.get("success"):
                        st.success(f"✅ Login + lưu cookies ({save_r['count']} cookies) thành công!")
                    else:
                        st.success("✅ Login thành công!")
                    st.balloons()
                elif run_check_2fa(st.session_state.rl_instance):
                    st.session_state.rl_step = "2fa"
                    st.warning("🔐 Cần mã xác thực 2FA! Kiểm tra điện thoại.")
                else:
                    st.warning("⚠️ Login chưa thành công. Xem ảnh và thử lại.")
                st.rerun()
        
        elif st.session_state.rl_step == "2fa" and st.session_state.rl_instance:
            st.markdown("**🔐 Nhập mã xác thực 2FA**")
            code = st.text_input("Mã xác thực", placeholder="123456", key="rl_2fa_code")
            if st.button("✅ Xác nhận", use_container_width=True):
                if code:
                    from sm_scraper.core.remote_login import run_enter_2fa, run_save_cookies
                    r = run_enter_2fa(st.session_state.rl_instance, code)
                    if r.get("screenshot"): st.session_state.rl_screenshot = r["screenshot"]
                    save_r = run_save_cookies(st.session_state.rl_instance)
                    st.session_state.rl_step = "logged_in"
                    st.success(f"✅ 2FA OK! Cookies saved ({save_r.get('count', '?')})")
                    st.balloons()
                    st.rerun()
        
        elif st.session_state.rl_step == "logged_in":
            st.success("🎉 **Đã đăng nhập thành công!**")
            st.markdown(f'<div class="vps-tip">✅ Cookies cho <b>{rl_platform.capitalize()}</b> đã sẵn sàng<br>👉 Qua tab **🔍 Scrape** để cào dữ liệu!</div>', unsafe_allow_html=True)
            if st.button("🔄 Làm lại", use_container_width=True):
                from sm_scraper.core.remote_login import run_close
                if st.session_state.rl_instance: run_close(st.session_state.rl_instance)
                st.session_state.rl_instance = None
                st.session_state.rl_step = "idle"
                st.session_state.rl_screenshot = None
                st.rerun()
        
        elif st.session_state.rl_step == "idle":
            st.info("💡 Bấm **'Mở Login Page'** để bắt đầu.")


# ═══════════════════════════════════════════════════════
# HISTORY MODE
# ═══════════════════════════════════════════════════════

elif mode == "📂 History":
    st.title("📂 Scraped Data History")
    st.caption("Browse all saved data files")
    
    od = Path.home() / "sm_scraped_data"
    if not od.exists():
        st.info("No data scraped yet. Go to **Scrape** tab!")
    else:
        pf = sorted([d.name for d in od.iterdir() if d.is_dir()])
        if not pf:
            st.info("No data directories found.")
        else:
            sp = st.selectbox("**Filter by Platform**", ["All"] + pf)
            files = []
            for p in (pf if sp == "All" else [sp]):
                for ud in (od / p).iterdir():
                    if ud.is_dir():
                        for f in sorted(ud.glob("*.json"), reverse=True):
                            files.append({"platform": p, "user": ud.name, "file": f.name, "path": f,
                                          "size": f.stat().st_size, "modified": datetime.fromtimestamp(f.stat().st_mtime)})
            if files:
                st.caption(f"📁 {len(files)} files")
                sr = st.selectbox("**Sort by**", ["Newest first", "Oldest first", "Largest first"])
                if "Oldest" in sr: files.reverse()
                if "Largest" in sr: files.sort(key=lambda x: x["size"], reverse=True)
                
                for f_info in files[:30]:
                    c1, c2, c3 = st.columns([1, 3, 2])
                    with c1:
                        st.markdown(f"**{PLATFORMS.get(f_info['platform'],{}).get('icon','📄')} {f_info['platform'].capitalize()}**")
                    with c2:
                        st.markdown(f"`{f_info['user']}/{f_info['file']}`")
                    with c3:
                        st.markdown(f"<span style='color:#8b8fa3;font-size:0.8rem'>{f_info['modified'].strftime('%Y-%m-%d %H:%M')} | {f_info['size']//1000}KB</span>", unsafe_allow_html=True)
                    if st.button(f"👁️ Preview", key=f"pv_{f_info['path']}"):
                        try:
                            content = json.loads(f_info["path"].read_text())
                            ca, cb = st.columns(2)
                            with ca: st.metric("Size", f"{len(json.dumps(content))//1000}KB")
                            with cb:
                                if isinstance(content, dict): st.metric("Fields", len(content))
                                elif isinstance(content, list): st.metric("Items", len(content))
                            st.json(content)
                            st.download_button("💾 Download", f_info["path"].read_bytes(), file_name=f_info["file"])
                        except: st.error("Cannot read")
                    st.divider()
            else:
                st.info(f"No files for '{sp}'")

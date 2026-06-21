#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  SM Scraper — VPS Setup Script
#  Cài đặt toàn bộ dependencies cho VPS headless
# ═══════════════════════════════════════════════════════════

set -e

echo "╔══════════════════════════════════════════════════╗"
echo "║   🚀 SM Scraper — VPS Setup                     ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── 1. System deps ──
echo "[1/5] 📦 Installing system dependencies..."
sudo apt update -qq
sudo apt install -y -qq \
    xvfb \
    x11-utils \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libxss1 \
    libgtk-3-0 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    fonts-liberation \
    libnss3 \
    libnspr4 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libu2f-udev
echo "  ✓ System deps installed"

# ── 2. Python deps ──
echo "[2/5] 🐍 Installing Python packages..."
pip3 install --user --quiet streamlit 2>/dev/null || pipx install streamlit --quiet
echo "  ✓ Python packages installed"

# ── 3. CloakBrowser ──
echo "[3/5] 🛡️ Checking CloakBrowser..."
if ! python3 -c "import cloakbrowser" 2>/dev/null; then
    pip3 install --user --quiet cloakbrowser 2>/dev/null || pipx install cloakbrowser --quiet
fi
echo "  ✓ CloakBrowser ready"

# ── 4. SM Scraper files ──
echo "[4/5] 📁 Setting up sm-scraper..."
if [ ! -d ~/sm-scraper ]; then
    echo "  ! sm-scraper directory not found. Run this script from ~/sm-scraper/"
    echo "  ! Or: git clone <repo> ~/sm-scraper"
else
    # Create symlink
    mkdir -p ~/.local/bin
    ln -sf ~/sm-scraper/start.sh ~/.local/bin/sm-dashboard 2>/dev/null
    chmod +x ~/sm-scraper/start.sh
    
    # Add PYTHONPATH to bashrc
    if ! grep -q 'sm-scraper' ~/.bashrc 2>/dev/null; then
        echo 'export PYTHONPATH="$HOME/sm-scraper:$PYTHONPATH"' >> ~/.bashrc
        echo 'export CLOAK_PY="$HOME/.local/share/pipx/venvs/cloakbrowser/bin/python"' >> ~/.bashrc
    fi
    echo "  ✓ sm-scraper configured"
fi

# ── 5. Cookie directory ──
echo "[5/5] 🔐 Creating cookie storage..."
mkdir -p ~/.sm_scraper_cookies
mkdir -p ~/sm_scraped_data
echo "  ✓ Ready"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   ✅ Setup Complete!                            ║"
echo "║                                                 ║"
echo "║   📋 Cách dùng trên VPS:                       ║"
echo "║                                                 ║"
echo "║   1. Start dashboard:                           ║"
echo "║      sm-dashboard                               ║"
echo "║      → http://localhost:8501                    ║"
echo "║                                                 ║"
echo "║   2. Auth = upload cookies:                     ║"
echo "║      - Login trên máy local                     ║"
echo "║      - Export cookies = JSON                    ║"
echo "║      - Upload qua Dashboard tab "Upload"        ║"
echo "║                                                 ║"
echo "║   3. Hoặc login = Xvfb:                         ║"
echo "║      Dashboard tab "Remote Browser"             ║"
echo "║      → Chạy browser ảo trên VPS                ║"
echo "║                                                 ║"
echo "║   4. Scrape:                                    ║"
echo "║      sm-scraper facebook profile zuck           ║"
echo "╚══════════════════════════════════════════════════╝"

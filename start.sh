#!/bin/bash
# sm-scraper Dashboard Launcher
# One command to start: just run this script

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "╔══════════════════════════════════════════════╗"
echo "║        🌐 SM Scraper Dashboard              ║"
echo "║   Multi-Platform Social Media Scraper       ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# Check streamlit
if ! command -v streamlit &> /dev/null; then
    echo "📦 Installing streamlit..."
    pipx install streamlit --quiet
fi

echo "🚀 Starting dashboard..."
echo "   ➜ Open: http://localhost:8501"
echo "   ➜ Press Ctrl+C to stop"
echo ""

# Add PYTHONPATH for sm_scraper imports
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

streamlit run sm_dashboard.py --server.headless true

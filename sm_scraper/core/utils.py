"""Utility helpers: data saving, formatting, logging."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

# Default output directory
OUTPUT_DIR = Path.home() / "sm_scraped_data"


def ensure_output_dir(platform: str, username: str) -> Path:
    """Create and return platform/user output directory."""
    path = OUTPUT_DIR / platform / username
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json(data: Any, filepath: Path) -> Path:
    """Save data as pretty-printed JSON with UTF-8."""
    filepath.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str)
    )
    print(f"  ✓ Saved: {filepath}")
    return filepath


def save_media_urls(urls: list[str], filepath: Path) -> Path:
    """Save list of media URLs to a text file."""
    filepath.write_text("\n".join(urls))
    print(f"  ✓ Media URLs: {filepath}")
    return filepath


def make_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def timestamp_iso() -> str:
    return datetime.now().isoformat()


def summary_stats(data: dict, label: str) -> None:
    """Print a quick summary of scraped data."""
    print(f"\n{'═'*50}")
    print(f"📊 {label}")
    print(f"{'═'*50}")
    for k, v in data.items():
        if isinstance(v, list):
            print(f"  {k}: {len(v)} items")
        elif isinstance(v, dict):
            print(f"  {k}: {len(v)} fields")
        else:
            print(f"  {k}: {v}")
    print(f"{'═'*50}\n")

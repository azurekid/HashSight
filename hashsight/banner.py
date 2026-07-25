"""Prints the HashSight ASCII art banner. Purely cosmetic - never called on library import."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .version import __version__

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[38;5;51m"
_AQUA = "\033[38;5;45m"
_NEON_PINK = "\033[38;5;213m"
_HOT_PINK = "\033[38;5;205m"
_VIOLET = "\033[38;5;99m"
_SUNSET_ORANGE = "\033[38;5;208m"
_SUNSET_GOLD = "\033[38;5;220m"

_FALLBACK_BANNER = r"""
  _   _           _      ____  _       _     _
 | | | | __ _ ___| |__  / ___|(_) __ _| |__ | |_
 | |_|/ _` / __| '_ \ \___ \| |/ _` | '_ \| __|
 |  _  | (_| \__ \ | | | ___) | | (_| | | | | |_
 |_| |_|\__,_|___/_| |_||____/|_|\__, |_| |_|\__|
                                 |___/
                                        v 2.0.1
    practical hash signature intelligence
"""


def _load_banner() -> str:
    """Load banner text from packaged asset, with a resilient inline fallback."""
    try:
        return (Path(__file__).resolve().parent / "assets" / "logo.txt").read_text(encoding="utf-8")
    except Exception:
        return _FALLBACK_BANNER


def show_banner() -> None:
    """Print the banner unless the HASHSIGHT_NO_BANNER environment variable is set."""
    if os.environ.get("HASHSIGHT_NO_BANNER"):
        return

    banner = _load_banner().rstrip("\n")
    version_text = f"v{__version__}"

    # Colorful in interactive terminals, plain everywhere else.
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR") is not None:
        print(banner)
        print(version_text)
        return

    lines = banner.splitlines()
    if not lines:
        return

    # Outrun / Miami Vice inspired row palette.
    palette = [_NEON_PINK, _HOT_PINK, _VIOLET, _AQUA, _CYAN]
    styled_lines: list[str] = []

    for idx, line in enumerate(lines):
        if not line.strip():
            styled_lines.append(line)
            continue

        if "hash signature intelligence" in line.lower():
            styled_lines.append(f"{_BOLD}{_SUNSET_ORANGE}{line}{_RESET}")
            continue

        if "|___/" in line:
            styled_lines.append(f"{_DIM}{_SUNSET_GOLD}{line}{_RESET}")
            continue

        color = palette[idx % len(palette)]
        style = _BOLD if idx < 3 else ""
        if idx >= len(lines) - 2:
            style = _DIM
        styled_lines.append(f"{style}{color}{line}{_RESET}")

    styled_lines.append(f"{_DIM}{_AQUA}{version_text}{_RESET}")
    print("\n".join(styled_lines))

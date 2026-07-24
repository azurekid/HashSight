"""Prints the HashSight ASCII art banner. Purely cosmetic - never called on library import."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_FALLBACK_BANNER = r"""
  _   _           _      ____  _       _     _
 | | | | __ _ ___| |__  / ___|(_) __ _| |__ | |_
 | |_|/ _` / __| '_ \ \___ \| |/ _` | '_ \| __|
 |  _  | (_| \__ \ | | | ___) | | (_| | | | | |_
 |_| |_|\__,_|___/_| |_||____/|_|\__, |_| |_|\__|
                                 |___/

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

    # Green by default for terminal-first workflows.
    if sys.stdout.isatty():
        print(f"\033[32m{banner}\033[0m")
    else:
        print(banner)

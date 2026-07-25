"""Lightweight update check for HashSight CLI."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional
from urllib.request import urlopen

_CACHE_TTL_SECONDS = 60 * 60 * 24
_CACHE_PATH = Path.home() / ".cache" / "hashsight" / "update-check.json"
_PYPI_URL = "https://pypi.org/pypi/hashsight/json"


def _version_key(version: str) -> tuple[int, ...]:
    """Convert semantic-ish version text to a sortable integer tuple."""
    numbers = [int(part) for part in re.findall(r"\d+", version)]
    return tuple(numbers) if numbers else (0,)


def _read_cache(now: int) -> Optional[str]:
    try:
        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None

    checked_at = int(data.get("checked_at", 0))
    latest = str(data.get("latest", "")).strip()
    if not latest:
        return None
    if (now - checked_at) > _CACHE_TTL_SECONDS:
        return None
    return latest


def _write_cache(now: int, latest: str) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(
            json.dumps({"checked_at": now, "latest": latest}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        # Cache writes are best-effort only.
        return


def _fetch_latest_version() -> Optional[str]:
    try:
        with urlopen(_PYPI_URL, timeout=1.2) as response:
            payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    latest = str(payload.get("info", {}).get("version", "")).strip()
    return latest or None


def get_update_notice(current_version: str) -> Optional[str]:
    """Return update notice text when a newer release appears available."""
    if os.environ.get("HASHSIGHT_NO_UPDATE_CHECK"):
        return None

    now = int(time.time())
    latest = _read_cache(now)
    if latest is None:
        latest = _fetch_latest_version()
        if latest:
            _write_cache(now, latest)

    if not latest:
        return None

    if _version_key(latest) <= _version_key(current_version):
        return None

    return (
        f"Update available: hashsight {latest} (current {current_version}). "
        "Upgrade with: python3 -m pip install --upgrade hashsight"
    )

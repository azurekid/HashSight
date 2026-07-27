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
_SIGNATURES_CATALOG_URL = (
    "https://raw.githubusercontent.com/azurekid/HashSight/main/hashsight/data/signatures.json"
)


def _version_key(version: str) -> tuple[int, ...]:
    """Convert semantic-ish version text to a sortable integer tuple."""
    numbers = [int(part) for part in re.findall(r"\d+", version)]
    return tuple(numbers) if numbers else (0,)


def _read_cache(now: int) -> dict[str, Optional[str]]:
    try:
        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

    checked_at = int(data.get("checked_at", 0))
    if (now - checked_at) > _CACHE_TTL_SECONDS:
        return {}

    # Backward-compatible with old cache payloads that only stored "latest".
    package_latest = str(data.get("package_latest", data.get("latest", ""))).strip() or None
    catalog_latest = str(data.get("catalog_latest", "")).strip() or None
    return {"package_latest": package_latest, "catalog_latest": catalog_latest}


def _write_cache(now: int, package_latest: Optional[str], catalog_latest: Optional[str]) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {"checked_at": now}
        if package_latest:
            payload["package_latest"] = package_latest
        if catalog_latest:
            payload["catalog_latest"] = catalog_latest
        _CACHE_PATH.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
    except Exception:
        # Cache writes are best-effort only.
        return


def _fetch_latest_package_version() -> Optional[str]:
    try:
        with urlopen(_PYPI_URL, timeout=1.2) as response:
            payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    latest = str(payload.get("info", {}).get("version", "")).strip()
    return latest or None


def _fetch_latest_catalog_version() -> Optional[str]:
    try:
        with urlopen(_SIGNATURES_CATALOG_URL, timeout=1.2) as response:
            payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    latest = str(payload.get("version", "")).strip()
    return latest or None


def _resolve_latest_versions() -> tuple[Optional[str], Optional[str]]:
    """Resolve latest package and catalog versions using shared cache interval."""
    now = int(time.time())
    cached = _read_cache(now)
    package_latest = cached.get("package_latest")
    catalog_latest = cached.get("catalog_latest")

    if package_latest is None:
        package_latest = _fetch_latest_package_version()
    if catalog_latest is None:
        catalog_latest = _fetch_latest_catalog_version()

    if package_latest or catalog_latest:
        _write_cache(now, package_latest, catalog_latest)

    return package_latest, catalog_latest


def get_update_notice(current_version: str) -> Optional[str]:
    """Return update notice text when a newer release appears available."""
    if os.environ.get("HASHSIGHT_NO_UPDATE_CHECK"):
        return None

    latest, _ = _resolve_latest_versions()

    if not latest:
        return None

    if _version_key(latest) <= _version_key(current_version):
        return None

    return (
        f"Update available: hashsight {latest} (current {current_version}). "
        "Upgrade with: python3 -m pip install --upgrade hashsight"
    )


def get_signature_update_notice(current_catalog_version: str) -> Optional[str]:
    """Return update notice text when a newer signature catalog version appears available."""
    if os.environ.get("HASHSIGHT_NO_UPDATE_CHECK"):
        return None

    _, latest_catalog = _resolve_latest_versions()
    if not latest_catalog:
        return None

    if _version_key(latest_catalog) <= _version_key(current_catalog_version):
        return None

    return (
        "Signature catalog update available: "
        f"{latest_catalog} (current {current_catalog_version}). "
        "Update HashSight to get the latest bundled signatures "
        "(pip upgrade or git pull)."
    )

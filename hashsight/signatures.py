"""Loading and querying the HashSight signature database (Data/signatures.json)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Optional


def _default_data_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "signatures.json"


def load_signatures(path: Optional[Path] = None) -> list[dict[str, Any]]:
    """Load the signature database from a JSON file.

    Defaults to the bundled ``hashsight/data/signatures.json``. Raises ``FileNotFoundError``
    or ``ValueError`` (both prefixed with "HashSight:") on missing/invalid input.
    """
    source = Path(path) if path is not None else _default_data_path()

    if not source.exists():
        raise FileNotFoundError(f"HashSight: signature file not found at '{source}'.")

    try:
        raw = source.read_text(encoding="utf-8")
        doc = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"HashSight: failed to parse signature file '{source}': {exc}") from exc

    signatures = doc.get("signatures")
    if not signatures:
        raise ValueError(f"HashSight: signature file '{source}' does not contain a 'signatures' array.")

    return signatures


def filter_signatures(
    signatures: Iterable[dict[str, Any]],
    mode: Optional[int] = None,
    category: Optional[str] = None,
    name: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Filter signature entries by hashcat mode, category, and/or name (case-insensitive contains)."""
    entries = list(signatures)

    if mode is not None:
        entries = [
            e for e in entries
            if e.get("mode") == mode or any(c.get("mode") == mode for c in (e.get("candidates") or []))
        ]

    if category:
        entries = [e for e in entries if e.get("category") == category]

    if name:
        needle = name.lower()
        entries = [e for e in entries if needle in (e.get("name") or "").lower()]

    return entries

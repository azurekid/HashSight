"""Mapping helpers from hashcat-centric signatures to John the Ripper formats.

The bundled `signatures.json` is now the primary source of truth for `john_format`.
This module therefore keeps only:
    - a small mode->john fallback map for legacy/custom signature packs that may
        omit `john_format`.
"""
from __future__ import annotations

from typing import Optional


_MODE_TO_JOHN: dict[int, str] = {
    # Intentionally minimal in the bundled project: john_format should live in
    # signatures.json to avoid duplicated sources of truth.
    # Kept as an extension point for custom signature packs.
}


def john_format_for(mode: Optional[int], name: Optional[str], category: Optional[str]) -> Optional[str]:
    """Return John format from explicit fallback map only.

    For bundled signatures, john_format should come from signatures.json.
    """
    if mode is not None and mode in _MODE_TO_JOHN:
        return _MODE_TO_JOHN[mode]

    return None

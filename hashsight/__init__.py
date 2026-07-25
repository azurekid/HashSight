"""HashSight - the eye that spots your hash.

Instant, auditable identification of hashcat modes from a community-maintained JSON
signature database. See https://github.com/azurekid/HashSight.
"""
from __future__ import annotations

from typing import Any, Optional

from .matcher import HashResult, HashSightIndex, resolve_hash
from .signatures import filter_signatures, load_signatures
from .version import __version__

__all__ = [
    "HashResult",
    "get_hash",
    "get_signature",
    "load_signatures",
    "__version__",
]

_signatures: list[dict[str, Any]] = load_signatures()
_index = HashSightIndex(_signatures)


def get_hash(
    hash_value: str,
    *,
    exact_only: bool = False,
    top: Optional[int] = None,
    context: Optional[str] = None,
    full_mode: bool = False,
) -> Optional[HashResult]:
    """Identify the hashcat mode(s) that match a given hash string.

    Confidence levels returned:
      - Exact                      : format is unique to a single hashcat mode.
      - Exact (unverified mode #N) : format recognized, but the exact mode number may
                                      drift between hashcat releases.
      - Ambiguous                  : format is valid for multiple hashcat modes; all
                                      candidates are returned, ranked by popularity.
      - Unknown                    : no signature matched.
      - Invalid                    : empty input.

    :param hash_value: The hash string to identify.
    :param exact_only: If True, return None instead of a non-Exact result.
    :param top: For ambiguous matches, limit ``candidates`` to the top N by popularity.
    :param context: Optional free-text hint (e.g. "windows ad", "linux shadow",
        "wordpress") used to re-rank ambiguous candidates and improve certainty.
    :param full_mode: If True, include broad catalog fallback matches for hash-like
        inputs that are otherwise Unknown. This may return a large candidate set.
    """
    result = resolve_hash(hash_value, _index, context_hint=context, include_fallback=full_mode)

    if top is not None and result.candidates:
        result.candidates = result.candidates[:top]
        result.best_guess = result.candidates[0]

    if exact_only and not result.confidence.startswith("Exact"):
        return None

    return result


def get_signature(
    mode: Optional[int] = None,
    category: Optional[str] = None,
    name: Optional[str] = None,
) -> list[dict[str, Any]]:
    """List or search the loaded HashSight signature database.

    :param mode: Filter to entries whose mode (or one of whose candidates) matches this
        hashcat mode number.
    :param category: Filter to entries in the given category (e.g. 'Crypto Wallet').
    :param name: Filter to entries whose name contains this text (case-insensitive).
    """
    return filter_signatures(_signatures, mode=mode, category=category, name=name)

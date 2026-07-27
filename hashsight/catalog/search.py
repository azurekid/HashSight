"""Ranked signature search helpers for the CLI."""
from __future__ import annotations

import difflib
import re
from typing import Any, Optional

from ..core.john import john_format_for


def _normalize_search_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def _search_certainty(query: Optional[str], target: str) -> int:
    if not query:
        return 100

    q = _normalize_search_text(query)
    t = _normalize_search_text(target)
    if not q or not t:
        return 0

    if q == t:
        return 100
    if t.startswith(q):
        return 94
    if f" {q} " in f" {t} ":
        return 88
    if q in t:
        return 78

    ratio = difflib.SequenceMatcher(None, q, t).ratio()
    if ratio < 0.6:
        return 0
    return int(round(45 + (ratio * 50)))


def signature_search_rows(
    *,
    mode: Optional[int],
    category: Optional[str],
    name: Optional[str],
) -> list[dict[str, Any]]:
    """Search top-level signatures and nested candidates with certainty ranking."""
    from .. import get_signature

    all_entries = get_signature()
    rows: list[dict[str, Any]] = []

    def _source_rank(*, is_top_level: bool, is_fallback: bool) -> int:
        # Prefer canonical top-level signatures, then non-fallback candidates,
        # and only then catalog fallback rows.
        if is_top_level:
            return 3
        if is_fallback:
            return 1
        return 2

    for entry in all_entries:
        entry_candidates = entry.get("candidates") or []

        if not entry_candidates:
            entry_mode = entry.get("mode")
            entry_name = str(entry.get("name") or "")
            entry_category = str(entry.get("category") or "-")
            entry_fallback = bool(entry.get("fallback") is True)

            if mode is not None and entry_mode != mode:
                continue
            if category and entry_category != category:
                continue

            certainty = _search_certainty(name, entry_name)
            if name and certainty == 0:
                continue

            rows.append(
                {
                    "name": entry_name or "-",
                    "mode": entry_mode,
                    "john": entry.get("john_format")
                    or john_format_for(entry_mode, entry_name, entry_category)
                    or "-",
                    "category": entry_category,
                    "certainty": certainty,
                    "_source_rank": _source_rank(is_top_level=True, is_fallback=entry_fallback),
                }
            )
            continue

        entry_fallback = bool(entry.get("fallback") is True)
        for candidate in entry_candidates:
            cand_mode = candidate.get("mode")
            cand_name = str(candidate.get("name") or "")
            cand_category = str(candidate.get("category") or entry.get("category") or "-")

            if mode is not None and cand_mode != mode:
                continue
            if category and cand_category != category:
                continue

            certainty = _search_certainty(name, cand_name)
            if name and certainty == 0:
                continue

            rows.append(
                {
                    "name": cand_name or "-",
                    "mode": cand_mode,
                    "john": candidate.get("john_format")
                    or entry.get("john_format")
                    or john_format_for(cand_mode, cand_name, cand_category)
                    or "-",
                    "category": cand_category,
                    "certainty": certainty,
                    "_source_rank": _source_rank(is_top_level=False, is_fallback=entry_fallback),
                }
            )

    best: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        mode_value = row.get("mode")
        if mode_value is not None:
            key = ("mode", mode_value)
        else:
            key = ("nomode", row["name"], row["john"], row["category"])
        existing = best.get(key)
        if existing is None:
            best[key] = row
            continue

        row_priority = (row["certainty"], row.get("_source_rank", 0))
        existing_priority = (existing["certainty"], existing.get("_source_rank", 0))
        if row_priority > existing_priority:
            best[key] = row

    result = []
    for row in best.values():
        row = dict(row)
        row.pop("_source_rank", None)
        result.append(row)

    return sorted(result, key=lambda r: (r["certainty"], str(r["name"]).lower()), reverse=True)

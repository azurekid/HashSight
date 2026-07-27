"""Three-tier hash matching engine.

Dispatch order, cheapest/most specific first:
  1. Prefix bucket lookup (literal, longest-match-first).
  2. Compiled regex list (structural formats).
  3. Bare-hex length lookup.
Falls back to 'Unknown' when nothing matches, or 'Invalid' for empty input.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .john import john_format_for

_HEX_RE = re.compile(r"^[A-Fa-f0-9]+$")
_BASE64ISH_RE = re.compile(r"^[A-Za-z0-9+/=._-]{16,}$")

_FIXED_SALT_LEN: dict[int, int] = {
    2611: 3,  # vBulletin < v3.8.5 (dynamic_7, hard 3-byte salt)
}


@dataclass
class HashResult:
    """Result of identifying a single hash string."""

    hash: str
    confidence: str
    mode: Optional[int] = None
    name: Optional[str] = None
    category: Optional[str] = None
    john_format: Optional[str] = None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    best_guess: Optional[dict[str, Any]] = None
    hint_terms: list[str] = field(default_factory=list)
    hint_applied: bool = False
    structural_hint_applied: bool = False
    deterministic_structural_match: bool = False


class HashSightIndex:
    """Builds and holds the prefix/regex/hex lookup indices used to resolve hashes."""

    def __init__(self, signatures: list[dict[str, Any]]):
        self.prefix_index: dict[str, list[dict[str, Any]]] = {}
        self.regex_index: list[tuple[re.Pattern, dict[str, Any]]] = []
        self.fallback_regex_index: list[tuple[re.Pattern, dict[str, Any]]] = []
        self.hex_index: dict[str, dict[str, Any]] = {}

        for entry in signatures:
            kind = entry.get("kind")
            if kind == "Prefix":
                bucket = entry["match"][0]
                self.prefix_index.setdefault(bucket, []).append(entry)
            elif kind == "Regex":
                if entry.get("fallback") is True:
                    self.fallback_regex_index.append((re.compile(entry["match"]), entry))
                else:
                    self.regex_index.append((re.compile(entry["match"]), entry))
            elif kind == "Hex":
                self.hex_index[f"hex:{entry['length']}"] = entry
            else:
                print(
                    f"HashSight: signature entry '{entry.get('name')}' has unknown kind "
                    f"'{kind}' and was skipped."
                )

        for bucket, entries in self.prefix_index.items():
            self.prefix_index[bucket] = sorted(entries, key=lambda e: len(e["match"]), reverse=True)


def complete_match(hash_value: str, entry: dict[str, Any]) -> HashResult:
    """Build the result object returned for a matched signature entry (internal helper)."""
    candidates = entry.get("candidates") or []
    hint_terms = _hint_terms_from_context(entry.get("_context_hint"))
    salt_features = _salt_features(hash_value)

    if candidates:
        scored = []
        for candidate in candidates:
            score, hint_matched, structural_matched, strong_match = _candidate_score(
                candidate, hint_terms, salt_features
            )
            candidate_copy = dict(candidate)
            candidate_copy["john_format"] = (
                candidate_copy.get("john_format")
                or entry.get("john_format")
                or john_format_for(
                    candidate_copy.get("mode"),
                    candidate_copy.get("name"),
                    candidate_copy.get("category"),
                )
            )
            candidate_copy["match_score"] = score
            scored.append((score, candidate_copy, hint_matched, structural_matched, strong_match))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Guard against accidental duplicate candidate rows in signature data.
        # Prefer the highest-scoring row for a given mode.
        seen_keys: set[tuple[Any, ...]] = set()
        sorted_candidates: list[dict[str, Any]] = []
        deduped_scored: list[tuple[int, dict[str, Any], bool, bool, bool]] = []
        for item in scored:
            _, candidate_copy, _, _, _ = item
            mode = candidate_copy.get("mode")
            if mode is not None:
                key = ("mode", mode)
            else:
                key = (
                    "name",
                    candidate_copy.get("name"),
                    candidate_copy.get("john_format"),
                )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped_scored.append(item)
            sorted_candidates.append(candidate_copy)

        _, _, top_hint_matched, top_structural_matched, top_strong_match = deduped_scored[0]
        return HashResult(
            hash=hash_value,
            confidence="Ambiguous",
            mode=None,
            name=entry.get("name"),
            category=entry.get("category"),
            john_format=None,
            candidates=sorted_candidates,
            best_guess=sorted_candidates[0],
            hint_terms=hint_terms,
            hint_applied=top_hint_matched,
            structural_hint_applied=top_structural_matched or top_strong_match,
            deterministic_structural_match=top_strong_match,
        )

    mode = entry.get("mode")

    confidence = "Exact"
    if entry.get("verified") is False:
        confidence = f"Exact (unverified mode #{mode})"

    return HashResult(
        hash=hash_value,
        confidence=confidence,
        mode=entry.get("mode"),
        name=entry.get("name"),
        category=entry.get("category"),
        john_format=entry.get("john_format")
        or john_format_for(entry.get("mode"), entry.get("name"), entry.get("category")),
        candidates=[],
        best_guess={
            "mode": entry.get("mode"),
            "name": entry.get("name"),
            "category": entry.get("category"),
            "john_format": entry.get("john_format")
            or john_format_for(entry.get("mode"), entry.get("name"), entry.get("category")),
            "popularity": 10,
        },
        hint_terms=hint_terms,
        hint_applied=False,
    )


def _hint_terms_from_context(context_hint: Optional[str]) -> list[str]:
    if not context_hint:
        return []
    return [t for t in re.split(r"[^a-z0-9]+", context_hint.lower()) if len(t) >= 2]


def _salt_features(hash_value: str) -> Optional[dict[str, Any]]:

    if ":" not in hash_value:
        return None
    salt = hash_value.split(":", 1)[1]
    if not salt:
        return None
    return {"len": len(salt), "hex": bool(_HEX_RE.match(salt))}


def _candidate_score(
    candidate: dict[str, Any],
    hint_terms: list[str],
    salt_features: Optional[dict[str, Any]] = None,
) -> tuple[int, bool, bool, bool]:

    base = candidate.get("popularity", 0) * 10
    bonus = 0
    hint_matched = False
    structural_matched = False
    strong_match = False

    if hint_terms:
        haystack = " ".join(
            [
                str(candidate.get("mode", "")),
                str(candidate.get("name", "")).lower(),
                str(candidate.get("category", "")).lower(),
                str(candidate.get("john_format", "")).lower(),
            ]
        )
        for term in hint_terms:
            if term in haystack:
                bonus += 18
                hint_matched = True

    salt_len_hint = candidate.get("salt_len_hint")
    if salt_features is not None and salt_len_hint is not None:
        diff = abs(salt_features["len"] - salt_len_hint)
        if diff == 0:
            bonus += 20
            structural_matched = True
        elif diff <= 2:
            bonus += 8
            structural_matched = True
        elif diff > 6:
            bonus -= 6

        salt_hex_hint = candidate.get("salt_hex_hint")
        if salt_hex_hint is not None:
            if salt_hex_hint == salt_features["hex"]:
                bonus += 5
            else:
                bonus -= 5

    fixed_len = _FIXED_SALT_LEN.get(candidate.get("mode"))
    if fixed_len is not None and salt_features is not None:
        if salt_features["len"] == fixed_len:
            bonus += 80
            structural_matched = True
            strong_match = True
        else:
            bonus -= 15

    return base + bonus, hint_matched, structural_matched, strong_match


def _looks_hashlike(value: str) -> bool:
    if len(value) < 8:
        return False
    if any(ch in value for ch in ("$", ":", "*")):
        return True
    if _HEX_RE.match(value) and len(value) >= 16:
        return True
    if _BASE64ISH_RE.match(value):
        has_digit = any(ch.isdigit() for ch in value)
        has_symbol = any(ch in "+/=_-" for ch in value)
        return has_digit or has_symbol
    return False


def resolve_hash(
    hash_value: str,
    index: HashSightIndex,
    context_hint: Optional[str] = None,
    include_fallback: bool = False,
) -> HashResult:
    """Identify a single hash string against the loaded signature indices (internal helper)."""
    trimmed = hash_value.strip()

    if not trimmed:
        return HashResult(hash=hash_value, confidence="Invalid")

    bucket = trimmed[0]
    for entry in index.prefix_index.get(bucket, []):
        if trimmed.startswith(entry["match"]):
            if context_hint:
                entry = dict(entry)
                entry["_context_hint"] = context_hint
            return complete_match(trimmed, entry)

    for pattern, entry in index.regex_index:
        if pattern.search(trimmed):
            if context_hint:
                entry = dict(entry)
                entry["_context_hint"] = context_hint
            return complete_match(trimmed, entry)

    if _HEX_RE.match(trimmed):
        entry = index.hex_index.get(f"hex:{len(trimmed)}")
        if entry:
            if context_hint:
                entry = dict(entry)
                entry["_context_hint"] = context_hint
            return complete_match(trimmed, entry)

    if include_fallback and _looks_hashlike(trimmed):
        for pattern, entry in index.fallback_regex_index:
            if pattern.search(trimmed):
                if context_hint:
                    entry = dict(entry)
                    entry["_context_hint"] = context_hint
                return complete_match(trimmed, entry)

    return HashResult(hash=trimmed, confidence="Unknown")

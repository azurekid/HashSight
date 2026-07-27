"""Loading and querying the HashSight signature database (Data/signatures.json)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Optional


_CATALOG_VERSION_RE = re.compile(
    r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)


def _default_data_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "signatures.json"


def _load_signature_document(path: Optional[Path] = None) -> tuple[Path, dict[str, Any]]:
    """Load and validate the raw signature catalog document."""
    source = Path(path) if path is not None else _default_data_path()

    if not source.exists():
        raise FileNotFoundError(f"HashSight: signature file not found at '{source}'.")

    try:
        raw = source.read_text(encoding="utf-8")
        doc = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"HashSight: failed to parse signature file '{source}': {exc}") from exc

    version = str(doc.get("version", "")).strip()
    if not version:
        raise ValueError(f"HashSight: signature file '{source}' is missing required 'version'.")
    if not _CATALOG_VERSION_RE.match(version):
        raise ValueError(
            "HashSight: invalid signature catalog version "
            f"'{version}' in '{source}'. Expected semantic version (e.g. 1.2.3)."
        )

    signatures = doc.get("signatures")
    if not signatures:
        raise ValueError(f"HashSight: signature file '{source}' does not contain a 'signatures' array.")

    _validate_signatures(signatures, source)

    return source, doc


def _candidate_ref_mode(candidate: Any) -> Any:
    """Return the mode from a candidate reference (bare int or object)."""
    if isinstance(candidate, bool):
        return None
    if isinstance(candidate, int):
        return candidate
    if isinstance(candidate, dict):
        return candidate.get("mode")
    return None


def _validate_signatures(signatures: list[dict[str, Any]], source: Path) -> None:
    """Validate required fields so malformed entries fail fast and loudly.

    Candidate references may be a bare integer mode or an object with a ``mode``.
    """
    for idx, entry in enumerate(signatures):
        candidates = entry.get("candidates") or []
        for c_idx, candidate in enumerate(candidates):
            mode = _candidate_ref_mode(candidate)
            if mode is None:
                raise ValueError(
                    "HashSight: invalid signature data in "
                    f"'{source}': signatures[{idx}].candidates[{c_idx}] is missing required 'mode'."
                )
            if not isinstance(mode, int):
                raise ValueError(
                    "HashSight: invalid signature data in "
                    f"'{source}': signatures[{idx}].candidates[{c_idx}].mode must be an integer, got {type(mode).__name__}."
                )


_CANDIDATE_META_FIELDS = (
    "name",
    "category",
    "john_format",
    "salt_len_hint",
    "salt_hex_hint",
    "total_len_hint",
    "field_count_hint",
)


def _expand_from_catalog(doc: dict[str, Any], signatures: list[dict[str, Any]]) -> None:
    """Expand a normalized document (with a top-level ``modes`` catalog) in place.

    Candidate references (bare ``int`` or ``{"mode", "popularity", ...}``) are expanded
    into full candidate dicts by merging the catalog's intrinsic mode metadata. Explicit
    per-reference keys always win over catalog values. Single-mode signatures have their
    ``name``/``category``/``john_format`` hydrated from the catalog when absent.
    """
    raw_modes = doc.get("modes") or {}
    catalog: dict[int, dict[str, Any]] = {}
    for key, meta in raw_modes.items():
        try:
            catalog[int(key)] = meta
        except (TypeError, ValueError):
            continue

    for entry in signatures:
        candidates = entry.get("candidates")
        if candidates:
            expanded: list[dict[str, Any]] = []
            for ref in candidates:
                if isinstance(ref, dict):
                    mode = ref.get("mode")
                    popularity = ref.get("popularity", 1)
                    overrides = {
                        k: v for k, v in ref.items() if k not in ("mode", "popularity")
                    }
                else:
                    mode = ref
                    popularity = 1
                    overrides = {}

                meta = catalog.get(mode, {})
                candidate: dict[str, Any] = {"mode": mode, "popularity": popularity}
                for f in _CANDIDATE_META_FIELDS:
                    if meta.get(f) is not None:
                        candidate[f] = meta[f]
                candidate.update(overrides)
                expanded.append(candidate)
            entry["candidates"] = expanded
        elif isinstance(entry.get("mode"), int):
            meta = catalog.get(entry["mode"])
            if meta:
                for f in ("name", "category", "john_format"):
                    if not entry.get(f) and meta.get(f) is not None:
                        entry[f] = meta[f]


def _canonical_mode_meta(signatures: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Build a best-effort mode->metadata map from top-level signature entries (legacy)."""
    mode_meta: dict[int, dict[str, Any]] = {}

    for entry in signatures:
        mode = entry.get("mode")
        if not isinstance(mode, int):
            continue

        name = entry.get("name")
        john_format = entry.get("john_format")
        if not name and not john_format:
            continue

        # Prefer verified exact entries, then entries that include john_format.
        rank = 0
        if entry.get("verified") is True:
            rank += 2
        if john_format:
            rank += 1

        current = mode_meta.get(mode)
        if current is None or rank > current["rank"]:
            mode_meta[mode] = {
                "name": name,
                "john_format": john_format,
                "rank": rank,
            }

    return mode_meta


def _hydrate_candidate_metadata(signatures: list[dict[str, Any]]) -> None:
    """Fill missing candidate metadata from canonical top-level mode metadata (legacy).

    Only used for legacy documents that lack a normalized ``modes`` catalog.
    """
    mode_meta = _canonical_mode_meta(signatures)

    for entry in signatures:
        for candidate in entry.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            mode = candidate.get("mode")
            if not isinstance(mode, int):
                continue

            meta = mode_meta.get(mode)
            if not meta:
                continue

            if not candidate.get("name") and meta.get("name"):
                candidate["name"] = meta["name"]

            if not candidate.get("john_format") and meta.get("john_format"):
                candidate["john_format"] = meta["john_format"]


def load_signatures(path: Optional[Path] = None) -> list[dict[str, Any]]:
    """Load the signature database from a JSON file.

    Defaults to the bundled ``hashsight/data/signatures.json``. Raises ``FileNotFoundError``
    or ``ValueError`` (both prefixed with "HashSight:") on missing/invalid input.
    """
    _, doc = _load_signature_document(path)
    signatures = doc["signatures"]
    if doc.get("modes"):
        _expand_from_catalog(doc, signatures)
    else:
        _hydrate_candidate_metadata(signatures)

    return signatures


def load_signature_catalog_info(path: Optional[Path] = None) -> dict[str, Any]:
    """Return top-level signature catalog metadata used for update/version checks."""
    source, doc = _load_signature_document(path)
    signatures = doc.get("signatures") or []

    candidate_count = 0
    mode_reference_count = 0
    unique_modes: set[int] = set()

    for entry in signatures:
        entry_mode = entry.get("mode")
        if isinstance(entry_mode, int):
            mode_reference_count += 1
            unique_modes.add(entry_mode)

        candidates = entry.get("candidates") or []
        candidate_count += len(candidates)
        for candidate in candidates:
            candidate_mode = _candidate_ref_mode(candidate)
            if isinstance(candidate_mode, int):
                mode_reference_count += 1
                unique_modes.add(candidate_mode)

    return {
        "path": str(source),
        "version": str(doc.get("version", "")).strip(),
        "source": str(doc.get("source", "")).strip() or None,
        "description": str(doc.get("description", "")).strip() or None,
        "signature_count": len(signatures),
        "candidate_count": candidate_count,
        "mode_reference_count": mode_reference_count,
        "unique_mode_count": len(unique_modes),
    }


def signature_catalog_version(path: Optional[Path] = None) -> str:
    """Return the semantic version of the loaded signature catalog."""
    info = load_signature_catalog_info(path)
    return str(info["version"])


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

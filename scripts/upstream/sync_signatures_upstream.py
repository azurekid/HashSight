#!/usr/bin/env python3
"""Fetch upstream hash data sources, analyze drift, and sync local signatures.json.

Data sources:
- Hashcat example hashes wiki (mode -> name catalog)
- PentestMonkey John format cheat sheet (legacy john format catalog)
- Haiti prototypes (regex + mode + john metadata)

Sync behavior:
- Enrich missing john_format values when Haiti provides one.
- Append missing hashcat modes as Regex signatures when Haiti provides a regex.
- Keep all writes schema-safe with explicit structural checks.
- Write an audit report under hashsight/data/upstream.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SIGNATURES_PATH = ROOT / "hashsight" / "data" / "signatures.json"
UPSTREAM_DIR = ROOT / "hashsight" / "data" / "upstream"

HASHCAT_EXAMPLES_URL = "https://hashcat.net/wiki/doku.php?id=example_hashes"
JOHN_FORMATS_URL = "https://pentestmonkey.net/cheat-sheet/john-the-ripper-hash-formats"
HAITI_PROTOTYPES_URL = "https://raw.githubusercontent.com/noraj/haiti/master/data/prototypes.json"


@dataclass
class SyncStats:
    fetched_files: int = 0
    cached_files_reused: int = 0
    hashcat_modes_total: int = 0
    hashcat_modes_in_local_before: int = 0
    hashcat_modes_in_local_after: int = 0
    hashcat_modes_missing_before: int = 0
    hashcat_modes_missing_after: int = 0
    john_formats_total: int = 0
    local_john_formats_total: int = 0
    local_john_formats_not_in_pentestmonkey: int = 0
    haiti_modes_total: int = 0
    local_modes_before: int = 0
    local_modes_after: int = 0
    added_modes: int = 0
    mode_catalog_entries_repaired: int = 0
    john_fields_enriched: int = 0


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "HashSight-Upstream-Sync/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def _fetch_json(url: str) -> Any:
    return json.loads(_fetch_text(url))


def _load_text_source(url: str, cache_path: Path) -> tuple[str, bool]:
    try:
        text = _fetch_text(url)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        if not cache_path.is_file():
            raise
        print(f"warning: failed to fetch {url}; using cached {cache_path.name}: {exc}")
        return cache_path.read_text(encoding="utf-8"), False

    cache_path.write_text(text, encoding="utf-8")
    return text, True


def _load_json_source(url: str, cache_path: Path) -> tuple[Any, bool]:
    try:
        payload = _fetch_json(url)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        if not cache_path.is_file():
            raise
        print(f"warning: failed to fetch {url}; using cached {cache_path.name}: {exc}")
        return json.loads(cache_path.read_text(encoding="utf-8")), False

    cache_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload, True


def _local_mode_set(signatures: list[dict[str, Any]]) -> set[int]:
    modes: set[int] = set()
    for entry in signatures:
        mode = entry.get("mode")
        if isinstance(mode, int):
            modes.add(mode)
        for candidate in entry.get("candidates") or []:
            if isinstance(candidate, dict):
                c_mode = candidate.get("mode")
                if isinstance(c_mode, int):
                    modes.add(c_mode)
    return modes


def _normalize_haiti_regex(regex: str) -> str:
    # Haiti uses Ruby-style anchors; Python regex in this project uses ^/$.
    return regex.replace(r"\A", "^").replace(r"\Z", "$")


def _strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    text = unescape(text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _parse_hashcat_mode_names(page_html: str) -> dict[int, str]:
    """Extract hashcat mode/name pairs from the example_hashes wiki table rows."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", page_html, flags=re.IGNORECASE | re.DOTALL)
    modes: dict[int, str] = {}

    for row in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.IGNORECASE | re.DOTALL)
        if len(cells) < 2:
            continue

        raw_mode = _strip_tags(cells[0])
        raw_name = _strip_tags(
            re.sub(r"<sup\b[^>]*>.*?</sup>", "", cells[1], flags=re.IGNORECASE | re.DOTALL)
        )

        if not raw_mode.isdigit() or not raw_name:
            continue

        mode = int(raw_mode)
        # Keep first seen to avoid churn where duplicate modes appear in multiple rows.
        modes.setdefault(mode, raw_name)

    return modes


def _parse_pentestmonkey_john_formats(page_html: str) -> set[str]:
    """Extract John format ids from h2 headings: '<format> – <description>'."""
    headers = re.findall(r"<h2[^>]*>(.*?)</h2>", page_html, flags=re.IGNORECASE | re.DOTALL)
    formats: set[str] = set()

    for header in headers:
        text = _strip_tags(header)
        if not text:
            continue

        if "–" in text:
            token = text.split("–", 1)[0].strip()
        elif "-" in text:
            token = text.split("-", 1)[0].strip()
        else:
            token = text.strip()

        token = token.lower()
        if token and token != "<none>":
            formats.add(token)

    return formats


def _build_haiti_mode_records(prototypes: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}

    for proto in prototypes:
        regex = proto.get("regex")
        if not isinstance(regex, str) or not regex:
            continue

        modes = proto.get("modes") or []
        for mode_info in modes:
            mode = mode_info.get("hashcat")
            if not isinstance(mode, int):
                continue

            name = mode_info.get("name") or f"Hash mode {mode}"
            john = mode_info.get("john")
            normalized_regex = _normalize_haiti_regex(regex)

            record = records.get(mode)
            if record is None:
                records[mode] = {
                    "mode": mode,
                    "name": name,
                    "john": john if isinstance(john, str) and john else None,
                    "regex": normalized_regex,
                }
                continue

            # Prefer records with john value and shorter regex (typically more specific/readable).
            if record.get("john") is None and isinstance(john, str) and john:
                record["john"] = john
            if len(normalized_regex) < len(record["regex"]):
                record["regex"] = normalized_regex
            # Keep first non-empty name unless current is generic.
            if (record.get("name") or "").startswith("Hash mode") and name:
                record["name"] = name

    return records


def _enrich_existing_john_formats(signatures: list[dict[str, Any]], haiti_records: dict[int, dict[str, Any]]) -> int:
    updated = 0

    for entry in signatures:
        mode = entry.get("mode")
        if isinstance(mode, int) and not entry.get("john_format"):
            john = haiti_records.get(mode, {}).get("john")
            if john:
                entry["john_format"] = john
                updated += 1

        for candidate in entry.get("candidates") or []:
            if isinstance(candidate, dict):
                c_mode = candidate.get("mode")
                if isinstance(c_mode, int) and not candidate.get("john_format"):
                    john = haiti_records.get(c_mode, {}).get("john")
                    if john:
                        candidate["john_format"] = john
                        updated += 1

    return updated


def _append_missing_modes(signatures: list[dict[str, Any]], haiti_records: dict[int, dict[str, Any]]) -> int:
    local_modes = _local_mode_set(signatures)
    missing = sorted(mode for mode in haiti_records if mode not in local_modes)

    for mode in missing:
        rec = haiti_records[mode]
        entry: dict[str, Any] = {
            "kind": "Regex",
            "match": rec["regex"],
            "mode": mode,
            "name": rec["name"],
            "category": "Imported/Haiti",
            "verified": False,
        }
        if rec.get("john"):
            entry["john_format"] = rec["john"]
        signatures.append(entry)

    return len(missing)


def _collect_local_john_formats(signatures: list[dict[str, Any]]) -> set[str]:
    values: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            values.add(value.strip().lower())

    for entry in signatures:
        add(entry.get("john_format"))
        for candidate in entry.get("candidates") or []:
            if isinstance(candidate, dict):
                add(candidate.get("john_format"))

    return values


def _collect_mode_metadata(signatures: list[dict[str, Any]]) -> dict[int, dict[str, str]]:
    values: dict[int, dict[str, str]] = {}

    def add(mode: Any, *, name: Any, category: Any, john_format: Any) -> None:
        if not isinstance(mode, int) or isinstance(mode, bool):
            return

        meta = values.setdefault(mode, {})
        if _has_nonempty_string(name) and "name" not in meta:
            meta["name"] = name.strip()
        if _has_nonempty_string(category) and "category" not in meta:
            meta["category"] = category.strip()
        if _has_nonempty_string(john_format) and "john_format" not in meta:
            meta["john_format"] = john_format.strip()

    for entry in signatures:
        add(
            entry.get("mode"),
            name=entry.get("name"),
            category=entry.get("category"),
            john_format=entry.get("john_format"),
        )
        for candidate in entry.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            add(
                candidate.get("mode"),
                name=candidate.get("name"),
                category=candidate.get("category"),
                john_format=candidate.get("john_format"),
            )

    return values


def _modes_requiring_catalog(signatures: list[dict[str, Any]]) -> set[int]:
    modes: set[int] = set()

    for entry in signatures:
        mode = entry.get("mode")
        if isinstance(mode, int) and not isinstance(mode, bool):
            if any(
                not _has_nonempty_string(entry.get(field))
                for field in ("name", "category", "john_format")
            ):
                modes.add(mode)

        for candidate in entry.get("candidates") or []:
            if isinstance(candidate, dict):
                candidate_mode = candidate.get("mode")
                if isinstance(candidate_mode, int) and not isinstance(candidate_mode, bool):
                    if any(
                        not _has_nonempty_string(candidate.get(field))
                        for field in ("name", "category", "john_format")
                    ):
                        modes.add(candidate_mode)
            elif isinstance(candidate, int) and not isinstance(candidate, bool):
                modes.add(candidate)

    return modes


def _catalog_meta_for_mode(mode_catalog: dict[str, Any] | None, mode: Any) -> dict[str, Any]:
    if not isinstance(mode_catalog, dict) or not isinstance(mode, int) or isinstance(mode, bool):
        return {}
    meta = mode_catalog.get(str(mode))
    return meta if isinstance(meta, dict) else {}


def _has_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_signature_shape(signatures: list[dict[str, Any]], mode_catalog: dict[str, Any] | None = None) -> None:
    """Fail fast on malformed entries before writing signatures.json.

    Candidate references may be stored either as bare integer modes or as objects
    that override catalog metadata while still resolving missing fields from the
    top-level ``modes`` catalog.
    """
    for idx, entry in enumerate(signatures):
        if not isinstance(entry, dict):
            raise ValueError(f"signatures[{idx}] must be an object")

        kind = entry.get("kind")
        name = entry.get("name")
        category = entry.get("category")
        entry_mode = entry.get("mode")
        entry_meta = _catalog_meta_for_mode(mode_catalog, entry_mode)

        if kind not in {"Prefix", "Regex", "Hex"}:
            raise ValueError(f"signatures[{idx}] invalid kind: {kind!r}")
        if not (_has_nonempty_string(name) or _has_nonempty_string(entry_meta.get("name"))):
            raise ValueError(f"signatures[{idx}] missing/invalid name")
        if not (_has_nonempty_string(category) or _has_nonempty_string(entry_meta.get("category"))):
            raise ValueError(f"signatures[{idx}] missing/invalid category")

        if kind in {"Prefix", "Regex"} and not isinstance(entry.get("match"), str):
            raise ValueError(f"signatures[{idx}] kind={kind} missing string match")
        if kind == "Hex" and not isinstance(entry.get("length"), int):
            raise ValueError(f"signatures[{idx}] kind=Hex missing integer length")

        raw_candidates = entry.get("candidates")
        if raw_candidates is not None and not isinstance(raw_candidates, list):
            raise ValueError(f"signatures[{idx}] candidates must be an array")

        has_mode = isinstance(entry_mode, int) and not isinstance(entry_mode, bool)
        candidates = raw_candidates or []
        has_candidates = isinstance(candidates, list) and len(candidates) > 0

        if not (has_mode or has_candidates):
            raise ValueError(f"signatures[{idx}] requires mode or candidates")

        for c_idx, candidate in enumerate(candidates):
            if isinstance(candidate, bool):
                raise ValueError(f"signatures[{idx}].candidates[{c_idx}] missing integer mode")

            if isinstance(candidate, int) and not isinstance(candidate, bool):
                candidate_mode = candidate
                candidate_name = None
                candidate_category = None
            elif isinstance(candidate, dict):
                candidate_mode = candidate.get("mode")
                candidate_name = candidate.get("name")
                candidate_category = candidate.get("category")
            else:
                raise ValueError(f"signatures[{idx}].candidates[{c_idx}] missing integer mode")

            if not isinstance(candidate_mode, int) or isinstance(candidate_mode, bool):
                raise ValueError(f"signatures[{idx}].candidates[{c_idx}] missing integer mode")

            candidate_meta = _catalog_meta_for_mode(mode_catalog, candidate_mode)

            if not (_has_nonempty_string(candidate_name) or _has_nonempty_string(candidate_meta.get("name"))):
                raise ValueError(f"signatures[{idx}].candidates[{c_idx}] missing/invalid name")
            if not (_has_nonempty_string(candidate_category) or _has_nonempty_string(candidate_meta.get("category"))):
                raise ValueError(f"signatures[{idx}].candidates[{c_idx}] missing/invalid category")


def _repair_mode_catalog(
    signatures_doc: dict[str, Any],
    hashcat_modes: dict[int, str],
    haiti_records: dict[int, dict[str, Any]],
) -> int:
    signatures = signatures_doc.get("signatures") or []
    mode_catalog = signatures_doc.get("modes")
    if mode_catalog is None:
        mode_catalog = {}
        signatures_doc["modes"] = mode_catalog
    if not isinstance(mode_catalog, dict):
        raise ValueError("signatures.json does not contain a valid modes object")

    local_meta = _collect_mode_metadata(signatures)
    repaired = 0

    for mode in sorted(_modes_requiring_catalog(signatures)):
        current = mode_catalog.get(str(mode))
        meta = dict(current) if isinstance(current, dict) else {}
        previous = dict(meta)

        if not _has_nonempty_string(meta.get("name")):
            for candidate in (
                local_meta.get(mode, {}).get("name"),
                hashcat_modes.get(mode),
                haiti_records.get(mode, {}).get("name"),
            ):
                if _has_nonempty_string(candidate):
                    meta["name"] = candidate.strip()
                    break

        if not _has_nonempty_string(meta.get("category")):
            category = local_meta.get(mode, {}).get("category")
            if _has_nonempty_string(category):
                meta["category"] = category.strip()
            elif _has_nonempty_string(meta.get("name")):
                meta["category"] = "Catalog Fallback"

        if not _has_nonempty_string(meta.get("john_format")):
            for candidate in (
                local_meta.get(mode, {}).get("john_format"),
                haiti_records.get(mode, {}).get("john"),
            ):
                if _has_nonempty_string(candidate):
                    meta["john_format"] = candidate.strip()
                    break

        if meta != previous or not isinstance(current, dict):
            mode_catalog[str(mode)] = meta
            repaired += 1

    return repaired


def _canonicalize_mode_catalog(signatures_doc: dict[str, Any]) -> None:
    mode_catalog = signatures_doc.get("modes")
    if mode_catalog is None:
        signatures_doc["modes"] = {}
        return
    if not isinstance(mode_catalog, dict):
        raise ValueError("signatures.json does not contain a valid modes object")

    merged_numeric: dict[int, dict[str, Any]] = {}
    non_numeric: list[tuple[str, dict[str, Any]]] = []

    for key, value in mode_catalog.items():
        if not isinstance(value, dict):
            value = {}
        try:
            mode = int(str(key))
        except (TypeError, ValueError):
            non_numeric.append((str(key), dict(value)))
            continue

        existing = merged_numeric.get(mode)
        if existing is None:
            merged_numeric[mode] = dict(value)
            continue

        for field, field_value in value.items():
            if existing.get(field) in (None, "") and field_value not in (None, ""):
                existing[field] = field_value

    canonical_modes: dict[str, dict[str, Any]] = {
        str(mode): merged_numeric[mode] for mode in sorted(merged_numeric)
    }
    for key, value in sorted(non_numeric, key=lambda item: item[0]):
        canonical_modes[key] = value

    signatures_doc["modes"] = canonical_modes


def main() -> int:
    UPSTREAM_DIR.mkdir(parents=True, exist_ok=True)

    stats = SyncStats()

    hashcat_page, hashcat_fetched = _load_text_source(
        HASHCAT_EXAMPLES_URL,
        UPSTREAM_DIR / "hashcat-example-hashes.html",
    )
    stats.fetched_files += int(hashcat_fetched)
    stats.cached_files_reused += int(not hashcat_fetched)

    john_page, john_fetched = _load_text_source(
        JOHN_FORMATS_URL,
        UPSTREAM_DIR / "john-pentestmonkey.html",
    )
    stats.fetched_files += int(john_fetched)
    stats.cached_files_reused += int(not john_fetched)

    haiti_prototypes, haiti_fetched = _load_json_source(
        HAITI_PROTOTYPES_URL,
        UPSTREAM_DIR / "haiti-prototypes.json",
    )
    stats.fetched_files += int(haiti_fetched)
    stats.cached_files_reused += int(not haiti_fetched)

    signatures_doc = json.loads(SIGNATURES_PATH.read_text(encoding="utf-8"))
    signatures = signatures_doc.get("signatures") or []
    if not isinstance(signatures, list):
        raise ValueError("signatures.json does not contain a valid signatures array")

    hashcat_modes = _parse_hashcat_mode_names(hashcat_page)
    john_formats = _parse_pentestmonkey_john_formats(john_page)

    stats.local_modes_before = len(_local_mode_set(signatures))
    stats.hashcat_modes_total = len(hashcat_modes)
    local_modes_before_set = _local_mode_set(signatures)
    stats.hashcat_modes_in_local_before = len(set(hashcat_modes) & local_modes_before_set)
    stats.hashcat_modes_missing_before = len(set(hashcat_modes) - local_modes_before_set)

    haiti_records = _build_haiti_mode_records(haiti_prototypes)
    stats.haiti_modes_total = len(haiti_records)

    stats.john_fields_enriched = _enrich_existing_john_formats(signatures, haiti_records)
    stats.added_modes = _append_missing_modes(signatures, haiti_records)
    stats.mode_catalog_entries_repaired = _repair_mode_catalog(
        signatures_doc,
        hashcat_modes,
        haiti_records,
    )
    _canonicalize_mode_catalog(signatures_doc)

    _validate_signature_shape(signatures, signatures_doc.get("modes"))

    stats.local_modes_after = len(_local_mode_set(signatures))
    local_modes_after_set = _local_mode_set(signatures)
    stats.hashcat_modes_in_local_after = len(set(hashcat_modes) & local_modes_after_set)
    stats.hashcat_modes_missing_after = len(set(hashcat_modes) - local_modes_after_set)

    local_john_formats = _collect_local_john_formats(signatures)
    stats.john_formats_total = len(john_formats)
    stats.local_john_formats_total = len(local_john_formats)
    stats.local_john_formats_not_in_pentestmonkey = len(local_john_formats - john_formats)

    signatures_doc["signatures"] = signatures
    SIGNATURES_PATH.write_text(
        json.dumps(signatures_doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "hashcat_examples": HASHCAT_EXAMPLES_URL,
            "john_formats": JOHN_FORMATS_URL,
            "haiti_prototypes": HAITI_PROTOTYPES_URL,
        },
        "stats": {
            "fetched_files": stats.fetched_files,
            "cached_files_reused": stats.cached_files_reused,
            "hashcat_modes_total": stats.hashcat_modes_total,
            "hashcat_modes_in_local_before": stats.hashcat_modes_in_local_before,
            "hashcat_modes_in_local_after": stats.hashcat_modes_in_local_after,
            "hashcat_modes_missing_before": stats.hashcat_modes_missing_before,
            "hashcat_modes_missing_after": stats.hashcat_modes_missing_after,
            "john_formats_total": stats.john_formats_total,
            "local_john_formats_total": stats.local_john_formats_total,
            "local_john_formats_not_in_pentestmonkey": stats.local_john_formats_not_in_pentestmonkey,
            "haiti_modes_total": stats.haiti_modes_total,
            "local_modes_before": stats.local_modes_before,
            "local_modes_after": stats.local_modes_after,
            "added_modes": stats.added_modes,
            "mode_catalog_entries_repaired": stats.mode_catalog_entries_repaired,
            "john_fields_enriched": stats.john_fields_enriched,
        },
    }

    (UPSTREAM_DIR / "sync-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(report["stats"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

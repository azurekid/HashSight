import json
import urllib.error
from pathlib import Path

import pytest

from scripts.upstream.sync_signatures_upstream import (
    _collect_local_john_formats,
    _load_text_source,
    _repair_mode_catalog,
    _validate_signature_shape,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNATURES_PATH = REPO_ROOT / "hashsight" / "data" / "signatures.json"


def test_validate_signature_shape_accepts_normalized_catalog_document() -> None:
    doc = json.loads(SIGNATURES_PATH.read_text(encoding="utf-8"))

    _validate_signature_shape(doc["signatures"], doc.get("modes"))


def test_validate_signature_shape_accepts_integer_candidate_references() -> None:
    _validate_signature_shape(
        [
            {
                "kind": "Prefix",
                "match": "$P$",
                "name": "phpass, phpBB3 (MD5)",
                "category": "Web Application",
                "candidates": [35700],
            }
        ],
        {"35700": {"name": "md5(sha1($pass))", "category": "Salted Digest"}},
    )


def test_validate_signature_shape_requires_resolvable_name_metadata() -> None:
    with pytest.raises(ValueError, match=r"signatures\[0\] missing/invalid name"):
        _validate_signature_shape([{"kind": "Prefix", "match": "$x$", "mode": 1}], {})


def test_validate_signature_shape_rejects_boolean_candidate_modes() -> None:
    with pytest.raises(ValueError, match=r"signatures\[0\]\.candidates\[0\] missing integer mode"):
        _validate_signature_shape(
            [
                {
                    "kind": "Prefix",
                    "match": "$x$",
                    "name": "Example",
                    "category": "Example",
                    "candidates": [{"mode": True}],
                }
            ],
            {},
        )


def test_validate_signature_shape_rejects_boolean_scalar_candidates() -> None:
    with pytest.raises(ValueError, match=r"signatures\[0\]\.candidates\[0\] missing integer mode"):
        _validate_signature_shape(
            [
                {
                    "kind": "Prefix",
                    "match": "$x$",
                    "name": "Example",
                    "category": "Example",
                    "candidates": [True],
                }
            ],
            {},
        )


def test_collect_local_john_formats_skips_integer_candidate_references() -> None:
    values = _collect_local_john_formats(
        [
            {
                "kind": "Prefix",
                "match": "$x$",
                "name": "Example",
                "category": "Example",
                "john_format": "Raw-MD5",
                "candidates": [35700, {"mode": 1000, "john_format": "Raw-SHA1"}],
            }
        ]
    )

    assert values == {"raw-md5", "raw-sha1"}


def test_load_text_source_uses_cache_when_fetch_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "john-pentestmonkey.html"
    cache_path.write_text("cached payload", encoding="utf-8")

    def fail_fetch(_: str) -> str:
        raise urllib.error.URLError("network down")

    monkeypatch.setattr("scripts.upstream.sync_signatures_upstream._fetch_text", fail_fetch)

    text, fetched = _load_text_source("https://example.test/john", cache_path)

    assert text == "cached payload"
    assert fetched is False


def test_repair_mode_catalog_restores_missing_compact_mode_metadata() -> None:
    doc = {
        "modes": {},
        "signatures": [
            {
                "kind": "Prefix",
                "match": "$1$",
                "mode": 500,
                "john_format": "md5crypt",
            }
        ],
    }

    repaired = _repair_mode_catalog(
        doc,
        {500: "md5crypt, MD5 (Unix), Cisco-IOS $1$ (MD5)"},
        {500: {"name": "MD5 Crypt", "john": "md5crypt"}},
    )

    assert repaired == 1
    assert doc["modes"]["500"] == {
        "name": "md5crypt, MD5 (Unix), Cisco-IOS $1$ (MD5)",
        "category": "Catalog Fallback",
        "john_format": "md5crypt",
    }

    _validate_signature_shape(doc["signatures"], doc["modes"])

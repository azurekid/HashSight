import json
from pathlib import Path

import pytest

from scripts.upstream.sync_signatures_upstream import _collect_local_john_formats, _validate_signature_shape


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

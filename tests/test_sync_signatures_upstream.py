import json
from pathlib import Path

import pytest

from scripts.upstream.sync_signatures_upstream import _validate_signature_shape


REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNATURES_PATH = REPO_ROOT / "hashsight" / "data" / "signatures.json"


def test_validate_signature_shape_accepts_normalized_catalog_document() -> None:
    doc = json.loads(SIGNATURES_PATH.read_text(encoding="utf-8"))

    _validate_signature_shape(doc["signatures"], doc.get("modes"))


def test_validate_signature_shape_requires_resolvable_name_metadata() -> None:
    with pytest.raises(ValueError, match=r"signatures\[0\] missing/invalid name"):
        _validate_signature_shape([{"kind": "Prefix", "match": "$x$", "mode": 1}], {})

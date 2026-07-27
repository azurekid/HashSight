"""Runtime configuration loading for HashSight CLI defaults."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_json_file(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    doc = json.loads(raw)
    if not isinstance(doc, dict):
        raise ValueError("config root must be a JSON object")
    return doc


def load_runtime_config() -> tuple[dict[str, Any], list[str]]:
    """Load merged CLI configuration and collect non-fatal warnings."""
    warnings: list[str] = []
    merged: dict[str, Any] = {}

    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_home:
        global_path = Path(xdg_home) / "hashsight" / "config.json"
    else:
        global_path = Path.home() / ".config" / "hashsight" / "config.json"

    local_config_json_path = Path.cwd() / "config.json"
    local_path = Path.cwd() / ".hashsight.json"

    paths: list[Path] = []
    if global_path.exists():
        paths.append(global_path)
    if local_config_json_path.exists():
        paths.append(local_config_json_path)
    if local_path.exists():
        paths.append(local_path)

    env_path_text = os.environ.get("HASHSIGHT_CONFIG")
    if env_path_text:
        env_path = Path(env_path_text).expanduser()
        if env_path.exists():
            paths.append(env_path)
        else:
            warnings.append(
                f"HASHSIGHT_CONFIG points to a missing file: {env_path}"
            )

    for path in paths:
        try:
            cfg = _read_json_file(path)
        except Exception as exc:
            warnings.append(f"failed to read config '{path}': {exc}")
            continue
        merged = _merge_dict(merged, cfg)

    hash_cfg = merged.get("hash")
    if isinstance(hash_cfg, dict):
        if "min_certainty" in hash_cfg and "min_candidate_certainty" not in hash_cfg:
            warnings.append(
                "config key 'hash.min_certainty' is deprecated; use "
                "'hash.min_candidate_certainty' instead"
            )
        if "min_result_certainty" in hash_cfg and "min_overall_certainty" not in hash_cfg:
            warnings.append(
                "config key 'hash.min_result_certainty' is deprecated; use "
                "'hash.min_overall_certainty' instead"
            )

    return merged, warnings

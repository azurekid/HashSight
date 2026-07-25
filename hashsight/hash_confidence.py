"""Confidence and candidate scoring presentation helpers for hash lookup."""
from __future__ import annotations

from typing import Any


def confidence_profile(result: Any) -> tuple[str, str]:
    """Return certainty percentage and rationale based on confidence + candidates."""
    confidence = result.confidence

    if confidence == "Exact":
        return "100%", "Unique signature match."

    if confidence.startswith("Exact (unverified"):
        return "90%", "Format is unique, but mode numbering may drift across releases."

    if confidence == "Ambiguous":
        candidates = result.candidates or []
        if not candidates:
            return "50%", "Shape matches multiple families, but no ranked candidates available."

        scores = [c.get("match_score", c.get("popularity", 0) * 10) for c in candidates]
        top = scores[0]
        second = scores[1] if len(scores) > 1 else 0
        denom = max(top, 10)
        relative_gap = max(0.0, (top - second) / denom)

        band = max(6, top * 0.15)
        contenders = sum(1 for s in scores if (top - s) <= band)

        certainty = 42 + (relative_gap * 43)
        certainty -= min(18, (contenders - 1) * 3)
        if getattr(result, "hint_applied", False):
            certainty += 10
        if getattr(result, "deterministic_structural_match", False):
            certainty += 20
        elif getattr(result, "structural_hint_applied", False):
            certainty += 8
        certainty = int(round(max(20, min(96, certainty))))

        basis = "Multiple valid modes share this shape; ranked by popularity."
        if getattr(result, "hint_applied", False):
            basis += " Context hint matched candidate metadata and improved ranking confidence."
        if getattr(result, "deterministic_structural_match", False):
            basis += " The hash's salt length matches a documented, mandatory constraint for this format."
        elif getattr(result, "structural_hint_applied", False):
            basis += " The hash's own salt length/format matched this candidate's known structure."
        if contenders > 1:
            basis += f" {contenders} candidates remain closely competitive."
        return f"{certainty}%", basis

    if confidence == "Unknown":
        return "0%", "No signature matched the observed format."

    if confidence == "Invalid":
        return "0%", "Input was empty after trimming whitespace."

    return "0%", "No confidence profile available."


def per_candidate_certainties(result: Any, top_certainty_pct: int) -> list[int]:
    """Scale overall certainty down per-candidate based on relative match score."""
    candidates = result.candidates or []
    if not candidates:
        return []

    scores = [max(0, c.get("match_score", c.get("popularity", 0) * 10)) for c in candidates]
    top_score = max(scores[0], 1)
    out = []
    for score in scores:
        ratio = score / top_score
        value = int(round(top_certainty_pct * ratio))
        out.append(max(3, min(top_certainty_pct, value)))
    return out


def visible_candidates(
    candidates: list[dict[str, Any]], certainties: list[int], min_certainty: int
) -> list[tuple[dict[str, Any], int]]:
    """Return only candidates that meet the minimum display certainty threshold."""
    return [
        (candidate, certainty)
        for candidate, certainty in zip(candidates, certainties)
        if certainty >= min_certainty
    ]

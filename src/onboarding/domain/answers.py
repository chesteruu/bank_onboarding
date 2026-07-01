"""Aggregation of per-step answers into a single lookup dict.

Steps are stored independently, but downstream checks read a flattened view.
Naive ``dict.update`` merging silently drops a value when two steps use the
same field name with different values (e.g. an applicant ``national_id`` and a
signatory ``national_id``). This helper keeps last-write-wins for backward
compatibility while preserving every colliding value under a step-namespaced
key (``{step_key}.{field}``) so no answer is ever lost.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def merge_step_answers(submissions: Iterable[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """Merge ``(step_key, answers)`` pairs (in submission order) into one dict.

    With no cross-step collisions the result is identical to a plain merge.
    On a genuine collision (same key, different value, different step) both the
    prior and current values are additionally exposed as ``{step}.{field}``.
    """
    flat: dict[str, Any] = {}
    origin: dict[str, str] = {}
    for step_key, answers in submissions:
        for field, value in answers.items():
            prior_step = origin.get(field)
            if field in flat and flat[field] != value and prior_step != step_key:
                flat[f"{prior_step}.{field}"] = flat[field]
                flat[f"{step_key}.{field}"] = value
            flat[field] = value
            origin[field] = step_key
    return flat

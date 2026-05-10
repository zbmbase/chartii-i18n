"""
Invalidate existing translations that violate current protected-term rules.

Used after source sync so users can re-run "missing only" AI translation without
manually deleting rows. Logic mirrors the translation pipeline: same term list
per key_path, same apply_protection word-boundary matching, same is_translation_valid checks.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List

from src.core import database as db
from src.logger import get_logger
import src.language_codes as lc
import src.protection as pt
from src.protection import apply_protection
from src.translation.validator import is_translation_valid

logger = get_logger(__name__)


def invalidate_translations_for_protected_terms(
    project_id: int,
    skip_locked: bool = True,
) -> Dict[str, Any]:
    """
    Delete translation rows that fail protected-term validation for the current source text.

    A row is invalidated only when:
    1. The project has protected terms enabled (not skip_protected_terms).
    2. The string is translatable and the row is not the source language.
    3. skip_locked is True and status is 'locked' -> row is left unchanged.
    4. At least one configured protected term applies to this key_path and appears in
       source_text under the same rules as translation (get_all_protected_terms_flat +
       apply_protection produces a non-empty placeholder map).
    5. is_translation_valid(...) is False using that protected_vars map (same validator
       as the AI translation path; variable placeholders are not re-checked here).

    Returns:
        Dict with skipped flag, deleted count, optional reasons histogram, optional error.
    """
    project = db.get_project_by_id(project_id)
    if not project:
        return {"skipped": True, "reason": "project_not_found", "deleted": 0, "reasons": {}}

    if project.get("skip_protected_terms"):
        return {
            "skipped": True,
            "reason": "protected_terms_disabled_for_project",
            "deleted": 0,
            "reasons": {},
        }

    source_lang = project.get("source_language") or ""

    with db.get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT t.string_id, t.language_code, t.translated_text, t.status,
                   s.key_path, s.source_text, s.should_translate
            FROM translations t
            INNER JOIN strings s ON s.id = t.string_id
            WHERE s.project_id = ?
            """,
            (project_id,),
        )
        rows: List[sqlite3.Row] = cursor.fetchall()

    deleted = 0
    reasons: Dict[str, int] = {}

    for row in rows:
        string_id = row["string_id"]
        language_code = row["language_code"]
        translated_text = row["translated_text"] or ""
        status = row["status"]
        key_path = row["key_path"] or ""
        source_text = row["source_text"] or ""
        should_translate = row["should_translate"]

        if not should_translate:
            continue
        if lc.languages_match(language_code, source_lang):
            continue
        if skip_locked and status == "locked":
            continue

        filtered_terms = pt.get_all_protected_terms_flat(project_id, key_path=key_path)
        if not filtered_terms:
            continue

        _, protected_vars = apply_protection(source_text, filtered_terms)
        if not protected_vars:
            # No configured term matches source with current word-boundary rules.
            continue

        ok, reason = is_translation_valid(
            source_text=source_text,
            translated_text=translated_text,
            source_lang=source_lang,
            target_lang=language_code,
            protected_vars=protected_vars,
            variable_placeholders=None,
            key_path=key_path,
            project_id=project_id,
            protected_terms_module=pt,
        )
        if ok:
            continue

        db.delete_translation(string_id, language_code)
        deleted += 1
        label = reason or "unknown"
        reasons[label] = reasons.get(label, 0) + 1

    if deleted:
        logger.info(
            "Protected-term invalidation for project %s: removed %s translation row(s); breakdown=%s",
            project_id,
            deleted,
            reasons,
        )
    else:
        logger.debug(
            "Protected-term invalidation for project %s: no rows removed",
            project_id,
        )

    return {
        "skipped": False,
        "deleted": deleted,
        "reasons": reasons,
    }

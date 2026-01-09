"""Translation management API routes."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request, g

from src.core import database as db
from src.logger import get_logger
import src.language_codes as lc
from src.ai.service import validate_ai_config, TranslationError
from src.web.tasks import (
    create_translation_job,
    get_job,
    cancel_job,
    get_latest_job,
    remove_failed_items_from_job as remove_items,
)
from src import i18n

translation_bp = Blueprint("translation", __name__)
logger = get_logger(__name__)


@translation_bp.post("/<int:project_id>/translate")
def start_translation_job(project_id: int):
    """Start an asynchronous translation job for a project."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Project %s not found when starting translation job", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    data: Dict[str, Any] = request.get_json(silent=True) or {}
    languages = data.get("languages")
    mode = data.get("mode", "missing_only")
    include_locked = data.get("include_locked", False)
    generate_files = data.get("generate_files", True)
    model_override = data.get("model")
    ai_provider = data.get("ai_provider")
    chunk_size_words = data.get("chunk_size_words")

    # Parse ai_provider if it's in "provider:model" format
    if ai_provider and isinstance(ai_provider, str) and ":" in ai_provider:
        parts = ai_provider.split(":", 1)
        provider_id = parts[0]
        model_from_provider = parts[1] if len(parts) > 1 else None
        if model_override is None and model_from_provider:
            model_override = model_from_provider
        ai_provider = provider_id

    if ai_provider == "":
        ai_provider = None

    # Validate AI configuration
    try:
        validate_ai_config(provider_override=ai_provider)
    except TranslationError as e:
        logger.warning("AI configuration validation failed: %s", e)
        error_response = {"error": str(e), "code": e.code or "ai_config_error"}
        if e.details:
            error_response["details"] = e.details
        return jsonify(error_response), 400

    # Validate chunk_size_words
    if chunk_size_words is not None:
        try:
            chunk_size_words = int(chunk_size_words)
            if chunk_size_words < 100:
                return jsonify({"error": i18n.get_translation("api.errors.chunk_size_min", lang=lang)}), 400
            if chunk_size_words > 10000:
                return jsonify({"error": i18n.get_translation("api.errors.chunk_size_max", lang=lang)}), 400
        except (ValueError, TypeError):
            return jsonify({"error": i18n.get_translation("api.errors.chunk_size_invalid", lang=lang)}), 400
    else:
        chunk_size_words = None

    # Validate mode
    if mode not in ("missing_only", "missing_and_ai", "full", "validate_only"):
        return jsonify({"error": i18n.get_translation("api.errors.invalid_mode", lang=lang, mode=mode)}), 400

    if mode == "full" and "include_locked" not in data:
        include_locked = True

    if languages is not None:
        if not isinstance(languages, list) or not all(
            isinstance(code, str) and code.strip() for code in languages
        ):
            return jsonify({"error": i18n.get_translation("api.errors.invalid_languages", lang=lang)}), 400
        normalised = []
        seen = set()
        for code in languages:
            code = code.strip()
            if not code:
                continue
            if lc.languages_match(code, project.get("source_language", ""), strict=True):
                continue
            if code not in seen:
                seen.add(code)
                normalised.append(code)
        languages = normalised

    # Save project translation settings if provided
    if chunk_size_words is not None:
        try:
            db.update_project(
                project_id=project_id,
                translation_ai_provider=ai_provider,
                translation_chunk_size_words=chunk_size_words,
            )
            logger.info(
                "Saved project translation settings: ai_provider=%s, chunk_size_words=%s",
                ai_provider,
                chunk_size_words,
            )
        except Exception as e:
            logger.exception(
                "Failed to save project translation settings for project %s: %s",
                project_id,
                e,
            )

    try:
        job = create_translation_job(
            project_id,
            languages=languages,
            mode=mode,
            include_locked=include_locked,
            generate_files=generate_files,
            model_override=model_override,
            ai_provider=ai_provider,
            chunk_size_words=chunk_size_words,
        )
        return (
            jsonify(
                {
                    "job_id": job.job_id,
                    "job": job.to_dict(),
                }
            ),
            202,
        )
    except Exception as e:
        logger.exception(
            "Failed to create translation job for project %s: %s",
            project_id,
            e,
        )
        return jsonify({"error": f"Failed to create translation job: {str(e)}"}), 500


@translation_bp.post("/<int:project_id>/translate/cancel")
def cancel_translation_job(project_id: int):
    """Cancel a running translation job."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    job_id = data.get("job_id")

    if not job_id:
        return jsonify({"error": i18n.get_translation("api.errors.job_id_required", lang=lang)}), 400

    job = get_job(job_id)
    if not job:
        return jsonify({"error": i18n.get_translation("api.errors.job_not_found_or_expired", lang=lang)}), 404

    if job.project_id != project_id:
        return jsonify({"error": i18n.get_translation("api.errors.job_does_not_belong", lang=lang)}), 404

    if cancel_job(job_id):
        return jsonify({"status": "cancellation_requested", "job_id": job_id})
    else:
        return jsonify({"error": i18n.get_translation("api.errors.job_cannot_cancel", lang=lang)}), 400


@translation_bp.get("/<int:project_id>/progress")
def get_translation_progress(project_id: int):
    """Return status for an asynchronous translation job."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    job_id = request.args.get("job_id")
    latest = request.args.get("latest", "false").lower() in ("true", "1", "yes")

    if latest:
        job = get_latest_job(project_id)
        if not job:
            return jsonify({"job_id": None, "state": None})
        job_id = job.job_id
    else:
        if not job_id:
            return jsonify({"error": i18n.get_translation("api.errors.job_id_required", lang=lang)}), 400

    job = get_job(job_id)
    if not job:
        return jsonify({"error": i18n.get_translation("api.errors.job_not_found_or_expired", lang=lang)}), 404

    if job.project_id != project_id:
        return jsonify({"error": i18n.get_translation("api.errors.job_does_not_belong", lang=lang)}), 404

    result = job.result or {}

    return jsonify(
        {
            "job_id": job.job_id,
            "state": job.state,
            "project_id": job.project_id,
            "progress": job.progress,
            "progress_history": job.progress_history,
            "result": result,
            "error": job.error,
            "failure_count": job.failure_count,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "languages": job.languages,
            "mode": job.mode,
            "include_locked": job.include_locked,
            "generate_files": job.generate_files,
        }
    )


@translation_bp.post("/<int:project_id>/progress/remove-failed-items")
def remove_failed_items_from_job(project_id: int):
    """Remove failed items from the latest job's result."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    data = request.get_json(silent=True) or {}
    failed_items_to_remove = data.get("failed_items", [])

    if not isinstance(failed_items_to_remove, list):
        return jsonify({"error": i18n.get_translation("api.errors.failed_items_must_be_list", lang=lang)}), 400

    job = get_latest_job(project_id)
    if not job:
        return jsonify({"error": i18n.get_translation("api.errors.no_job_found", lang=lang)}), 404

    success = remove_items(job.job_id, failed_items_to_remove)

    if success:
        return jsonify({
            "success": True,
            "job_id": job.job_id,
            "removed_count": len(failed_items_to_remove)
        })
    else:
        return jsonify({"error": i18n.get_translation("api.errors.failed_to_remove_failed_items", lang=lang)}), 500


@translation_bp.get("/<int:project_id>/keys")
def list_project_keys(project_id: int):
    """List keys for manual translation, optionally filtered by page."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Project %s not found when requesting keys", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    simple = request.args.get("simple", "").lower() == "true"
    if simple:
        strings = db.get_all_strings_for_project(project_id)
        key_paths = sorted([s.get("key_path", "") for s in strings if s.get("key_path")])
        return jsonify({"key_paths": key_paths})

    page_filter = request.args.get("page")
    search_term = (request.args.get("search") or "").strip().lower()

    strings = db.get_all_strings_for_project(project_id)

    filtered: List[Dict[str, Any]] = []
    for string in strings:
        key_path = string.get("key_path", "") or ""
        page_name = _derive_page_name(key_path)
        if page_filter and page_name != page_filter:
            continue

        source_text = string.get("source_text", "") or ""

        if search_term:
            haystack_key = key_path.lower()
            haystack_text = source_text.lower()
            if search_term not in haystack_key and search_term not in haystack_text:
                continue

        filtered.append(
            {
                "key_path": key_path,
                "page": page_name,
                "source_text": source_text,
                "should_translate": bool(string.get("should_translate", 1)),
                "value_type": string.get("value_type"),
            }
        )

    filtered.sort(key=lambda item: item["key_path"])

    return jsonify({"keys": filtered})


@translation_bp.get("/<int:project_id>/translations")
def get_translations_for_key(project_id: int):
    """Return translations for a specific key across all target languages."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Project %s not found when requesting translations", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    key_path = request.args.get("key")
    if not key_path:
        return jsonify({"error": i18n.get_translation("api.errors.key_parameter_required", lang=lang)}), 400

    string_record = db.get_string_by_key(project_id, key_path)
    if not string_record:
        return jsonify({"error": i18n.get_translation("api.errors.key_not_found", lang=lang)}), 404
    payload = _build_translations_payload(project, string_record)
    if payload is None:
        return jsonify({"error": i18n.get_translation("api.errors.failed_to_fetch_translations", lang=lang)}), 500
    return jsonify(payload)


@translation_bp.put("/<int:project_id>/translations")
def update_translations_for_key(project_id: int):
    """Save manual translations for a key."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Project %s not found when updating translations", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    data: Dict[str, Any] = request.get_json(silent=True) or {}
    key_path = data.get("key_path")
    entries = data.get("entries")

    if not key_path:
        return jsonify({"error": i18n.get_translation("api.errors.key_path_required", lang=lang)}), 400
    if not isinstance(entries, list) or not entries:
        return jsonify({"error": i18n.get_translation("api.errors.entries_must_be_list", lang=lang)}), 400

    string_record = db.get_string_by_key(project_id, key_path)
    if not string_record:
        return jsonify({"error": i18n.get_translation("api.errors.key_not_found", lang=lang)}), 404

    source_language = project.get("source_language")
    updates_applied = 0

    for entry in entries:
        language_code = entry.get("language_code")
        if not language_code or not isinstance(language_code, str):
            return jsonify({"error": i18n.get_translation("api.errors.each_entry_must_include_language_code", lang=lang)}), 400
        if lc.languages_match(language_code, source_language):
            return jsonify({"error": i18n.get_translation("api.errors.cannot_update_source_language", lang=lang)}), 400

        translated_text = entry.get("translated_text")
        if translated_text is None:
            translated_text = ""
        status = entry.get("status") or "needs_review"

        if not isinstance(translated_text, str):
            translated_text = str(translated_text)

        try:
            db.create_translation(
                string_id=string_record["id"],
                language_code=language_code,
                translated_text=translated_text,
                status=status,
            )
            updates_applied += 1
        except Exception as exc:
            logger.exception(
                "Failed to save translation for key %s language %s: %s",
                key_path,
                language_code,
                exc,
            )
            return jsonify({"error": i18n.get_translation("api.errors.failed_to_save_translation", lang=lang, language_code=language_code)}), 500

    payload = _build_translations_payload(project, string_record)
    if payload is None:
        return jsonify({"error": i18n.get_translation("api.errors.failed_to_fetch_updated_translations", lang=lang)}), 500

    payload["updated_count"] = updates_applied
    return jsonify(payload)


@translation_bp.delete("/<int:project_id>/translations")
def delete_translation_for_key(project_id: int):
    """Delete a specific translation for a key and language."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Project %s not found when deleting translation", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    data: Dict[str, Any] = request.get_json(silent=True) or {}
    key_path = data.get("key_path")
    language_code = data.get("language_code")

    if not key_path:
        return jsonify({"error": i18n.get_translation("api.errors.key_path_required", lang=lang)}), 400
    if not language_code:
        return jsonify({"error": i18n.get_translation("api.errors.language_code_required", lang=lang)}), 400

    string_record = db.get_string_by_key(project_id, key_path)
    if not string_record:
        return jsonify({"error": i18n.get_translation("api.errors.key_not_found", lang=lang)}), 404

    source_language = project.get("source_language")
    if lc.languages_match(language_code, source_language):
        return jsonify({"error": i18n.get_translation("api.errors.cannot_delete_source_language", lang=lang)}), 400

    try:
        deleted = db.delete_translation(
            string_id=string_record["id"],
            language_code=language_code,
        )
        if deleted:
            logger.info(
                "Deleted translation for key %s language %s in project %s",
                key_path,
                language_code,
                project_id,
            )
            return jsonify({"success": True, "deleted": True})
        else:
            return jsonify({"success": True, "deleted": False, "message": "Translation not found"})
    except Exception as exc:
        logger.exception(
            "Failed to delete translation for key %s language %s: %s",
            key_path,
            language_code,
            exc,
        )
        return jsonify({"error": f"Failed to delete translation: {str(exc)}"}), 500


@translation_bp.get("/<int:project_id>/manual-locked")
def list_locked_translations(project_id: int):
    """List all locked translations for a project."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning(
            "Project %s not found when requesting locked translations", project_id
        )
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    try:
        with db.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    s.key_path,
                    s.source_text,
                    t.language_code,
                    t.translated_text,
                    t.status,
                    t.last_translated_at
                FROM strings s
                JOIN translations t ON s.id = t.string_id
                WHERE s.project_id = ?
                  AND t.status = 'locked'
                """,
                (project_id,),
            )
            rows = cursor.fetchall()
    except Exception as exc:
        logger.exception(
            "Failed to load locked translations for project %s: %s", project_id, exc
        )
        return jsonify({"error": i18n.get_translation("api.errors.failed_to_fetch_locked_translations", lang=lang)}), 500

    items: List[Dict[str, Any]] = []
    for row in rows:
        key_path = row["key_path"] or ""
        language_code = row["language_code"]
        language_name = (
            lc.get_language_name(language_code) if language_code else None
        ) or language_code
        items.append(
            {
                "key_path": key_path,
                "page": _derive_page_name(key_path),
                "source_text": row["source_text"],
                "language_code": language_code,
                "language_name": language_name,
                "translated_text": row["translated_text"],
                "status": row["status"],
                "last_translated_at": row["last_translated_at"],
            }
        )

    items.sort(key=lambda item: (item["key_path"], item["language_code"]))

    return jsonify({"project_id": project_id, "items": items})


# Helper functions

def _derive_page_name(key_path: Optional[str]) -> str:
    """Extract the first segment of a dotted key path."""
    if not key_path:
        return "(root)"
    key_path = key_path.strip(". ")
    if not key_path:
        return "(root)"
    return key_path.split(".", 1)[0] or "(root)"


def _build_translations_payload(
    project: Dict[str, Any], string_record: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Build translations payload for a key."""
    from src.web.routes.projects import _collect_project_languages_metadata

    project_id = project.get("id")
    key_path = string_record.get("key_path")
    translations_map: Dict[str, Dict[str, Any]] = {}
    try:
        with db.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT language_code, translated_text, status, last_translated_at
                FROM translations
                WHERE string_id = ?
                """,
                (string_record["id"],),
            )
            for row in cursor.fetchall():
                translations_map[row["language_code"]] = dict(row)
    except Exception as exc:
        logger.exception(
            "Failed to load translations for key %s (project %s): %s",
            key_path,
            project_id,
            exc,
        )
        return None

    languages = _collect_project_languages_metadata(project)
    source_language = project.get("source_language")

    entries: List[Dict[str, Any]] = []
    for lang in languages:
        if lc.languages_match(lang["language_code"], source_language):
            continue

        lang_code = lang["language_code"]
        lang_entry = translations_map.get(lang_code)
        status = (lang_entry or {}).get("status") or "missing"
        entries.append(
            {
                "language_code": lang_code,
                "language_name": lang.get("language_name")
                or lc.get_language_name(lang_code)
                or lang_code,
                "translated_text": (lang_entry or {}).get("translated_text"),
                "status": status,
                "last_translated_at": (lang_entry or {}).get("last_translated_at"),
                "is_locked": status == "locked",
            }
        )

    entries.sort(key=lambda item: item["language_code"])

    return {
        "project_id": project_id,
        "key_path": key_path,
        "source_text": string_record.get("source_text"),
        "translations": entries,
    }

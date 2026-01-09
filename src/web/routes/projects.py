"""Project management API routes - CRUD and statistics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request, g

from src.core import database as db
from src.core import validation
from src.logger import get_logger
import src.language_codes as lc
from src.project.creator import ImportResult, create_project_with_source
from src.project.scanner import scan_locales_directory
from src import i18n

projects_bp = Blueprint("projects", __name__)
logger = get_logger(__name__)


@projects_bp.get("/")
def list_projects():
    """Return all projects stored in the database with additional info."""
    projects = db.get_all_projects()

    enriched_projects = []
    for project in projects:
        locales_path = Path(project.get("locales_path", ""))
        source_language = project.get("source_language", "")
        source_file_path = str(locales_path / f"{source_language}.json") if locales_path and source_language else None

        language_file_count = 0
        if locales_path and locales_path.exists():
            try:
                scan_result = scan_locales_directory(locales_path)
                language_file_count = len(scan_result.detected_files)
            except Exception as e:
                logger.warning("Error scanning locales directory for project %s: %s", project.get("id"), e)

        enriched_project = {
            **project,
            "source_file_path": source_file_path,
            "language_file_count": language_file_count
        }
        enriched_projects.append(enriched_project)

    logger.debug("Projects listed: %s", len(enriched_projects))
    return jsonify({"projects": enriched_projects})


@projects_bp.get("/<int:project_id>")
def get_project(project_id: int):
    """Return details for a single project."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Project %s not found", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    locales_path = Path(project.get("locales_path", ""))
    source_language = project.get("source_language", "")
    source_file_path = str(locales_path / f"{source_language}.json") if locales_path and source_language else None
    source_language_name = lc.get_language_name(source_language) if source_language else None

    all_strings = db.get_all_strings_for_project(project_id)
    source_key_count = len(all_strings)

    enriched_project = {
        **project,
        "source_file_path": source_file_path,
        "source_language_name": source_language_name,
        "source_key_count": source_key_count,
        "translation_ai_provider": project.get("translation_ai_provider"),
        "translation_chunk_size_words": project.get("translation_chunk_size_words"),
        "last_synced_at": project.get("last_synced_at"),
    }

    return jsonify({"project": enriched_project})


@projects_bp.get("/<int:project_id>/languages")
def get_project_languages(project_id: int):
    """Return available languages for a project, including file metadata."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Project %s not found when requesting languages", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404
    detected_languages = _collect_project_languages_metadata(project)
    source_language = project.get("source_language")
    return jsonify(
        {
            "source_language": source_language,
            "languages": detected_languages,
        }
    )


@projects_bp.get("/<int:project_id>/pages")
def get_project_pages(project_id: int):
    """Return page groupings (first segment of key path) with key counts."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Project %s not found when requesting pages", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    strings = db.get_all_strings_for_project(project_id)
    page_map: Dict[str, int] = {}

    for string in strings:
        key_path = string.get("key_path", "")
        page = _derive_page_name(key_path)
        page_map[page] = page_map.get(page, 0) + 1

    pages = [
        {"page": page, "key_count": count}
        for page, count in page_map.items()
    ]

    pages.sort(key=lambda item: (-item["key_count"], item["page"]))

    total_keys = len(strings)

    return jsonify(
        {
            "pages": pages,
            "total_keys": total_keys,
        }
    )


@projects_bp.get("/<int:project_id>/stats")
def get_project_stats(project_id: int):
    """Return translation statistics for a project."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Project %s not found when requesting stats", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    source_language = project.get("source_language")
    locales_path_str = project.get("locales_path") or ""
    locales_path = Path(locales_path_str) if locales_path_str else None

    all_strings = db.get_all_strings_for_project(project_id)
    total_keys = len(all_strings)
    translatable_keys = sum(1 for item in all_strings if item.get("should_translate", 1) == 1)

    stats_list = validation.get_all_translation_stats(project_id)
    status_counts = _get_translation_status_counts(project_id)

    languages_map: Dict[str, Dict[str, Any]] = {}
    for stats in stats_list:
        status_breakdown = status_counts.get(stats.language_code, {})
        languages_map[stats.language_code] = {
            "language_code": stats.language_code,
            "language_name": stats.language_name,
            "translated_count": stats.translated_count,
            "missing_count": stats.missing_count,
            "completion_rate": stats.completeness_percent,
            "is_complete": stats.is_complete,
            "locked_count": status_breakdown.get("locked", 0),
            "ai_translated_count": status_breakdown.get("ai_translated", 0),
            "needs_review_count": status_breakdown.get("needs_review", 0),
            "has_file": False,
            "file_path": None,
        }

    detected_files = []
    if locales_path and locales_path.exists():
        try:
            scan_result = scan_locales_directory(locales_path)
            detected_files = scan_result.detected_files
        except Exception as exc:
            logger.exception(
                "Failed scanning locales directory for stats (project %s): %s",
                project_id,
                exc,
            )

    for file_info in detected_files:
        if lc.languages_match(file_info.language_code, source_language):
            continue
        entry = languages_map.get(file_info.language_code)
        if not entry:
            missing_count = translatable_keys
            entry = {
                "language_code": file_info.language_code,
                "language_name": file_info.language_name,
                "translated_count": 0,
                "missing_count": missing_count,
                "completion_rate": 0.0,
                "is_complete": False,
                "locked_count": 0,
                "ai_translated_count": 0,
                "needs_review_count": 0,
                "has_file": True,
                "file_path": str(file_info.file_path),
            }
            languages_map[file_info.language_code] = entry
        else:
            entry["has_file"] = True
            entry["file_path"] = str(file_info.file_path)
            entry["language_name"] = entry["language_name"] or file_info.language_name

    db_languages = _get_languages_from_db(project_id)
    for lang_code in db_languages:
        if lc.languages_match(lang_code, source_language):
            continue
        if lang_code not in languages_map:
            languages_map[lang_code] = {
                "language_code": lang_code,
                "language_name": lc.get_language_name(lang_code) or lang_code,
                "translated_count": status_counts.get(lang_code, {}).get("total", 0),
                "missing_count": max(
                    0, translatable_keys - status_counts.get(lang_code, {}).get("total", 0)
                ),
                "completion_rate": 0.0,
                "is_complete": False,
                "locked_count": status_counts.get(lang_code, {}).get("locked", 0),
                "ai_translated_count": status_counts.get(lang_code, {}).get("ai_translated", 0),
                "needs_review_count": status_counts.get(lang_code, {}).get("needs_review", 0),
                "has_file": False,
                "file_path": None,
            }

    languages = list(languages_map.values())
    languages.sort(key=lambda item: item["language_code"])

    try:
        project_complete = validation.is_project_complete(project_id)
    except Exception:
        project_complete = False

    return jsonify(
        {
            "project_id": project_id,
            "source_language": source_language,
            "source_language_name": lc.get_language_name(source_language) if source_language else None,
            "total_keys": translatable_keys,
            "all_keys": total_keys,
            "languages": languages,
            "is_complete": project_complete,
        }
    )


@projects_bp.post("/")
def create_project():
    """Create a new project using an existing source language file."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    data: Dict[str, Any] = request.get_json(silent=True) or {}

    name = data.get("name")
    source_file = data.get("source_file_path")
    translation_context = data.get("translation_context", "")
    import_mode = data.get("import_mode", "retranslate")

    if translation_context and len(translation_context) > 1000:
        return jsonify({"error": i18n.get_translation("api.errors.project_summary_too_long", lang=lang)}), 400

    missing_fields = [
        field
        for field, value in [
            ("name", name),
            ("source_file_path", source_file),
        ]
        if not value
    ]

    if missing_fields:
        logger.warning("Missing required project fields: %s", missing_fields)
        return (
            jsonify(
                {
                    "error": i18n.get_translation("api.errors.config_missing", lang=lang),
                    "missing_fields": missing_fields,
                }
            ),
            400,
        )

    try:
        creation_result = create_project_with_source(
            name=name,
            source_file_path=Path(source_file),
            translation_context=translation_context,
            import_mode=import_mode,
        )
        project = db.get_project_by_id(creation_result["project_id"])
    except ValueError as err:
        logger.warning("Project creation validation failed: %s", err)
        return jsonify({"error": str(err)}), 400
    except Exception as exc:
        logger.exception("Unexpected error creating project")
        return jsonify({"error": i18n.get_translation("api.errors.failed_to_create_project", lang=lang)}), 500

    return jsonify(
        {
            "project": project,
            "import_summary": serialize_import_results(
                creation_result.get("imported_translations", [])
            ),
            "target_languages": creation_result.get("target_languages", []),
            "source_language": creation_result.get("source_language"),
            "source_key_count": creation_result.get("source_key_count"),
            "import_mode": creation_result.get("import_mode"),
        }
    ), 201


@projects_bp.put("/<int:project_id>")
def update_project(project_id: int):
    """Update a project's name, translation context, and optionally source file path."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Attempted to update missing project %s", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    data: Dict[str, Any] = request.get_json(silent=True) or {}
    name = data.get("name")
    translation_context = data.get("translation_context", "")
    source_file_path = data.get("source_file_path")

    if not name:
        return jsonify({"error": i18n.get_translation("api.errors.project_name_required", lang=lang)}), 400

    if translation_context and len(translation_context) > 1000:
        return jsonify({"error": i18n.get_translation("api.errors.project_summary_too_long", lang=lang)}), 400

    locales_path = None
    source_language = None
    if source_file_path:
        source_file = Path(source_file_path)
        if not source_file.exists():
            return jsonify({"error": i18n.get_translation("api.errors.source_file_not_exists", lang=lang)}), 400

        detected_language = lc.extract_language_from_filename(str(source_file))
        if not detected_language:
            return jsonify({"error": i18n.get_translation("api.errors.language_detection_failed", lang=lang)}), 400

        locales_path = str(source_file.parent)
        source_language = detected_language

    try:
        db.update_project(
            project_id=project_id,
            name=name,
            translation_context=translation_context,
            locales_path=locales_path,
            source_language=source_language
        )
        updated_project = db.get_project_by_id(project_id)
        logger.info("Updated project %s", project_id)
        return jsonify({"project": updated_project})
    except Exception as exc:
        logger.exception("Error updating project %s", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.failed_to_update_project", lang=lang)}), 500


@projects_bp.delete("/<int:project_id>")
def delete_project(project_id: int):
    """Delete a project."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Attempted to delete missing project %s", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    db.delete_project(project_id)
    logger.info("Deleted project %s", project_id)
    return jsonify({"status": "deleted"})


@projects_bp.post("/validate-source-path")
def validate_source_path():
    """Validate if a source file path exists and is readable."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    file_path_str = data.get("file_path", "").strip()

    if not file_path_str:
        return jsonify({"valid": False, "message": i18n.get_translation("api.errors.file_path_required", lang=lang)}), 400

    try:
        file_path = Path(file_path_str)

        if not file_path.exists():
            return jsonify(
                {"valid": False, "message": i18n.get_translation("api.errors.file_not_exists", lang=lang)}
            ), 200

        if not file_path.is_file():
            return jsonify(
                {"valid": False, "message": i18n.get_translation("api.errors.path_not_file", lang=lang)}
            ), 200

        if not file_path.suffix.lower() == ".json":
            return jsonify(
                {"valid": False, "message": i18n.get_translation("api.errors.file_must_be_json", lang=lang)}
            ), 200

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                json.load(f)
        except json.JSONDecodeError:
            return jsonify(
                {"valid": False, "message": i18n.get_translation("api.errors.file_not_valid_json", lang=lang)}
            ), 200
        except PermissionError:
            return jsonify(
                {"valid": False, "message": i18n.get_translation("api.errors.permission_denied", lang=lang)}
            ), 200

        return jsonify(
            {"valid": True, "message": i18n.get_translation("api.errors.file_path_validated", lang=lang)}
        ), 200

    except Exception as exc:
        logger.exception("Error validating source path: %s", file_path_str)
        return jsonify(
            {"valid": False, "message": i18n.get_translation("api.errors.error_validating_path", lang=lang, error=str(exc))}
        ), 200


# Helper functions

def serialize_import_results(results: List[Any]) -> List[Dict[str, Any]]:
    """Convert ImportResult dataclasses into JSON serialisable dictionaries."""
    serialised: List[Dict[str, Any]] = []
    for result in results:
        if isinstance(result, ImportResult):
            serialised.append(
                {
                    "language_code": result.language_code,
                    "imported_count": result.imported_count,
                    "missing_count": result.missing_count,
                    "total_count": result.total_count,
                    "completeness": result.completeness,
                }
            )
        elif isinstance(result, dict):
            serialised.append(
                {
                    "language_code": result.get("language_code"),
                    "imported_count": result.get("imported_count"),
                    "missing_count": result.get("missing_count"),
                    "total_count": result.get("total_count"),
                    "completeness": result.get("completeness"),
                }
            )
    return serialised


def _get_languages_from_db(project_id: int) -> List[str]:
    """Helper to retrieve all distinct language codes that have translations."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT t.language_code
                FROM translations t
                JOIN strings s ON t.string_id = s.id
                WHERE s.project_id = ?
                ORDER BY t.language_code
                """,
                (project_id,),
            )
            rows = cursor.fetchall()
            return [row[0] for row in rows if row and row[0]]
    except Exception as exc:
        logger.exception(
            "Failed retrieving languages from database for project %s: %s",
            project_id,
            exc,
        )
        return []


def _derive_page_name(key_path: Optional[str]) -> str:
    """Extract the first segment of a dotted key path."""
    if not key_path:
        return "(root)"
    key_path = key_path.strip(". ")
    if not key_path:
        return "(root)"
    return key_path.split(".", 1)[0] or "(root)"


def _get_translation_status_counts(project_id: int) -> Dict[str, Dict[str, int]]:
    """Return translation status counts grouped by language."""
    counts: Dict[str, Dict[str, int]] = {}
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    t.language_code,
                    SUM(CASE WHEN t.status = 'locked' THEN 1 ELSE 0 END) AS locked_count,
                    SUM(CASE WHEN t.status = 'ai_translated' THEN 1 ELSE 0 END) AS ai_count,
                    SUM(CASE WHEN t.status = 'needs_review' THEN 1 ELSE 0 END) AS review_count,
                    COUNT(*) AS total_count
                FROM translations t
                JOIN strings s ON t.string_id = s.id
                WHERE s.project_id = ?
                GROUP BY t.language_code
                """,
                (project_id,),
            )
            for row in cursor.fetchall():
                language_code = row[0]
                counts[language_code] = {
                    "locked": row[1] or 0,
                    "ai_translated": row[2] or 0,
                    "needs_review": row[3] or 0,
                    "total": row[4] or 0,
                }
    except Exception as exc:
        logger.exception(
            "Failed to compute translation status counts for project %s: %s",
            project_id,
            exc,
        )
    return counts


def _collect_project_languages_metadata(project: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Gather metadata about available languages for a project."""
    project_id = project.get("id")
    locales_path_str = project.get("locales_path") or ""
    locales_path = Path(locales_path_str) if locales_path_str else None
    source_language = project.get("source_language")
    detected_languages: List[Dict[str, Any]] = []

    if locales_path and locales_path.exists():
        try:
            scan_result = scan_locales_directory(locales_path)
            logger.debug(
                "Detected %s locale files for project %s",
                len(scan_result.detected_files),
                project_id,
            )
            for file_info in scan_result.detected_files:
                detected_languages.append(
                    {
                        "language_code": file_info.language_code,
                        "language_name": file_info.language_name,
                        "file_path": str(file_info.file_path),
                        "file_size": file_info.file_size,
                        "key_count": file_info.key_count,
                        "is_valid_json": file_info.is_valid_json,
                        "error": file_info.error,
                        "is_source": lc.languages_match(
                            file_info.language_code, source_language
                        ),
                    }
                )
        except Exception as exc:
            logger.exception(
                "Failed scanning locales directory for project %s: %s",
                project_id,
                exc,
            )
    else:
        logger.info(
            "Locales path missing or not found for project %s: %s",
            project_id,
            locales_path,
        )

    if source_language and not any(
        lc.languages_match(lang["language_code"], source_language) for lang in detected_languages
    ):
        detected_languages.insert(
            0,
            {
                "language_code": source_language,
                "language_name": lc.get_language_name(source_language) or source_language,
                "file_path": str(locales_path / f"{source_language}.json") if locales_path else None,
                "file_size": None,
                "key_count": None,
                "is_valid_json": None,
                "error": "Source language file not detected",
                "is_source": True,
            },
        )

    db_languages = _get_languages_from_db(project_id)
    for lang in db_languages:
        if not any(
            lc.languages_match(lang, entry["language_code"]) for entry in detected_languages
        ):
            detected_languages.append(
                {
                    "language_code": lang,
                    "language_name": lc.get_language_name(lang) or lang,
                    "file_path": None,
                    "file_size": None,
                    "key_count": None,
                    "is_valid_json": None,
                    "error": "Translations exist without a corresponding file",
                    "is_source": lc.languages_match(lang, source_language),
                }
            )

    return detected_languages

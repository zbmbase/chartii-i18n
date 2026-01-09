"""Sync and file generation API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request, g

from src.core import database as db
from src.core import sync
from src.core import validation
from src.logger import get_logger
import src.language_codes as lc
from src.project import generator as file_generator
from src import i18n

sync_bp = Blueprint("sync", __name__)
logger = get_logger(__name__)


@sync_bp.post("/<int:project_id>/sync")
def sync_project_endpoint(project_id: int):
    """Synchronise source language file with the database, with optional dry-run."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Project %s not found when requesting sync", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    dry_run_param = request.args.get("dry_run", "false").lower()
    dry_run = dry_run_param in {"1", "true", "yes"}

    locales_path = project.get("locales_path")
    source_language = project.get("source_language")
    if not locales_path or not source_language:
        return jsonify({"error": i18n.get_translation("api.errors.locales_path_missing", lang=lang)}), 400

    source_file_path = Path(locales_path) / f"{source_language}.json"
    if not source_file_path.exists():
        return jsonify(
            {
                "error": i18n.get_translation("api.errors.source_language_file_not_found", lang=lang),
                "source_file_path": str(source_file_path),
            }
        ), 400

    try:
        analysis = _build_sync_preview(project_id, source_file_path)
    except Exception as exc:
        logger.exception("Failed preparing sync analysis for project %s", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.unable_to_analyse_source_file", lang=lang, error=str(exc))}), 500

    result = analysis["result"]
    preview = analysis["preview"]

    if dry_run:
        logger.info("Returning dry-run sync preview for project %s", project_id)
        response_payload = _format_sync_response(
            project_id=project_id,
            source_file=str(source_file_path),
            result=result,
            preview=preview,
            dry_run=True,
        )
        return jsonify(response_payload)

    # Apply changes to database
    try:
        sync.apply_sync_changes(project_id, result)
        db.update_project_last_synced(project_id)
    except Exception as exc:
        logger.exception("Failed applying sync changes for project %s", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.failed_to_apply_sync_changes", lang=lang, error=str(exc))}), 500

    logger.info(
        "Sync applied for project %s (new=%s, updated=%s, deleted=%s)",
        project_id,
        len(result.new_strings),
        len(result.updated_strings),
        len(result.deleted_strings),
    )

    response_payload = _format_sync_response(
        project_id=project_id,
        source_file=str(source_file_path),
        result=result,
        preview=preview,
        dry_run=False,
    )
    return jsonify(response_payload)


@sync_bp.post("/<int:project_id>/generate")
def generate_language_files(project_id: int):
    """Generate translation files for all or selected target languages."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Project %s not found when generating files", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    locales_path = project.get("locales_path")
    if not locales_path:
        return jsonify({"error": i18n.get_translation("api.errors.locales_path_not_configured", lang=lang)}), 400

    locales_dir = Path(locales_path)
    locales_dir.mkdir(parents=True, exist_ok=True)

    data: Dict[str, Any] = request.get_json(silent=True) or {}
    languages = data.get("languages")

    if languages is not None and (
        not isinstance(languages, list)
        or not all(isinstance(code, str) and code.strip() for code in languages)
    ):
        return jsonify({"error": i18n.get_translation("api.errors.invalid_languages", lang=lang)}), 400

    source_language = project.get("source_language")

    try:
        if not languages:
            generated = file_generator.generate_all_language_files(project_id)
        else:
            generated = {}
            for raw_code in languages:
                code = raw_code.strip()
                if lc.languages_match(code, source_language):
                    return jsonify({"error": i18n.get_translation("api.errors.cannot_generate_source_language", lang=lang)}), 400
                output_path = locales_dir / f"{code}.json"
                file_generator.generate_language_file(project_id, code, output_path)
                generated[code] = output_path
    except validation.IncompleteTranslationError as exc:
        logger.warning(
            "Incomplete translations prevented generation for project %s: %s",
            project_id,
            exc,
        )
        return jsonify({"error": str(exc), "type": "incomplete_translations"}), 409
    except file_generator.FileGenerationError as exc:
        logger.exception(
            "File generation error for project %s: %s",
            project_id,
            exc,
        )
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        logger.exception(
            "Unexpected error generating files for project %s: %s",
            project_id,
            exc,
        )
        return jsonify({"error": i18n.get_translation("api.errors.failed_to_generate_files", lang=lang)}), 500

    generated_paths = {lang: str(path) for lang, path in generated.items()}
    return jsonify(
        {
            "project_id": project_id,
            "generated": generated_paths,
        }
    )


def _build_sync_preview(project_id: int, source_file_path: Path) -> Dict[str, Any]:
    """Analyse source file vs database without mutating state."""
    result = sync.SyncResult()
    source_strings = sync.load_source_file(source_file_path)

    source_data = {}
    for sort_order, (key_path, (text, value_type, should_translate)) in enumerate(source_strings.items()):
        source_data[key_path] = {
            "text": text,
            "hash": sync.calculate_hash(text),
            "value_type": value_type,
            "should_translate": should_translate,
            "sort_order": sort_order,
        }
        result.sort_order_map[key_path] = sort_order
        result.should_translate_map[key_path] = should_translate

    existing_strings = db.get_all_strings_for_project(project_id)
    existing_dict = {entry["key_path"]: entry for entry in existing_strings}
    existing_by_id = {entry["id"]: entry for entry in existing_strings}

    source_keys = set(source_data.keys())
    db_keys = set(existing_dict.keys())

    new_preview: List[Dict[str, Any]] = []
    updated_preview: List[Dict[str, Any]] = []
    deleted_preview: List[Dict[str, Any]] = []

    for key_path in sorted(source_keys - db_keys):
        info = source_data[key_path]
        result.new_strings.append(
            (
                key_path,
                info["hash"],
                info["text"],
                info["value_type"],
                info["should_translate"],
                info["sort_order"],
            )
        )
        new_preview.append(
            {
                "key": key_path,
                "text": info["text"],
            }
        )

    for key_path in sorted(db_keys - source_keys):
        string_record = existing_dict[key_path]
        result.deleted_strings.append(string_record["id"])
        deleted_preview.append(
            {
                "key": key_path,
                "string_id": string_record["id"],
            }
        )

    for key_path in sorted(source_keys & db_keys):
        info = source_data[key_path]
        db_record = existing_dict[key_path]
        if info["hash"] != db_record["source_hash"]:
            result.updated_strings.append(
                (
                    db_record["id"],
                    key_path,
                    info["hash"],
                    info["text"],
                )
            )
            updated_preview.append(
                {
                    "key": key_path,
                    "string_id": db_record["id"],
                    "old_text": db_record["source_text"],
                    "new_text": info["text"],
                }
            )
        else:
            result.unchanged_strings += 1

    preview_data = {
        "new": new_preview,
        "updated": updated_preview,
        "deleted": deleted_preview,
        "unchanged": result.unchanged_strings,
        "total_source_keys": len(source_data),
        "total_database_keys": len(existing_strings),
        "existing_by_id": existing_by_id,
    }

    return {
        "result": result,
        "preview": preview_data,
    }


def _format_sync_response(
    project_id: int,
    source_file: str,
    result: sync.SyncResult,
    preview: Dict[str, Any],
    dry_run: bool,
) -> Dict[str, Any]:
    """Format sync response for API."""
    summary = {
        "new_keys": len(result.new_strings),
        "updated_keys": len(result.updated_strings),
        "deleted_keys": len(result.deleted_strings),
        "unchanged_keys": preview.get("unchanged", 0),
        "total_source_keys": preview.get("total_source_keys"),
        "total_database_keys": preview.get("total_database_keys"),
    }

    samples: List[Dict[str, Any]] = []

    for item in preview.get("new", [])[:5]:
        samples.append(
            {
                "type": "new",
                "key": item["key"],
                "preview": item.get("text"),
            }
        )

    for item in preview.get("updated", [])[:5]:
        samples.append(
            {
                "type": "updated",
                "key": item["key"],
                "preview": item.get("new_text"),
            }
        )

    for item in preview.get("deleted", [])[:5]:
        samples.append(
            {
                "type": "deleted",
                "key": item["key"],
                "preview": preview["existing_by_id"]
                .get(item["string_id"], {})
                .get("source_text"),
            }
        )

    return {
        "project_id": project_id,
        "source_file_path": source_file,
        "dry_run": dry_run,
        "summary": summary,
        "samples": samples,
    }

"""Protected terms management API routes."""

from __future__ import annotations

from typing import Any, Dict, List

from flask import Blueprint, jsonify, request, g

from src.core import database as db
from src.core.schema import ensure_all_schemas
from src.logger import get_logger
from src.protection import (
    DEFAULT_CATEGORY_METADATA,
    analyze_protected_terms as analyze_terms,
)
from src import i18n

protected_bp = Blueprint("protected", __name__)
logger = get_logger(__name__)


@protected_bp.get("/<int:project_id>/protected-terms")
def list_protected_terms(project_id: int):
    """Return current protected terms and settings."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    # Ensure database schema integrity before querying
    try:
        ensure_all_schemas()
    except Exception as e:
        logger.warning(f"Failed to ensure database schema integrity: {e}")

    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Project %s not found when listing protected terms", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    try:
        terms = db.get_protected_terms(project_id)
    except Exception as exc:
        logger.exception("Failed to get protected terms for project %s: %s", project_id, exc)
        return jsonify({"error": "Failed to retrieve protected terms", "details": str(exc)}), 500

    enabled = not bool(project.get("skip_protected_terms"))
    analyzed = bool(project.get("protected_terms_analyzed"))

    formatted_terms = [
        {
            "id": term.get("id"),
            "term": term.get("term"),
            "category": term.get("category"),
            "is_regex": bool(term.get("is_regex")),
            "key_scopes": term.get("key_scopes", []),
            "created_at": term.get("created_at"),
            "updated_at": term.get("updated_at"),
        }
        for term in terms
    ]

    return jsonify(
        {
            "project_id": project_id,
            "enabled": enabled,
            "analyzed": analyzed,
            "terms": formatted_terms,
            "categories": DEFAULT_CATEGORY_METADATA,
        }
    )


@protected_bp.post("/<int:project_id>/protected-terms/add")
def add_protected_terms(project_id: int):
    """Add new protected terms without replacing existing ones."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Project %s not found when adding protected terms", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    data: Dict[str, Any] = request.get_json(silent=True) or {}
    terms = data.get("terms")
    if not isinstance(terms, list):
        return jsonify({"error": i18n.get_translation("api.errors.terms_must_be_list", lang=lang)}), 400

    # Validate key_paths exist in project
    all_strings = db.get_all_strings_for_project(project_id)
    valid_key_paths = {s.get("key_path") for s in all_strings if s.get("key_path")}

    normalised_terms: List[Dict[str, Any]] = []
    for item in terms:
        if not isinstance(item, dict):
            return jsonify({"error": i18n.get_translation("api.errors.each_term_must_be_object", lang=lang)}), 400
        term_value = (item.get("term") or "").strip()
        if not term_value:
            continue

        # Validate and normalize key_scopes
        key_scopes = item.get("key_scopes", [])
        if not isinstance(key_scopes, list):
            return jsonify({"error": i18n.get_translation("api.errors.key_scopes_must_be_array", lang=lang)}), 400

        # Filter out invalid key_paths
        valid_scopes = [kp for kp in key_scopes if kp in valid_key_paths]

        normalised_terms.append(
            {
                "term": term_value,
                "category": item.get("category") or None,
                "is_regex": bool(item.get("is_regex", False)),
                "key_scopes": valid_scopes if valid_scopes else [],
            }
        )

    try:
        added_count, merged_count = db.add_protected_terms_batch(project_id, normalised_terms)
    except Exception as exc:
        logger.exception(
            "Failed to add protected terms for project %s: %s", project_id, exc
        )
        error_msg = str(exc) if exc else "Failed to add protected terms"
        return jsonify({"error": error_msg, "details": str(exc)}), 500

    # Return updated list
    refreshed_terms = db.get_protected_terms(project_id)
    formatted_terms = [
        {
            "id": term.get("id"),
            "term": term.get("term"),
            "category": term.get("category"),
            "is_regex": bool(term.get("is_regex")),
            "key_scopes": term.get("key_scopes", []),
            "created_at": term.get("created_at"),
            "updated_at": term.get("updated_at"),
        }
        for term in refreshed_terms
    ]

    return jsonify(
        {
            "project_id": project_id,
            "terms": formatted_terms,
            "enabled": not bool(project.get("skip_protected_terms")),
            "added_count": added_count,
            "merged_count": merged_count,
        }
    )


@protected_bp.post("/<int:project_id>/protected-terms/analyze")
def analyze_protected_terms(project_id: int):
    """Analyze project source strings and suggest protected terms."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Project %s not found when analyzing protected terms", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    data: Dict[str, Any] = request.get_json(silent=True) or {}
    provider = data.get("provider")
    model_override = data.get("model_override")

    suggestions_by_category = analyze_terms(
        project_id,
        provider=provider,
        model_override=model_override
    )
    all_strings = db.get_all_strings_for_project(project_id)
    source_texts = [s.get("source_text", "") for s in all_strings]

    suggestions: List[Dict[str, Any]] = []
    for category, terms in suggestions_by_category.items():
        for term in terms:
            count = sum(text.count(term) for text in source_texts)
            suggestions.append(
                {
                    "term": term,
                    "category": category,
                    "match_count": count,
                }
            )

    db.update_project_protected_terms_status(project_id, analyzed=True)

    return jsonify(
        {
            "project_id": project_id,
            "suggestions": suggestions,
        }
    )


@protected_bp.put("/<int:project_id>/protected-terms/settings")
def update_protected_term_settings(project_id: int):
    """Update protected term settings (enable/disable)."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Project %s not found when updating protected term settings", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    data: Dict[str, Any] = request.get_json(silent=True) or {}
    enabled = data.get("enabled")
    if enabled is None or not isinstance(enabled, bool):
        return jsonify({"error": i18n.get_translation("api.errors.enabled_boolean_required", lang=lang)}), 400

    try:
        db.update_project_protected_terms_status(project_id, skip=not enabled)
    except Exception as exc:
        logger.exception(
            "Failed to update protected term settings for project %s: %s",
            project_id,
            exc,
        )
        return jsonify({"error": i18n.get_translation("api.errors.failed_to_update_settings", lang=lang)}), 500

    return jsonify({"project_id": project_id, "enabled": enabled})


@protected_bp.delete("/<int:project_id>/protected-terms/<int:term_id>")
def delete_protected_term(project_id: int, term_id: int):
    """Delete a single protected term."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Project %s not found when deleting protected term", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    # Verify the term belongs to this project
    term = db.get_protected_term_by_id(term_id)
    if not term:
        return jsonify({"error": i18n.get_translation("api.errors.protected_term_not_found", lang=lang)}), 404

    if term.get("project_id") != project_id:
        logger.warning(
            "Term %s does not belong to project %s", term_id, project_id
        )
        return jsonify({"error": i18n.get_translation("api.errors.protected_term_not_found", lang=lang)}), 404

    try:
        db.delete_protected_term(term_id)
        return jsonify({"success": True, "term_id": term_id})
    except Exception as exc:
        logger.exception(
            "Failed to delete protected term %s for project %s: %s",
            term_id,
            project_id,
            exc,
        )
        return jsonify({"error": i18n.get_translation("api.errors.failed_to_delete_term", lang=lang)}), 500


@protected_bp.put("/<int:project_id>/protected-terms/<int:term_id>")
def update_protected_term(project_id: int, term_id: int):
    """Update a single protected term."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    project = db.get_project_by_id(project_id)
    if not project:
        logger.warning("Project %s not found when updating protected term", project_id)
        return jsonify({"error": i18n.get_translation("api.errors.project_not_found", lang=lang)}), 404

    # Verify the term belongs to this project
    term = db.get_protected_term_by_id(term_id)
    if not term:
        return jsonify({"error": i18n.get_translation("api.errors.protected_term_not_found", lang=lang)}), 404

    if term.get("project_id") != project_id:
        logger.warning(
            "Term %s does not belong to project %s", term_id, project_id
        )
        return jsonify({"error": i18n.get_translation("api.errors.protected_term_not_found", lang=lang)}), 404

    data: Dict[str, Any] = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": i18n.get_translation("api.errors.request_body_required", lang=lang)}), 400

    # Validate key_paths exist in project
    all_strings = db.get_all_strings_for_project(project_id)
    valid_key_paths = {s.get("key_path") for s in all_strings if s.get("key_path")}

    # Validate and normalize key_scopes
    key_scopes = data.get("key_scopes", [])
    if not isinstance(key_scopes, list):
        return jsonify({"error": i18n.get_translation("api.errors.key_scopes_must_be_array", lang=lang)}), 400

    # Filter out invalid key_paths
    valid_scopes = [kp for kp in key_scopes if kp in valid_key_paths]

    term_value = (data.get("term") or "").strip()
    if not term_value:
        return jsonify({"error": i18n.get_translation("api.errors.term_field_required", lang=lang)}), 400

    update_data = {
        "term": term_value,
        "category": data.get("category"),
        "is_regex": bool(data.get("is_regex", False)),
        "key_scopes": valid_scopes if valid_scopes else [],
    }

    try:
        db.update_protected_term(term_id, update_data)

        # Return updated term
        updated_term = db.get_protected_term_by_id(term_id)
        formatted_term = {
            "id": updated_term.get("id"),
            "term": updated_term.get("term"),
            "category": updated_term.get("category"),
            "is_regex": bool(updated_term.get("is_regex")),
            "key_scopes": updated_term.get("key_scopes", []),
            "created_at": updated_term.get("created_at"),
        }
        return jsonify({"success": True, "term": formatted_term})
    except Exception as exc:
        logger.exception(
            "Failed to update protected term %s for project %s: %s",
            term_id,
            project_id,
            exc,
        )
        return jsonify({"error": i18n.get_translation("api.errors.failed_to_update_term", lang=lang)}), 500

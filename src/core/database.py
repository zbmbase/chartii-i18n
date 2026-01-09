"""
Database CRUD Operations Module

This module handles all database CRUD operations for:
- Projects
- Strings
- Translations
- Protected Terms
- App Config

For schema management and migrations, see core/schema.py
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

DB_FILE = Path(__file__).parent.parent / "translations.db"


def get_connection():
    """Get a database connection."""
    return sqlite3.connect(DB_FILE)


# ============================================================
# Project CRUD Operations
# ============================================================

def create_project(name: str, locales_path: str,
                   source_language: str, translation_context: str = "") -> int:
    """Create a new project."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO projects (name, locales_path, source_language, translation_context)
            VALUES (?, ?, ?, ?)
        """, (name, locales_path, source_language, translation_context))
        conn.commit()
        return cursor.lastrowid


def get_all_projects() -> List[Dict[str, Any]]:
    """Get all projects."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects")
        return [dict(row) for row in cursor.fetchall()]


def get_project_by_id(project_id: int) -> Optional[Dict[str, Any]]:
    """Get a project by ID."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_project(project_id: int, name: str = None, locales_path: str = None,
                   source_language: str = None, translation_context: str = None,
                   translation_ai_provider: str = None, translation_chunk_size_words: int = None):
    """Update a project."""
    with get_connection() as conn:
        cursor = conn.cursor()
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if locales_path is not None:
            updates.append("locales_path = ?")
            params.append(locales_path)
        if source_language is not None:
            updates.append("source_language = ?")
            params.append(source_language)
        if translation_context is not None:
            updates.append("translation_context = ?")
            params.append(translation_context)
        if translation_ai_provider is not None:
            updates.append("translation_ai_provider = ?")
            params.append(translation_ai_provider)
        if translation_chunk_size_words is not None:
            updates.append("translation_chunk_size_words = ?")
            params.append(translation_chunk_size_words)

        if updates:
            params.append(project_id)
            cursor.execute(f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()


def delete_project(project_id: int):
    """Delete a project and all its associated data."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Delete translations first (foreign key constraint)
        cursor.execute("""
            DELETE FROM translations
            WHERE string_id IN (
                SELECT id FROM strings WHERE project_id = ?
            )
        """, (project_id,))
        # Delete strings
        cursor.execute("DELETE FROM strings WHERE project_id = ?", (project_id,))
        # Delete project
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()


def update_project_last_synced(project_id: int):
    """Update the last_synced_at timestamp for a project."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE projects
            SET last_synced_at = datetime('now')
            WHERE id = ?
        """, (project_id,))
        conn.commit()


def update_project_protected_terms_status(project_id: int, analyzed: bool = None, skip: bool = None):
    """Update project's protected terms analysis status."""
    with get_connection() as conn:
        cursor = conn.cursor()
        updates = []
        params = []

        if analyzed is not None:
            updates.append("protected_terms_analyzed = ?")
            params.append(1 if analyzed else 0)

        if skip is not None:
            updates.append("skip_protected_terms = ?")
            params.append(1 if skip else 0)

        if updates:
            params.append(project_id)
            cursor.execute(f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()


# ============================================================
# String CRUD Operations
# ============================================================

def create_string(project_id: int, key_path: str, source_hash: str, source_text: str,
                  should_translate: bool = True, value_type: str = 'string') -> int:
    """Create a new string entry."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO strings (project_id, key_path, source_hash, source_text, should_translate, value_type)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (project_id, key_path, source_hash, source_text, 1 if should_translate else 0, value_type))
        conn.commit()
        return cursor.lastrowid


def get_string_by_key(project_id: int, key_path: str) -> Optional[Dict[str, Any]]:
    """Get a string by project ID and key path."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM strings
            WHERE project_id = ? AND key_path = ?
        """, (project_id, key_path))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_strings_for_project(project_id: int) -> List[Dict[str, Any]]:
    """Get all strings for a project, ordered by source file order (sort_order), fallback to id."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM strings WHERE project_id = ? ORDER BY sort_order, id", (project_id,))
        return [dict(row) for row in cursor.fetchall()]


def update_string(string_id: int, source_hash: str, source_text: str):
    """Update a string's hash and text."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE strings
            SET source_hash = ?, source_text = ?
            WHERE id = ?
        """, (source_hash, source_text, string_id))
        conn.commit()


def delete_string(string_id: int):
    """Delete a string and its translations."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Delete translations first
        cursor.execute("DELETE FROM translations WHERE string_id = ?", (string_id,))
        # Delete string
        cursor.execute("DELETE FROM strings WHERE id = ?", (string_id,))
        conn.commit()


# ============================================================
# Translation CRUD Operations
# ============================================================

def create_translation(string_id: int, language_code: str, translated_text: str,
                       status: str = "ai_translated") -> None:
    """Create or update a translation."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Delete existing translation first to ensure no duplicates
        cursor.execute("""
            DELETE FROM translations
            WHERE string_id = ? AND language_code = ?
        """, (string_id, language_code))
        # Insert new translation
        cursor.execute("""
            INSERT INTO translations
            (string_id, language_code, translated_text, last_translated_at, status)
            VALUES (?, ?, ?, ?, ?)
        """, (string_id, language_code, translated_text, datetime.now(), status))
        conn.commit()


def get_translation(string_id: int, language_code: str) -> Optional[Dict[str, Any]]:
    """Get a specific translation."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM translations
            WHERE string_id = ? AND language_code = ?
        """, (string_id, language_code))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_translations_for_language(project_id: int, language_code: str) -> List[Dict[str, Any]]:
    """Get all translations for a specific language in a project, ordered by source file order."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.key_path, t.translated_text, t.status
            FROM translations t
            JOIN strings s ON t.string_id = s.id
            WHERE s.project_id = ? AND t.language_code = ?
            ORDER BY s.sort_order, s.id
        """, (project_id, language_code))
        return [dict(row) for row in cursor.fetchall()]


def update_translation_status(string_id: int, language_code: str, status: str):
    """Update translation status."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE translations
            SET status = ?
            WHERE string_id = ? AND language_code = ?
        """, (status, string_id, language_code))
        conn.commit()


def delete_translation(string_id: int, language_code: str) -> bool:
    """Delete a specific translation."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM translations
            WHERE string_id = ? AND language_code = ?
        """, (string_id, language_code))
        conn.commit()
        return cursor.rowcount > 0


def get_translations_by_status(project_id: int, status: str) -> List[Dict[str, Any]]:
    """Get all translations with a specific status."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.*, t.language_code, t.translated_text, t.status
            FROM translations t
            JOIN strings s ON t.string_id = s.id
            WHERE s.project_id = ? AND t.status = ?
        """, (project_id, status))
        return [dict(row) for row in cursor.fetchall()]


# ============================================================
# Protected Terms CRUD Operations
# ============================================================

def create_protected_term(project_id: int, term: str, category: str = None, is_regex: bool = False) -> int:
    """Create a new protected term."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO protected_terms (project_id, term, category, is_regex, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (project_id, term, category, 1 if is_regex else 0))
        conn.commit()
        return cursor.lastrowid


def get_protected_terms(project_id: int, category: str = None) -> List[Dict[str, Any]]:
    """Get all protected terms for a project, optionally filtered by category."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if category:
            cursor.execute("""
                SELECT * FROM protected_terms
                WHERE project_id = ? AND category = ?
                ORDER BY COALESCE(updated_at, created_at, id) DESC, id DESC
            """, (project_id, category))
        else:
            cursor.execute("""
                SELECT * FROM protected_terms
                WHERE project_id = ?
                ORDER BY COALESCE(updated_at, created_at, id) DESC, id DESC
            """, (project_id,))

        results = []
        for row in cursor.fetchall():
            term_dict = dict(row)
            # Parse key_scopes JSON if present
            if term_dict.get('key_scopes'):
                try:
                    term_dict['key_scopes'] = json.loads(term_dict['key_scopes'])
                except (json.JSONDecodeError, TypeError):
                    term_dict['key_scopes'] = []
            else:
                term_dict['key_scopes'] = []
            results.append(term_dict)
        return results


def get_protected_term_by_id(term_id: int) -> Dict[str, Any]:
    """Get a single protected term by ID."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM protected_terms WHERE id = ?", (term_id,))
        row = cursor.fetchone()
        if not row:
            return None
        term_dict = dict(row)
        # Parse key_scopes JSON if present
        if term_dict.get('key_scopes'):
            try:
                term_dict['key_scopes'] = json.loads(term_dict['key_scopes'])
            except (json.JSONDecodeError, TypeError):
                term_dict['key_scopes'] = []
        else:
            term_dict['key_scopes'] = []
        return term_dict


def update_protected_term(term_id: int, term_data: Dict[str, Any]):
    """Update a single protected term."""
    from src.logger import get_logger
    logger = get_logger(__name__)

    with get_connection() as conn:
        cursor = conn.cursor()

        # Validate required fields
        term_value = (term_data.get('term') or '').strip()
        if not term_value:
            raise ValueError("term field is required and cannot be empty")

        key_scopes = term_data.get('key_scopes', [])
        if not isinstance(key_scopes, list):
            logger.warning(f"Invalid key_scopes type for term '{term_value}', converting to list")
            key_scopes = []

        key_scopes_json = json.dumps(key_scopes, ensure_ascii=False) if key_scopes else None

        cursor.execute("""
            UPDATE protected_terms
            SET term = ?, category = ?, is_regex = ?, key_scopes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            term_value,
            term_data.get('category'),
            1 if term_data.get('is_regex', False) else 0,
            key_scopes_json,
            term_id
        ))
        conn.commit()


def delete_protected_term(term_id: int):
    """Delete a protected term."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM protected_terms WHERE id = ?", (term_id,))
        conn.commit()


def delete_all_protected_terms(project_id: int):
    """Delete all protected terms for a project."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM protected_terms WHERE project_id = ?", (project_id,))
        conn.commit()


def add_protected_terms_batch(project_id: int, terms: List[Dict[str, Any]]):
    """
    Add multiple protected terms at once, merging key_scopes for existing terms.
    If a term with the same (term, category) already exists, merge key_scopes instead of skipping.

    Args:
        project_id: The project ID
        terms: List of dicts with 'term', 'category', 'key_scopes' keys

    Returns:
        Tuple of (added_count, merged_count) where:
        - added_count: Number of new terms added
        - merged_count: Number of existing terms that had key_scopes merged
    """
    from src.logger import get_logger
    logger = get_logger(__name__)

    with get_connection() as conn:
        cursor = conn.cursor()

        # Get existing terms with their key_scopes for merging
        cursor.execute("""
            SELECT id, term, category, key_scopes FROM protected_terms
            WHERE project_id = ?
        """, (project_id,))
        existing_terms_map = {}
        for row in cursor.fetchall():
            term_id, term_value, category, key_scopes_json = row
            key = (term_value, category)
            existing_key_scopes = []
            if key_scopes_json:
                try:
                    existing_key_scopes = json.loads(key_scopes_json)
                    if not isinstance(existing_key_scopes, list):
                        existing_key_scopes = []
                except (json.JSONDecodeError, TypeError):
                    existing_key_scopes = []
            existing_terms_map[key] = {
                'id': term_id,
                'key_scopes': existing_key_scopes
            }

        # Process terms: add new ones or merge key_scopes for existing ones
        added_count = 0
        merged_count = 0
        for term_data in terms:
            try:
                # Validate required fields
                if 'term' not in term_data or not term_data.get('term'):
                    logger.warning(f"Skipping term with missing or empty 'term' field: {term_data}")
                    continue

                term_value = term_data['term'].strip()
                category = term_data.get('category')
                key = (term_value, category)

                # Get new key_scopes
                new_key_scopes = term_data.get('key_scopes', [])
                if not isinstance(new_key_scopes, list):
                    logger.warning(f"Invalid key_scopes type for term '{term_value}', converting to list")
                    new_key_scopes = []

                # Check if term already exists
                if key in existing_terms_map:
                    # Merge key_scopes: combine existing and new, remove duplicates
                    existing_key_scopes = existing_terms_map[key]['key_scopes']
                    merged_key_scopes = list(set(existing_key_scopes + new_key_scopes))

                    # Only update if there are new key_scopes to add
                    if set(merged_key_scopes) != set(existing_key_scopes):
                        merged_key_scopes_json = json.dumps(merged_key_scopes, ensure_ascii=False) if merged_key_scopes else None
                        cursor.execute("""
                            UPDATE protected_terms
                            SET key_scopes = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (merged_key_scopes_json, existing_terms_map[key]['id']))
                        merged_count += 1
                        # Update the map for potential subsequent merges in the same batch
                        existing_terms_map[key]['key_scopes'] = merged_key_scopes
                        logger.debug(f"Merged key_scopes for term '{term_value}' (category: {category}): {existing_key_scopes} + {new_key_scopes} = {merged_key_scopes}")
                    else:
                        logger.debug(f"Term '{term_value}' (category: {category}) already has all key_scopes, no update needed")
                else:
                    # Insert new term
                    key_scopes_json = json.dumps(new_key_scopes, ensure_ascii=False) if new_key_scopes else None
                    cursor.execute("""
                        INSERT INTO protected_terms (project_id, term, category, is_regex, key_scopes, updated_at)
                        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (
                        project_id,
                        term_value,
                        category,
                        1 if term_data.get('is_regex', False) else 0,
                        key_scopes_json
                    ))
                    added_count += 1
                    # Add to map for potential subsequent merges in the same batch
                    existing_terms_map[key] = {
                        'id': cursor.lastrowid,
                        'key_scopes': new_key_scopes
                    }
            except Exception as e:
                logger.exception(f"Error processing term {term_data}: {e}")
                raise

        conn.commit()
        logger.info(f"Added {added_count} new protected terms, merged key_scopes for {merged_count} existing terms")
        return added_count, merged_count


# ============================================================
# App Config CRUD Operations
# ============================================================

def get_app_config(key: str) -> Optional[str]:
    """Get a configuration value by key."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_config WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else None


def set_app_config(key: str, value: str):
    """Set a configuration value."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Ensure app_config table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            INSERT OR REPLACE INTO app_config (key, value, updated_at)
            VALUES (?, ?, ?)
        """, (key, value, datetime.now()))
        conn.commit()


def get_all_app_config() -> Dict[str, str]:
    """Get all configuration values."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM app_config")
        return {row[0]: row[1] for row in cursor.fetchall()}

"""
Source file synchronization module.

This module handles syncing source language files with the database:
- Detecting new, updated, and deleted strings
- Applying changes to the database
- Rebuilding JSON files from translations
"""

import json
import hashlib
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple, Any

from src.core import database as db
from src.logger import get_logger

logger = get_logger(__name__)


class SyncResult:
    """Container for synchronization results."""

    def __init__(self):
        self.new_strings: List[Tuple[str, str, str]] = []  # (key_path, hash, text, ...)
        self.updated_strings: List[Tuple[int, str, str, str]] = []  # (string_id, key_path, new_hash, new_text)
        self.deleted_strings: List[int] = []  # string_ids to delete
        self.unchanged_strings: int = 0
        self.sort_order_map: Dict[str, int] = {}  # {key_path: sort_order} for all keys
        self.should_translate_map: Dict[str, bool] = {}  # {key_path: should_translate} for all keys

    def __str__(self):
        return (f"SyncResult(new={len(self.new_strings)}, "
                f"updated={len(self.updated_strings)}, "
                f"deleted={len(self.deleted_strings)}, "
                f"unchanged={self.unchanged_strings})")


def calculate_hash(text: str) -> str:
    """Calculate SHA-256 hash of a text string."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def flatten_json(data: Dict[str, Any], parent_key: str = '', separator: str = '.') -> Dict[str, Tuple[str, str, bool]]:
    """
    Flatten a nested JSON structure into a flat dictionary.

    Args:
        data: The nested dictionary to flatten
        parent_key: The parent key for recursion
        separator: The separator to use between keys

    Returns:
        A flat dictionary with composite keys mapping to (value, value_type, should_translate):
        - value: String representation of the value
        - value_type: 'string', 'number', 'boolean', 'null'
        - should_translate: Whether this value should be translated

    Example:
        Input: {"title": "Welcome", "port": 3000, "enabled": true}
        Output: {
            "title": ("Welcome", "string", True),
            "port": ("3000", "number", False),
            "enabled": ("true", "boolean", False)
        }
    """
    items = []

    for key, value in data.items():
        new_key = f"{parent_key}{separator}{key}" if parent_key else key

        if isinstance(value, dict):
            # Recursively flatten nested dictionaries
            items.extend(flatten_json(value, new_key, separator).items())
        elif isinstance(value, list):
            # Handle arrays by adding indexed keys
            for i, item in enumerate(value):
                if isinstance(item, str):
                    # Array of strings: translatable only if non-empty
                    should_translate = bool(item.strip())
                    items.append((f"{new_key}{separator}{i}", (item, 'string', should_translate)))
                elif isinstance(item, dict):
                    # Array of objects: recursively flatten
                    items.extend(flatten_json(item, f"{new_key}{separator}{i}", separator).items())
                elif isinstance(item, bool):
                    # Boolean: not translatable
                    items.append((f"{new_key}{separator}{i}", (str(item).lower(), 'boolean', False)))
                elif isinstance(item, (int, float)):
                    # Number: not translatable
                    items.append((f"{new_key}{separator}{i}", (str(item), 'number', False)))
                elif item is None:
                    # Null: not translatable
                    items.append((f"{new_key}{separator}{i}", ('null', 'null', False)))
                else:
                    # Unknown type: convert to string, don't translate
                    items.append((f"{new_key}{separator}{i}", (str(item), 'unknown', False)))
                    logger.debug(f"Unknown type in array at '{new_key}.{i}': {type(item)}")
        elif isinstance(value, str):
            # String values: translatable only if non-empty
            # Empty strings don't need translation (they stay empty in all languages)
            should_translate = bool(value.strip())
            items.append((new_key, (value, 'string', should_translate)))
        elif isinstance(value, bool):
            # Boolean: not translatable (check bool before int, as bool is subclass of int)
            items.append((new_key, (str(value).lower(), 'boolean', False)))
        elif isinstance(value, (int, float)):
            # Number: not translatable
            items.append((new_key, (str(value), 'number', False)))
        elif value is None:
            # Null: not translatable
            items.append((new_key, ('null', 'null', False)))
        else:
            # Unknown type: convert to string, don't translate
            items.append((new_key, (str(value), 'unknown', False)))
            logger.debug(f"Unknown type at '{new_key}': {type(value)}")

    return dict(items)


def load_source_file(file_path: Path) -> Dict[str, Tuple[str, str, bool]]:
    """
    Load and flatten a source language JSON file.

    Args:
        file_path: Path to the JSON file

    Returns:
        Flattened dictionary of key_path: (text, value_type, should_translate)

    Raises:
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the file is not valid JSON
    """
    logger.info(f"Loading source file: {file_path}")

    if not file_path.exists():
        raise FileNotFoundError(f"Source file not found: {file_path}")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Source file must contain a JSON object, got {type(data)}")

        flattened = flatten_json(data)
        logger.info(f"Loaded {len(flattened)} items from source file")

        # Count translatable strings
        translatable_count = sum(1 for _, _, should_translate in flattened.values() if should_translate)
        logger.info(f"  {translatable_count} translatable strings, {len(flattened) - translatable_count} non-translatable values")

        return flattened

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON file: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to load source file: {e}")
        raise


def sync_project(project_id: int, source_file_path: Path) -> SyncResult:
    """
    Synchronize a project's source file with the database.

    This function:
    1. Loads and flattens the source file
    2. Compares it with database records
    3. Identifies new, updated, and deleted strings
    4. Updates the database accordingly

    Args:
        project_id: The project ID to synchronize
        source_file_path: Path to the source language JSON file

    Returns:
        SyncResult object containing sync statistics
    """
    logger.info(f"Starting sync for project {project_id}")
    result = SyncResult()

    # Load source file
    try:
        source_strings = load_source_file(source_file_path)
    except Exception as e:
        logger.error(f"Failed to load source file: {e}")
        raise

    # Calculate hashes for all source items and track sort order
    # Python 3.7+ dicts preserve insertion order, so enumerate gives us the source file order
    source_data = {}
    for sort_order, (key_path, (text, value_type, should_translate)) in enumerate(source_strings.items()):
        source_data[key_path] = {
            'text': text,
            'hash': calculate_hash(text),
            'value_type': value_type,
            'should_translate': should_translate,
            'sort_order': sort_order
        }
        result.sort_order_map[key_path] = sort_order
        result.should_translate_map[key_path] = should_translate

    # Get existing strings from database
    existing_strings = db.get_all_strings_for_project(project_id)
    existing_dict = {s['key_path']: s for s in existing_strings}

    logger.debug(f"Source file has {len(source_data)} strings")
    logger.debug(f"Database has {len(existing_dict)} strings")

    # Compare and categorize
    source_keys = set(source_data.keys())
    db_keys = set(existing_dict.keys())

    # Find new strings (in source but not in database)
    new_keys = source_keys - db_keys
    for key_path in new_keys:
        data = source_data[key_path]
        result.new_strings.append((
            key_path, data['hash'], data['text'],
            data['value_type'], data['should_translate'], data['sort_order']
        ))

    # Find deleted strings (in database but not in source)
    deleted_keys = db_keys - source_keys
    for key_path in deleted_keys:
        result.deleted_strings.append(existing_dict[key_path]['id'])

    # Find potentially updated strings (in both)
    common_keys = source_keys & db_keys
    for key_path in common_keys:
        source_data_item = source_data[key_path]
        db_string = existing_dict[key_path]

        if source_data_item['hash'] != db_string['source_hash']:
            # String has been updated
            result.updated_strings.append((
                db_string['id'],
                key_path,
                source_data_item['hash'],
                source_data_item['text']
            ))
        else:
            # String is unchanged
            result.unchanged_strings += 1

    logger.info(f"Sync analysis complete: {result}")

    # Apply changes to database
    apply_sync_changes(project_id, result)

    return result


def apply_sync_changes(project_id: int, result: SyncResult):
    """
    Apply synchronization changes to the database.

    This function executes all database operations within a transaction
    to ensure data consistency.

    Args:
        project_id: The project ID
        result: SyncResult containing the changes to apply
    """
    logger.info("Applying sync changes to database...")

    conn = db.get_connection()
    cursor = conn.cursor()

    try:
        # Add new strings
        for item in result.new_strings:
            if len(item) == 6:
                # Current format: (key_path, hash, text, value_type, should_translate, sort_order)
                key_path, source_hash, source_text, value_type, should_translate, sort_order = item
                cursor.execute("""
                    INSERT INTO strings (project_id, key_path, source_hash, source_text, should_translate, value_type, sort_order)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (project_id, key_path, source_hash, source_text, 1 if should_translate else 0, value_type, sort_order))
            elif len(item) == 5:
                # Legacy format: (key_path, hash, text, value_type, should_translate)
                key_path, source_hash, source_text, value_type, should_translate = item
                cursor.execute("""
                    INSERT INTO strings (project_id, key_path, source_hash, source_text, should_translate, value_type)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (project_id, key_path, source_hash, source_text, 1 if should_translate else 0, value_type))
            else:
                # Old format for compatibility: (key_path, hash, text)
                key_path, source_hash, source_text = item
                cursor.execute("""
                    INSERT INTO strings (project_id, key_path, source_hash, source_text)
                    VALUES (?, ?, ?, ?)
                """, (project_id, key_path, source_hash, source_text))

            string_id = cursor.lastrowid
            logger.debug(f"Created new string: {key_path} (id={string_id})")

        # Update changed strings
        for string_id, key_path, new_hash, new_text in result.updated_strings:
            cursor.execute("""
                UPDATE strings
                SET source_hash = ?, source_text = ?
                WHERE id = ?
            """, (new_hash, new_text, string_id))
            logger.debug(f"Updated string: {key_path} (id={string_id})")

            # Update translation statuses
            # If translation is locked, mark as needs_review
            # If translation is ai_translated, it will be re-translated
            cursor.execute("""
                UPDATE translations
                SET status = CASE
                    WHEN status = 'locked' THEN 'needs_review'
                    ELSE status
                END
                WHERE string_id = ?
            """, (string_id,))

        # Delete removed strings (delete translations first due to foreign key)
        for string_id in result.deleted_strings:
            cursor.execute("DELETE FROM translations WHERE string_id = ?", (string_id,))
            cursor.execute("DELETE FROM strings WHERE id = ?", (string_id,))
            logger.debug(f"Deleted string (id={string_id})")

        # Update sort_order and should_translate for all existing strings based on source file
        # This ensures that even unchanged strings get their sort_order and should_translate updated
        # when the source file order or content changes
        if result.sort_order_map:
            sort_order_updated = 0
            should_translate_updated = 0
            for key_path, sort_order in result.sort_order_map.items():
                # Get should_translate value (default to True for backward compatibility)
                should_translate = result.should_translate_map.get(key_path, True)
                cursor.execute("""
                    UPDATE strings
                    SET sort_order = ?, should_translate = ?
                    WHERE project_id = ? AND key_path = ?
                """, (sort_order, 1 if should_translate else 0, project_id, key_path))
                if cursor.rowcount > 0:
                    sort_order_updated += 1
            logger.info(f"Updated sort_order and should_translate for {sort_order_updated} strings")

        conn.commit()
        logger.info("Sync changes committed successfully")

    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to apply sync changes: {e}")
        raise
    finally:
        conn.close()


def get_translation_tasks(project_id: int) -> List[Dict[str, Any]]:
    """
    Get all strings that need translation.

    Returns strings that:
    - Are new (no translations exist)
    - Have translations with status 'ai_translated' and source has changed

    Args:
        project_id: The project ID

    Returns:
        List of dictionaries containing string info
    """
    logger.info(f"Getting translation tasks for project {project_id}")

    conn = db.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all strings that either:
    # 1. Have no translations at all
    # 2. Have translations that need updating (ai_translated status with changed source)
    query = """
        SELECT DISTINCT s.id, s.key_path, s.source_text, s.project_id
        FROM strings s
        LEFT JOIN translations t ON s.id = t.string_id
        WHERE s.project_id = ?
        AND (
            t.string_id IS NULL
            OR (t.status = 'ai_translated')
        )
        GROUP BY s.id
    """

    cursor.execute(query, (project_id,))
    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()

    logger.info(f"Found {len(tasks)} strings needing translation")
    return tasks


def rebuild_json(project_id: int, language_code: str) -> Dict[str, Any]:
    """
    Rebuild a nested JSON structure from flat translations.

    Uses the source language JSON file as a template to preserve exact key order.
    Replaces translatable string values with translations.

    Args:
        project_id: The project ID
        language_code: The target language code

    Returns:
        Nested dictionary ready to be written as JSON (with same key order as source)

    Raises:
        ValueError: If translations are incomplete or source file not found
    """
    logger.info(f"Rebuilding JSON for project {project_id}, language {language_code}")

    # Get project info to find source file
    project = db.get_project_by_id(project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")

    source_file = Path(project['locales_path']) / f"{project['source_language']}.json"
    if not source_file.exists():
        raise ValueError(f"Source file not found: {source_file}")

    # Load source JSON to get exact structure and key order
    with open(source_file, 'r', encoding='utf-8') as f:
        source_json = json.load(f)

    # Get all translations and build lookup dict
    translations = db.get_all_translations_for_language(project_id, language_code)
    trans_dict = {t['key_path']: t['translated_text'] for t in translations}

    logger.info(f"Rebuilding with {len(translations)} translations using source structure")

    def copy_with_translations(source: Any, prefix: str = '') -> Any:
        """Recursively copy source structure, replacing string values with translations."""
        if isinstance(source, dict):
            result = {}
            for key, value in source.items():
                key_path = f"{prefix}.{key}" if prefix else key
                result[key] = copy_with_translations(value, key_path)
            return result
        elif isinstance(source, list):
            return [copy_with_translations(item, f"{prefix}.{i}") for i, item in enumerate(source)]
        elif isinstance(source, str):
            # This is a translatable string value - get translation if exists
            if prefix in trans_dict:
                return trans_dict[prefix]
            else:
                # Fallback to source if no translation (shouldn't happen for complete translations)
                logger.warning(f"No translation found for key: {prefix}")
                return source
        else:
            # Non-translatable (number, bool, null) - keep original value
            return source

    result = copy_with_translations(source_json)
    logger.info(f"Rebuilt JSON with source structure preserved")
    return result

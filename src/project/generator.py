"""
Language file generator module.

This module handles generating language files from database translations:
- Atomic file writing
- Validation before generation
- File structure rebuilding
"""

import json
import tempfile
from pathlib import Path
from typing import List, Dict, Any

from src.core import database as db
from src.core import sync
from src.core import validation
from src.logger import get_logger

logger = get_logger(__name__)


class FileGenerationError(Exception):
    """File generation error."""
    pass


def generate_language_file(project_id: int, language_code: str, output_path: Path) -> bool:
    """
    Generate a language file from database translations.

    This function:
    1. Validates that ALL translations are complete (no fallback)
    2. Retrieves all translations for the specified language
    3. Rebuilds the nested JSON structure
    4. Writes to file using atomic write (temp file + rename)

    Args:
        project_id: The project ID
        language_code: The language code (e.g., 'zh', 'es')
        output_path: Path where the file should be written

    Returns:
        True if successful

    Raises:
        FileGenerationError: If generation fails
        validation.IncompleteTranslationError: If translations are incomplete
    """
    logger.info(f"Generating language file for project {project_id}, language {language_code}")
    logger.info(f"Output path: {output_path}")

    try:
        # Get project info
        project = db.get_project_by_id(project_id)
        if not project:
            raise FileGenerationError(f"Project {project_id} not found")

        # Validate completeness (no fallback allowed)
        try:
            validation.require_complete_translations(project_id, language_code)
        except validation.IncompleteTranslationError as e:
            logger.error(f"Translation incomplete: {e}")
            raise  # Re-raise to caller

        # Rebuild JSON from database (guaranteed to be complete)
        json_data = sync.rebuild_json(project_id, language_code)

        # Write to file atomically
        _atomic_write_json(output_path, json_data)

        logger.info(f"Successfully generated language file: {output_path}")
        return True

    except validation.IncompleteTranslationError:
        # Re-raise validation errors as-is
        raise

    except Exception as e:
        error_msg = f"Failed to generate language file: {e}"
        logger.error(error_msg)
        raise FileGenerationError(error_msg)


def generate_all_language_files(project_id: int) -> Dict[str, Path]:
    """
    Generate all language files for a project.

    This function:
    1. Validates that ALL translations are complete for ALL languages
    2. Gets the project's locales directory
    3. Finds all languages that have translations
    4. Generates a file for each language

    Args:
        project_id: The project ID

    Returns:
        Dict mapping language_code to generated file path

    Raises:
        FileGenerationError: If any file generation fails
        validation.IncompleteTranslationError: If any translation is incomplete
    """
    logger.info(f"Generating all language files for project {project_id}")

    # Get project info
    project = db.get_project_by_id(project_id)
    if not project:
        raise FileGenerationError(f"Project {project_id} not found")

    locales_path = Path(project['locales_path'])
    source_language = project['source_language']

    # Ensure locales directory exists
    if not locales_path.exists():
        logger.warning(f"Locales directory does not exist, creating: {locales_path}")
        locales_path.mkdir(parents=True, exist_ok=True)

    # Get all languages that have translations
    languages = _get_available_languages(project_id)

    if not languages:
        logger.warning("No languages with translations found")
        return {}

    # Filter out source language
    target_languages = [lang for lang in languages if lang != source_language]

    if not target_languages:
        logger.warning("No target languages found")
        return {}

    logger.info(f"Found {len(target_languages)} target languages: {target_languages}")

    # Validate all languages first (fail fast)
    incomplete_languages = validation.validate_all_translations(project_id)
    if incomplete_languages:
        error_messages = []
        for lang_code, missing in incomplete_languages.items():
            error_messages.append(f"{lang_code}: missing {len(missing)} translations")

        raise validation.IncompleteTranslationError(
            f"Cannot generate files - incomplete translations:\n" + "\n".join(error_messages),
            missing_keys=[m['key_path'] for missing in incomplete_languages.values() for m in missing]
        )

    # All translations complete, generate files
    results = {}
    errors = []

    for language_code in target_languages:
        output_path = locales_path / f"{language_code}.json"

        try:
            generate_language_file(project_id, language_code, output_path)
            results[language_code] = output_path
            logger.info(f"✓ Generated {language_code}.json")

        except Exception as e:
            error_msg = f"Failed to generate {language_code}.json: {e}"
            logger.error(f"✗ {error_msg}")
            errors.append(error_msg)

    # If any failures, raise exception with details
    if errors:
        raise FileGenerationError(
            f"Failed to generate {len(errors)} file(s):\n" + "\n".join(errors)
        )

    success_count = len(results)
    logger.info(f"Generated {success_count} language files")

    return results


def _get_available_languages(project_id: int) -> List[str]:
    """
    Get all languages that have translations for a project.

    Args:
        project_id: The project ID

    Returns:
        List of language codes
    """
    conn = db.get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT t.language_code
        FROM translations t
        JOIN strings s ON t.string_id = s.id
        WHERE s.project_id = ?
        ORDER BY t.language_code
    """, (project_id,))

    languages = [row[0] for row in cursor.fetchall()]
    conn.close()

    return languages


def _atomic_write_json(file_path: Path, data: Dict[str, Any]):
    """
    Write JSON to file atomically.

    This function writes to a temporary file first, then renames it to the
    target path. This ensures that:
    1. The file is never in a partially-written state
    2. If the write fails, the original file is unchanged
    3. The write is atomic on most file systems

    Args:
        file_path: Target file path
        data: Data to write as JSON

    Raises:
        FileGenerationError: If write fails
    """
    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Create temp file in the same directory (for atomic rename)
    temp_fd, temp_path = tempfile.mkstemp(
        dir=file_path.parent,
        prefix=f".{file_path.stem}_",
        suffix=".json.tmp"
    )

    temp_path = Path(temp_path)

    try:
        # Write to temp file
        with open(temp_fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')  # Add trailing newline

        # Atomic rename
        temp_path.replace(file_path)
        logger.debug(f"Atomic write successful: {file_path}")

    except Exception as e:
        # Clean up temp file on error
        if temp_path.exists():
            temp_path.unlink()
        raise FileGenerationError(f"Atomic write failed: {e}")


def validate_language_file(project_id: int, language_code: str, file_path: Path) -> Dict[str, Any]:
    """
    Validate a language file against the database.

    Checks:
    1. File exists and is valid JSON
    2. Has same structure as database
    3. No missing or extra keys

    Args:
        project_id: The project ID
        language_code: The language code
        file_path: Path to the file to validate

    Returns:
        Dict with validation results
    """
    logger.info(f"Validating language file: {file_path}")

    result = {
        'valid': True,
        'errors': [],
        'warnings': []
    }

    # Check file exists
    if not file_path.exists():
        result['valid'] = False
        result['errors'].append(f"File does not exist: {file_path}")
        return result

    # Check file is valid JSON
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            file_data = json.load(f)
    except json.JSONDecodeError as e:
        result['valid'] = False
        result['errors'].append(f"Invalid JSON: {e}")
        return result

    # Flatten the file data
    file_flat = sync.flatten_json(file_data)

    # Get expected translations from database
    db_translations = db.get_all_translations_for_language(project_id, language_code)
    db_flat = {t['key_path']: t['translated_text'] for t in db_translations}

    # Check for missing keys
    file_keys = set(file_flat.keys())
    db_keys = set(db_flat.keys())

    missing_keys = db_keys - file_keys
    extra_keys = file_keys - db_keys

    if missing_keys:
        result['valid'] = False
        result['errors'].append(f"Missing keys: {missing_keys}")

    if extra_keys:
        result['warnings'].append(f"Extra keys (not in database): {extra_keys}")

    # Check for value mismatches
    mismatches = []
    for key in file_keys & db_keys:
        if file_flat[key] != db_flat[key]:
            mismatches.append(key)

    if mismatches:
        result['warnings'].append(f"Values differ from database: {mismatches}")

    if result['valid']:
        logger.info("✓ File validation passed")
    else:
        logger.warning(f"✗ File validation failed: {result['errors']}")

    return result


def preview_language_file(project_id: int, language_code: str) -> str:
    """
    Preview what a language file would look like without writing it.

    Args:
        project_id: The project ID
        language_code: The language code

    Returns:
        JSON string of the file content
    """
    json_data = sync.rebuild_json(project_id, language_code)
    return json.dumps(json_data, ensure_ascii=False, indent=2)

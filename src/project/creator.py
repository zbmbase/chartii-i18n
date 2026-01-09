"""
Project creation with existing translation import.

This module handles the complete project creation workflow:
1. Create project in database
2. Sync source file
3. Import existing translations (optional)
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

from src.core import database as db
from src.core import sync
from src.project import scanner as project_scanner
import src.language_codes as lc
from src.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ImportResult:
    """Result of importing existing translations."""
    language_code: str
    imported_count: int
    missing_count: int
    total_count: int

    @property
    def completeness(self) -> float:
        """Completion percentage."""
        if self.total_count == 0:
            return 0.0
        return (self.imported_count / self.total_count) * 100


def create_project_with_source(
    name: str,
    source_file_path: Path,
    translation_context: str = "",
    import_mode: str = "retranslate"  # 'retranslate' or 'merge'
) -> Dict:
    """
    Create a new project and import source file.

    Args:
        name: Project display name
        source_file_path: Path to source language file
        translation_context: Context for AI translation
        import_mode: How to handle existing translation files in the directory:
                     - 'retranslate': Ignore existing files, AI will translate everything (default)
                     - 'merge': Import existing translations, only translate missing keys

    Returns:
        Dict with:
        - project_id: Created project ID
        - source_language: Detected source language
        - source_key_count: Number of keys in source
        - imported_translations: List of ImportResult
        - target_languages: List of detected target language codes
    """
    logger.info(f"Creating project: {name}")

    # Validate source file
    if not source_file_path.exists():
        raise ValueError(f"Source file not found: {source_file_path}")

    # Detect source language from filename
    source_language = lc.extract_language_from_filename(str(source_file_path))
    if not source_language:
        raise ValueError(
            f"Cannot detect language from filename: {source_file_path.name}\n"
            f"Filename should be in format: <language_code>.json (e.g., en.json)"
        )

    logger.info(f"Detected source language: {source_language}")

    # Get locales path
    locales_path = source_file_path.parent

    # Create project in database
    project_id = db.create_project(
        name=name,
        locales_path=str(locales_path),
        source_language=source_language,
        translation_context=translation_context
    )

    logger.info(f"Created project with ID: {project_id}")

    # Sync source file
    sync_result = sync.sync_project(project_id, source_file_path)
    source_key_count = len(sync_result.new_strings)

    logger.info(f"Synced source file: {source_key_count} keys")

    # Handle existing translations
    scan_result, imported_translations = _import_existing_translations(
        project_id,
        locales_path,
        source_language,
        import_mode
    )

    # Get list of target languages (all detected languages except source)
    target_languages = [
        f.language_code for f in scan_result.detected_files
        if f.language_code != source_language
    ]

    return {
        'project_id': project_id,
        'source_language': source_language,
        'source_key_count': source_key_count,
        'target_languages': target_languages,
        'imported_translations': imported_translations,
        'import_mode': import_mode
    }


def _import_existing_translations(
    project_id: int,
    locales_path: Path,
    source_language: str,
    import_mode: str
) -> tuple:
    """
    Import existing translation files.

    Args:
        project_id: Project ID
        locales_path: Directory containing language files
        source_language: Source language code (to skip)
        import_mode: 'merge' or 'retranslate'

    Returns:
        (scan_result, imported_translations) tuple
    """
    logger.info(f"Scanning for existing translations in {locales_path}")

    # Scan directory
    scan_result = project_scanner.scan_locales_directory(locales_path)

    # Get total string count
    all_strings = db.get_all_strings_for_project(project_id)
    total_count = len(all_strings)

    imported = []

    for file_info in scan_result.detected_files:
        # Skip source language
        if file_info.language_code == source_language:
            logger.debug(f"Skipping source language: {file_info.language_code}")
            continue

        # Skip invalid files
        if not file_info.is_valid_json:
            logger.warning(f"Skipping invalid file: {file_info.file_path}")
            continue

        if import_mode == 'merge':
            # Import existing translations
            result = _import_translation_file(
                project_id,
                file_info.file_path,
                file_info.language_code,
                all_strings
            )
            imported.append(result)

            logger.info(
                f"Imported {result.language_code}: "
                f"{result.imported_count}/{result.total_count} keys "
                f"({result.completeness:.1f}%)"
            )

        elif import_mode == 'retranslate':
            # Don't import, just log
            logger.info(
                f"Skipping {file_info.language_code} (will retranslate)"
            )

    return scan_result, imported


def _import_translation_file(
    project_id: int,
    file_path: Path,
    language_code: str,
    all_strings: List[Dict]
) -> ImportResult:
    """
    Import a single translation file.

    Args:
        project_id: Project ID
        file_path: Path to translation file
        language_code: Language code
        all_strings: All strings in the project (from database)

    Returns:
        ImportResult with import statistics
    """
    logger.debug(f"Importing {file_path}")

    # Load translation file
    with open(file_path, 'r', encoding='utf-8') as f:
        translation_data = json.load(f)

    # Flatten - returns dict of key_path: (text, value_type, should_translate)
    flat_translations = sync.flatten_json(translation_data)

    imported_count = 0

    for string_record in all_strings:
        key_path = string_record['key_path']

        # Check if translation exists in file
        if key_path in flat_translations:
            # flat_translations[key_path] is a tuple: (text, value_type, should_translate)
            translated_text = flat_translations[key_path][0]

            # Store in database - mark as locked (manual translation)
            # so they appear in the manual translations tab
            db.create_translation(
                string_id=string_record['id'],
                language_code=language_code,
                translated_text=translated_text,
                status='locked'
            )
            imported_count += 1

    missing_count = len(all_strings) - imported_count

    return ImportResult(
        language_code=language_code,
        imported_count=imported_count,
        missing_count=missing_count,
        total_count=len(all_strings)
    )



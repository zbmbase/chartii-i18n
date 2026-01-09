"""
Translation completeness validation.

This module ensures that all translations are complete before generating files.
No fallback mechanism - files must be 100% translated.
"""

from typing import List, Dict, Any
from dataclasses import dataclass

from src.core import database as db
from src.logger import get_logger

logger = get_logger(__name__)


class IncompleteTranslationError(Exception):
    """Raised when trying to generate files with incomplete translations."""

    def __init__(self, message: str, missing_keys: List[str] = None):
        super().__init__(message)
        self.missing_keys = missing_keys or []


@dataclass
class TranslationStats:
    """Statistics for a language's translation status."""
    language_code: str
    language_name: str
    total_strings: int
    translated_count: int
    missing_count: int
    completeness_percent: float
    is_complete: bool

    def __str__(self):
        status = "Complete" if self.is_complete else f"Missing {self.missing_count} entries"
        return (f"{self.language_name} ({self.language_code}): "
                f"{self.translated_count}/{self.total_strings} "
                f"({self.completeness_percent:.1f}%) {status}")


def validate_translation_completeness(project_id: int, language_code: str) -> List[Dict[str, Any]]:
    """
    Validate that all source strings have translations for the given language.

    Args:
        project_id: The project ID
        language_code: The language code to validate

    Returns:
        List of missing string records (empty list if complete)
        Each record contains: id, key_path, source_text

    Example:
        >>> missing = validate_translation_completeness(1, 'zh')
        >>> if missing:
        ...     print(f"Missing {len(missing)} translations")
        ...     for record in missing:
        ...         print(f"  - {record['key_path']}: {record['source_text']}")
    """
    logger.info(f"Validating translation completeness for project {project_id}, language {language_code}")

    # Get all source strings (only those that should be translated)
    all_strings = db.get_all_strings_for_project(project_id)
    translatable_strings = [s for s in all_strings if s.get('should_translate', 1) == 1]

    logger.debug(f"Found {len(all_strings)} total strings, {len(translatable_strings)} translatable")

    # Get existing translations
    translations = db.get_all_translations_for_language(project_id, language_code)

    # Create set of translated key paths
    translated_keys = {t['key_path'] for t in translations}

    # Find missing translations (only for translatable strings)
    missing = []
    for string_record in translatable_strings:
        if string_record['key_path'] not in translated_keys:
            missing.append({
                'id': string_record['id'],
                'key_path': string_record['key_path'],
                'source_text': string_record['source_text']
            })

    if missing:
        logger.warning(f"Found {len(missing)} missing translations for {language_code}")
    else:
        logger.info(f"Translation for {language_code} is complete")

    return missing


def get_translation_stats(project_id: int, language_code: str) -> TranslationStats:
    """
    Get translation statistics for a language.

    Args:
        project_id: The project ID
        language_code: The language code

    Returns:
        TranslationStats object with detailed statistics

    Example:
        >>> stats = get_translation_stats(1, 'zh')
        >>> print(f"Progress: {stats.completeness_percent:.1f}%")
        >>> if not stats.is_complete:
        ...     print(f"Need to translate {stats.missing_count} more items")
    """
    from src import language_codes as lc

    # Get all source strings (only translatable ones)
    all_strings = db.get_all_strings_for_project(project_id)
    translatable_strings = [s for s in all_strings if s.get('should_translate', 1) == 1]
    total_strings = len(translatable_strings)

    # Build set of translatable key paths
    translatable_keys = {s['key_path'] for s in translatable_strings}

    # Get existing translations and deduplicate by key_path
    # This ensures consistent counting even if duplicate records exist in DB
    translations = db.get_all_translations_for_language(project_id, language_code)
    translated_keys = {t['key_path'] for t in translations}

    # Only count translations for keys that should be translated
    valid_translated_keys = translated_keys & translatable_keys
    translated_count = len(valid_translated_keys)

    # Calculate stats
    missing_count = total_strings - translated_count
    completeness_percent = (translated_count / total_strings * 100) if total_strings > 0 else 0
    is_complete = missing_count == 0

    language_name = lc.get_language_name(language_code)

    return TranslationStats(
        language_code=language_code,
        language_name=language_name,
        total_strings=total_strings,
        translated_count=translated_count,
        missing_count=missing_count,
        completeness_percent=completeness_percent,
        is_complete=is_complete
    )


def get_all_translation_stats(project_id: int) -> List[TranslationStats]:
    """
    Get translation statistics for all target languages in a project.

    Args:
        project_id: The project ID

    Returns:
        List of TranslationStats for each target language

    Example:
        >>> all_stats = get_all_translation_stats(1)
        >>> for stats in all_stats:
        ...     print(stats)
        Chinese (zh): 179/188 (95.2%) Missing 9 entries
        Hindi (hi): 142/188 (75.5%) Missing 46 entries
    """
    # Get project info
    project = db.get_project_by_id(project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")

    source_language = project['source_language']

    # Get all languages that have at least one translation
    conn = db.get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT t.language_code
        FROM translations t
        JOIN strings s ON t.string_id = s.id
        WHERE s.project_id = ?
        ORDER BY t.language_code
    """, (project_id,))

    language_codes = [row[0] for row in cursor.fetchall()]
    conn.close()

    # Filter out source language
    target_languages = [code for code in language_codes if code != source_language]

    # Get stats for each target language
    stats_list = []
    for language_code in target_languages:
        stats = get_translation_stats(project_id, language_code)
        stats_list.append(stats)

    return stats_list


def validate_all_translations(project_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """
    Validate translations for all target languages.

    Args:
        project_id: The project ID

    Returns:
        Dict mapping language_code to list of missing translations
        Empty dict means all languages are complete

    Example:
        >>> missing_by_lang = validate_all_translations(1)
        >>> if missing_by_lang:
        ...     print("Incomplete translations:")
        ...     for lang, missing in missing_by_lang.items():
        ...         print(f"  {lang}: {len(missing)} missing")
        ... else:
        ...     print("All translations complete!")
    """
    stats_list = get_all_translation_stats(project_id)

    result = {}
    for stats in stats_list:
        if not stats.is_complete:
            missing = validate_translation_completeness(project_id, stats.language_code)
            result[stats.language_code] = missing

    return result


def require_complete_translations(project_id: int, language_code: str):
    """
    Validate that translations are complete, raise exception if not.

    This is a strict validation function used before generating files.

    Args:
        project_id: The project ID
        language_code: The language code

    Raises:
        IncompleteTranslationError: If any translations are missing

    Example:
        >>> try:
        ...     require_complete_translations(1, 'zh')
        ... except IncompleteTranslationError as e:
        ...     print(f"Cannot generate: {e}")
        ...     print(f"Missing keys: {e.missing_keys}")
    """
    missing = validate_translation_completeness(project_id, language_code)

    if missing:
        missing_keys = [m['key_path'] for m in missing]
        raise IncompleteTranslationError(
            f"Cannot generate file for {language_code}: "
            f"missing {len(missing)} translations. "
            f"Please complete translation first.",
            missing_keys=missing_keys
        )


def is_project_complete(project_id: int) -> bool:
    """
    Check if all target languages have complete translations.

    Args:
        project_id: The project ID

    Returns:
        True if all target languages are 100% translated

    Example:
        >>> if is_project_complete(1):
        ...     print("Ready to generate all files!")
        ... else:
        ...     print("Still need more translations")
    """
    stats_list = get_all_translation_stats(project_id)

    if not stats_list:
        # No target languages yet
        return False

    return all(stats.is_complete for stats in stats_list)

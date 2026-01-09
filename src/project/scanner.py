"""
Project scanner for detecting language files in a locales directory.

This module provides utilities to:
- Scan a directory for language files
- Detect file completeness and size
- Recommend source language
- Validate project structure
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import src.language_codes as lc
from src.core import sync
from src.logger import get_logger

logger = get_logger(__name__)


@dataclass
class LanguageFileInfo:
    """Information about a detected language file."""
    language_code: str
    language_name: str
    file_path: Path
    file_size: int  # bytes
    key_count: int  # number of translation keys
    is_valid_json: bool
    error: Optional[str] = None


@dataclass
class ProjectScanResult:
    """Result of scanning a locales directory."""
    locales_path: Path
    detected_files: List[LanguageFileInfo]
    recommended_source: Optional[str] = None  # language code
    recommendation_reason: str = ""


def scan_locales_directory(locales_path: Path) -> ProjectScanResult:
    """
    Scan a locales directory and detect all language files.

    Args:
        locales_path: Path to locales directory

    Returns:
        ProjectScanResult with detected files and recommendation
    """
    logger.info(f"Scanning locales directory: {locales_path}")

    if not locales_path.exists():
        logger.warning(f"Directory does not exist: {locales_path}")
        return ProjectScanResult(
            locales_path=locales_path,
            detected_files=[],
            recommendation_reason="Directory does not exist"
        )

    if not locales_path.is_dir():
        logger.error(f"Path is not a directory: {locales_path}")
        return ProjectScanResult(
            locales_path=locales_path,
            detected_files=[],
            recommendation_reason="Path is not a directory"
        )

    # Find all .json files
    json_files = list(locales_path.glob("*.json"))
    logger.info(f"Found {len(json_files)} JSON files")

    detected_files = []

    for file_path in json_files:
        file_info = _analyze_language_file(file_path)
        if file_info:
            detected_files.append(file_info)

    # Sort by key count (descending) - most complete files first
    detected_files.sort(key=lambda f: f.key_count, reverse=True)

    # Recommend source language
    recommended_source, reason = _recommend_source_language(detected_files)

    result = ProjectScanResult(
        locales_path=locales_path,
        detected_files=detected_files,
        recommended_source=recommended_source,
        recommendation_reason=reason
    )

    logger.info(f"Scan complete: {len(detected_files)} files, recommended: {recommended_source}")
    return result


def _analyze_language_file(file_path: Path) -> Optional[LanguageFileInfo]:
    """
    Analyze a single language file.

    Args:
        file_path: Path to JSON file

    Returns:
        LanguageFileInfo or None if not a valid language file
    """
    # Extract language code from filename
    language_code = lc.extract_language_from_filename(str(file_path))

    if not language_code:
        logger.debug(f"Skipping file (not a valid language file): {file_path.name}")
        return None

    language_name = lc.get_language_name(language_code) or language_code

    # Get file size
    file_size = file_path.stat().st_size

    # Try to load and count keys
    is_valid_json = True
    key_count = 0
    error = None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Count keys (flatten the JSON)
        flat_data = sync.flatten_json(data)
        key_count = len(flat_data)

    except json.JSONDecodeError as e:
        is_valid_json = False
        error = f"Invalid JSON: {e}"
        logger.warning(f"File {file_path.name} has invalid JSON: {e}")

    except Exception as e:
        is_valid_json = False
        error = f"Error reading file: {e}"
        logger.error(f"Error analyzing file {file_path.name}: {e}")

    return LanguageFileInfo(
        language_code=language_code,
        language_name=language_name,
        file_path=file_path,
        file_size=file_size,
        key_count=key_count,
        is_valid_json=is_valid_json,
        error=error
    )


def _recommend_source_language(files: List[LanguageFileInfo]) -> tuple[Optional[str], str]:
    """
    Recommend which language should be the source.

    Heuristics:
    1. If 'en' exists, recommend it (most common)
    2. Otherwise, recommend the file with most keys
    3. If tie, recommend first alphabetically

    Args:
        files: List of detected language files

    Returns:
        (language_code, reason) tuple
    """
    if not files:
        return None, "No language files found"

    # Filter out invalid files
    valid_files = [f for f in files if f.is_valid_json and f.key_count > 0]

    if not valid_files:
        return None, "No valid language files found"

    # Rule 1: Prefer English if available
    en_files = [f for f in valid_files if f.language_code == 'en']
    if en_files:
        return en_files[0].language_code, "English (en) is the most common source language"

    # Rule 2: Prefer en-US, en-GB if no plain 'en'
    en_variant_files = [f for f in valid_files if f.language_code.startswith('en-')]
    if en_variant_files:
        recommended = en_variant_files[0]
        return recommended.language_code, f"{recommended.language_name} is an English variant"

    # Rule 3: File with most keys (already sorted)
    most_complete = valid_files[0]

    # Check if there are other files with similar key counts
    similar_files = [
        f for f in valid_files
        if abs(f.key_count - most_complete.key_count) <= 5  # Within 5 keys
    ]

    if len(similar_files) > 1:
        reason = (
            f"{most_complete.language_name} has the most keys ({most_complete.key_count}), "
            f"but {len(similar_files) - 1} other file(s) are similar"
        )
    else:
        reason = f"{most_complete.language_name} has the most keys ({most_complete.key_count})"

    return most_complete.language_code, reason


def calculate_completeness(
    target_file: LanguageFileInfo,
    source_file: LanguageFileInfo
) -> Dict[str, Any]:
    """
    Calculate how complete a translation file is compared to source.

    Args:
        target_file: Translation file to check
        source_file: Source language file

    Returns:
        Dict with:
        - percentage: Completion percentage (0-100)
        - missing_count: Number of missing keys
        - extra_count: Number of extra keys (not in source)
        - missing_keys: List of missing key paths (max 10)
    """
    if not source_file.is_valid_json or not target_file.is_valid_json:
        return {
            'percentage': 0,
            'missing_count': 0,
            'extra_count': 0,
            'missing_keys': []
        }

    # Load both files
    try:
        with open(source_file.file_path, 'r', encoding='utf-8') as f:
            source_data = json.load(f)

        with open(target_file.file_path, 'r', encoding='utf-8') as f:
            target_data = json.load(f)

        # Flatten
        source_flat = sync.flatten_json(source_data)
        target_flat = sync.flatten_json(target_data)

        # Calculate
        source_keys = set(source_flat.keys())
        target_keys = set(target_flat.keys())

        missing_keys = source_keys - target_keys
        extra_keys = target_keys - source_keys

        if len(source_keys) == 0:
            percentage = 0
        else:
            percentage = (len(target_keys & source_keys) / len(source_keys)) * 100

        return {
            'percentage': round(percentage, 1),
            'missing_count': len(missing_keys),
            'extra_count': len(extra_keys),
            'missing_keys': list(missing_keys)[:10]  # First 10
        }

    except Exception as e:
        logger.error(f"Error calculating completeness: {e}")
        return {
            'percentage': 0,
            'missing_count': 0,
            'extra_count': 0,
            'missing_keys': []
        }



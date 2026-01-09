"""
Internationalization (i18n) module for CharTii-i18n.

This module provides translation functionality for both frontend (Jinja2 templates)
and backend (Python API responses). It loads JSON language packs and provides
a simple interface for retrieving translations.

Note: Log messages are NOT translated - they remain in English for debugging purposes.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from functools import lru_cache

from src.logger import get_logger

logger = get_logger(__name__)

# Language pack directory
LOCALES_DIR = Path(__file__).parent / "web" / "locales"

# Default language
DEFAULT_LANGUAGE = "en"

# Supported languages with their display names
SUPPORTED_LANGUAGES = {
    "en": {"name": "English", "native_name": "English"},
    "zh-CN": {"name": "Chinese (Simplified)", "native_name": "简体中文"},
    "zh-TW": {"name": "Chinese (Traditional)", "native_name": "繁體中文"},
    "es": {"name": "Spanish", "native_name": "Español"},
    "de": {"name": "German", "native_name": "Deutsch"},
    "fr": {"name": "French", "native_name": "Français"},
    "ja": {"name": "Japanese", "native_name": "日本語"},
    "ko": {"name": "Korean", "native_name": "한국어"},
}

# Cache for loaded language packs
_language_cache: Dict[str, Dict[str, Any]] = {}


def get_locales_dir() -> Path:
    """Get the locales directory path."""
    return LOCALES_DIR


def ensure_locales_dir() -> None:
    """Ensure the locales directory exists."""
    LOCALES_DIR.mkdir(parents=True, exist_ok=True)


def load_language(lang_code: str) -> Dict[str, Any]:
    """
    Load a language pack from JSON file.

    Args:
        lang_code: The language code (e.g., 'en', 'zh-CN')

    Returns:
        Dictionary containing all translations for the language
    """
    # Check cache first
    if lang_code in _language_cache:
        return _language_cache[lang_code]

    # Normalize language code
    lang_code = normalize_language_code(lang_code)

    # Check cache again after normalization
    if lang_code in _language_cache:
        return _language_cache[lang_code]

    lang_file = LOCALES_DIR / f"{lang_code}.json"

    if not lang_file.exists():
        logger.debug(f"Language file not found: {lang_file}, falling back to {DEFAULT_LANGUAGE}")
        if lang_code != DEFAULT_LANGUAGE:
            return load_language(DEFAULT_LANGUAGE)
        return {}

    try:
        with open(lang_file, 'r', encoding='utf-8') as f:
            translations = json.load(f)
            _language_cache[lang_code] = translations
            logger.debug(f"Loaded language pack: {lang_code}")
            return translations
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse language file {lang_file}: {e}")
        if lang_code != DEFAULT_LANGUAGE:
            return load_language(DEFAULT_LANGUAGE)
        return {}
    except Exception as e:
        logger.error(f"Failed to load language file {lang_file}: {e}")
        if lang_code != DEFAULT_LANGUAGE:
            return load_language(DEFAULT_LANGUAGE)
        return {}


def normalize_language_code(lang_code: str) -> str:
    """
    Normalize a language code to match our supported languages.

    Args:
        lang_code: Raw language code (e.g., 'zh', 'zh-cn', 'zh_CN')

    Returns:
        Normalized language code (e.g., 'zh-CN')
    """
    if not lang_code:
        return DEFAULT_LANGUAGE

    # Convert to lowercase for comparison
    lang_lower = lang_code.lower().replace('_', '-')

    # Direct match
    for supported in SUPPORTED_LANGUAGES:
        if lang_lower == supported.lower():
            return supported

    # Partial match (e.g., 'zh' -> 'zh-CN')
    lang_prefix = lang_lower.split('-')[0]
    for supported in SUPPORTED_LANGUAGES:
        if supported.lower().startswith(lang_prefix):
            return supported

    return DEFAULT_LANGUAGE


def get_nested_value(data: Dict[str, Any], key_path: str) -> Optional[str]:
    """
    Get a value from a nested dictionary using dot notation.

    Args:
        data: The dictionary to search
        key_path: Dot-separated key path (e.g., 'nav.home')

    Returns:
        The value if found, None otherwise
    """
    keys = key_path.split('.')
    current = data

    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None

    return current if isinstance(current, str) else None


def get_translation(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    """
    Get a translated string for the given key and language.

    Args:
        key: The translation key (dot notation, e.g., 'nav.home')
        lang: The language code (default: 'en')
        **kwargs: Optional format arguments for string interpolation

    Returns:
        The translated string, or the key itself if not found
    """
    lang = normalize_language_code(lang)
    translations = load_language(lang)

    # Try to get the translation
    value = get_nested_value(translations, key)

    # Fallback to English if not found and not already English
    if value is None and lang != DEFAULT_LANGUAGE:
        en_translations = load_language(DEFAULT_LANGUAGE)
        value = get_nested_value(en_translations, key)

    # If still not found, return the key
    if value is None:
        logger.debug(f"Translation not found for key: {key} (lang: {lang})")
        return key

    # Apply string interpolation if kwargs provided
    if kwargs:
        try:
            value = value.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing interpolation key {e} for translation: {key}")

    return value


# Alias for convenience
t = get_translation


def get_available_languages() -> List[Dict[str, str]]:
    """
    Get a list of available languages.

    Returns:
        List of dictionaries with language info
    """
    languages = []
    for code, info in SUPPORTED_LANGUAGES.items():
        lang_file = LOCALES_DIR / f"{code}.json"
        languages.append({
            "code": code,
            "name": info["name"],
            "native_name": info["native_name"],
            "available": lang_file.exists()
        })
    return languages


def get_all_translations(lang: str = DEFAULT_LANGUAGE) -> Dict[str, Any]:
    """
    Get all translations for a language (useful for frontend).

    Args:
        lang: The language code

    Returns:
        Complete translations dictionary
    """
    return load_language(normalize_language_code(lang))


def clear_cache() -> None:
    """Clear the language cache (useful for development/testing)."""
    global _language_cache
    _language_cache = {}
    logger.debug("Language cache cleared")


def reload_language(lang_code: str) -> Dict[str, Any]:
    """
    Reload a specific language pack (clears cache for that language).

    Args:
        lang_code: The language code to reload

    Returns:
        The reloaded translations dictionary
    """
    lang_code = normalize_language_code(lang_code)
    if lang_code in _language_cache:
        del _language_cache[lang_code]
    return load_language(lang_code)

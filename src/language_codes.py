"""
Language code mappings and utilities.

Standards:
- ISO 639-1: 2-letter language codes (en, zh, es)
- BCP 47: Language + Region codes (en-US, zh-CN, pt-BR)

Language JSON File Naming Convention:
The language code determines the JSON filename used for translation files.
For example:
- Language code 'en' maps to filename 'en.json'
- Language code 'zh-CN' maps to filename 'zh-CN.json'
- Language code 'bo' maps to filename 'bo.json'
The get_language_file_name() function handles this mapping automatically.
"""

from typing import Optional, Dict

# ISO 639-1 language codes (2-letter)
# Source: https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes
ISO_639_1 = {
    'af': 'Afrikaans',
    'am': 'Amharic',
    'ar': 'Arabic',
    'ay': 'Aymara',
    'az': 'Azerbaijani',
    'bg': 'Bulgarian',
    'bn': 'Bengali',
    'bo': 'Tibetan',
    'bs': 'Bosnian',
    'ca': 'Catalan',
    'cs': 'Czech',
    'cy': 'Welsh',
    'da': 'Danish',
    'de': 'German',
    'el': 'Greek',
    'en': 'English',
    'es': 'Spanish',
    'et': 'Estonian',
    'eu': 'Basque',
    'fa': 'Persian',
    'ff': 'Fulah',
    'fi': 'Finnish',
    'fr': 'French',
    'ga': 'Irish',
    'gl': 'Galician',
    'gn': 'Guarani',
    'gu': 'Gujarati',
    'ha': 'Hausa',
    'he': 'Hebrew',
    'hi': 'Hindi',
    'hr': 'Croatian',
    'hu': 'Hungarian',
    'hy': 'Armenian',
    'id': 'Indonesian',
    'ig': 'Igbo',
    'is': 'Icelandic',
    'it': 'Italian',
    'ja': 'Japanese',
    'ka': 'Georgian',
    'kk': 'Kazakh',
    'km': 'Khmer',
    'kn': 'Kannada',
    'ko': 'Korean',
    'ky': 'Kyrgyz',
    'lb': 'Luxembourgish',
    'lo': 'Lao',
    'lt': 'Lithuanian',
    'lv': 'Latvian',
    'mg': 'Malagasy',
    'mi': 'Maori',
    'mk': 'Macedonian',
    'ml': 'Malayalam',
    'mn': 'Mongolian',
    'mr': 'Marathi',
    'ms': 'Malay',
    'mt': 'Maltese',
    'my': 'Burmese',
    'ne': 'Nepali',
    'nl': 'Dutch',
    'no': 'Norwegian',
    'om': 'Oromo',
    'or': 'Odia',
    'pa': 'Punjabi',
    'pl': 'Polish',
    'pt': 'Portuguese',
    'qu': 'Quechua',
    'rn': 'Kirundi',
    'ro': 'Romanian',
    'ru': 'Russian',
    'rw': 'Kinyarwanda',
    'si': 'Sinhala',
    'sk': 'Slovak',
    'sl': 'Slovenian',
    'so': 'Somali',
    'sq': 'Albanian',
    'sr': 'Serbian',
    'ss': 'Swati',
    'st': 'Southern Sotho',
    'sv': 'Swedish',
    'sw': 'Swahili',
    'ta': 'Tamil',
    'te': 'Telugu',
    'tg': 'Tajik',
    'th': 'Thai',
    'tk': 'Turkmen',
    'tn': 'Tswana',
    'tr': 'Turkish',
    'ts': 'Tsonga',
    'uk': 'Ukrainian',
    'ur': 'Urdu',
    'uz': 'Uzbek',
    've': 'Venda',
    'vi': 'Vietnamese',
    'xh': 'Xhosa',
    'yo': 'Yoruba',
    'zh': 'Chinese',
    'zu': 'Zulu',
}

# BCP 47 language-region codes (common variants)
BCP_47_VARIANTS = {
    'en-US': 'English (United States)',
    'en-GB': 'English (United Kingdom)',
    'en-AU': 'English (Australia)',
    'en-CA': 'English (Canada)',

    'zh-CN': 'Chinese (Simplified, China)',
    'zh-TW': 'Chinese (Traditional, Taiwan)',
    'zh-HK': 'Chinese (Traditional, Hong Kong)',
    'zh-SG': 'Chinese (Simplified, Singapore)',

    'es-ES': 'Spanish (Spain)',
    'es-MX': 'Spanish (Mexico)',
    'es-AR': 'Spanish (Argentina)',
    'es-CO': 'Spanish (Colombia)',

    'pt-BR': 'Portuguese (Brazil)',
    'pt-PT': 'Portuguese (Portugal)',

    'fr-FR': 'French (France)',
    'fr-CA': 'French (Canada)',
    'fr-BE': 'French (Belgium)',
    'fr-CH': 'French (Switzerland)',

    'de-DE': 'German (Germany)',
    'de-AT': 'German (Austria)',
    'de-CH': 'German (Switzerland)',

    'ar-SA': 'Arabic (Saudi Arabia)',
    'ar-AE': 'Arabic (United Arab Emirates)',
    'ar-EG': 'Arabic (Egypt)',
}

# Combined mapping
ALL_LANGUAGE_CODES = {**ISO_639_1, **BCP_47_VARIANTS}


def is_valid_language_code(code: str) -> bool:
    """
    Check if a language code is valid.

    Args:
        code: Language code (e.g., 'en', 'zh-CN')

    Returns:
        True if code is valid

    Examples:
        >>> is_valid_language_code('en')
        True
        >>> is_valid_language_code('zh-CN')
        True
        >>> is_valid_language_code('invalid')
        False
    """
    return code in ALL_LANGUAGE_CODES


def get_language_name(code: str) -> Optional[str]:
    """
    Get the full language name from code.

    Args:
        code: Language code

    Returns:
        Language name or None if invalid

    Examples:
        >>> get_language_name('en')
        'English'
        >>> get_language_name('zh-CN')
        'Chinese (Simplified, China)'
    """
    return ALL_LANGUAGE_CODES.get(code)


def extract_base_language(code: str) -> str:
    """
    Extract base language from code (remove region).

    Args:
        code: Language code (e.g., 'zh-CN', 'en-US', 'fr')

    Returns:
        Base language code (e.g., 'zh', 'en', 'fr')

    Examples:
        >>> extract_base_language('zh-CN')
        'zh'
        >>> extract_base_language('en-US')
        'en'
        >>> extract_base_language('fr')
        'fr'
    """
    return code.split('-')[0]


def languages_match(code1: str, code2: str, strict: bool = False) -> bool:
    """
    Check if two language codes match.

    Args:
        code1: First language code
        code2: Second language code
        strict: If True, must match exactly. If False, base language match is ok.

    Returns:
        True if languages match

    Examples:
        >>> languages_match('en', 'en-US')
        True
        >>> languages_match('en', 'en-US', strict=True)
        False
        >>> languages_match('zh-CN', 'zh-TW')
        True
        >>> languages_match('zh-CN', 'zh-TW', strict=True)
        False
    """
    if strict:
        return code1 == code2

    return extract_base_language(code1) == extract_base_language(code2)


def get_language_file_name(language_code: str) -> str:
    """
    Get the expected filename for a language.

    Args:
        language_code: Language code

    Returns:
        Filename (e.g., 'en.json', 'zh-CN.json')

    Examples:
        >>> get_language_file_name('en')
        'en.json'
        >>> get_language_file_name('zh-CN')
        'zh-CN.json'
    """
    return f"{language_code}.json"


def extract_language_from_filename(filename: str) -> Optional[str]:
    """
    Extract language code from filename.

    Args:
        filename: Filename (e.g., 'en.json', 'zh-CN.json', 'locales/fr.json')

    Returns:
        Language code or None if cannot extract

    Examples:
        >>> extract_language_from_filename('en.json')
        'en'
        >>> extract_language_from_filename('zh-CN.json')
        'zh-CN'
        >>> extract_language_from_filename('/path/to/locales/es.json')
        'es'
        >>> extract_language_from_filename('invalid.txt')
        None
    """
    from pathlib import Path

    # Get filename without path
    filename = Path(filename).name

    # Remove .json extension
    if not filename.endswith('.json'):
        return None

    code = filename[:-5]  # Remove '.json'

    # Validate
    if is_valid_language_code(code):
        return code

    return None


def get_all_language_codes() -> Dict[str, str]:
    """
    Get all supported language codes.

    Returns:
        Dict mapping code to language name
    """
    return ALL_LANGUAGE_CODES.copy()

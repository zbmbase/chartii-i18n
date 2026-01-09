"""
Translation Validation Module

Contains validation functions for checking translation quality:
- Variable preservation checks
- Protected term validation
- Translation content validation
"""

import re
from typing import Dict, List, Optional, Set, Tuple

from src.logger import get_logger
import src.language_codes as lc

logger = get_logger(__name__)


def extract_variables(text: str, variable_patterns: List[str]) -> Set[str]:
    """
    Extract all variables from text using configured patterns.

    Args:
        text: Text to extract variables from
        variable_patterns: List of regex patterns to match variables

    Returns:
        Set of variable strings found in text
    """
    variables = set()
    for pattern in variable_patterns:
        try:
            matches = re.findall(pattern, text)
            variables.update(matches)
        except re.error:
            continue
    return variables


def validate_native_variables_preserved(
    source: str,
    translation: str,
    variable_patterns: List[str],
) -> Tuple[bool, Optional[str]]:
    """
    Check if all variables from source are preserved in translation.

    In the first translation attempt, variables are kept in their native form
    (e.g., {percent}, ${name}) rather than replaced with placeholders.
    This allows the AI to understand the full context.

    Args:
        source: Original source text with variables
        translation: Translated text that should preserve variables
        variable_patterns: List of regex patterns to match variables

    Returns:
        Tuple of (is_valid, error_reason)
    """
    source_vars = extract_variables(source, variable_patterns)
    translation_vars = extract_variables(translation, variable_patterns)

    if source_vars != translation_vars:
        missing = source_vars - translation_vars
        if missing:
            return False, f"native_variables_lost:{','.join(missing)}"
        extra = translation_vars - source_vars
        if extra:
            return False, f"native_variables_added:{','.join(extra)}"

    return True, None


def is_translation_valid(
    source_text: str,
    translated_text: str,
    source_lang: str,
    target_lang: str,
    protected_vars: Optional[Dict[str, str]] = None,
    variable_placeholders: Optional[Dict[str, str]] = None,
    key_path: Optional[str] = None,
    project_id: Optional[int] = None,
    protected_terms_module=None,
) -> Tuple[bool, Optional[str]]:
    """
    Unified validation for all translation validation needs.

    Validation philosophy: Trust AI for translation quality.
    Only check for obvious errors that AI cannot produce correctly.

    Checks:
    1. Not empty - Translation must contain actual content
    2. Not identical - Translation must differ from source (unless same language or pure numbers)
    3. Protected vars - Protected terms must be preserved in translation
    4. Variables - Variable placeholders must be preserved in translation

    Args:
        source_text: Original source text
        translated_text: Translated text to validate
        source_lang: Source language code
        target_lang: Target language code
        protected_vars: Optional dict of placeholder -> original protected term mappings
        variable_placeholders: Optional dict of placeholder -> original variable mappings
        key_path: Optional key path for direct protected term lookup
        project_id: Optional project ID for protected term lookup
        protected_terms_module: Optional module for protected terms lookup

    Returns:
        Tuple of (is_valid: bool, error_reason: Optional[str])
    """
    # Check 1: Not empty
    if not translated_text or not translated_text.strip():
        return False, "empty"

    # Check 2: Content not identical (language-aware)
    # Special case: If source text is exactly a protected term,
    # it's valid for translation to equal source (protected terms shouldn't be translated)
    source_is_protected_term = False

    # Method 1: Check via protected_vars
    if protected_vars:
        # Check if source text exactly matches any protected term
        for placeholder, original_var in protected_vars.items():
            if source_text.strip() == original_var.strip():
                source_is_protected_term = True
                break

    # Method 2 (fallback): Direct database lookup when protected_vars is empty
    # This handles cases where the source text IS the protected term itself
    if not source_is_protected_term and key_path and project_id and protected_terms_module:
        filtered_terms = protected_terms_module.get_all_protected_terms_flat(
            project_id, key_path=key_path
        )
        if source_text.strip() in [t.strip() for t in filtered_terms]:
            source_is_protected_term = True
            logger.debug(f"Source text '{source_text}' identified as protected term via direct lookup")

    # If translation equals source AND different language AND not pure numbers
    # This catches AI failures where it simply returns the source unchanged
    # Exception: If source is a protected term, it's valid to keep it unchanged
    if translated_text.strip() == source_text.strip():
        if not lc.languages_match(target_lang, source_lang):
            if not source_text.replace(" ", "").isdigit():
                if not source_is_protected_term:
                    return False, "identical_to_source"

    # Check 3: Protected terms preserved
    if protected_vars:
        for placeholder, original_var in protected_vars.items():
            # Special case: If source text is exactly this protected term,
            # and translation equals source, it's valid (protected term preserved)
            if source_text.strip() == original_var.strip() and translated_text.strip() == source_text.strip():
                continue  # Valid: protected term kept as-is

            # The original protected term should appear in the translated text
            # (either as placeholder or restored original)
            if original_var not in translated_text and placeholder not in translated_text:
                return False, f"protected_term_lost:{original_var}"

    # Check 4: Variables preserved
    if variable_placeholders:
        for placeholder, original_var in variable_placeholders.items():
            # The original variable should appear in the translated text
            # (either as placeholder or restored original)
            if original_var not in translated_text and placeholder not in translated_text:
                return False, f"variable_lost:{original_var}"

    return True, None


def validate_translation_result(
    source_text: str,
    translated_text: str,
    source_lang: str,
    target_lang: str,
    protected_vars: Optional[Dict[str, str]] = None,
    variable_placeholders: Optional[Dict[str, str]] = None,
    key_path: Optional[str] = None,
    project_id: Optional[int] = None,
    protected_terms_module=None,
) -> Tuple[bool, Optional[str]]:
    """
    Validate translation result in the translation pipeline.

    Delegates to is_translation_valid() for unified validation logic.

    Args:
        source_text: Original source text
        translated_text: Translated text to validate
        source_lang: Source language code
        target_lang: Target language code
        protected_vars: Optional dict of placeholder -> original protected term mappings
        variable_placeholders: Optional dict of placeholder -> original variable mappings
        key_path: Optional key path for direct protected term lookup
        project_id: Optional project ID for protected term lookup
        protected_terms_module: Optional module for protected terms lookup

    Returns:
        Tuple of (is_valid: bool, error_reason: str or None)
    """
    return is_translation_valid(
        source_text=source_text,
        translated_text=translated_text,
        source_lang=source_lang,
        target_lang=target_lang,
        protected_vars=protected_vars,
        variable_placeholders=variable_placeholders,
        key_path=key_path,
        project_id=project_id,
        protected_terms_module=protected_terms_module,
    )

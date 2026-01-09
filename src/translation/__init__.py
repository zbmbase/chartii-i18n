"""
Translation module - Core translation functionality

This module provides:
- TranslationManager: Main translation workflow coordinator
- TranslationProgress: Progress tracking dataclass
- Validation functions for translation quality
- Processing utilities for chunk-based translation
"""

from src.translation.progress import TranslationProgress
from src.translation.manager import TranslationManager
from src.translation.validator import (
    extract_variables,
    validate_native_variables_preserved,
    is_translation_valid,
    validate_translation_result,
)
from src.translation.processor import (
    translate_chunks_sequential,
    translate_chunks_sequential_with_progress,
    replace_variables_with_placeholders,
    restore_variables_from_placeholders,
)

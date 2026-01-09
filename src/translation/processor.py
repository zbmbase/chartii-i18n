"""
Translation Processing Module

Contains functions for processing translation chunks:
- Sequential chunk translation with progress
- Variable placeholder replacement and restoration
"""

import re
from typing import Callable, Dict, List, Optional, Tuple

from src.logger import get_logger
from src.translation.progress import TranslationProgress

logger = get_logger(__name__)


def translate_chunks_sequential_with_progress(
    chunks: List[List[tuple]],
    source_lang: str,
    target_lang: str,
    context: str,
    ai_service,
    cancel_check: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[TranslationProgress], None]] = None,
    lang_code: str = "",
    lang_name: str = "",
    total_languages: int = 0,
    completed_languages: int = 0,
    total_batches: int = 0,
    processed_items: int = 0,
    total_items: int = 0,
    translated_count: int = 0,
    failure_count: int = 0,
) -> List[List[str]]:
    """
    Translate multiple chunks sequentially with real-time progress updates.

    Returns list of translated text lists (same order as input chunks).
    On failure, returns original texts (graceful degradation).
    Sends batch_done progress update immediately after each chunk is translated.

    Args:
        chunks: List of chunks, where each chunk is a list of (key_path, text) tuples
        source_lang: Source language code
        target_lang: Target language code
        context: Translation context string
        ai_service: AIService instance for translation
        cancel_check: Optional function to check for cancellation
        progress_callback: Optional callback for progress updates
        lang_code: Current language code
        lang_name: Current language name
        total_languages: Total number of languages
        completed_languages: Number of completed languages
        total_batches: Total number of batches
        processed_items: Number of processed items
        total_items: Total number of items
        translated_count: Number of successful translations
        failure_count: Number of failed translations

    Returns:
        List of translated text lists, one per chunk
    """
    results = []

    for chunk_idx, chunk in enumerate(chunks):
        # Check for cancellation
        if cancel_check and cancel_check():
            # Fill remaining with originals
            for remaining_chunk in chunks[chunk_idx:]:
                results.append([text for _, text in remaining_chunk])
            break

        texts = [text for _, text in chunk]
        try:
            logger.debug(f"Chunk {chunk_idx + 1}/{len(chunks)}: Starting translation of {len(texts)} strings")
            translated = ai_service.translate_array(
                texts=texts,
                source_language=source_lang,
                target_language=target_lang,
                context=context,
            )
            logger.debug(f"Chunk {chunk_idx + 1}/{len(chunks)}: Translation completed")
            results.append(translated)

            # Get token usage for this batch
            batch_token_usage = ai_service.get_last_token_usage()

            # Send batch_done progress update immediately after translation completes
            if progress_callback:
                progress = TranslationProgress(
                    current_language=lang_code,
                    current_language_name=lang_name,
                    total_languages=total_languages,
                    completed_languages=completed_languages,
                    current_item=processed_items,
                    total_items=total_items,
                    current_key="",
                    current_text="",
                    success_count=translated_count,
                    failure_count=failure_count,
                    current_batch=chunk_idx + 1,
                    total_batches=total_batches,
                    batch_keys_count=len(chunk),
                    phase="batch_done",  # Batch translation completed
                    token_usage=batch_token_usage,  # Token usage for this batch
                )
                if progress_callback(progress):
                    # Cancellation requested
                    # Fill remaining with originals
                    for remaining_chunk in chunks[chunk_idx + 1:]:
                        results.append([text for _, text in remaining_chunk])
                    break
        except Exception as e:
            logger.error(f"Chunk {chunk_idx + 1}/{len(chunks)} translation failed: {e}. Returning originals.")
            results.append(texts)  # Graceful fallback

            # Get token usage for this batch (may be zero if API call failed)
            batch_token_usage = ai_service.get_last_token_usage()

            # Still send batch_done progress update even on failure
            if progress_callback:
                progress = TranslationProgress(
                    current_language=lang_code,
                    current_language_name=lang_name,
                    total_languages=total_languages,
                    completed_languages=completed_languages,
                    current_item=processed_items,
                    total_items=total_items,
                    current_key="",
                    current_text="",
                    success_count=translated_count,
                    failure_count=failure_count,
                    current_batch=chunk_idx + 1,
                    total_batches=total_batches,
                    batch_keys_count=len(chunk),
                    phase="batch_done",  # Batch completed (even if failed)
                    token_usage=batch_token_usage,  # Token usage for this batch (may be zero on failure)
                )
                if progress_callback(progress):
                    # Cancellation requested
                    # Fill remaining with originals
                    for remaining_chunk in chunks[chunk_idx + 1:]:
                        results.append([text for _, text in remaining_chunk])
                    break

    return results


def translate_chunks_sequential(
    chunks: List[List[tuple]],
    source_lang: str,
    target_lang: str,
    context: str,
    ai_service,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> List[List[str]]:
    """
    Translate multiple chunks sequentially.

    Returns list of translated text lists (same order as input chunks).
    On failure, returns original texts (graceful degradation).

    Args:
        chunks: List of chunks, where each chunk is a list of (key_path, text) tuples
        source_lang: Source language code
        target_lang: Target language code
        context: Translation context string
        ai_service: AIService instance for translation
        cancel_check: Optional function to check for cancellation

    Returns:
        List of translated text lists, one per chunk
    """
    results = []

    for chunk_idx, chunk in enumerate(chunks):
        # Check for cancellation
        if cancel_check and cancel_check():
            # Fill remaining with originals
            for remaining_chunk in chunks[chunk_idx:]:
                results.append([text for _, text in remaining_chunk])
            break

        texts = [text for _, text in chunk]
        try:
            logger.debug(f"Chunk {chunk_idx + 1}/{len(chunks)}: Starting translation of {len(texts)} strings")
            translated = ai_service.translate_array(
                texts=texts,
                source_language=source_lang,
                target_language=target_lang,
                context=context,
            )
            logger.debug(f"Chunk {chunk_idx + 1}/{len(chunks)}: Translation completed")
            results.append(translated)
        except Exception as e:
            logger.error(f"Chunk {chunk_idx + 1}/{len(chunks)} translation failed: {e}. Returning originals.")
            results.append(texts)  # Graceful fallback

    return results


def replace_variables_with_placeholders(
    text: str,
    variable_patterns: List[str],
    preserve_variables: bool = True,
) -> Tuple[str, Dict[str, str]]:
    """
    Replace variables in text with placeholders for fallback translation.

    This method is used when the first translation attempt (with native variables)
    fails to preserve variables, and we need to retry with placeholder protection.

    Args:
        text: The text containing variables to replace
        variable_patterns: List of regex patterns to match variables
        preserve_variables: Whether to preserve variables (if False, returns unchanged)

    Returns:
        Tuple of (text_with_placeholders, placeholder_map)
        where placeholder_map is {"__VAR_0__": "{original_var}", ...}
    """
    if not preserve_variables:
        return text, {}

    if not variable_patterns:
        return text, {}

    protected_text = text
    placeholder_map = {}
    placeholder_index = 0

    # Sort patterns by length (longest first) to handle overlapping patterns
    sorted_patterns = sorted(variable_patterns, key=lambda p: len(p) if isinstance(p, str) else 0, reverse=True)

    for pattern in sorted_patterns:
        matches = list(re.finditer(pattern, protected_text))
        if matches:
            # Replace from end to start to preserve positions
            for match in reversed(matches):
                var = match.group(0)
                placeholder = f"__VAR_{placeholder_index}__"
                placeholder_map[placeholder] = var
                start, end = match.span()
                protected_text = protected_text[:start] + placeholder + protected_text[end:]
                placeholder_index += 1

    if placeholder_map:
        logger.debug(f"Replaced {len(placeholder_map)} variables with placeholders: {text[:50]}... -> {protected_text[:50]}...")

    return protected_text, placeholder_map


def restore_variables_from_placeholders(text: str, placeholder_map: Dict[str, str]) -> str:
    """
    Restore original variables from placeholders after fallback translation.

    Args:
        text: Translated text containing __VAR_N__ placeholders
        placeholder_map: Mapping from placeholders to original variables
                       e.g., {"__VAR_0__": "{percent}", "__VAR_1__": "{name}"}

    Returns:
        Text with placeholders replaced by original variables
    """
    if not placeholder_map:
        return text

    restored_text = text
    for placeholder, original_var in placeholder_map.items():
        restored_text = restored_text.replace(placeholder, original_var)

    return restored_text

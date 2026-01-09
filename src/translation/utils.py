"""
Translation utility functions for flatten/rebuild, chunking, and JSON extraction.
Provides capabilities for processing nested JSON structures and chunking translation tasks.
"""

import json
import re
from typing import List, Dict, Any, Tuple, Optional


def flatten_json(obj: Any, path: str = "", pairs: List[Tuple[str, Any]] = None) -> List[Tuple[str, Any]]:
    """
    Flatten nested JSON into key-value pairs.

    Args:
        obj: JSON object to flatten
        path: Current key path
        pairs: Accumulator list (created if None)

    Returns:
        List of (key_path, value) tuples

    Example:
        >>> flatten_json({"home": {"title": "Hello"}})
        [("home.title", "Hello")]
    """
    if pairs is None:
        pairs = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            new_path = f"{path}.{key}" if path else key
            if isinstance(value, dict):
                flatten_json(value, new_path, pairs)
            else:
                pairs.append((new_path, value))
    else:
        if path:
            pairs.append((path, obj))

    return pairs


def group_pairs(pairs: List[Tuple[str, Any]]) -> Tuple[List[Tuple[str, str]], List[Tuple[str, Any]]]:
    """
    Separate pairs into translatable strings and non-strings.

    Args:
        pairs: List of (key, value) tuples

    Returns:
        Tuple of (require_translation, no_translation)
    """
    require_translation = []
    no_translation = []

    for key, value in pairs:
        if isinstance(value, str) and value.strip():
            require_translation.append((key, value))
        else:
            no_translation.append((key, value))

    return require_translation, no_translation


def build_json_from_pairs(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    """
    Rebuild nested JSON from key-value pairs.

    Args:
        pairs: List of (key_path, value) tuples

    Returns:
        Nested dictionary

    Example:
        >>> build_json_from_pairs([("home.title", "Hello")])
        {"home": {"title": "Hello"}}
    """
    result = {}

    for path, value in pairs:
        keys = path.split('.')
        node = result

        for i, key in enumerate(keys[:-1]):
            if key not in node:
                node[key] = {}
            elif not isinstance(node[key], dict):
                # Handle conflict: if existing value is not dict, wrap it
                node[key] = {}
            node = node[key]

        if keys:
            node[keys[-1]] = value

    return result


def count_words(text: str) -> int:
    """
    Count words in text: English/European languages by whitespace, CJK languages by characters.

    Args:
        text: Text to count words for

    Returns:
        Word count (words for English, characters for CJK)
    """
    if not text:
        return 0

    # Detect CJK characters (Chinese, Japanese, Korean)
    cjk_pattern = re.compile(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7a3]')
    has_cjk = bool(cjk_pattern.search(text))

    if has_cjk:
        # Count all characters for CJK languages
        return len(text)
    else:
        # Count words by whitespace for English/European languages
        return len(text.split())


def chunk_with_keys(
    items: List[Tuple[str, str]],
    max_chars: int = None,
    max_words: int = None
) -> List[List[Tuple[str, str]]]:
    """
    Split key-value pairs into chunks based on total value word count or character count.

    Priority: max_words > max_chars
    If max_words is provided, uses word counting (English by spaces, CJK by characters).
    If only max_chars is provided, uses character count (for backward compatibility).

    Args:
        items: List of (key, value) tuples
        max_chars: Maximum characters per chunk (deprecated, use max_words instead)
        max_words: Maximum words per chunk (recommended)

    Returns:
        List of chunks, each containing list of (key, value) tuples
    """
    if not items:
        return []

    # Determine which limit to use
    use_words = max_words is not None
    limit = max_words if use_words else (max_chars or 1000)

    chunks = []
    current_chunk = []
    current_size = 0

    for key, value in items:
        if use_words:
            # Estimate words for this value
            value_size = count_words(value) if value else 0
        else:
            # Use character count (backward compatibility)
            value_size = len(value) if value else 0

        # If adding this item would exceed limit AND we have items in current chunk
        # then start a new chunk
        if current_size + value_size > limit and current_chunk:
            chunks.append(current_chunk)
            current_chunk = [(key, value)]
            current_size = value_size
        else:
            current_chunk.append((key, value))
            current_size += value_size

    # Add the last chunk if it has items
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def match_json_array(text: str) -> Optional[str]:
    """
    Extract JSON array from mixed text using bracket matching.

    Args:
        text: Text potentially containing JSON array

    Returns:
        Extracted JSON array string, or None if not found
    """
    if not text:
        return None

    stack = []
    start = -1

    for i, char in enumerate(text):
        if char == '[':
            if not stack:
                start = i
            stack.append('[')
        elif char == ']':
            if stack:
                stack.pop()
                if not stack and start >= 0:
                    return text[start:i+1]

    return None


def match_json_object(text: str) -> Optional[str]:
    """
    Extract JSON object from mixed text using bracket matching.

    Args:
        text: Text potentially containing JSON object

    Returns:
        Extracted JSON object string, or None if not found
    """
    if not text:
        return None

    stack = []
    start = -1
    in_string = False
    escape_next = False

    for i, char in enumerate(text):
        if escape_next:
            escape_next = False
            continue

        if char == '\\':
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == '{':
            if not stack:
                start = i
            stack.append('{')
        elif char == '}':
            if stack:
                stack.pop()
                if not stack and start >= 0:
                    return text[start:i+1]

    return None


def safe_parse_json_array(text: str) -> Optional[List[str]]:
    """
    Safely parse JSON array from potentially malformed text.

    Tries multiple strategies:
    1. Direct parse
    2. Remove markdown code blocks and parse
    3. Extract with matchJSON and parse

    Args:
        text: Text to parse

    Returns:
        Parsed list or None on failure
    """
    if not text:
        return None

    text = text.strip()

    # Strategy 1: Direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Strategy 2: Remove markdown code blocks
    clean_text = text
    if clean_text.startswith('```'):
        lines = clean_text.split('\n')
        # Remove first line (```json or ```)
        if lines[0].startswith('```'):
            lines = lines[1:]
        # Remove last line if it's closing ```
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        clean_text = '\n'.join(lines).strip()

        try:
            result = json.loads(clean_text)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # Strategy 3: Extract with bracket matching
    extracted = match_json_array(text)
    if extracted:
        try:
            result = json.loads(extracted)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    return None


def safe_parse_json_object(text: str) -> Optional[Dict]:
    """
    Safely parse JSON object from potentially malformed text.

    Args:
        text: Text to parse

    Returns:
        Parsed dict or None on failure
    """
    if not text:
        return None

    text = text.strip()

    # Strategy 1: Direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Strategy 2: Remove markdown code blocks
    clean_text = text
    if clean_text.startswith('```'):
        lines = clean_text.split('\n')
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        clean_text = '\n'.join(lines).strip()

        try:
            result = json.loads(clean_text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # Strategy 3: Extract with bracket matching
    extracted = match_json_object(text)
    if extracted:
        try:
            result = json.loads(extracted)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    return None


def parse_translations_response(text: str, expected_count: int = None) -> Optional[List[str]]:
    """
    Parse translation response with multiple fallback strategies.
    Handles both array format and object with translations key.

    Args:
        text: Response text from AI
        expected_count: Expected number of translations (for validation)

    Returns:
        List of translated strings or None on failure
    """
    if not text:
        return None

    # Try array format first
    result = safe_parse_json_array(text)
    if result is not None:
        # Validate count if specified
        if expected_count is not None and len(result) != expected_count:
            # Log warning but still return result
            pass
        return result

    # Try object format with translations key
    obj = safe_parse_json_object(text)
    if obj is not None:
        if 'translations' in obj:
            translations = obj['translations']
            if isinstance(translations, list):
                # Extract text from key-value pairs if needed
                if translations and isinstance(translations[0], dict):
                    return [t.get('text', '') for t in translations]
                return translations

    return None

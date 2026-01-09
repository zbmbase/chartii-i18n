"""
Protected Terms Management Module - Core Functions

This module handles the protection and restoration of terms that should not be translated.
Includes placeholder replacement and retrieval functions.

For AI-based analysis, see protection/analyzer.py
"""

import re
from typing import Dict, List, Tuple

from src.core import database as db
from src.logger import get_logger

logger = get_logger(__name__)


# Category definitions
DEFAULT_CATEGORY_METADATA = {
    'brand': {
        'name': 'Brand / Product',
        'description': 'Brand names and product names',
        'examples': ['PixABC', 'OpenAI', 'ChatGPT']
    },
    'technical': {
        'name': 'Technical Terms',
        'description': 'Technical abbreviations and domain-specific terminology',
        'examples': ['API', 'JSON', 'HTTP', 'CSS']
    },
    'url': {
        'name': 'URL / Domain',
        'description': 'URLs, domains, and email addresses',
        'examples': ['example.com', 'https://api.example.com']
    },
    'code': {
        'name': 'Code Identifiers',
        'description': 'Identifiers found inside code, such as variable or function names',
        'examples': ['onClick', 'className', 'getUserData']
    }
}


def apply_protection(text: str, protected_terms: List[str]) -> Tuple[str, Dict[str, str]]:
    """
    Replace protected terms with placeholders.

    Args:
        text: The text to protect
        protected_terms: List of terms to protect

    Returns:
        Tuple of (protected_text, placeholder_map)

    Example:
        >>> text = "Welcome to PixABC API"
        >>> protected_text, mapping = apply_protection(text, ["PixABC", "API"])
        >>> print(protected_text)
        "Welcome to __PROT_0__ __PROT_1__"
        >>> print(mapping)
        {"__PROT_0__": "PixABC", "__PROT_1__": "API"}
    """
    if not protected_terms:
        return text, {}

    protected_text = text
    placeholder_map = {}
    index = 0

    # Sort by length (longest first) to handle overlapping terms
    sorted_terms = sorted(set(protected_terms), key=len, reverse=True)

    for term in sorted_terms:
        if not term:
            continue

        # Use word boundaries for whole word matching
        # Escape special regex characters
        escaped_term = re.escape(term)
        pattern = rf'\b{escaped_term}\b'

        matches = list(re.finditer(pattern, protected_text))

        if matches:
            for match in reversed(matches):  # Replace from end to start to preserve positions
                placeholder = f"__PROT_{index}__"
                placeholder_map[placeholder] = term

                # Replace this occurrence
                start, end = match.span()
                protected_text = protected_text[:start] + placeholder + protected_text[end:]

                index += 1

    return protected_text, placeholder_map


def restore_protection(text: str, placeholder_map: Dict[str, str]) -> str:
    """
    Restore original terms from placeholders.

    Args:
        text: Text with placeholders
        placeholder_map: Mapping of placeholders to original terms

    Returns:
        Text with original terms restored
    """
    if not placeholder_map:
        return text

    restored_text = text

    for placeholder, original_term in placeholder_map.items():
        restored_text = restored_text.replace(placeholder, original_term)

    return restored_text


def get_all_protected_terms_grouped(project_id: int) -> Dict[str, List[str]]:
    """
    Get all protected terms for a project, grouped by category.

    Args:
        project_id: The project ID

    Returns:
        Dict with category keys and lists of terms
    """
    all_terms = db.get_protected_terms(project_id)

    grouped = {
        'brand': [],
        'technical': [],
        'url': [],
        'code': []
    }

    for term_data in all_terms:
        category = term_data.get('category', 'brand')
        term = term_data.get('term', '')

        if category in grouped and term:
            grouped[category].append(term)

    return grouped


def get_all_protected_terms_flat(project_id: int, key_path: str = None) -> List[str]:
    """
    Get all protected terms as a flat list, optionally filtered by key_path.

    Args:
        project_id: The project ID
        key_path: Optional key_path to filter terms. If provided, only returns terms
                  where key_scopes is empty (global) or contains this key_path.
                  If None, returns all terms (for backward compatibility).

    Returns:
        List of protected term strings
    """
    all_terms = db.get_protected_terms(project_id)

    if key_path is None:
        # Backward compatibility: return all terms
        return [term_data['term'] for term_data in all_terms if term_data.get('term')]

    # Filter by key_path
    filtered_terms = []
    for term_data in all_terms:
        if not term_data.get('term'):
            continue

        key_scopes = term_data.get('key_scopes', [])
        # If key_scopes is empty/null, it's global protection
        if not key_scopes:
            filtered_terms.append(term_data['term'])
        elif key_path in key_scopes:
            filtered_terms.append(term_data['term'])

    return filtered_terms

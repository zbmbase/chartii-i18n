"""
Protection module - Protected terms management

This module provides:
- terms: Core protection functions (apply_protection, restore_protection)
- analyzer: AI-based term analysis
"""

from src.protection.terms import (
    DEFAULT_CATEGORY_METADATA,
    apply_protection,
    restore_protection,
    get_all_protected_terms_grouped,
    get_all_protected_terms_flat,
)

from src.protection.analyzer import (
    analyze_protected_terms,
)

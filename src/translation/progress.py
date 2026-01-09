"""
Translation Progress Data Class

Contains the TranslationProgress dataclass for tracking translation progress.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class TranslationProgress:
    """Progress information for ongoing translation."""
    current_language: str
    current_language_name: str
    total_languages: int
    completed_languages: int
    current_item: int
    total_items: int
    current_key: str
    current_text: str
    success_count: int
    failure_count: int
    estimated_time_remaining: Optional[float] = None
    # Batch progress fields
    current_batch: int = 0           # Current batch number (1-indexed)
    total_batches: int = 0           # Total batches for current language
    batch_keys_count: int = 0        # Number of keys in current batch
    phase: str = "translating"       # "translating", "retrying", "saving"
    retry_keys_count: int = 0        # Number of keys being retried
    # Task statistics fields (for tasks_found phase)
    missing_count: int = 0           # Number of missing entries
    ai_count: int = 0                # Number of AI-generated entries to retranslate
    locked_count: int = 0            # Number of locked entries (for full mode)
    total_tasks: int = 0             # Total number of tasks
    mode: str = ""                   # Translation mode (for frontend display)
    # Token usage fields
    token_usage: Optional[Dict[str, int]] = None  # Token usage for current language
    # Failed items for current language (only populated when phase is "completed")
    failed_items: Optional[List[Dict[str, Any]]] = None  # Failed items for the current language

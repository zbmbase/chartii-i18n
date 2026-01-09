"""
AI Service Exceptions

This module contains exception classes for the AI service.
Separated to avoid circular imports between service.py and providers.py.
"""


class TranslationError(Exception):
    """Translation service error with optional code and details."""

    def __init__(self, message: str, code: str = None, details: dict = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

"""Web application package for CharTii-i18n."""

from flask import Flask

from src.config import initialize_app


def create_app() -> Flask:
    """Application factory for the web interface."""
    initialize_app()

    from .app import build_app  # Import here to avoid circular imports

    return build_app()


__all__ = ["create_app"]

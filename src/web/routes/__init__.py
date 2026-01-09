"""Route blueprints for the web application."""

from .projects import projects_bp
from .translation import translation_bp
from .protected import protected_bp
from .sync import sync_bp

__all__ = [
    "projects_bp",
    "translation_bp",
    "protected_bp",
    "sync_bp",
]

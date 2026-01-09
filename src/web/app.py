"""Flask application configuration and blueprint registration."""

from __future__ import annotations

from datetime import datetime

from flask import Flask, jsonify, render_template, request, g

from src.logger import get_logger
from src.core import database as db
from src.core.schema import ensure_all_schemas
from src import i18n

from .routes.projects import projects_bp
from .routes.translation import translation_bp
from .routes.protected import protected_bp
from .routes.sync import sync_bp
from .routes.settings import settings_bp

logger = get_logger(__name__)


def get_current_language() -> str:
    """
    Determine the current language from various sources.
    Priority: query param > cookie > Accept-Language header > default (en)
    """
    # 1. Check query parameter
    lang = request.args.get('lang')
    if lang and lang in i18n.SUPPORTED_LANGUAGES:
        return lang

    # 2. Check cookie
    lang = request.cookies.get('lang')
    if lang and lang in i18n.SUPPORTED_LANGUAGES:
        return lang

    # 3. Check Accept-Language header
    accept_lang = request.accept_languages.best_match(
        list(i18n.SUPPORTED_LANGUAGES.keys()),
        default=i18n.DEFAULT_LANGUAGE
    )
    if accept_lang:
        return i18n.normalize_language_code(accept_lang)

    return i18n.DEFAULT_LANGUAGE


def build_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # Ensure JSON responses keep Unicode data.
    app.config["JSON_AS_ASCII"] = False

    # Register i18n context processor
    @app.before_request
    def before_request():
        """Set current language in g before each request."""
        g.lang = get_current_language()

    @app.context_processor
    def inject_i18n():
        """Inject i18n functions and data into Jinja2 templates."""
        lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)

        def t(key, **kwargs):
            """Translation function for templates."""
            return i18n.get_translation(key, lang, **kwargs)

        return {
            't': t,
            'current_lang': lang,
            'available_languages': i18n.get_available_languages(),
            'supported_languages': i18n.SUPPORTED_LANGUAGES,
        }

    register_blueprints(app)
    register_default_routes(app)

    return app


def register_blueprints(app: Flask) -> None:
    """Register Flask blueprints."""
    app.register_blueprint(projects_bp, url_prefix="/api/projects")
    app.register_blueprint(translation_bp, url_prefix="/api/projects")
    app.register_blueprint(protected_bp, url_prefix="/api/projects")
    app.register_blueprint(sync_bp, url_prefix="/api/projects")
    app.register_blueprint(settings_bp, url_prefix="/api/settings")


def register_default_routes(app: Flask) -> None:
    """Register default health and index routes."""

    @app.get("/health")
    def health_check():
        logger.debug("Health check requested")
        return jsonify({"status": "ok"})

    @app.get("/")
    def home():
        projects = db.get_all_projects()
        return render_template(
            "index.html",
            title="CharTii-i18n",
            current_year=datetime.now().year,
            projects=projects,
        )

    @app.get("/projects/<int:project_id>/manage")
    def manage_project(project_id: int):
        # Ensure database schema integrity on page access
        # This is fast (just checking table structure) and ensures data consistency
        try:
            ensure_all_schemas()
        except Exception as e:
            logger.warning(f"Failed to ensure database schema integrity: {e}")
            # Continue anyway - don't block page access if schema check fails

        lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
        project = db.get_project_by_id(project_id)
        if not project:
            error_title = i18n.get_translation("errors.page_not_found_title", lang=lang)
            return render_template(
                "error.html",
                title=error_title,
                current_year=datetime.now().year,
                error_title=error_title,
                error_message=i18n.get_translation("api.errors.project_not_found", lang=lang),
                error_code=404,
            ), 404
        manage_text = i18n.get_translation("api.errors.manage", lang=lang)
        return render_template(
            "manage.html",
            title=f"{manage_text} {project['name']}",
            current_year=datetime.now().year,
            project_id=project_id,
            project_name=project["name"],
        )

    # Custom error handlers
    @app.errorhandler(404)
    def page_not_found(e):
        """Handle 404 errors with a friendly page."""
        lang = get_current_language()
        error_title = i18n.get_translation("errors.page_not_found_title", lang=lang)
        return render_template(
            "error.html",
            title=error_title,
            current_year=datetime.now().year,
            error_title=error_title,
            error_message=i18n.get_translation("errors.page_not_found_message", lang=lang),
            error_code=404,
        ), 404

    @app.errorhandler(500)
    def internal_error(e):
        """Handle 500 errors with a friendly page."""
        logger.exception("Internal server error: %s", e)
        lang = get_current_language()
        error_title = i18n.get_translation("errors.something_went_wrong", lang=lang)
        return render_template(
            "error.html",
            title=i18n.get_translation("errors.server_error_title", lang=lang),
            current_year=datetime.now().year,
            error_title=error_title,
            error_message=i18n.get_translation("errors.unexpected_error_occurred", lang=lang),
            error_code=500,
        ), 500




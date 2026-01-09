"""Settings management API routes."""

from __future__ import annotations

import json
import re
from typing import Any, Dict

from flask import Blueprint, jsonify, request, g
from pathlib import Path

import src.config as config
from src.config import (
    BUILTIN_PROVIDERS,
    BUILTIN_PROVIDER_DISPLAY_NAMES,
    PROVIDER_DEFAULTS,
    PROVIDER_NAME_PATTERN,
)
from src.core import database as db
from src.logger import get_logger, LOG_FILE, _clear_log_mode_cache
from src import i18n

settings_bp = Blueprint("settings", __name__)
logger = get_logger(__name__)


@settings_bp.get("/")
def get_settings():
    """Return current system configuration with default values merged."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    try:
        current_config = config.load_config()
        default_config = config.DEFAULT_CONFIG

        # Merge default URLs and models if not present in current config
        for provider in BUILTIN_PROVIDERS:
            if provider in current_config:
                provider_config = current_config[provider]
                default_provider = default_config.get(provider, {})

                # Set default API URL if not present or empty
                if not provider_config.get("api_url"):
                    provider_config["api_url"] = default_provider.get("api_url", "")

                # Set default models if not present or empty
                if not provider_config.get("models") or len(provider_config.get("models", [])) == 0:
                    provider_config["models"] = default_provider.get("models", [])
            else:
                # Provider config doesn't exist, use defaults
                current_config[provider] = default_config.get(provider, {}).copy()

        logger.debug("Settings retrieved with defaults merged")

        # Return config with meta information for frontend
        return jsonify({
            "config": current_config,
            "meta": {
                "builtin_providers": [
                    {"id": p, "name": BUILTIN_PROVIDER_DISPLAY_NAMES[p]}
                    for p in BUILTIN_PROVIDERS
                ],
                "provider_defaults": PROVIDER_DEFAULTS,
                "provider_name_pattern": PROVIDER_NAME_PATTERN
            }
        })
    except Exception as e:
        logger.error(f"Failed to retrieve settings: {e}")
        return jsonify({"error": i18n.get_translation("api.errors.failed_to_retrieve_settings", lang=lang)}), 500


@settings_bp.put("/")
def update_settings():
    """Update system configuration."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    try:
        data = request.get_json()
        if not data or "config" not in data:
            return jsonify({"error": i18n.get_translation("api.errors.config_missing", lang=lang)}), 400

        new_config = data["config"]

        # Validate configuration structure
        validation_error = validate_config(new_config)
        if validation_error:
            return jsonify({"error": validation_error}), 400

        # Merge with existing config to preserve any fields not in the request
        current_config = config.load_config()

        # Identify all providers (built-in and custom)
        top_level_keys = ["ai_provider", "log_mode", "translation"]
        
        # Deep merge provider configs to preserve api_url and other fields
        for provider in BUILTIN_PROVIDERS:
            if provider in new_config:
                if provider in current_config and isinstance(current_config[provider], dict):
                    # Preserve api_url from current config if not in new config
                    if "api_url" in current_config[provider] and "api_url" not in new_config[provider]:
                        new_config[provider]["api_url"] = current_config[provider]["api_url"]
                    # Merge provider config (update existing, preserve missing fields)
                    current_config[provider].update(new_config[provider])
                else:
                    # If provider config doesn't exist, use new config
                    current_config[provider] = new_config[provider]
        
        # Handle custom providers - add or update them
        for key, value in new_config.items():
            if (
                key not in BUILTIN_PROVIDERS
                and key not in top_level_keys
                and isinstance(value, dict)
                and "api_key" in value
            ):
                # This is a custom provider
                current_config[key] = value
        
        # Update top-level config keys (ai_provider, log_mode, etc.)
        for key in top_level_keys:
            if key in new_config:
                current_config[key] = new_config[key]
        
        # Update other top-level config fields not in top_level_keys
        # but preserve translation and other fields not in new_config
        for key, value in new_config.items():
            if key not in BUILTIN_PROVIDERS and key not in top_level_keys:
                # Skip custom providers (already handled above)
                if not (isinstance(value, dict) and "api_key" in value):
                    current_config[key] = value

        # Identify custom providers (not built-in, not top-level config keys)
        custom_providers = []
        for key in new_config.keys():
            if (
                key not in BUILTIN_PROVIDERS
                and key not in top_level_keys
                and isinstance(new_config[key], dict)
                and "api_key" in new_config[key]
            ):
                # Validate custom provider name
                if not re.match(PROVIDER_NAME_PATTERN, key):
                    return jsonify({"error": f"Invalid custom provider name: {key}. Only letters, numbers, hyphens, and underscores allowed."}), 400
                custom_providers.append(key)

        # Ensure provider-specific configs are properly structured
        if "ai_provider" in new_config:
            provider = new_config["ai_provider"]
            # Allow custom providers
            if provider not in BUILTIN_PROVIDERS and provider not in custom_providers:
                # Check if it's a valid custom provider name format
                if not re.match(PROVIDER_NAME_PATTERN, provider):
                    return jsonify({"error": f"Invalid AI provider: {provider}"}), 400
                # Provider name is valid format, but config might not be in new_config yet
                # This is okay if it's being selected from existing config

        # Validate all providers (built-in and custom)
        all_providers = list(BUILTIN_PROVIDERS) + custom_providers
        for provider in all_providers:
            if provider in new_config:
                provider_config = new_config[provider]
                if not isinstance(provider_config, dict):
                    return jsonify({"error": f"{provider} config must be an object"}), 400

                # Validate API URL if provided
                if "api_url" in provider_config:
                    api_url = provider_config["api_url"]
                    if api_url and not isinstance(api_url, str):
                        return jsonify({"error": f"{provider} api_url must be a string"}), 400

                # Validate models array (new format) - models are optional
                if "models" in provider_config:
                    models = provider_config["models"]
                    if not isinstance(models, list):
                        return jsonify({"error": f"{provider} models must be an array"}), 400
                    # Filter out empty strings (models are optional, so empty array is allowed)
                    models = [m for m in models if m and isinstance(m, str)]
                    if len(models) > 5:
                        return jsonify({"error": f"{provider} can have at most 5 models"}), 400
                    provider_config["models"] = models

                # Backward compatibility: convert 'model' to 'models' array
                elif "model" in provider_config:
                    model = provider_config.pop("model")
                    if model:
                        provider_config["models"] = [model]
                    else:
                        # Empty model is allowed - set to empty array
                        provider_config["models"] = []

                # Validate max_retries
                if "max_retries" in provider_config:
                    retries = provider_config["max_retries"]
                    if not isinstance(retries, int) or retries < 1:
                        return jsonify({"error": f"{provider} max_retries must be at least 1"}), 400

                # Validate timeout
                if "timeout" in provider_config:
                    timeout = provider_config["timeout"]
                    if not isinstance(timeout, (int, float)) or timeout <= 0:
                        return jsonify({"error": f"{provider} timeout must be a positive number"}), 400

        # Save configuration
        config.save_config(current_config)
        
        # Clear log mode cache to ensure new log mode takes effect
        _clear_log_mode_cache()
        
        logger.info("Settings updated successfully")

        return jsonify({"message": "Settings updated successfully", "config": current_config})
    except json.JSONDecodeError:
        return jsonify({"error": i18n.get_translation("api.errors.invalid_json", lang=lang)}), 400
    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        return jsonify({"error": i18n.get_translation("api.errors.failed_to_update_settings", lang=lang)}), 500


@settings_bp.delete("/logs")
def clear_logs():
    """Delete all log files to free up disk space."""
    lang = getattr(g, 'lang', i18n.DEFAULT_LANGUAGE)
    try:
        log_file = Path(LOG_FILE)
        deleted_count = 0
        
        # Delete the main log file
        if log_file.exists():
            log_file.unlink()
            deleted_count += 1
            logger.info("Log file deleted")
        
        # Delete any other log files in the logs directory
        log_dir = log_file.parent
        if log_dir.exists():
            for log_path in log_dir.glob("*.log"):
                if log_path.exists():
                    log_path.unlink()
                    deleted_count += 1
        
        if deleted_count > 0:
            return jsonify({"message": f"Successfully deleted {deleted_count} log file(s)"})
        else:
            return jsonify({"message": "No log files found to delete"})
    except Exception as e:
        logger.error(f"Failed to delete logs: {e}")
        return jsonify({"error": i18n.get_translation("api.errors.failed_to_delete_logs", lang=lang)}), 500


def validate_config(config_dict: Dict[str, Any]) -> str | None:
    """Validate configuration structure and return error message if invalid."""
    if not isinstance(config_dict, dict):
        return "Configuration must be an object"

    # Check for required top-level structure
    if "ai_provider" in config_dict:
        provider = config_dict["ai_provider"]
        # Allow built-in providers or custom providers with valid names
        if provider not in BUILTIN_PROVIDERS:
            # Check if it's a valid custom provider name format
            if not re.match(PROVIDER_NAME_PATTERN, provider):
                return f"Invalid AI provider name: {provider}. Only letters, numbers, hyphens, and underscores allowed."

    return None


@settings_bp.get("/translations")
def get_translations():
    """Return translations for the requested language (for frontend JavaScript)."""
    try:
        lang = request.args.get("lang", i18n.DEFAULT_LANGUAGE)
        translations = i18n.get_all_translations(lang)
        return jsonify({
            "translations": translations,
            "lang": lang,
            "available_languages": i18n.get_available_languages()
        })
    except Exception as e:
        logger.error(f"Failed to load translations: {e}")
        return jsonify({"error": "Failed to load translations", "translations": {}}), 500



import json
from pathlib import Path
from typing import Dict, Any

from src.core import database as db
from src.core.schema import initialize_database
from src.logger import get_logger

logger = get_logger(__name__)

# Translation configuration constants
DEFAULT_CHUNK_SIZE_WORDS = 300  # Maximum words per batch for translation
DEFAULT_SYSTEM_MESSAGE = "You are a professional translator. Return only valid JSON."

# Provider configuration constants
BUILTIN_PROVIDERS = ["openai", "deepseek", "gemini"]

BUILTIN_PROVIDER_DISPLAY_NAMES = {
    "openai": "OpenAI",
    "deepseek": "DeepSeek",
    "gemini": "Gemini"
}

PROVIDER_DEFAULTS = {
    "max_retries": 3,
    "timeout": 120
}

PROVIDER_NAME_PATTERN = r"^[a-zA-Z0-9_-]+$"

# Get base directory (project root)
BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Default prompts
DEFAULT_PROMPTS = {
    "array_translation_prompt": {
        "version": "1.0",
        "description": "Array translation prompt for translate_array method",
        "prompt": """You are a professional translator specializing in i18n locale content translation.

Translate each string from {source_language_name} ({source_language_code}) to {target_language_name} ({target_language_code}). Return ONLY a JSON array with the translated strings in the same order.
{context_section}

CRITICAL REQUIREMENTS:
- Preserve ALL placeholders EXACTLY as they appear, including:
  * Variable placeholders: __VAR_0__, __VAR_1__, etc. (DO NOT translate or modify these)
  * Protected term placeholders: __PROT_0__, __PROT_1__, etc. (DO NOT translate or modify these)
  * Original variable patterns: {{name}}, ${{var}}, %s, %d, etc. (if any remain, keep them unchanged)
- Maintain the original tone and style
- Return exactly {text_count} translated strings
- Do not add, remove, or modify any placeholders

Array to translate:
{texts_json}

Return format: ["translated1", "translated2", ...]
Do not include explanations, markdown code blocks, or any text outside the JSON array. Return ONLY the JSON array."""
    }
}

# Default configuration templates
DEFAULT_CONFIG = {
    "ai_provider": "openai",
    "openai": {
        "api_key": "YOUR_API_KEY_HERE",
        "models": ["gpt-5-mini", "gpt-5", "gpt-4o-mini", "gpt-4o"],  # Up to 5 models, first is default
        "max_retries": 3,
        "timeout": 120,
        "api_url": "https://api.openai.com/v1/chat/completions"
    },
    "deepseek": {
        "api_key": "YOUR_API_KEY_HERE",
        "models": ["deepseek-chat"],  # Up to 5 models, first is default
        "max_retries": 3,
        "timeout": 120,
        "api_url": "https://api.deepseek.com/chat/completions"
    },
    "gemini": {
        "api_key": "YOUR_API_KEY_HERE",
        "models": ["gemini-2.5-flash"],  # Up to 5 models, first is default
        "max_retries": 3,
        "timeout": 120,
        "api_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    },
    "translation": {
        "preserve_variables": True,
        "variable_patterns": [
            r"\{[^}]+\}",
            r"\$\{[^}]+\}",
            r"%[sd]",
            r"{{[^}]+}}"
        ]
    },
    "log_mode": "off"
}

def ensure_config_directory():
    """Ensure the config directory exists."""
    CONFIG_DIR.mkdir(exist_ok=True)
    logger.debug(f"Config directory ensured: {CONFIG_DIR}")

def create_default_config():
    """Create the default config.json file."""
    ensure_config_directory()
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
    logger.info(f"Created default config file: {CONFIG_FILE}")

def initialize_app():
    """
    Initialize the application.
    This function is called on first run or when performing a factory reset.
    It creates the database and default configuration in database.
    """
    logger.info("Initializing application...")

    # Initialize database
    initialize_database()
    logger.info("Database initialized")

    # Initialize default configuration in database if not exists
    try:
        existing_config = db.get_app_config('config')
        if not existing_config:
            logger.info("No config in database, initializing default config")
            save_config(DEFAULT_CONFIG)
            logger.info("Default configuration saved to database")
        else:
            logger.debug("Config already exists in database")
    except Exception as e:
        logger.error(f"Failed to check/initialize config in database: {e}")
        logger.warning("Attempting to save default config anyway...")
        try:
            save_config(DEFAULT_CONFIG)
            logger.info("Default configuration saved to database after error")
        except Exception as save_error:
            logger.error(f"Failed to save default config: {save_error}")
            logger.warning("Application will use in-memory default configuration")

    logger.info("Application initialization complete")


def load_config() -> Dict[str, Any]:
    """Load the configuration from database."""
    try:
        config_json = db.get_app_config('config')
        if config_json:
            config = json.loads(config_json)
            logger.debug("Configuration loaded from database")
            return config
        else:
            # No config in database, use defaults and save to database
            logger.info("No config in database, using defaults and saving to database")
            config = DEFAULT_CONFIG.copy()
            try:
                save_config(config)
                logger.info("Default configuration saved to database successfully")
            except Exception as save_error:
                logger.error(f"Failed to save default config to database: {save_error}")
                logger.warning("Returning default configuration without saving")
            return config
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse config from database: {e}")
        logger.warning("Using default configuration")
        # Try to save default config to fix corrupted data
        try:
            config = DEFAULT_CONFIG.copy()
            save_config(config)
            logger.info("Saved default configuration to replace corrupted data")
        except Exception:
            pass
        return DEFAULT_CONFIG.copy()
    except Exception as e:
        logger.error(f"Failed to load config from database: {e}")
        logger.warning("Using default configuration")
        # Try to save default config
        try:
            config = DEFAULT_CONFIG.copy()
            save_config(config)
            logger.info("Saved default configuration after error")
        except Exception:
            pass
        return DEFAULT_CONFIG.copy()

def save_config(config: Dict[str, Any]):
    """Save the configuration to database."""
    try:
        config_json = json.dumps(config, ensure_ascii=False)
        db.set_app_config('config', config_json)
        logger.info("Configuration saved to database")
    except Exception as e:
        logger.error(f"Failed to save config to database: {e}")
        raise

def load_prompts() -> Dict[str, Any]:
    """Load the prompts from default configuration.
    
    Note: Prompts are hardcoded in the codebase and should not be saved to database.
    This function always returns the default prompts.
    """
    return DEFAULT_PROMPTS.copy()

def get_prompt(prompt_name: str = "array_translation_prompt") -> Dict[str, Any]:
    """Get a specific prompt by name."""
    prompts = load_prompts()
    return prompts.get(prompt_name, DEFAULT_PROMPTS.get(prompt_name, DEFAULT_PROMPTS["array_translation_prompt"]))

def factory_reset():
    """
    Perform a factory reset.
    WARNING: This will delete all data and reset to defaults.
    """
    logger.warning("Performing factory reset...")

    # Delete database
    from src.core.database import DB_FILE
    if DB_FILE.exists():
        DB_FILE.unlink()
        logger.info("Database deleted")

    # Reinitialize
    initialize_app()
    logger.info("Factory reset complete")

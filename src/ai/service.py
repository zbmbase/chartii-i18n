"""
AI Translation Service Module

This module provides the main AI service for translation:
- AIService class for coordinating translations
- Configuration validation
- Error handling and retry logic

For provider-specific API implementations, see ai/providers.py
"""

import json
import time
from typing import List, Dict, Any, Tuple, Optional

from src.config import load_config, get_prompt, DEFAULT_SYSTEM_MESSAGE
from src.logger import get_logger
from src import language_codes as lc
from src.ai.exceptions import TranslationError

logger = get_logger(__name__)


def validate_ai_config(provider_override: Optional[str] = None) -> None:
    """
    Validate that AI provider configuration is properly set up.

    Args:
        provider_override: Optional provider to validate instead of the default.

    Raises:
        TranslationError: If configuration is invalid or missing, with code and details.
    """
    config = load_config()
    provider = provider_override if provider_override else config.get('ai_provider', 'gemini')

    built_in_providers = ['openai', 'deepseek', 'gemini']

    # Check if provider is built-in or custom
    if provider not in built_in_providers:
        # Custom provider - check if it exists in config
        if provider not in config or not isinstance(config.get(provider), dict):
            raise TranslationError(
                f"Custom AI provider '{provider}' configuration not found",
                code="ai_config_missing",
                details={"provider": provider}
            )

    provider_config = config.get(provider, {})
    if not provider_config:
        raise TranslationError(
            f"AI provider '{provider}' configuration not found",
            code="ai_config_missing",
            details={"provider": provider}
        )

    api_key = provider_config.get('api_key', '')
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        provider_display = provider.replace('-', ' ').title() if provider not in built_in_providers else provider.capitalize()
        raise TranslationError(
            f"{provider_display} API key not configured. Please set it in Settings.",
            code="ai_config_missing",
            details={"provider": provider, "missing_field": "api_key"}
        )

    # Check for models array (new format) or model field (legacy)
    models = provider_config.get('models', [])
    model = provider_config.get('model', '')
    if not models and not model:
        provider_display = provider.replace('-', ' ').title() if provider not in built_in_providers else provider.capitalize()
        raise TranslationError(
            f"{provider_display} model not configured",
            code="ai_config_missing",
            details={"provider": provider, "missing_field": "models"}
        )
    # Check that at least one valid model exists
    if models and isinstance(models, list):
        valid_models = [m for m in models if m and isinstance(m, str)]
        if not valid_models:
            provider_display = provider.replace('-', ' ').title() if provider not in built_in_providers else provider.capitalize()
            raise TranslationError(
                f"{provider_display} model not configured",
                code="ai_config_missing",
                details={"provider": provider, "missing_field": "models"}
            )


class AIService:
    """AI service for translation."""

    def __init__(self, model_override: Optional[str] = None, provider_override: Optional[str] = None):
        self.config = load_config()
        # Use provider_override if specified, otherwise use config default
        self.provider = provider_override if provider_override else self.config.get('ai_provider', 'gemini')
        self.model_override = model_override
        self.translation_config = self.config.get('translation', {})
        # Token usage tracking
        self._last_token_usage = {'prompt_tokens': 0, 'completion_tokens': 0}
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        if model_override or provider_override:
            logger.info(f"Initialized AI service with provider: {self.provider}, model override: {model_override}")
        else:
            logger.info(f"Initialized AI service with provider: {self.provider}")

    def _get_model(self, provider_config: Dict[str, Any], default_model: str = "") -> str:
        """
        Get the model to use for translation.

        Priority:
        1. model_override (if set)
        2. First model from 'models' array
        3. 'model' field (legacy)
        4. default_model
        """
        if self.model_override:
            return self.model_override

        # Try models array first (new format)
        models = provider_config.get('models', [])
        if models and isinstance(models, list) and models[0]:
            return models[0]

        # Fall back to model field (legacy)
        return provider_config.get('model', default_model)

    def get_last_token_usage(self) -> Dict[str, int]:
        """Get token usage from the last API call."""
        return self._last_token_usage.copy()

    def get_total_token_usage(self) -> Dict[str, int]:
        """Get accumulated token usage."""
        return {
            'prompt_tokens': self.total_prompt_tokens,
            'completion_tokens': self.total_completion_tokens,
        }

    def accumulate_tokens(self):
        """Add last call's tokens to total."""
        self.total_prompt_tokens += self._last_token_usage.get('prompt_tokens', 0)
        self.total_completion_tokens += self._last_token_usage.get('completion_tokens', 0)

    def _get_system_message(self, default: str = DEFAULT_SYSTEM_MESSAGE) -> str:
        """Get system message from config or use default."""
        return self.translation_config.get('system_message', default)

    def translate_array(
        self,
        texts: List[str],
        source_language: str,
        target_language: str,
        context: str = ""
    ) -> List[str]:
        """
        Translate a simple array of strings.

        On failure, returns original strings (graceful degradation).

        Args:
            texts: List of strings to translate
            source_language: Source language code
            target_language: Target language code
            context: Optional context

        Returns:
            List of translated strings (same order as input)
        """
        if not texts:
            return []

        logger.debug(f"Starting array translation: {len(texts)} strings from {source_language} to {target_language}")

        # Build simple array prompt
        prompt = self._build_array_prompt(texts, source_language, target_language, context)
        logger.debug(f"  Input to AI (prompt):\n{prompt}")

        max_retries = self.config.get(self.provider, {}).get('max_retries', 3)
        last_error = None

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(f"  Retry attempt {attempt + 1}/{max_retries}")

                # Call API and get text response
                response_text = self._call_ai_api_text(prompt)
                logger.debug(f"  Output from AI (response):\n{response_text}")

                # Parse with fallback strategies
                from src.translation.utils import parse_translations_response
                translations = parse_translations_response(response_text, expected_count=len(texts))

                if translations is not None:
                    # Validate count
                    if len(translations) != len(texts):
                        logger.warning(f"Translation count mismatch: expected {len(texts)}, got {len(translations)}")
                        # Pad or truncate to match
                        if len(translations) < len(texts):
                            translations.extend(texts[len(translations):])
                        translations = translations[:len(texts)]

                    logger.info(f"Successfully translated {len(translations)} strings")
                    return translations

                # Parse failed, will retry
                raise TranslationError("Could not parse translations from response")

            except Exception as e:
                last_error = e
                should_retry, wait_time = self._categorize_error(e, attempt)

                if should_retry and attempt < max_retries - 1:
                    logger.warning(f"  Attempt {attempt + 1} failed: {e}. Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                elif not should_retry:
                    logger.error(f"  Non-recoverable error: {e}")
                    break

        # All retries failed - return original texts (graceful fallback)
        logger.warning(f"Translation failed after {max_retries} attempts. Returning original texts.")
        return texts

    def _build_array_prompt(
        self,
        texts: List[str],
        source_language: str,
        target_language: str,
        context: str
    ) -> str:
        """Build simple array translation prompt using configured template."""
        # Get language names for better AI understanding
        source_language_name = lc.get_language_name(source_language) or source_language
        target_language_name = lc.get_language_name(target_language) or target_language

        # Get prompt template
        prompt_template = get_prompt('array_translation_prompt')['prompt']

        # Build context section
        context_section = f"\nProject context: {context}" if context else ""

        # Format the prompt
        prompt = prompt_template.format(
            source_language_name=source_language_name,
            source_language_code=source_language,
            target_language_name=target_language_name,
            target_language_code=target_language,
            context_section=context_section,
            text_count=len(texts),
            texts_json=json.dumps(texts, ensure_ascii=False)
        )

        return prompt

    def _call_ai_api_text(self, prompt: str) -> str:
        """
        Call AI API and return raw text response.
        Works with any provider without requiring structured outputs.
        """
        from src.ai.providers import (
            call_gemini_api,
            call_openai_api_text,
            call_deepseek_api_text,
            call_custom_provider_api_text,
        )

        built_in_providers = ['openai', 'deepseek', 'gemini']

        if self.provider == 'gemini':
            return call_gemini_api(self, prompt)
        elif self.provider == 'openai':
            return call_openai_api_text(self, prompt)
        elif self.provider == 'deepseek':
            return call_deepseek_api_text(self, prompt)
        elif self.provider not in built_in_providers:
            # Custom provider - use OpenAI-compatible API format
            return call_custom_provider_api_text(self, prompt)
        else:
            raise TranslationError(f"Unsupported AI provider: {self.provider}")

    def _categorize_error(self, error: Exception, attempt: int) -> Tuple[bool, float]:
        """
        Categorize an error and determine retry strategy.

        Returns:
            Tuple of (should_retry, wait_time_seconds)
        """
        error_str = str(error).lower()

        # Rate limiting (429) - long backoff
        if '429' in str(error) or 'rate limit' in error_str or 'too many requests' in error_str:
            wait_time = 30 * (2 ** attempt)  # 30s, 60s, 120s
            return True, min(wait_time, 300)  # Max 5 minutes

        # Authentication errors (401, 403) - don't retry
        if '401' in str(error) or '403' in str(error) or 'unauthorized' in error_str or 'forbidden' in error_str:
            return False, 0

        # Invalid request (400) - don't retry
        if '400' in str(error) and ('invalid' in error_str or 'bad request' in error_str):
            return False, 0

        # Server errors (5xx) - standard backoff
        if any(code in str(error) for code in ['500', '502', '503', '504']):
            wait_time = 2 ** attempt
            return True, wait_time

        # Timeout - retry with backoff
        if 'timeout' in error_str:
            wait_time = 5 * (2 ** attempt)  # 5s, 10s, 20s
            return True, wait_time

        # Parse errors - retry once
        if 'parse' in error_str or 'json' in error_str:
            return attempt < 1, 1.0

        # Unknown errors - standard backoff
        return True, 2 ** attempt

"""
AI Provider API Implementations

This module contains the API call implementations for each AI provider:
- Gemini
- OpenAI
- DeepSeek
- Custom providers (OpenAI-compatible)

Each function takes an AIService instance and a prompt, returns the text response.
"""

from typing import Any
import httpx

from src.logger import get_logger
from src.ai.exceptions import TranslationError

logger = get_logger(__name__)


def get_httpx_timeout(timeout_config: Any) -> httpx.Timeout:
    """
    Convert timeout configuration to httpx.Timeout object.

    Args:
        timeout_config: Either a number (total timeout) or a dict with
            connect, write, read, pool keys

    Returns:
        httpx.Timeout object
    """
    if isinstance(timeout_config, dict):
        return httpx.Timeout(
            connect=timeout_config.get('connect', 10.0),
            write=timeout_config.get('write', 60.0),
            read=timeout_config.get('read', 120.0),
            pool=timeout_config.get('pool', 10.0),
        )
    else:
        timeout_value = float(timeout_config) if timeout_config else 120.0
        return httpx.Timeout(
            connect=10.0,
            write=60.0,
            read=timeout_value,
            pool=10.0,
        )


def handle_http_error(e: httpx.HTTPStatusError, provider: str):
    """Handle HTTP errors with detailed messages."""
    status_code = e.response.status_code
    error_text = "Unknown error"

    try:
        error_json = e.response.json()
        if isinstance(error_json, dict) and "error" in error_json:
            error_detail = error_json["error"]
            if isinstance(error_detail, dict):
                error_text = error_detail.get("message", str(error_detail))
            else:
                error_text = str(error_detail)
    except Exception:
        error_text = e.response.text[:500] if hasattr(e.response, 'text') else "No details"

    raise TranslationError(f"{provider} API error ({status_code}): {error_text}")


def call_gemini_api(service, prompt: str) -> str:
    """Call Gemini API."""
    provider_config = service.config['gemini']
    api_key = provider_config['api_key']
    model = service._get_model(provider_config, 'gemini-2.0-flash')
    timeout = provider_config.get('timeout', 120)

    if api_key == "YOUR_API_KEY_HERE":
        raise TranslationError("Gemini API key not configured. Please set it in config/config.json")

    # Build API URL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    # Build request body
    body = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }],
        "generationConfig": {
            "maxOutputTokens": 8192,
        }
    }

    logger.debug(f"Calling Gemini API: {model}")

    try:
        httpx_timeout = get_httpx_timeout(timeout)
        with httpx.Client(timeout=httpx_timeout) as client:
            response = client.post(url, json=body)
            response.raise_for_status()

            result = response.json()

            # Extract token usage from Gemini API
            usage_metadata = result.get('usageMetadata', {})

            if usage_metadata:
                logger.debug(f"Gemini usageMetadata: {usage_metadata}")

            prompt_tokens = usage_metadata.get('promptTokenCount', 0)
            completion_tokens = usage_metadata.get('candidatesTokenCount', 0)

            # Fallback: calculate from total if candidatesTokenCount is missing
            if completion_tokens == 0 and prompt_tokens > 0:
                total_tokens = usage_metadata.get('totalTokenCount', 0)
                if total_tokens > prompt_tokens:
                    completion_tokens = total_tokens - prompt_tokens
                    logger.debug(f"Calculated completion_tokens from total: {completion_tokens}")

            service._last_token_usage = {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
            }

            if prompt_tokens > 0 or completion_tokens > 0:
                logger.debug(f"Gemini token usage extracted: prompt={prompt_tokens}, completion={completion_tokens}")
            else:
                logger.warning(f"Gemini token usage not found. usageMetadata keys: {list(usage_metadata.keys()) if usage_metadata else 'None'}")
                logger.debug(f"Gemini response keys: {list(result.keys())}")

            service.accumulate_tokens()

            # Extract text from response
            if 'candidates' in result and len(result['candidates']) > 0:
                candidate = result['candidates'][0]
                if 'content' in candidate and 'parts' in candidate['content']:
                    text = candidate['content']['parts'][0].get('text', '')
                    return text

            raise TranslationError(f"Unexpected Gemini API response format: {result}")

    except httpx.HTTPStatusError as e:
        logger.error(f"Gemini API HTTP error: {e.response.status_code} - {e.response.text}")
        raise TranslationError(f"Gemini API error: {e.response.status_code}")
    except httpx.TimeoutException:
        raise TranslationError("Gemini API request timeout")
    except Exception as e:
        logger.error(f"Gemini API call failed: {e}")
        raise TranslationError(f"Gemini API call failed: {e}")


def call_openai_api_text(service, prompt: str) -> str:
    """
    Call OpenAI API and return text response (without structured outputs).
    This works with more models and is more resilient.
    """
    provider_config = service.config['openai']
    api_key = provider_config['api_key']
    model = service._get_model(provider_config, 'gpt-4o-mini')
    timeout = provider_config.get('timeout', 120)
    api_url = provider_config.get('api_url', 'https://api.openai.com/v1/chat/completions')

    if api_key == "YOUR_API_KEY_HERE":
        raise TranslationError("OpenAI API key not configured")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    system_message = service._get_system_message()

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ],
    }

    logger.debug(f"  Calling OpenAI API (text mode, model: {model})...")

    try:
        httpx_timeout = get_httpx_timeout(timeout)
        with httpx.Client(timeout=httpx_timeout) as client:
            response = client.post(api_url, headers=headers, json=body)
            response.raise_for_status()

            result = response.json()

            # Extract token usage
            usage = result.get('usage', {})
            service._last_token_usage = {
                'prompt_tokens': usage.get('prompt_tokens', 0),
                'completion_tokens': usage.get('completion_tokens', 0),
            }
            service.accumulate_tokens()

            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message'].get('content', '')
                logger.debug(f"  Received {len(content)} chars from OpenAI (tokens: {service._last_token_usage})")
                return content

            raise TranslationError("No content in OpenAI response")

    except httpx.HTTPStatusError as e:
        handle_http_error(e, "OpenAI")
    except httpx.TimeoutException:
        raise TranslationError("OpenAI API request timeout")
    except Exception as e:
        raise TranslationError(f"OpenAI API call failed: {e}")


def call_deepseek_api_text(service, prompt: str) -> str:
    """Call DeepSeek API and return text response."""
    provider_config = service.config.get('deepseek', {})
    api_key = provider_config.get('api_key', '')
    model = service._get_model(provider_config, 'deepseek-chat')
    timeout = 120
    api_url = provider_config.get('api_url', 'https://api.deepseek.com/v1/chat/completions')

    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise TranslationError("DeepSeek API key not configured")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    system_message = service._get_system_message()

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ],
    }

    logger.debug(f"  Calling DeepSeek API (model: {model})...")

    try:
        httpx_timeout = get_httpx_timeout(timeout)
        with httpx.Client(timeout=httpx_timeout) as client:
            response = client.post(api_url, headers=headers, json=body)
            response.raise_for_status()

            result = response.json()

            # Extract token usage
            usage = result.get('usage', {})
            service._last_token_usage = {
                'prompt_tokens': usage.get('prompt_tokens', 0),
                'completion_tokens': usage.get('completion_tokens', 0),
            }
            service.accumulate_tokens()

            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message'].get('content', '')
                logger.debug(f"  Received {len(content)} chars from DeepSeek (tokens: {service._last_token_usage})")
                return content

            raise TranslationError("No content in DeepSeek response")

    except httpx.HTTPStatusError as e:
        handle_http_error(e, "DeepSeek")
    except httpx.TimeoutException:
        raise TranslationError("DeepSeek API request timeout")
    except Exception as e:
        raise TranslationError(f"DeepSeek API call failed: {e}")


def call_custom_provider_api_text(service, prompt: str) -> str:
    """Call custom provider API using OpenAI-compatible format."""
    provider = service.provider
    provider_config = service.config.get(provider, {})
    api_key = provider_config.get('api_key', '')
    model = service._get_model(provider_config, '')
    timeout = provider_config.get('timeout', 120)
    api_url = provider_config.get('api_url', '')

    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise TranslationError(f"Custom provider '{provider}' API key not configured")

    if not api_url:
        raise TranslationError(f"Custom provider '{provider}' API URL not configured")

    if not model:
        raise TranslationError(f"Custom provider '{provider}' model not configured")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    system_message = service._get_system_message()

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ],
    }

    logger.debug(f"  Calling custom provider '{provider}' API (model: {model}, url: {api_url})...")

    try:
        httpx_timeout = get_httpx_timeout(timeout)
        with httpx.Client(timeout=httpx_timeout) as client:
            response = client.post(api_url, headers=headers, json=body)
            response.raise_for_status()

            result = response.json()

            # Extract token usage (if available)
            usage = result.get('usage', {})
            service._last_token_usage = {
                'prompt_tokens': usage.get('prompt_tokens', 0),
                'completion_tokens': usage.get('completion_tokens', 0),
            }
            service.accumulate_tokens()

            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message'].get('content', '')
                logger.debug(f"  Received {len(content)} chars from custom provider '{provider}' (tokens: {service._last_token_usage})")
                return content

            raise TranslationError(f"No content in custom provider '{provider}' response")

    except httpx.HTTPStatusError as e:
        handle_http_error(e, f"Custom provider '{provider}'")
    except httpx.TimeoutException:
        raise TranslationError(f"Custom provider '{provider}' API request timeout")
    except Exception as e:
        raise TranslationError(f"Custom provider '{provider}' API call failed: {e}")

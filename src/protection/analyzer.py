"""
Protected Terms AI Analyzer Module

This module handles AI-based analysis of source strings to identify protected terms.
Supports multiple AI providers: Gemini, OpenAI, DeepSeek, and custom providers.

For core protection functions, see protection/terms.py
"""

import json
import random
import re
from typing import Dict, List
import httpx

from src.core import database as db
from src.logger import get_logger
from src.config import load_config

logger = get_logger(__name__)

# Regex pattern to match variable placeholders
VARIABLE_PATTERN = re.compile(
    r'\{[^}]+\}|'           # {name}, {0}, {count}
    r'__[A-Z0-9_]+__|'      # __VAR_0__, __NAME__
    r'%[sd]|'               # %s, %d
    r'%\([^)]+\)[sd]|'      # %(name)s, %(count)d
    r'\$\{[^}]+\}|'         # ${variable}
    r'\{\{[^}]+\}\}'        # {{variable}}
)


def _filter_variables(text: str) -> str:
    """Remove variable placeholders from text."""
    return VARIABLE_PATTERN.sub('', text).strip()


def _merge_results(results: List[Dict[str, List[str]]]) -> Dict[str, List[str]]:
    """Merge multiple analysis results into one, removing duplicates."""
    merged = {'brand': [], 'technical': [], 'url': [], 'code': []}
    for result in results:
        for key in merged:
            merged[key].extend(result.get(key, []))
    # Remove duplicates
    for key in merged:
        merged[key] = list(set(term.strip() for term in merged[key] if term and term.strip()))
    return merged


def analyze_protected_terms(project_id: int, provider: str = None, model_override: str = None) -> Dict[str, List[str]]:
    """
    Use AI to analyze source strings and identify protected terms.

    Args:
        project_id: The project ID to analyze
        provider: Optional provider name (openai, deepseek, gemini)
        model_override: Optional model name to use instead of default

    Returns:
        Dict with category keys and lists of terms:
        {
            'brand': ['CharTii-i18n', 'OpenAI'],
            'technical': ['API', 'JSON'],
            'url': ['example.com'],
            'code': ['onClick', 'className']
        }
    """
    logger.info("=" * 60)
    logger.info(f"[STEP 1] Starting protected terms analysis for project {project_id}")

    # Get all source strings
    all_strings = db.get_all_strings_for_project(project_id)
    logger.info(f"[STEP 2] Retrieved {len(all_strings)} source strings from database")

    if not all_strings:
        logger.warning("[STEP 2] No source strings found for analysis")
        return {'brand': [], 'technical': [], 'url': [], 'code': []}

    # Prepare strings for AI:
    # 1. Limit to first 500 characters of each
    # 2. Filter out variable placeholders
    # 3. Remove empty strings after filtering
    source_texts = []
    for s in all_strings:
        text = s['source_text'][:500]
        filtered = _filter_variables(text)
        if filtered:  # Only add non-empty strings
            source_texts.append(filtered)

    logger.info(f"[STEP 3] Prepared {len(source_texts)} strings after filtering variables (max 500 chars each)")

    # Sample if too many strings (max 300)
    if len(source_texts) > 300:
        source_texts = random.sample(source_texts, 300)
        logger.info(f"[STEP 3] Sampled 300 strings for analysis")

    # Split into batches of 100 for better accuracy
    batch_size = 100
    batches = [source_texts[i:i + batch_size] for i in range(0, len(source_texts), batch_size)]
    logger.info(f"[STEP 4] Split into {len(batches)} batches of up to {batch_size} strings each")

    # Process each batch and collect results
    all_results = []
    for batch_idx, batch in enumerate(batches, 1):
        logger.info(f"[STEP 5] Processing batch {batch_idx}/{len(batches)} ({len(batch)} strings)")

        # Build analysis prompt for this batch
        prompt = _build_analysis_prompt(batch)
        logger.info(f"[STEP 5] Batch {batch_idx} prompt ({len(prompt)} characters)")
        logger.debug(f"[STEP 5] Prompt content:\n{'-' * 40}\n{prompt}\n{'-' * 40}")

        # Call AI
        try:
            result = _call_ai_for_analysis(prompt, provider=provider, model_override=model_override)
            batch_terms = sum(len(v) for v in result.values())
            logger.info(f"[STEP 5] Batch {batch_idx} completed: {batch_terms} terms found")
            logger.info(f"[STEP 5] Batch {batch_idx} results: {json.dumps(result, ensure_ascii=False)}")
            all_results.append(result)
        except Exception as e:
            logger.error(f"[STEP 5] Batch {batch_idx} failed: {e}")
            # Continue with other batches even if one fails

    # Merge all batch results
    if not all_results:
        logger.error("[STEP 6] All batches failed, returning empty result")
        logger.info("=" * 60)
        return {'brand': [], 'technical': [], 'url': [], 'code': []}

    merged_result = _merge_results(all_results)
    total_terms = sum(len(v) for v in merged_result.values())
    logger.info(f"[STEP 6] AI analysis completed: {total_terms} unique terms found across all batches")
    logger.info(f"[STEP 6] Final results: {json.dumps(merged_result, ensure_ascii=False, indent=2)}")
    logger.info("=" * 60)
    return merged_result


def _build_analysis_prompt(source_texts: List[str]) -> str:
    """Build the analysis prompt for AI."""

    # Format as JSON array
    strings_json = json.dumps(source_texts, ensure_ascii=False, indent=2)

    prompt = f"""You are a professional localization expert.
Your job is to read the source text below and identify terms that should NOT be translated (must remain exactly as they are).

### CATEGORIES
1. **brand**: Product names and company names.
2. **technical**: Technical terms, acronyms, and file extensions.
3. **url**: Web addresses, domains, and emails.
4. **code**: Variable names, function names, and code syntax.

### RULES
1. **Strict Matching:** Only list terms exactly as they appear in the text.
2. **No Guessing:** If a category has no matches, return an empty list.

### SOURCE TEXT
{strings_json}

### OUTPUT FORMAT
Return ONLY a valid JSON object.
{{
  "brand": [],
  "technical": [],
  "url": [],
  "code": []
}}"""

    return prompt


def _call_ai_for_analysis(prompt: str, provider: str = None, model_override: str = None) -> Dict[str, List[str]]:
    """Call AI API to analyze protected terms."""
    config = load_config()

    # Use provided provider, or fall back to config default
    if not provider:
        provider = config.get('ai_provider', 'gemini')

    logger.info(f"[STEP 5] Using AI provider: {provider}, model: {model_override or 'default'}")

    built_in_providers = ['openai', 'deepseek', 'gemini']

    if provider == 'gemini':
        return _call_gemini_for_analysis(prompt, config, model_override=model_override)
    elif provider == 'openai':
        return _call_openai_for_analysis(prompt, config, model_override=model_override)
    elif provider == 'deepseek':
        return _call_deepseek_for_analysis(prompt, config, model_override=model_override)
    elif provider not in built_in_providers:
        # Custom provider - use OpenAI-compatible format
        return _call_custom_provider_for_analysis(prompt, config, provider, model_override=model_override)
    else:
        raise ValueError(f"Unsupported AI provider: {provider}")


def _call_gemini_for_analysis(prompt: str, config: Dict, model_override: str = None) -> Dict[str, List[str]]:
    """Call Gemini API for analysis."""
    provider_config = config.get('gemini', {})
    api_key = provider_config.get('api_key', '')
    models = provider_config.get('models', [])
    model = model_override if model_override else (models[0] if models else 'gemini-1.5-flash')
    timeout = provider_config.get('timeout', 120)

    if api_key == 'YOUR_API_KEY_HERE' or not api_key:
        raise ValueError("Gemini API key not configured")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    body = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "maxOutputTokens": 2048,
        }
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=body)
            response.raise_for_status()

            result = response.json()

            if 'candidates' in result and len(result['candidates']) > 0:
                candidate = result['candidates'][0]
                if 'content' in candidate and 'parts' in candidate['content']:
                    text = candidate['content']['parts'][0].get('text', '')
                    return _parse_analysis_response(text)

            raise ValueError(f"Unexpected Gemini API response format: {result}")

    except httpx.HTTPStatusError as e:
        raise ValueError(f"Gemini API error: {e.response.status_code}")
    except Exception as e:
        raise ValueError(f"Gemini API call failed: {e}")


def _call_openai_for_analysis(prompt: str, config: Dict, model_override: str = None) -> Dict[str, List[str]]:
    """Call OpenAI API for analysis."""
    provider_config = config.get('openai', {})
    api_key = provider_config.get('api_key', '')
    models = provider_config.get('models', [])
    model = model_override if model_override else (models[0] if models else 'gpt-4o-mini')
    timeout = provider_config.get('timeout', 120)
    api_url = provider_config.get('api_url', 'https://api.openai.com/v1/chat/completions')

    if api_key == 'YOUR_API_KEY_HERE' or not api_key:
        raise ValueError("OpenAI API key not configured")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a conservative term analyzer. Only identify terms with high confidence."},
            {"role": "user", "content": prompt}
        ],
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(api_url, headers=headers, json=body)
            response.raise_for_status()

            result = response.json()

            if 'choices' in result and len(result['choices']) > 0:
                text = result['choices'][0]['message']['content']
                return _parse_analysis_response(text)

            raise ValueError(f"Unexpected OpenAI API response format: {result}")

    except httpx.HTTPStatusError as e:
        raise ValueError(f"OpenAI API error: {e.response.status_code}")
    except Exception as e:
        raise ValueError(f"OpenAI API call failed: {e}")


def _call_deepseek_for_analysis(prompt: str, config: Dict, model_override: str = None) -> Dict[str, List[str]]:
    """Call DeepSeek API for analysis."""
    provider_config = config.get('deepseek', {})
    api_key = provider_config.get('api_key', '')
    models = provider_config.get('models', [])
    model = model_override if model_override else (models[0] if models else 'deepseek-chat')
    timeout = provider_config.get('timeout', 120)
    api_url = provider_config.get('api_url', 'https://api.deepseek.com/v1/chat/completions')

    if api_key == 'YOUR_API_KEY_HERE' or not api_key:
        raise ValueError("DeepSeek API key not configured")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a conservative term analyzer. Only identify terms with high confidence."},
            {"role": "user", "content": prompt}
        ],
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(api_url, headers=headers, json=body)
            response.raise_for_status()

            result = response.json()

            if 'choices' in result and len(result['choices']) > 0:
                text = result['choices'][0]['message']['content']
                return _parse_analysis_response(text)

            raise ValueError(f"Unexpected DeepSeek API response format: {result}")

    except httpx.HTTPStatusError as e:
        raise ValueError(f"DeepSeek API error: {e.response.status_code}")
    except Exception as e:
        raise ValueError(f"DeepSeek API call failed: {e}")


def _call_custom_provider_for_analysis(prompt: str, config: Dict, provider: str, model_override: str = None) -> Dict[str, List[str]]:
    """Call custom provider API for analysis using OpenAI-compatible format."""
    provider_config = config.get(provider, {})
    api_key = provider_config.get('api_key', '')
    models = provider_config.get('models', [])
    model = model_override if model_override else (models[0] if models else '')
    timeout = provider_config.get('timeout', 120)
    api_url = provider_config.get('api_url', '')

    if api_key == 'YOUR_API_KEY_HERE' or not api_key:
        raise ValueError(f"Custom provider '{provider}' API key not configured")

    if not api_url:
        raise ValueError(f"Custom provider '{provider}' API URL not configured")

    if not model:
        raise ValueError(f"Custom provider '{provider}' model not configured")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a conservative term analyzer. Only identify terms with high confidence."},
            {"role": "user", "content": prompt}
        ],
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(api_url, headers=headers, json=body)
            response.raise_for_status()

            result = response.json()

            if 'choices' in result and len(result['choices']) > 0:
                text = result['choices'][0]['message']['content']
                return _parse_analysis_response(text)

            raise ValueError(f"Unexpected custom provider '{provider}' API response format: {result}")

    except httpx.HTTPStatusError as e:
        raise ValueError(f"Custom provider '{provider}' API error: {e.response.status_code}")
    except Exception as e:
        raise ValueError(f"Custom provider '{provider}' API call failed: {e}")


def _parse_analysis_response(response_text: str) -> Dict[str, List[str]]:
    """Parse AI response into categorized terms."""
    # Clean up the response
    text = response_text.strip()

    # Remove markdown code blocks if present
    if text.startswith('```'):
        lines = text.split('\n')
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].startswith('```'):
            lines = lines[:-1]
        text = '\n'.join(lines).strip()

    # Parse JSON
    try:
        result = json.loads(text)

        # Validate structure
        expected_keys = {'brand', 'technical', 'url', 'code'}
        if not isinstance(result, dict):
            raise ValueError("Response is not a JSON object")

        # Ensure all expected keys exist
        for key in expected_keys:
            if key not in result:
                result[key] = []
            elif not isinstance(result[key], list):
                result[key] = []

        # Remove duplicates and empty strings
        for key in expected_keys:
            result[key] = list(set(term.strip() for term in result[key] if term and term.strip()))

        logger.debug(f"Parsed {sum(len(v) for v in result.values())} protected terms")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        logger.debug(f"Response text: {text[:500]}")
        return {'brand': [], 'technical': [], 'url': [], 'code': []}

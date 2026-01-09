"""
Translation Manager Module

Main TranslationManager class that coordinates the translation workflow:
- Identify missing translations
- Translate using AI (with retry mechanism)
- Update database
- Generate files
"""

import time
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path

from src.core import database as db
from src.core import validation
from src.ai.service import AIService
from src.protection import apply_protection, restore_protection, get_all_protected_terms_flat
from src.logger import get_logger
import src.language_codes as lc
from src.config import DEFAULT_CHUNK_SIZE_WORDS, load_config

from src.translation.progress import TranslationProgress
from src.translation.validator import (
    extract_variables,
    validate_native_variables_preserved,
    is_translation_valid,
    validate_translation_result,
)
from src.translation.processor import (
    translate_chunks_sequential_with_progress,
    translate_chunks_sequential,
    replace_variables_with_placeholders,
    restore_variables_from_placeholders,
)

logger = get_logger(__name__)


class TranslationManager:
    """
    Manages automated translation workflows.

    Features:
    - Translates all missing translations for all target languages
    - Retry mechanism for failed translations (up to 3 attempts)
    - Progress tracking and callbacks
    - Automatic file generation after completion
    """

    def __init__(self, project_id: int):
        """
        Initialize translation manager.

        Args:
            project_id: The project ID to manage
        """
        self.project_id = project_id
        self.failed_items: List[Dict[str, Any]] = []
        self.start_time: Optional[float] = None

        # Get project info
        self.project = db.get_project_by_id(project_id)
        if not self.project:
            raise ValueError(f"Project {project_id} not found")

        # Protected terms will be filtered by key_path during translation
        logger.info("Protected terms will be filtered by key_path during translation")

        # Load translation config for variable patterns
        self.translation_config = load_config().get('translation', {})

    def get_translation_summary(self) -> Dict[str, Any]:
        """
        Get a summary of translation status for the project.

        Returns:
            Dict with translation summary for all languages
        """
        all_stats = validation.get_all_translation_stats(self.project_id)

        languages_info = []
        for stats in all_stats:
            languages_info.append({
                'code': stats.language_code,
                'name': stats.language_name,
                'total': stats.total_strings,
                'translated': stats.translated_count,
                'missing': stats.missing_count,
                'completeness': stats.completeness_percent,
                'is_complete': stats.is_complete
            })

        is_all_complete = validation.is_project_complete(self.project_id)

        return {
            'project_id': self.project_id,
            'project_name': self.project['name'],
            'source_language': self.project['source_language'],
            'total_languages': len(all_stats),
            'complete_languages': sum(1 for stats in all_stats if stats.is_complete),
            'is_all_complete': is_all_complete,
            'languages': languages_info
        }

    def _resolve_target_languages(self, requested: Optional[List[str]]) -> List[str]:
        """Resolve target languages from requested list or discover incomplete ones."""
        source_language = self.project.get("source_language")

        if requested:
            normalised: List[str] = []
            for code in requested:
                if not isinstance(code, str):
                    continue
                trimmed = code.strip()
                if not trimmed:
                    continue
                if lc.languages_match(trimmed, source_language):
                    continue
                if trimmed not in normalised:
                    normalised.append(trimmed)
            if normalised:
                return normalised

        stats = validation.get_all_translation_stats(self.project_id)
        auto_languages = [
            stat.language_code
            for stat in stats
            if not stat.is_complete and not lc.languages_match(stat.language_code, source_language)
        ]
        return auto_languages

    def _get_tasks_for_language(
        self, language_code: str, mode: str = "missing_only", include_locked: bool = False
    ) -> List[Dict[str, Any]]:
        """Get translation tasks for a specific language based on mode."""
        with db.get_connection() as conn:
            conn.row_factory = db.sqlite3.Row
            cursor = conn.cursor()

            # Build WHERE clause based on mode
            if mode == "missing_only":
                status_condition = "t.string_id IS NULL"
            elif mode == "missing_and_ai":
                status_condition = "(t.string_id IS NULL OR t.status = 'ai_translated')"
            elif mode == "full":
                if include_locked:
                    status_condition = "1=1"
                else:
                    status_condition = "(t.string_id IS NULL OR t.status != 'locked')"
            else:
                status_condition = "t.string_id IS NULL"

            query = f"""
                SELECT s.id, s.key_path, s.source_text
                FROM strings s
                LEFT JOIN translations t
                    ON s.id = t.string_id AND t.language_code = ?
                WHERE s.project_id = ?
                  AND s.should_translate = 1
                  AND ({status_condition})
                ORDER BY s.sort_order, s.id
            """

            cursor.execute(query, (language_code, self.project_id))
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def _get_task_statistics(
        self, language_code: str, mode: str = "missing_only", include_locked: bool = False
    ) -> Dict[str, int]:
        """Get statistics for tasks by mode."""
        with db.get_connection() as conn:
            cursor = conn.cursor()

            stats = {
                "missing_count": 0,
                "ai_count": 0,
                "locked_count": 0,
                "total_tasks": 0,
            }

            # Count missing entries
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM strings s
                LEFT JOIN translations t
                    ON s.id = t.string_id AND t.language_code = ?
                WHERE s.project_id = ?
                  AND s.should_translate = 1
                  AND t.string_id IS NULL
            """, (language_code, self.project_id))
            stats["missing_count"] = cursor.fetchone()[0] or 0

            # Count AI-generated entries
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM strings s
                INNER JOIN translations t
                    ON s.id = t.string_id AND t.language_code = ?
                WHERE s.project_id = ?
                  AND s.should_translate = 1
                  AND t.status = 'ai_translated'
            """, (language_code, self.project_id))
            stats["ai_count"] = cursor.fetchone()[0] or 0

            # Count locked entries
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM strings s
                INNER JOIN translations t
                    ON s.id = t.string_id AND t.language_code = ?
                WHERE s.project_id = ?
                  AND s.should_translate = 1
                  AND t.status = 'locked'
            """, (language_code, self.project_id))
            stats["locked_count"] = cursor.fetchone()[0] or 0

            # Get total tasks based on mode
            if mode == "missing_only":
                stats["total_tasks"] = stats["missing_count"]
            elif mode == "missing_and_ai":
                stats["total_tasks"] = stats["missing_count"] + stats["ai_count"]
            elif mode == "full":
                if include_locked:
                    cursor.execute("""
                        SELECT COUNT(*) as count
                        FROM strings s
                        WHERE s.project_id = ?
                          AND s.should_translate = 1
                    """, (self.project_id,))
                    stats["total_tasks"] = cursor.fetchone()[0] or 0
                else:
                    cursor.execute("""
                        SELECT COUNT(*) as count
                        FROM strings s
                        LEFT JOIN translations t
                            ON s.id = t.string_id AND t.language_code = ?
                        WHERE s.project_id = ?
                          AND s.should_translate = 1
                          AND (t.string_id IS NULL OR t.status != 'locked')
                    """, (language_code, self.project_id))
                    stats["total_tasks"] = cursor.fetchone()[0] or 0
            else:
                stats["total_tasks"] = stats["missing_count"]

            return stats

    def _extract_variables(self, text: str) -> set:
        """Extract all variables from text using configured patterns."""
        patterns = self.translation_config.get('variable_patterns', [])
        return extract_variables(text, patterns)

    def _validate_native_variables_preserved(
        self, source: str, translation: str
    ) -> tuple:
        """Check if all variables from source are preserved in translation."""
        patterns = self.translation_config.get('variable_patterns', [])
        return validate_native_variables_preserved(source, translation, patterns)

    def _is_translation_valid(
        self,
        source_text: str,
        translated_text: str,
        source_lang: str,
        target_lang: str,
        protected_vars: Optional[Dict[str, str]] = None,
        variable_placeholders: Optional[Dict[str, str]] = None,
        key_path: Optional[str] = None,
    ) -> tuple:
        """Unified validation for all translation validation needs."""
        import src.protection as pt
        return is_translation_valid(
            source_text=source_text,
            translated_text=translated_text,
            source_lang=source_lang,
            target_lang=target_lang,
            protected_vars=protected_vars,
            variable_placeholders=variable_placeholders,
            key_path=key_path,
            project_id=self.project_id,
            protected_terms_module=pt,
        )

    def _validate_translation_result(
        self,
        source_text: str,
        translated_text: str,
        source_lang: str,
        target_lang: str,
        protected_vars: Optional[Dict[str, str]] = None,
        variable_placeholders: Optional[Dict[str, str]] = None,
        key_path: Optional[str] = None,
    ) -> tuple:
        """Validate translation result in the translation pipeline."""
        return self._is_translation_valid(
            source_text=source_text,
            translated_text=translated_text,
            source_lang=source_lang,
            target_lang=target_lang,
            protected_vars=protected_vars,
            variable_placeholders=variable_placeholders,
            key_path=key_path,
        )

    def _replace_variables_with_placeholders(self, text: str) -> tuple:
        """Replace variables in text with placeholders for fallback translation."""
        preserve = self.translation_config.get('preserve_variables', True)
        patterns = self.translation_config.get('variable_patterns', [])
        return replace_variables_with_placeholders(text, patterns, preserve)

    def _restore_variables_from_placeholders(self, text: str, placeholder_map: Dict[str, str]) -> str:
        """Restore original variables from placeholders after fallback translation."""
        return restore_variables_from_placeholders(text, placeholder_map)

    def _build_result(
        self,
        translated_count: int,
        failure_count: int,
        generated_files: Dict[str, str],
        cancelled: bool = False,
        token_usage: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """Build the result dictionary."""
        elapsed_time = time.time() - self.start_time if self.start_time else 0

        result = {
            "success": failure_count == 0 and not cancelled,
            "total_translated": translated_count,
            "total_failed": failure_count,
            "failed_items": self.failed_items,
            "generated_files": generated_files,
            "elapsed_time": elapsed_time,
        }

        if token_usage:
            result["token_usage"] = token_usage

        if cancelled:
            result["cancelled"] = True

        logger.info(
            "Translation %s in %.1f seconds (success=%d, failed=%d%s)",
            "cancelled" if cancelled else "completed",
            elapsed_time,
            translated_count,
            failure_count,
            f", tokens: {token_usage}" if token_usage else "",
        )

        return result

    def translate_all_missing_chunked(
        self,
        progress_callback: Optional[Callable[[TranslationProgress], None]] = None,
        target_languages: Optional[List[str]] = None,
        mode: str = "missing_only",
        include_locked: bool = False,
        generate_files: bool = True,
        cancel_check: Optional[Callable[[], bool]] = None,
        model_override: Optional[str] = None,
        chunk_size_words: Optional[int] = None,
        ai_provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Translate all missing translations using chunked approach.

        This method uses a chunked translation approach:
        1. Collect all texts for a language
        2. Chunk by word count
        3. Translate chunks sequentially
        4. Graceful fallback on failure (return original text)

        Args:
            progress_callback: Optional callback for progress updates
            target_languages: Optional list of languages to translate
            mode: Translation mode (missing_only, missing_and_ai, full)
            include_locked: Whether to include locked translations
            generate_files: Whether to generate output files
            cancel_check: Optional function to check for cancellation
            model_override: Optional specific model to use instead of default
            chunk_size_words: Optional chunk size in words
            ai_provider: Optional AI provider to use

        Returns:
            Dict with results including success status, counts, and generated files
        """
        # Import here to avoid circular imports
        from src.translation.utils import chunk_with_keys
        import src.project.generator as file_generator

        logger.info(f"Starting chunked translation for project {self.project_id}")
        if model_override:
            logger.info(f"Using model override: {model_override}")
        if ai_provider:
            logger.info(f"Using AI provider: {ai_provider}")
        self.start_time = time.time()
        self.failed_items = []

        languages = self._resolve_target_languages(target_languages)
        total_languages = len(languages)

        processed_items = 0
        translated_count = 0
        failure_count = 0
        generated_files: Dict[str, str] = {}
        total_items = 0

        # Initialize AI service
        ai_service = AIService(model_override=model_override, provider_override=ai_provider)
        source_language = self.project["source_language"]
        context = self.project.get("translation_context", "")
        locales_path = Path(self.project["locales_path"])

        # Track token usage per language and total
        token_usage_by_language: Dict[str, Dict[str, int]] = {}
        total_token_usage = {"prompt_tokens": 0, "completion_tokens": 0}

        # Process each language completely before moving to the next
        for lang_idx, lang_code in enumerate(languages):
            # Check for cancellation
            if cancel_check and cancel_check():
                logger.info("Translation cancelled by user request")
                return self._build_result(translated_count, failure_count, generated_files, cancelled=True, token_usage=total_token_usage)

            lang_name = lc.get_language_name(lang_code) or lang_code

            # Phase 1: Send "checking" progress
            logger.info(f"Checking {lang_name} ({lang_code}) for pending translations...")
            if progress_callback:
                progress = TranslationProgress(
                    current_language=lang_code,
                    current_language_name=lang_name,
                    total_languages=total_languages,
                    completed_languages=lang_idx,
                    current_item=processed_items,
                    total_items=total_items,
                    current_key="",
                    current_text="",
                    success_count=translated_count,
                    failure_count=failure_count,
                    current_batch=0,
                    total_batches=0,
                    batch_keys_count=0,
                    phase="checking",
                )
                if progress_callback(progress):
                    return self._build_result(translated_count, failure_count, generated_files, cancelled=True)

            # Phase 2: Check for pending tasks
            tasks = self._get_tasks_for_language(lang_code, mode=mode, include_locked=include_locked)

            # Get language statistics for briefing
            try:
                lang_stats = validation.get_translation_stats(self.project_id, lang_code)
                total_keys = lang_stats.total_strings
                completed_keys = lang_stats.translated_count
                missing_keys = lang_stats.missing_count
            except Exception as e:
                logger.warning(f"Failed to get stats for {lang_code}: {e}")
                total_keys = len(tasks) if tasks else 0
                completed_keys = 0
                missing_keys = len(tasks) if tasks else 0

            # Send "checked" phase with statistics
            logger.info(f"Checked {lang_name} ({lang_code}): Total: {total_keys}, Completed: {completed_keys}, Missing: {missing_keys}")
            if progress_callback:
                progress = TranslationProgress(
                    current_language=lang_code,
                    current_language_name=lang_name,
                    total_languages=total_languages,
                    completed_languages=lang_idx,
                    current_item=processed_items,
                    total_items=total_keys,
                    current_key="",
                    current_text="",
                    success_count=completed_keys,
                    failure_count=missing_keys,
                    current_batch=0,
                    total_batches=0,
                    batch_keys_count=0,
                    phase="checked",
                    mode=mode,
                )
                if progress_callback(progress):
                    return self._build_result(translated_count, failure_count, generated_files, cancelled=True)

            if not tasks:
                # No tasks for this language
                logger.info(f"No pending translations for {lang_code}")
                logger.info(f"All translations complete for {lang_name} ({lang_code})")

                task_stats = self._get_task_statistics(lang_code, mode=mode, include_locked=include_locked)

                # Send "no_work" progress
                if progress_callback:
                    progress = TranslationProgress(
                        current_language=lang_code,
                        current_language_name=lang_name,
                        total_languages=total_languages,
                        completed_languages=lang_idx,
                        current_item=processed_items,
                        total_items=total_items,
                        current_key="",
                        current_text="",
                        success_count=translated_count,
                        failure_count=failure_count,
                        current_batch=0,
                        total_batches=0,
                        batch_keys_count=0,
                        phase="no_work",
                        missing_count=task_stats["missing_count"],
                        ai_count=task_stats["ai_count"],
                        locked_count=task_stats["locked_count"],
                        total_tasks=task_stats["total_tasks"],
                        mode=mode,
                    )
                    if progress_callback(progress):
                        return self._build_result(translated_count, failure_count, generated_files, cancelled=True)

                # Generate file for this language
                if generate_files:
                    try:
                        logger.info(f"Generating language file for {lang_name} ({lang_code})...")
                        output_path = locales_path / f"{lang_code}.json"
                        file_generator.generate_language_file(self.project_id, lang_code, output_path)
                        generated_files[lang_code] = str(output_path)
                        logger.info(f"Generated file for {lang_code}: {output_path}")

                        if progress_callback:
                            progress = TranslationProgress(
                                current_language=lang_code,
                                current_language_name=lang_name,
                                total_languages=total_languages,
                                completed_languages=lang_idx + 1,
                                current_item=processed_items,
                                total_items=total_items,
                                current_key="",
                                current_text="",
                                success_count=translated_count,
                                failure_count=failure_count,
                                current_batch=0,
                                total_batches=0,
                                batch_keys_count=0,
                                phase="file_generated",
                            )
                            progress_callback(progress)
                    except Exception as e:
                        logger.error(f"Failed to generate file for {lang_code}: {e}")

                # Send "completed" phase for no_work case
                if progress_callback:
                    progress = TranslationProgress(
                        current_language=lang_code,
                        current_language_name=lang_name,
                        total_languages=total_languages,
                        completed_languages=lang_idx + 1,
                        current_item=processed_items,
                        total_items=total_items,
                        current_key="",
                        current_text="",
                        success_count=0,
                        failure_count=0,
                        current_batch=0,
                        total_batches=0,
                        batch_keys_count=0,
                        phase="completed",
                    )
                    progress_callback(progress)

                continue

            # Has tasks - proceed with translation
            total_items += len(tasks)
            tasks_count = len(tasks)

            task_stats = self._get_task_statistics(lang_code, mode=mode, include_locked=include_locked)

            # Send "tasks_found" phase
            logger.info(f"Found {tasks_count} keys to translate for {lang_name} ({lang_code})")
            if progress_callback:
                progress = TranslationProgress(
                    current_language=lang_code,
                    current_language_name=lang_name,
                    total_languages=total_languages,
                    completed_languages=lang_idx,
                    current_item=processed_items,
                    total_items=tasks_count,
                    current_key="",
                    current_text="",
                    success_count=0,
                    failure_count=0,
                    current_batch=0,
                    total_batches=0,
                    batch_keys_count=0,
                    phase="tasks_found",
                    missing_count=task_stats["missing_count"],
                    ai_count=task_stats["ai_count"],
                    locked_count=task_stats["locked_count"],
                    total_tasks=task_stats["total_tasks"],
                    mode=mode,
                )
                if progress_callback(progress):
                    return self._build_result(translated_count, failure_count, generated_files, cancelled=True)

            logger.info(f"Starting translation for {lang_name} ({lang_code}) - {tasks_count} items")

            # Record token usage before translation
            lang_token_start = ai_service.get_total_token_usage()

            # Prepare texts with protected terms and variables
            key_text_pairs: List[tuple] = []
            protected_maps: Dict[str, Dict[str, str]] = {}
            variable_maps: Dict[str, set] = {}
            string_id_map: Dict[str, int] = {}

            for task in tasks:
                key_path = task["key_path"]
                source_text = task["source_text"]
                string_id_map[key_path] = task["id"]

                # Apply protected terms (filtered by key_path)
                filtered_protected_terms = get_all_protected_terms_flat(
                    self.project_id, key_path=key_path
                )
                if filtered_protected_terms:
                    protected_text, placeholder_map = apply_protection(source_text, filtered_protected_terms)
                    if placeholder_map:
                        protected_maps[key_path] = placeholder_map
                else:
                    protected_text = source_text

                # Keep native variables (do NOT replace with placeholders on first attempt)
                final_text = protected_text

                # Detect variables for later validation
                source_variables = self._extract_variables(source_text)
                if source_variables:
                    variable_maps[key_path] = source_variables
                    logger.debug(f"Detected {len(source_variables)} variables in: {source_text[:50]}...")

                key_text_pairs.append((key_path, final_text))

            # Chunk by word count
            chunk_size = chunk_size_words if chunk_size_words is not None else DEFAULT_CHUNK_SIZE_WORDS
            chunks = chunk_with_keys(key_text_pairs, max_words=chunk_size)
            total_batches = len(chunks)
            logger.info(f"Split into {total_batches} chunks for {lang_name} ({lang_code}) (chunk size: {chunk_size} words)")

            # Send "starting" progress
            logger.info(f"Starting translation for {lang_name} ({lang_code}) - {len(tasks)} items in {total_batches} batches")
            if progress_callback:
                progress = TranslationProgress(
                    current_language=lang_code,
                    current_language_name=lang_name,
                    total_languages=total_languages,
                    completed_languages=lang_idx,
                    current_item=processed_items,
                    total_items=total_items,
                    current_key="",
                    current_text="",
                    success_count=translated_count,
                    failure_count=failure_count,
                    current_batch=0,
                    total_batches=total_batches,
                    batch_keys_count=0,
                    phase="starting",
                )
                if progress_callback(progress):
                    return self._build_result(translated_count, failure_count, generated_files, cancelled=True)

            # Translate chunks sequentially
            chunk_results = translate_chunks_sequential_with_progress(
                chunks=chunks,
                source_lang=source_language,
                target_lang=lang_code,
                context=context,
                ai_service=ai_service,
                cancel_check=cancel_check,
                progress_callback=progress_callback,
                lang_code=lang_code,
                lang_name=lang_name,
                total_languages=total_languages,
                completed_languages=lang_idx,
                total_batches=total_batches,
                processed_items=processed_items,
                total_items=total_items,
                translated_count=translated_count,
                failure_count=failure_count,
            )

            # Process results: validate and collect failed items for retry
            valid_translations: List[Dict[str, Any]] = []
            failed_validations: List[Dict[str, Any]] = []
            placeholder_fallback_items: List[Dict[str, Any]] = []

            for chunk_idx, (chunk, translated_texts) in enumerate(zip(chunks, chunk_results)):
                for (key_path, original_text), translated_text in zip(chunk, translated_texts):
                    if cancel_check and cancel_check():
                        return self._build_result(translated_count, failure_count, generated_files, cancelled=True)

                    original_source = next(
                        (t["source_text"] for t in tasks if t["key_path"] == key_path),
                        original_text
                    )

                    protected_vars = protected_maps.get(key_path)
                    source_variables = variable_maps.get(key_path)

                    # Restore protected terms
                    restored_text = translated_text
                    if protected_vars:
                        restored_text = restore_protection(restored_text, protected_vars)

                    # Basic validation
                    is_valid, error_reason = self._validate_translation_result(
                        source_text=original_source,
                        translated_text=restored_text,
                        source_lang=source_language,
                        target_lang=lang_code,
                        protected_vars=protected_vars,
                        variable_placeholders=None,
                        key_path=key_path,
                    )

                    if not is_valid:
                        logger.warning(f"[INVALID] {key_path}: {error_reason}")
                        failed_validations.append({
                            "key_path": key_path,
                            "string_id": string_id_map[key_path],
                            "original_text": original_source,
                            "protected_text": original_text,
                            "protected_vars": protected_vars,
                            "source_variables": source_variables,
                            "error_reason": error_reason,
                        })
                        continue

                    # Native variable validation
                    if source_variables:
                        vars_valid, vars_error = self._validate_native_variables_preserved(
                            original_source, restored_text
                        )
                        if not vars_valid:
                            logger.warning(f"[FALLBACK] {key_path}: {vars_error}, will retry with placeholders")
                            placeholder_fallback_items.append({
                                "key_path": key_path,
                                "string_id": string_id_map[key_path],
                                "original_text": original_source,
                                "protected_vars": protected_vars,
                                "source_variables": source_variables,
                            })
                            continue

                    # All validations passed
                    logger.debug(f"[VALID] {key_path}: translation passed all checks")
                    valid_translations.append({
                        "key_path": key_path,
                        "string_id": string_id_map[key_path],
                        "translated_text": restored_text,
                        "original_text": original_source,
                    })

            # Placeholder fallback: retry items where native variables were lost
            if placeholder_fallback_items:
                logger.info(f"Processing {len(placeholder_fallback_items)} items with placeholder fallback method")
                for idx, item in enumerate(placeholder_fallback_items):
                    key_path = item["key_path"]
                    source_text = item["original_text"]

                    protected_text, var_map = self._replace_variables_with_placeholders(source_text)
                    logger.debug(f"Fallback for {key_path}: replacing {len(var_map)} variables with placeholders")

                    protected_vars = item.get("protected_vars", {})
                    if protected_vars:
                        for placeholder, term in protected_vars.items():
                            protected_text = protected_text.replace(term, placeholder)

                    try:
                        translated_texts = ai_service.translate_array(
                            [protected_text], source_language, lang_code, context
                        )
                        translated = translated_texts[0] if translated_texts else ""
                    except Exception as e:
                        logger.error(f"Fallback translation failed for {key_path}: {e}")
                        failure_count += 1
                        continue

                    restored = self._restore_variables_from_placeholders(translated, var_map)
                    if protected_vars:
                        restored = restore_protection(restored, protected_vars)

                    is_valid, error_reason = self._validate_translation_result(
                        source_text=source_text,
                        translated_text=restored,
                        source_lang=source_language,
                        target_lang=lang_code,
                        protected_vars=protected_vars,
                        variable_placeholders=var_map,
                        key_path=key_path,
                    )

                    if is_valid:
                        valid_translations.append({
                            "key_path": key_path,
                            "string_id": item["string_id"],
                            "translated_text": restored,
                            "original_text": source_text,
                        })
                        logger.info(f"✓ Fallback succeeded for {key_path}")
                    else:
                        logger.warning(f"Fallback validation failed for {key_path}: {error_reason}")
                        failure_count += 1

            # Retry failed validations once
            if failed_validations:
                logger.info(f"Retrying {len(failed_validations)} failed validations for {lang_code}")

                if progress_callback:
                    progress = TranslationProgress(
                        current_language=lang_code,
                        current_language_name=lang_name,
                        total_languages=total_languages,
                        completed_languages=lang_idx,
                        current_item=processed_items,
                        total_items=total_items,
                        current_key="",
                        current_text="",
                        success_count=translated_count,
                        failure_count=failure_count,
                        current_batch=0,
                        total_batches=total_batches,
                        batch_keys_count=0,
                        phase="retrying",
                        retry_keys_count=len(failed_validations),
                    )
                    if progress_callback(progress):
                        return self._build_result(translated_count, failure_count, generated_files, cancelled=True)

                retry_pairs = [(item["key_path"], item["protected_text"]) for item in failed_validations]
                chunk_size = chunk_size_words if chunk_size_words is not None else DEFAULT_CHUNK_SIZE_WORDS
                retry_chunks = chunk_with_keys(retry_pairs, max_words=chunk_size)

                retry_results = translate_chunks_sequential(
                    chunks=retry_chunks,
                    source_lang=source_language,
                    target_lang=lang_code,
                    context=context,
                    ai_service=ai_service,
                    cancel_check=cancel_check,
                )

                retry_idx = 0
                for retry_chunk, retry_translated in zip(retry_chunks, retry_results):
                    if cancel_check and cancel_check():
                        return self._build_result(translated_count, failure_count, generated_files, cancelled=True)

                    for (key_path, _), new_translation in zip(retry_chunk, retry_translated):
                        item = failed_validations[retry_idx]
                        retry_idx += 1

                        protected_vars = item.get("protected_vars")
                        source_variables = item.get("source_variables")
                        restored_text = new_translation
                        if protected_vars:
                            restored_text = restore_protection(restored_text, protected_vars)

                        is_valid, error_reason = self._validate_translation_result(
                            source_text=item["original_text"],
                            translated_text=restored_text,
                            source_lang=source_language,
                            target_lang=lang_code,
                            protected_vars=protected_vars,
                            variable_placeholders=None,
                            key_path=key_path,
                        )

                        if is_valid and source_variables:
                            vars_valid, vars_error = self._validate_native_variables_preserved(
                                item["original_text"], restored_text
                            )
                            if not vars_valid:
                                is_valid = False
                                error_reason = vars_error

                        if is_valid:
                            valid_translations.append({
                                "key_path": key_path,
                                "string_id": item["string_id"],
                                "translated_text": restored_text,
                                "original_text": item["original_text"],
                            })
                            logger.info(f"✓ Retry succeeded for {key_path}")
                        else:
                            failure_count += 1
                            self.failed_items.append({
                                "language_code": lang_code,
                                "language_name": lang_name,
                                "key_path": key_path,
                                "source_text": item["original_text"],
                                "error": f"validation_failed:{error_reason}",
                            })
                            logger.error(f"✗ Retry failed for {key_path}: {error_reason}")

            # Send "saving" phase
            lang_success_count = len(valid_translations)
            lang_failure_count = len(failed_validations) - sum(
                1 for item in failed_validations
                if any(v["key_path"] == item["key_path"] for v in valid_translations)
            )
            if progress_callback:
                progress = TranslationProgress(
                    current_language=lang_code,
                    current_language_name=lang_name,
                    total_languages=total_languages,
                    completed_languages=lang_idx,
                    current_item=processed_items,
                    total_items=total_items,
                    current_key="",
                    current_text="",
                    success_count=lang_success_count,
                    failure_count=lang_failure_count,
                    current_batch=0,
                    total_batches=total_batches,
                    batch_keys_count=0,
                    phase="saving",
                )
                if progress_callback(progress):
                    return self._build_result(translated_count, failure_count, generated_files, cancelled=True)

            # Save valid translations to database
            for item in valid_translations:
                if cancel_check and cancel_check():
                    return self._build_result(translated_count, failure_count, generated_files, cancelled=True)

                processed_items += 1
                if progress_callback:
                    elapsed = time.time() - self.start_time
                    avg_time = elapsed / max(processed_items, 1)
                    remaining = (total_items - processed_items) * avg_time

                    progress = TranslationProgress(
                        current_language=lang_code,
                        current_language_name=lang_name,
                        total_languages=total_languages,
                        completed_languages=lang_idx,
                        current_item=processed_items,
                        total_items=total_items,
                        current_key=item["key_path"],
                        current_text=item["original_text"],
                        success_count=translated_count,
                        failure_count=failure_count,
                        estimated_time_remaining=remaining,
                        phase="saving",
                    )
                    if progress_callback(progress):
                        return self._build_result(translated_count, failure_count, generated_files, cancelled=True)

                try:
                    db.create_translation(
                        string_id=item["string_id"],
                        language_code=lang_code,
                        translated_text=item["translated_text"],
                        status="ai_translated",
                    )
                    translated_count += 1
                    logger.debug(f"✓ Saved translation for {item['key_path']}")
                except Exception as e:
                    failure_count += 1
                    self.failed_items.append({
                        "language_code": lang_code,
                        "language_name": lang_name,
                        "key_path": item["key_path"],
                        "source_text": item["original_text"],
                        "error": str(e),
                    })
                    logger.error(f"✗ Failed to save translation for {item['key_path']}: {e}")

            # Calculate token usage for this language
            lang_token_end = ai_service.get_total_token_usage()
            lang_token_usage = {
                "prompt_tokens": lang_token_end["prompt_tokens"] - lang_token_start["prompt_tokens"],
                "completion_tokens": lang_token_end["completion_tokens"] - lang_token_start["completion_tokens"],
            }

            token_usage_by_language[lang_code] = lang_token_usage
            total_token_usage["prompt_tokens"] += lang_token_usage["prompt_tokens"]
            total_token_usage["completion_tokens"] += lang_token_usage["completion_tokens"]

            lang_final_success = sum(1 for item in valid_translations
                                    if not any(f["key_path"] == item["key_path"]
                                               for f in self.failed_items if f["language_code"] == lang_code))
            lang_final_failure = len(tasks) - lang_final_success

            logger.info(f"Translation completed for {lang_name} ({lang_code}): {lang_final_success} succeeded, {lang_final_failure} failed (tokens: {lang_token_usage})")

            lang_failed_items = [
                item for item in self.failed_items
                if item.get("language_code") == lang_code
            ]

            if progress_callback:
                progress = TranslationProgress(
                    current_language=lang_code,
                    current_language_name=lang_name,
                    total_languages=total_languages,
                    completed_languages=lang_idx + 1,
                    current_item=processed_items,
                    total_items=total_items,
                    current_key="",
                    current_text="",
                    success_count=lang_final_success,
                    failure_count=lang_final_failure,
                    current_batch=0,
                    total_batches=total_batches,
                    batch_keys_count=0,
                    phase="completed",
                    token_usage=lang_token_usage,
                    failed_items=lang_failed_items if lang_failed_items else None,
                )
                progress_callback(progress)

            # Generate file for this language
            if generate_files:
                try:
                    logger.info(f"Generating language file for {lang_name} ({lang_code}) after translation...")
                    output_path = locales_path / f"{lang_code}.json"
                    file_generator.generate_language_file(self.project_id, lang_code, output_path)
                    generated_files[lang_code] = str(output_path)
                    logger.info(f"Generated file for {lang_code}: {output_path}")

                    if progress_callback:
                        progress = TranslationProgress(
                            current_language=lang_code,
                            current_language_name=lang_name,
                            total_languages=total_languages,
                            completed_languages=lang_idx + 1,
                            current_item=processed_items,
                            total_items=total_items,
                            current_key="",
                            current_text="",
                            success_count=translated_count,
                            failure_count=failure_count,
                            current_batch=0,
                            total_batches=0,
                            batch_keys_count=0,
                            phase="file_generated",
                        )
                        progress_callback(progress)
                except Exception as e:
                    logger.error(f"Failed to generate file for {lang_code}: {e}")

        return self._build_result(translated_count, failure_count, generated_files, token_usage=total_token_usage)

    def validate_and_clear_invalid(
        self,
        target_languages: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[TranslationProgress], bool]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """
        Validate all existing translations and clear invalid ones.

        Invalid translations include:
        - Empty or whitespace-only translations
        - Translations identical to source text (for non-matching language codes)
        - Translations with lost protected variables

        Args:
            target_languages: Optional list of language codes to validate
            progress_callback: Optional callback for progress updates
            cancel_check: Optional function to check if operation should be cancelled

        Returns:
            Dict with validation results including cleared count
        """
        import src.project.generator as file_generator

        source_lang = self.project.get("source_language")
        if not source_lang:
            raise ValueError("Project source_language is not configured")

        if target_languages:
            languages = target_languages
        else:
            stats = validation.get_all_translation_stats(self.project_id)
            languages = [
                stat.language_code for stat in stats
                if not lc.languages_match(stat.language_code, source_lang)
            ]

        total_validated = 0
        total_cleared = 0
        validation_details: Dict[str, Dict[str, Any]] = {}
        translations_to_delete: List[tuple] = []
        skipped_languages: List[str] = []

        for lang_idx, lang_code in enumerate(languages):
            if cancel_check and cancel_check():
                break

            lang_name = lc.get_language_name(lang_code) or lang_code

            # Send "checking" progress
            logger.info(f"Checking {lang_name} ({lang_code}) for validation...")
            if progress_callback:
                progress = TranslationProgress(
                    current_language=lang_code,
                    current_language_name=lang_name,
                    total_languages=len(languages),
                    completed_languages=lang_idx,
                    current_item=0,
                    total_items=0,
                    current_key="",
                    current_text="",
                    success_count=total_validated,
                    failure_count=total_cleared,
                    current_batch=0,
                    total_batches=0,
                    batch_keys_count=0,
                    phase="checking",
                    mode="validate_only",
                )
                if progress_callback(progress):
                    break

            validation_details[lang_code] = {
                "validated": 0,
                "cleared": 0,
                "reasons": {}
            }

            # Get all translations for this language
            with db.get_connection() as conn:
                conn.row_factory = db.sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT t.string_id, t.language_code, t.translated_text, t.status,
                           s.key_path, s.source_text
                    FROM translations t
                    JOIN strings s ON t.string_id = s.id
                    WHERE s.project_id = ? AND t.language_code = ?
                """, (self.project_id, lang_code))
                translations = [dict(row) for row in cursor.fetchall()]

            # Get language statistics
            try:
                lang_stats = validation.get_translation_stats(self.project_id, lang_code)
                total_keys = lang_stats.total_strings
                completed_keys = lang_stats.translated_count
                missing_keys = lang_stats.missing_count
            except Exception as e:
                logger.warning(f"Failed to get stats for {lang_code}: {e}")
                total_keys = len(translations) if translations else 0
                completed_keys = len(translations) if translations else 0
                missing_keys = 0

            # Send "checked" phase
            logger.info(f"Checked {lang_name} ({lang_code}): Total: {total_keys}, Completed: {completed_keys}, Missing: {missing_keys}")
            if progress_callback:
                progress = TranslationProgress(
                    current_language=lang_code,
                    current_language_name=lang_name,
                    total_languages=len(languages),
                    completed_languages=lang_idx,
                    current_item=0,
                    total_items=total_keys,
                    current_key="",
                    current_text="",
                    success_count=completed_keys,
                    failure_count=missing_keys,
                    current_batch=0,
                    total_batches=0,
                    batch_keys_count=0,
                    phase="checked",
                    mode="validate_only",
                )
                if progress_callback(progress):
                    break

            if not translations:
                skipped_languages.append(lang_code)
                logger.info(f"Validation skipped for {lang_name} ({lang_code}): No translations exist yet")

                if progress_callback:
                    progress = TranslationProgress(
                        current_language=lang_code,
                        current_language_name=lang_name,
                        total_languages=len(languages),
                        completed_languages=lang_idx,
                        current_item=0,
                        total_items=0,
                        current_key="",
                        current_text="",
                        success_count=total_validated,
                        failure_count=total_cleared,
                        current_batch=0,
                        total_batches=0,
                        batch_keys_count=0,
                        phase="no_work",
                        mode="validate_only",
                        total_tasks=0,
                    )
                    if progress_callback(progress):
                        break

                    progress = TranslationProgress(
                        current_language=lang_code,
                        current_language_name=lang_name,
                        total_languages=len(languages),
                        completed_languages=lang_idx + 1,
                        current_item=0,
                        total_items=0,
                        current_key="",
                        current_text="",
                        success_count=0,
                        failure_count=0,
                        current_batch=0,
                        total_batches=0,
                        batch_keys_count=0,
                        phase="completed",
                        mode="validate_only",
                    )
                    progress_callback(progress)
                continue

            # Send "tasks_found" and "starting" phases
            validation_count = len(translations)
            logger.info(f"Found {validation_count} entries to validate for {lang_name} ({lang_code})")
            if progress_callback:
                progress = TranslationProgress(
                    current_language=lang_code,
                    current_language_name=lang_name,
                    total_languages=len(languages),
                    completed_languages=lang_idx,
                    current_item=0,
                    total_items=validation_count,
                    current_key="",
                    current_text="",
                    success_count=0,
                    failure_count=0,
                    current_batch=0,
                    total_batches=0,
                    batch_keys_count=0,
                    phase="tasks_found",
                    mode="validate_only",
                    total_tasks=validation_count,
                )
                if progress_callback(progress):
                    break

                progress = TranslationProgress(
                    current_language=lang_code,
                    current_language_name=lang_name,
                    total_languages=len(languages),
                    completed_languages=lang_idx,
                    current_item=0,
                    total_items=validation_count,
                    current_key="",
                    current_text="",
                    success_count=total_validated,
                    failure_count=total_cleared,
                    current_batch=0,
                    total_batches=0,
                    batch_keys_count=0,
                    phase="starting",
                    mode="validate_only",
                )
                if progress_callback(progress):
                    break

            for idx, trans in enumerate(translations):
                if progress_callback:
                    progress = TranslationProgress(
                        current_language=lang_code,
                        current_language_name=lang_name,
                        total_languages=len(languages),
                        completed_languages=lang_idx,
                        current_item=idx + 1,
                        total_items=len(translations),
                        current_key=trans["key_path"],
                        current_text=f"Validating: {trans['key_path']}",
                        success_count=total_validated,
                        failure_count=total_cleared,
                    )
                    if progress_callback(progress):
                        break

                if cancel_check and cancel_check():
                    break

                source_text = trans["source_text"] or ""
                translated_text = trans["translated_text"] or ""

                # Get protected vars for validation
                protected_vars = None
                key_path = trans.get("key_path", "")
                filtered_protected_terms = get_all_protected_terms_flat(self.project_id, key_path=key_path)
                if filtered_protected_terms:
                    _, protected_vars = apply_protection(source_text, filtered_protected_terms)

                source_variables = self._extract_variables(source_text)

                is_valid, reason = self._is_translation_valid(
                    source_text=source_text,
                    translated_text=translated_text,
                    source_lang=source_lang,
                    target_lang=lang_code,
                    protected_vars=protected_vars,
                    variable_placeholders=None,
                )

                if is_valid and source_variables:
                    vars_valid, vars_error = self._validate_native_variables_preserved(
                        source_text, translated_text
                    )
                    if not vars_valid:
                        is_valid = False
                        reason = vars_error

                total_validated += 1
                validation_details[lang_code]["validated"] += 1

                if not is_valid:
                    translations_to_delete.append((trans["string_id"], lang_code))
                    total_cleared += 1
                    validation_details[lang_code]["cleared"] += 1

                    if reason not in validation_details[lang_code]["reasons"]:
                        validation_details[lang_code]["reasons"][reason] = 0
                    validation_details[lang_code]["reasons"][reason] += 1

                    logger.debug(f"Cleared invalid translation: {trans['key_path']} [{lang_code}] - {reason}")

            lang_validated = validation_details[lang_code]["validated"]
            lang_cleared = validation_details[lang_code]["cleared"]
            logger.info(f"Validation completed for {lang_name} ({lang_code}): validated={lang_validated}, cleared={lang_cleared}")

            if progress_callback:
                progress = TranslationProgress(
                    current_language=lang_code,
                    current_language_name=lang_name,
                    total_languages=len(languages),
                    completed_languages=lang_idx + 1,
                    current_item=len(translations),
                    total_items=len(translations),
                    current_key="",
                    current_text="",
                    success_count=lang_validated - lang_cleared,
                    failure_count=lang_cleared,
                    current_batch=0,
                    total_batches=0,
                    batch_keys_count=0,
                    phase="completed",
                    mode="validate_only",
                )
                progress_callback(progress)

            if cancel_check and cancel_check():
                break

        # Delete invalid translations
        if translations_to_delete:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                for string_id, lang_code in translations_to_delete:
                    cursor.execute(
                        "DELETE FROM translations WHERE string_id = ? AND language_code = ?",
                        (string_id, lang_code)
                    )
                conn.commit()

        # Generate files if any were cleared
        if total_cleared > 0:
            try:
                file_generator.generate_all_language_files(self.project_id)
            except Exception as e:
                logger.warning(f"Failed to generate files after validation: {e}")

        cancelled = cancel_check() if cancel_check else False

        logger.info(f"Validation {'cancelled' if cancelled else 'completed'}: validated={total_validated}, cleared={total_cleared}, skipped={len(skipped_languages)} languages")

        if total_validated == 0 and skipped_languages:
            message = "Validation skipped: Selected language(s) have no existing translations. Run translation first."
        elif total_cleared == 0 and total_validated > 0:
            message = f"Validation completed: All {total_validated} translations are valid."
        else:
            message = None

        return {
            "success": True,
            "cancelled": cancelled,
            "total_validated": total_validated,
            "total_cleared": total_cleared,
            "details": validation_details,
            "skipped_languages": skipped_languages,
            "message": message,
        }

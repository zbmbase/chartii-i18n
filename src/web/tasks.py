"""
Asynchronous task helpers for long-running background jobs (e.g. translation).
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from src.logger import get_logger

from src.translation.manager import TranslationManager
from src.translation.progress import TranslationProgress

logger = get_logger(__name__)


@dataclass
class JobState:
    """In-memory representation of an asynchronous job."""

    job_id: str
    project_id: int
    languages: List[str] = field(default_factory=list)
    mode: str = "missing_only"  # missing_only|missing_and_ai|full
    include_locked: bool = False
    generate_files: bool = True
    model_override: Optional[str] = None  # Optional specific model to use
    ai_provider: Optional[str] = None  # AI provider for this job
    chunk_size_words: Optional[int] = None  # Word count limit per batch
    cancel_requested: bool = False
    state: str = "pending"  # pending|running|completed|failed|cancelled
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    progress: Dict[str, Any] = field(default_factory=dict)
    progress_history: List[Dict[str, Any]] = field(default_factory=list)  # History of all progress updates
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    failure_count: int = 0
    last_update: float = field(default_factory=time.time)
    
    def request_cancel(self):
        """Mark this job as requested for cancellation."""
        self.cancel_requested = True
        self.last_update = time.time()

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        # Ensure floats are rounded for JSON friendliness
        for key in ("created_at", "started_at", "finished_at", "last_update"):
            if payload.get(key) is not None:
                payload[key] = float(payload[key])
        return payload


_jobs: Dict[str, JobState] = {}
_jobs_lock = threading.Lock()
_JOB_RETENTION_SECONDS = 600  # Retain job info for 10 minutes after completion


def create_translation_job(
    project_id: int,
    languages: Optional[List[str]] = None,
    mode: str = "missing_only",
    include_locked: bool = False,
    generate_files: bool = True,
    model_override: Optional[str] = None,
    ai_provider: Optional[str] = None,
    chunk_size_words: Optional[int] = None,
) -> JobState:
    """
    Create and launch an asynchronous translation job for a project.

    Args:
        project_id: Project identifier.
        languages: Optional list of language codes to translate. None => auto.
        mode: Translation mode: "missing_only", "missing_and_ai", or "full".
        include_locked: Whether to include locked translations (only for full mode).
        generate_files: Whether to generate language files after completion.
        model_override: Optional specific model to use instead of default.

    Returns:
        JobState for the new job (already registered and running in background).
    """
    job_id = uuid.uuid4().hex
    job_state = JobState(
        job_id=job_id,
        project_id=project_id,
        languages=languages or [],
        mode=mode,
        include_locked=include_locked,
        generate_files=generate_files,
        model_override=model_override,
        ai_provider=ai_provider,
        chunk_size_words=chunk_size_words,
    )

    with _jobs_lock:
        _cleanup_jobs_locked()
        _jobs[job_id] = job_state

    thread = threading.Thread(
        target=_run_translation_job,
        args=(job_state,),
        name=f"translation-job-{job_id}",
        daemon=True,
    )
    thread.start()
    logger.info(
        "Translation job %s started for project %s (languages=%s, mode=%s, include_locked=%s)",
        job_id,
        project_id,
        job_state.languages or "auto",
        job_state.mode,
        job_state.include_locked,
    )
    return job_state


def get_job(job_id: str) -> Optional[JobState]:
    """Fetch a job by ID (if still retained)."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job and job.finished_at and (time.time() - job.finished_at) > _JOB_RETENTION_SECONDS:
            # Expired; remove
            _jobs.pop(job_id, None)
            return None
        return job


def cancel_job(job_id: str) -> bool:
    """
    Request cancellation of a running job.
    
    Args:
        job_id: The job ID to cancel.
        
    Returns:
        True if job was found and cancellation requested, False otherwise.
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return False
        if job.state in ("completed", "failed", "cancelled"):
            return False  # Already finished
        job.request_cancel()
        logger.info("Cancellation requested for job %s", job_id)
        return True


def get_latest_active_job(project_id: int) -> Optional[JobState]:
    """
    Get the latest active (pending or running) job for a project.
    
    Args:
        project_id: The project ID.
        
    Returns:
        The latest active JobState, or None if no active job found.
    """
    with _jobs_lock:
        active_jobs = [
            job for job in _jobs.values()
            if job.project_id == project_id
            and job.state in ("pending", "running")
            and (not job.finished_at or (time.time() - job.finished_at) < _JOB_RETENTION_SECONDS)
        ]
        if not active_jobs:
            return None
        # Return the most recently created job
        return max(active_jobs, key=lambda j: j.created_at)


def get_latest_job(project_id: int) -> Optional[JobState]:
    """
    Get the latest job (including completed/failed) for a project.
    
    Args:
        project_id: The project ID.
        
    Returns:
        The latest JobState, or None if no job found.
    """
    with _jobs_lock:
        project_jobs = [
            job for job in _jobs.values()
            if job.project_id == project_id
            and (not job.finished_at or (time.time() - job.finished_at) < _JOB_RETENTION_SECONDS)
        ]
        if not project_jobs:
            return None
        # Return the most recently created job
        return max(project_jobs, key=lambda j: j.created_at)


def remove_failed_items_from_job(
    job_id: str, 
    failed_items_to_remove: List[Dict[str, Any]]
) -> bool:
    """
    Remove specific failed items from a job's result.
    
    Args:
        job_id: The job ID
        failed_items_to_remove: List of failed items to remove, each item should have
                               key_path, language_code, and source_text
    
    Returns:
        True if items were removed, False if job not found
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job or not job.result:
            return False
        
        failed_items = job.result.get("failed_items", [])
        if not isinstance(failed_items, list):
            return False
        
        # Build a set of identifiers for items to remove
        # Format: "key_path:language_code:source_text"
        items_to_remove = set()
        for item in failed_items_to_remove:
            key_path = item.get("key_path", "")
            language_code = item.get("language_code", "")
            source_text = item.get("source_text", "")
            items_to_remove.add(f"{key_path}:{language_code}:{source_text}")
        
        # Filter out items that match
        original_count = len(failed_items)
        job.result["failed_items"] = [
            item for item in failed_items
            if f"{item.get('key_path', '')}:{item.get('language_code', '')}:{item.get('source_text', '')}" 
            not in items_to_remove
        ]
        
        removed_count = original_count - len(job.result["failed_items"])
        if removed_count > 0:
            logger.info(
                f"Removed {removed_count} failed items from job {job_id}"
            )
        
        return removed_count > 0


def serialize_job(job: JobState) -> Dict[str, Any]:
    """Convert JobState into JSON-safe dict."""
    payload = job.to_dict()
    # Convert progress nested dataclass if present
    if isinstance(payload.get("progress"), TranslationProgress):
        payload["progress"] = _serialize_progress(payload["progress"])
    return payload


def _run_translation_job(job: JobState):
    """Worker function executed in a background thread."""
    job.state = "running"
    job.started_at = time.time()
    job.last_update = job.started_at
    try:
        manager = TranslationManager(job.project_id)

        def on_progress(progress: TranslationProgress):
            with _jobs_lock:
                serialized = _serialize_progress(progress)
                job.progress = serialized  # Latest state
                job.progress_history.append(serialized)  # Save to history
                job.failure_count = progress.failure_count
                job.last_update = time.time()
                # Check for cancellation request
                if job.cancel_requested:
                    return True  # Signal to stop
            return False

        def check_cancel():
            """Check if job cancellation was requested."""
            with _jobs_lock:
                return job.cancel_requested

        # Handle different modes
        if job.mode == "validate_only":
            # Validation mode: check and clear invalid translations
            result = manager.validate_and_clear_invalid(
                target_languages=job.languages or None,
                progress_callback=on_progress,
                cancel_check=check_cancel,
            )
        else:
            # Use the new chunked translation method
            # Falls back gracefully on errors and uses concurrent chunk processing
            result = manager.translate_all_missing_chunked(
                target_languages=job.languages or None,
                mode=job.mode,
                include_locked=job.include_locked,
                generate_files=job.generate_files,
                progress_callback=on_progress,
                cancel_check=check_cancel,
                model_override=job.model_override,
                chunk_size_words=job.chunk_size_words,
                ai_provider=job.ai_provider,
            )
        
        # If cancelled, update state
        if job.cancel_requested:
            job.state = "cancelled"
            job.finished_at = time.time()
            job.last_update = job.finished_at
            if job.mode == "validate_only":
                logger.info(
                    "Validation job %s cancelled (validated=%s, cleared=%s)",
                    job.job_id,
                    result.get("total_validated", 0),
                    result.get("total_cleared", 0),
                )
            else:
                logger.info(
                    "Translation job %s cancelled (translated=%s, failed=%s)",
                    job.job_id,
                    result.get("total_translated", 0),
                    result.get("total_failed", 0),
                )
            return
        job.result = result
        job.state = "completed" if result.get("success", True) else "failed"
        job.finished_at = time.time()
        job.last_update = job.finished_at
        if job.mode == "validate_only":
            logger.info(
                "Validation job %s finished (success=%s, validated=%s, cleared=%s)",
                job.job_id,
                job.state == "completed",
                result.get("total_validated"),
                result.get("total_cleared"),
            )
        else:
            logger.info(
                "Translation job %s finished (success=%s, translated=%s, failed=%s)",
                job.job_id,
                job.state == "completed",
                result.get("total_translated"),
                result.get("total_failed"),
            )
    except Exception as exc:
        job.state = "failed"
        error_type = type(exc).__name__
        error_message = str(exc)
        job.error = f"{error_type}: {error_message}"
        job.finished_at = time.time()
        job.last_update = job.finished_at
        logger.exception(
            "✗ Translation job %s failed for project %s: %s: %s",
            job.job_id,
            job.project_id,
            error_type,
            error_message,
        )


def _cleanup_jobs_locked():
    """Remove completed jobs that exceeded retention period (call with lock held)."""
    now = time.time()
    expired = [
        job_id
        for job_id, job in _jobs.items()
        if job.finished_at and (now - job.finished_at) > _JOB_RETENTION_SECONDS
    ]
    for job_id in expired:
        _jobs.pop(job_id, None)


def _serialize_progress(progress: TranslationProgress) -> Dict[str, Any]:
    return {
        "current_language": progress.current_language,
        "current_language_name": progress.current_language_name,
        "total_languages": progress.total_languages,
        "completed_languages": progress.completed_languages,
        "current_item": progress.current_item,
        "total_items": progress.total_items,
        "current_key": progress.current_key,
        "current_text": progress.current_text,
        "success_count": progress.success_count,
        "failure_count": progress.failure_count,
        "estimated_time_remaining": progress.estimated_time_remaining,
        # Batch progress fields
        "current_batch": progress.current_batch,
        "total_batches": progress.total_batches,
        "batch_keys_count": progress.batch_keys_count,
        "phase": progress.phase,
        "retry_keys_count": progress.retry_keys_count,
        # Task statistics fields
        "missing_count": progress.missing_count,
        "ai_count": progress.ai_count,
        "locked_count": progress.locked_count,
        "total_tasks": progress.total_tasks,
        "mode": progress.mode,
        # Token usage
        "token_usage": progress.token_usage,
        # Failed items for current language (only when phase is "completed")
        "failed_items": progress.failed_items,
    }


"""
Database Async Queue Writer Module

Provides a thread-safe asynchronous queue for batching SQLite writes.
Avoids "database is locked" errors under high multi-threading concurrency.
"""

import queue
import threading
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
from src.core import database as db
from src.logger import get_logger

logger = get_logger(__name__)


class DatabaseWriter:
    """
    Singleton / Threaded DB Writer Queue.
    Collects translation records from multiple worker threads
    and writes them in batches into SQLite.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabaseWriter, cls).__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self):
        self.queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        # Track pending write counts per language for flush_and_wait_for_language
        self._pending_events: Dict[str, threading.Event] = {}
        self._pending_lock = threading.Lock()
        self.worker_thread = threading.Thread(
            target=self._process_queue, name="AsyncDBWriterThread", daemon=True
        )
        self.worker_thread.start()
        logger.info("AsyncDBWriterThread started successfully")

    def enqueue_save_translations(
        self,
        project_id: str,
        language_code: str,
        items: List[Dict[str, Any]],
        status: str = "ai_translated",
        model: Optional[str] = None,
        provider: Optional[str] = None,
        done_event: Optional[threading.Event] = None,
    ) -> None:
        """
        Enqueue a batch of translations to be saved to DB.

        :param items: List of dicts with keys 'string_id', 'translated_text'
        :param done_event: Optional threading.Event to set after this batch is flushed
        """
        if not items:
            if done_event:
                done_event.set()
            return
        self.queue.put({
            "action": "save_translations",
            "project_id": project_id,
            "language_code": language_code,
            "items": items,
            "status": status,
            "model": model,
            "provider": provider,
            "done_event": done_event,
        })

    def enqueue_and_flush(
        self,
        project_id: str,
        language_code: str,
        items: List[Dict[str, Any]],
        status: str = "ai_translated",
        model: Optional[str] = None,
        provider: Optional[str] = None,
        timeout: float = 30.0,
    ) -> bool:
        """
        Enqueue a batch of translations and BLOCK until they are flushed to DB.
        Use this before reading back data that was just written (e.g. before file generation).

        :returns: True if flushed successfully within timeout, False on timeout
        """
        if not items:
            return True
        done_event = threading.Event()
        self.enqueue_save_translations(
            project_id=project_id,
            language_code=language_code,
            items=items,
            status=status,
            model=model,
            provider=provider,
            done_event=done_event,
        )
        result = done_event.wait(timeout=timeout)
        if not result:
            logger.warning(
                f"DB flush timeout ({timeout}s) for language {language_code} "
                f"({len(items)} items). File generation may use stale data."
            )
        return result

    def _process_queue(self):
        """Worker loop to process DB write queue in micro-batches."""
        batch_items = []
        last_flush_time = time.time()

        while not self.stop_event.is_set() or not self.queue.empty():
            try:
                try:
                    task = self.queue.get(timeout=0.2)
                    batch_items.append(task)
                    self.queue.task_done()
                except queue.Empty:
                    pass

                # Flush batch if size reached or timeout elapsed
                now = time.time()
                if batch_items and (len(batch_items) >= 20 or (now - last_flush_time) >= 0.3):
                    self._flush_batch(batch_items)
                    batch_items = []
                    last_flush_time = now

            except Exception as e:
                logger.error(f"Error in AsyncDBWriterThread worker loop: {e}")
                # Signal any done_events so callers don't hang forever
                for task in batch_items:
                    ev = task.get("done_event")
                    if ev:
                        ev.set()
                batch_items = []

        # Final flush on shutdown
        if batch_items:
            self._flush_batch(batch_items)

    def _flush_batch(self, batch: List[Dict[str, Any]]) -> None:
        """Execute a batch of save_translations in a single SQLite transaction."""
        if not batch:
            return

        done_events = []

        with db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                for task in batch:
                    if task["action"] == "save_translations":
                        project_id = task["project_id"]
                        language_code = task["language_code"]
                        status = task["status"]

                        for item in task["items"]:
                            string_id = item["string_id"]
                            translated_text = item["translated_text"]

                            # Delete existing first to avoid unique key conflict
                            cursor.execute(
                                """
                                DELETE FROM translations
                                WHERE string_id = ? AND language_code = ?
                                """,
                                (string_id, language_code),
                            )

                            # Insert new translation matching main branch schema
                            cursor.execute(
                                """
                                INSERT INTO translations
                                (string_id, language_code, translated_text, last_translated_at, status)
                                VALUES (?, ?, ?, ?, ?)
                                """,
                                (string_id, language_code, translated_text, datetime.now(), status),
                            )

                    # Collect done_events to signal after commit
                    ev = task.get("done_event")
                    if ev:
                        done_events.append(ev)

                conn.commit()
                logger.debug(f"AsyncDBWriter successfully flushed {len(batch)} DB tasks")
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to flush DB batch: {e}")
            finally:
                # Always signal done_events regardless of success/failure
                for ev in done_events:
                    ev.set()

    def flush_and_wait(self) -> None:
        """Wait until all current tasks in queue are processed."""
        self.queue.join()


# Global accessor
db_writer = DatabaseWriter()

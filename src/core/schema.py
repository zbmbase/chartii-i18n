"""
Database Schema Management Module

This module handles database initialization, schema validation, and migrations.
For CRUD operations, see core/database.py
"""

import sqlite3

# Import database module to use DB_FILE and get_connection dynamically
# This ensures monkeypatching in tests works correctly
import src.core.database as db

DB_VERSION = 12  # Increment when schema changes (added performance indexes in v12)


def get_connection():
    """Get a database connection using the database module's DB_FILE."""
    return db.get_connection()


def get_db_version() -> int:
    """Get current database version."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version FROM db_version LIMIT 1")
            row = cursor.fetchone()
            return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0


def set_db_version(version: int):
    """Set database version."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS db_version (version INTEGER)")
        cursor.execute("DELETE FROM db_version")
        cursor.execute("INSERT INTO db_version (version) VALUES (?)", (version,))
        conn.commit()


def initialize_database():
    """Initializes the database and creates the tables."""
    from src.logger import get_logger
    logger = get_logger(__name__)

    if db.DB_FILE.exists():
        # Check if migration needed
        current_version = get_db_version()
        if current_version < DB_VERSION:
            migrate_database(current_version, DB_VERSION)
        # Also check if columns exist even if version matches (safety check)
        elif current_version == DB_VERSION:
            # Verify that all required columns exist
            try:
                ensure_all_schemas()
            except Exception as e:
                logger.warning(f"Failed to verify/add version columns: {e}")
        return

    with get_connection() as conn:
        cursor = conn.cursor()

        # Create projects table
        cursor.execute("""
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            locales_path TEXT NOT NULL,
            source_language TEXT NOT NULL,
            translation_context TEXT,
            protected_terms_analyzed INTEGER DEFAULT 0,
            skip_protected_terms INTEGER DEFAULT 0,
            translation_ai_provider TEXT,
            translation_chunk_size_words INTEGER,
            last_synced_at TIMESTAMP
        )
        """)

        # Create strings table
        cursor.execute("""
        CREATE TABLE strings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            key_path TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            source_text TEXT NOT NULL,
            should_translate INTEGER DEFAULT 1,
            value_type TEXT DEFAULT 'string',
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
        """)

        # Create translations table
        cursor.execute("""
        CREATE TABLE translations (
            string_id INTEGER NOT NULL,
            language_code TEXT NOT NULL,
            translated_text TEXT NOT NULL,
            last_translated_at TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'ai_translated',
            FOREIGN KEY (string_id) REFERENCES strings (id)
        )
        """)

        # Create protected_terms table
        cursor.execute("""
        CREATE TABLE protected_terms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            term TEXT NOT NULL,
            category TEXT,
            is_regex INTEGER DEFAULT 0,
            key_scopes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """)

        # Create app_config table
        cursor.execute("""
        CREATE TABLE app_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Create indexes for performance
        ensure_database_indexes()

        # Set initial database version
        set_db_version(DB_VERSION)

        conn.commit()


# ============================================================
# Database Schema Validation
# ============================================================

def ensure_projects_schema():
    """
    Ensure projects table has all required columns.
    This function should be called during database initialization/migration.
    """
    from src.logger import get_logger
    logger = get_logger(__name__)

    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            # Get existing columns
            cursor.execute("PRAGMA table_info(projects)")
            existing_cols = {row[1] for row in cursor.fetchall()}

            # Ensure all required columns exist
            if "protected_terms_analyzed" not in existing_cols:
                logger.info("Adding protected_terms_analyzed column to projects table")
                cursor.execute("ALTER TABLE projects ADD COLUMN protected_terms_analyzed INTEGER DEFAULT 0")

            if "skip_protected_terms" not in existing_cols:
                logger.info("Adding skip_protected_terms column to projects table")
                cursor.execute("ALTER TABLE projects ADD COLUMN skip_protected_terms INTEGER DEFAULT 0")

            if "translation_ai_provider" not in existing_cols:
                logger.info("Adding translation_ai_provider column to projects table")
                cursor.execute("ALTER TABLE projects ADD COLUMN translation_ai_provider TEXT")

            if "translation_chunk_size_words" not in existing_cols:
                logger.info("Adding translation_chunk_size_words column to projects table")
                cursor.execute("ALTER TABLE projects ADD COLUMN translation_chunk_size_words INTEGER")

            if "last_synced_at" not in existing_cols:
                logger.info("Adding last_synced_at column to projects table")
                cursor.execute("ALTER TABLE projects ADD COLUMN last_synced_at TIMESTAMP")

            conn.commit()
    except Exception as e:
        logger.error(f"Failed to ensure projects schema: {e}")
        raise


def ensure_strings_schema():
    """
    Ensure strings table has all required columns.
    This function should be called during database initialization/migration.
    """
    from src.logger import get_logger
    logger = get_logger(__name__)

    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            # Get existing columns
            cursor.execute("PRAGMA table_info(strings)")
            existing_cols = {row[1] for row in cursor.fetchall()}

            # Ensure all required columns exist
            if "should_translate" not in existing_cols:
                logger.info("Adding should_translate column to strings table")
                cursor.execute("ALTER TABLE strings ADD COLUMN should_translate INTEGER DEFAULT 1")

            if "value_type" not in existing_cols:
                logger.info("Adding value_type column to strings table")
                cursor.execute("ALTER TABLE strings ADD COLUMN value_type TEXT DEFAULT 'string'")

            if "sort_order" not in existing_cols:
                logger.info("Adding sort_order column to strings table")
                cursor.execute("ALTER TABLE strings ADD COLUMN sort_order INTEGER DEFAULT 0")

            conn.commit()
    except Exception as e:
        logger.error(f"Failed to ensure strings schema: {e}")
        raise


def ensure_protected_terms_schema():
    """
    Ensure protected_terms table has all required columns.
    This function should be called during database initialization/migration.
    """
    from src.logger import get_logger
    logger = get_logger(__name__)

    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            # Get existing columns
            cursor.execute("PRAGMA table_info(protected_terms)")
            existing_cols = {row[1] for row in cursor.fetchall()}

            # Ensure all required columns exist
            if "key_scopes" not in existing_cols:
                logger.info("Adding key_scopes column to protected_terms table")
                cursor.execute("ALTER TABLE protected_terms ADD COLUMN key_scopes TEXT")

            if "updated_at" not in existing_cols:
                logger.info("Adding updated_at column to protected_terms table")
                # SQLite doesn't support CURRENT_TIMESTAMP as default in ALTER TABLE ADD COLUMN
                # So we add the column without default, then update existing records
                cursor.execute("ALTER TABLE protected_terms ADD COLUMN updated_at TIMESTAMP")
                # Set initial updated_at to created_at for existing records, or current time if created_at is NULL
                cursor.execute("""
                    UPDATE protected_terms
                    SET updated_at = COALESCE(created_at, datetime('now'))
                """)

            conn.commit()
    except Exception as e:
        logger.error(f"Failed to ensure protected_terms schema: {e}")
        raise


def ensure_translations_schema():
    """
    Ensure translations table has proper constraints.
    - Remove duplicate translations (keep the most recent one)
    - Add unique constraint on (string_id, language_code)
    """
    from src.logger import get_logger
    logger = get_logger(__name__)

    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            # Check if unique index already exists
            cursor.execute("PRAGMA index_list(translations)")
            indexes = cursor.fetchall()
            has_unique_index = any(
                idx[1] == 'idx_translations_unique' for idx in indexes
            )

            if has_unique_index:
                logger.debug("Translations unique index already exists")
                return

            logger.info("Ensuring translations schema integrity...")

            # Count duplicates before cleanup
            cursor.execute("""
                SELECT string_id, language_code, COUNT(*) as cnt
                FROM translations
                GROUP BY string_id, language_code
                HAVING cnt > 1
            """)
            duplicates = cursor.fetchall()

            if duplicates:
                duplicate_count = sum(row[2] - 1 for row in duplicates)
                logger.warning(f"Found {duplicate_count} duplicate translation records, cleaning up...")

                # Remove duplicates, keeping the one with the latest timestamp or highest rowid
                cursor.execute("""
                    DELETE FROM translations
                    WHERE rowid NOT IN (
                        SELECT MAX(rowid)
                        FROM translations
                        GROUP BY string_id, language_code
                    )
                """)
                logger.info(f"Removed {cursor.rowcount} duplicate translation records")

            # Create unique index to prevent future duplicates
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_translations_unique
                ON translations(string_id, language_code)
            """)
            logger.info("Created unique index on translations(string_id, language_code)")

            conn.commit()
    except Exception as e:
        logger.error(f"Failed to ensure translations schema: {e}")
        raise


def ensure_database_indexes():
    """
    Ensure all performance-critical indexes exist.
    This function should be called during database initialization/migration.
    """
    from src.logger import get_logger
    logger = get_logger(__name__)

    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            # Strings table indexes
            logger.info("Ensuring strings table indexes...")
            
            # Index on project_id (most common filter)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_strings_project_id 
                ON strings(project_id)
            """)
            
            # Composite index for sorted queries (project_id + sort_order + id)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_strings_project_sort 
                ON strings(project_id, sort_order, id)
            """)
            
            # Composite index for key_path lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_strings_project_key 
                ON strings(project_id, key_path)
            """)

            # Translations table indexes
            logger.info("Ensuring translations table indexes...")
            
            # Index on string_id for JOIN operations
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_translations_string_id 
                ON translations(string_id)
            """)
            
            # Index on language_code for language-based queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_translations_language_code 
                ON translations(language_code)
            """)
            
            # Note: idx_translations_unique on (string_id, language_code) 
            # is already created in ensure_translations_schema()

            # Protected terms table indexes
            logger.info("Ensuring protected_terms table indexes...")
            
            # Index on project_id
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_protected_terms_project_id 
                ON protected_terms(project_id)
            """)
            
            # Composite index for category filtering
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_protected_terms_project_category 
                ON protected_terms(project_id, category)
            """)

            conn.commit()
            logger.info("Database indexes created/verified successfully")
            
    except Exception as e:
        logger.error(f"Failed to ensure database indexes: {e}")
        raise


def ensure_all_schemas():
    """
    Ensure all tables have all required columns and indexes.
    This is a convenience function that calls all individual schema validation functions.
    """
    ensure_projects_schema()
    ensure_strings_schema()
    ensure_protected_terms_schema()
    ensure_translations_schema()
    # Also ensure indexes exist
    ensure_database_indexes()


# ============================================================
# Database Migration
# ============================================================

def migrate_database(from_version: int, to_version: int):
    """
    Migrate database from one version to another.

    Since the project hasn't been released yet, we only ensure schema integrity
    for any version mismatch. Future migrations should be added here when needed.
    """
    from src.logger import get_logger
    logger = get_logger(__name__)

    logger.info(f"Migrating database from version {from_version} to {to_version}")

    with get_connection() as conn:
        cursor = conn.cursor()

        # For any version mismatch, ensure all schemas are complete
        # This handles cases where the database structure might be incomplete
        # ensure_all_schemas() also ensures indexes exist
        ensure_all_schemas()

        # Update database version
        set_db_version(to_version)
        conn.commit()
        logger.info(f"Database migration completed: now at version {to_version}")

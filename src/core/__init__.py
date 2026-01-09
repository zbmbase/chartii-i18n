"""
Core module - Database and validation utilities

This module provides:
- database: CRUD operations for all entities
- schema: Database initialization and migrations
- validation: Translation completeness validation
- sync: Source file synchronization
"""

from src.core.database import (
    DB_FILE,
    get_connection,
    # Project operations
    create_project,
    get_all_projects,
    get_project_by_id,
    update_project,
    delete_project,
    update_project_last_synced,
    update_project_protected_terms_status,
    # String operations
    create_string,
    get_string_by_key,
    get_all_strings_for_project,
    update_string,
    delete_string,
    # Translation operations
    create_translation,
    get_translation,
    get_all_translations_for_language,
    update_translation_status,
    delete_translation,
    get_translations_by_status,
    # Protected terms operations
    create_protected_term,
    get_protected_terms,
    get_protected_term_by_id,
    update_protected_term,
    delete_protected_term,
    delete_all_protected_terms,
    add_protected_terms_batch,
    # App config operations
    get_app_config,
    set_app_config,
    get_all_app_config,
)

from src.core.schema import (
    DB_VERSION,
    get_db_version,
    set_db_version,
    initialize_database,
    ensure_all_schemas,
    migrate_database,
)

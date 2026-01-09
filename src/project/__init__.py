"""
Project module - Project management functionality

This module provides:
- creator: Project creation and import
- scanner: Directory scanning and language detection
- generator: Language file generation
"""

from src.project.creator import (
    ImportResult,
    create_project_with_source,
)

from src.project.scanner import (
    LanguageFileInfo,
    ProjectScanResult,
    scan_locales_directory,
    calculate_completeness,
)

from src.project.generator import (
    FileGenerationError,
    generate_language_file,
    generate_all_language_files,
    validate_language_file,
    preview_language_file,
)

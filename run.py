"""Project root entry point for launching the web interface."""

from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_path() -> None:
    """Ensure the src/ directory is importable when running from project root."""
    project_root = Path(__file__).resolve().parent
    src_dir = project_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def main():
    _bootstrap_path()
    from web import create_app

    app = create_app()
    app.run(host="0.0.0.0", port=5500, debug=True)


if __name__ == "__main__":
    main()


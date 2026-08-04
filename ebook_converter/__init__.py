"""Ebook Converter — any-format-to-any-format document conversion.

The heavy lifting is Calibre's ``ebook-convert``; this package wraps it with
format metadata, job planning and settings so the Qt layer stays thin.
"""

import sys
from pathlib import Path

APP_NAME = "Ebook Converter"
BUNDLE_ID = "com.netrunner3000.ebookconverter"

__all__ = ["APP_NAME", "BUNDLE_ID", "asset_path", "project_root"]


def project_root() -> Path:
    """Directory holding the bundled resources.

    In a PyInstaller build the data files are unpacked to ``sys._MEIPASS``;
    from source they sit next to this package.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def asset_path(name: str) -> Path:
    return project_root() / "assets" / name

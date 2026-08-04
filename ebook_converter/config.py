"""Persisted settings.

Everything writable lives under ``~/Library/Application Support/<App Name>/``.
A frozen .app must never write inside its own bundle: it breaks the code
signature, and reinstalling wipes whatever was stored there.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from . import APP_NAME, formats
from .jobs import OutputMode

SUPPORT_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
CONFIG_PATH = SUPPORT_DIR / "settings.json"


@dataclass
class Settings:
    output_ext: str = formats.DEFAULT_OUTPUT_EXT
    output_mode: str = OutputMode.BESIDE_SOURCE.value
    output_dir: str = ""
    overwrite: bool = False
    recurse: bool = True
    last_source_dir: str = ""

    @property
    def output_format(self) -> formats.OutputFormat:
        return formats.OUTPUT_BY_EXT.get(
            self.output_ext, formats.OUTPUT_BY_EXT[formats.DEFAULT_OUTPUT_EXT]
        )

    @property
    def mode(self) -> OutputMode:
        try:
            return OutputMode(self.output_mode)
        except ValueError:
            return OutputMode.BESIDE_SOURCE

    def resolved_output_dir(self) -> Path | None:
        return Path(self.output_dir).expanduser() if self.output_dir else None


def load() -> Settings:
    """Read settings, falling back to defaults on anything unreadable.

    A corrupt or hand-edited settings file must not stop the app from opening —
    there is nothing in it worth failing a launch over.
    """
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(raw, dict):
        return Settings()
    known = {field: raw[field] for field in Settings().__dict__ if field in raw}
    try:
        return Settings(**known)
    except TypeError:
        return Settings()


def save(settings: Settings) -> None:
    """Write settings, ignoring failures — this is a convenience, not state."""
    try:
        SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    except OSError:
        pass

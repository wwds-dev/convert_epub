#!/usr/bin/env python3
"""Ebook Converter — entry point.

    python main.py              launch the app
    python main.py --selftest   check a build's wiring and exit

The self-test exists because a packaged .app fails in ways the source tree
cannot. Two in particular: an app launched from Finder gets a bare PATH, so the
``ebook-convert`` lookup that works in a terminal finds nothing; and PyInstaller
rewrites the dynamic-linker environment, which can make the Calibre subprocess
load the wrong libraries and die. Running this against the built binary proves
a real conversion still works before the app is trusted with a library of
books.
"""

import sys


def selftest() -> int:
    import tempfile
    from pathlib import Path

    from ebook_converter import APP_NAME, asset_path, calibre, config, formats, runner
    from ebook_converter.jobs import Job, Status

    frozen = getattr(sys, "frozen", False)
    icon = asset_path("icon.icns")
    binary = calibre.find_ebook_convert()

    print(f"{APP_NAME} self-test")
    print(f"  frozen bundle:   {frozen}")
    print(f"  icon asset:      {icon} ({'found' if icon.exists() else 'MISSING'})")
    print(f"  config path:     {config.CONFIG_PATH}")
    print(f"  ebook-convert:   {binary or 'NOT FOUND'}")
    print(f"  calibre version: {calibre.version(binary) or 'unknown'}")
    print(f"  formats:         {len(formats.INPUT_EXTENSIONS)} in / {len(formats.OUTPUT_FORMATS)} out")

    problems = []
    if not icon.exists():
        problems.append("icon asset missing from the bundle")
    if frozen and ".app/" in str(config.CONFIG_PATH):
        problems.append("config would be written inside the .app bundle")

    if binary is None:
        problems.append("ebook-convert not found — conversion cannot work")
    else:
        # A real end-to-end conversion; nothing else proves the subprocess
        # environment survived packaging.
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "selftest.txt"
            source.write_text("Chapter 1\n\nRound-trip probe.\n", encoding="utf-8")
            job = Job(source=source, target=Path(tmp) / "selftest.epub")
            runner.execute(job, formats.OUTPUT_BY_EXT["epub"], binary=binary)
            print(f"  txt -> epub:     {job.status.value} {job.detail}")
            if job.status is not Status.DONE:
                problems.append(f"round-trip conversion failed: {job.detail}")

    drift = formats.missing_from_calibre()
    if drift and any(drift):
        problems.append(f"format lists are stale — Calibre also supports {drift}")

    if problems:
        print("\nFAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("\nOK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())

    from ui.main_window import run

    sys.exit(run())

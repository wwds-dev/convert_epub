"""Executing a job: outcomes, the KEPUB rename, and failure handling."""

from pathlib import Path

import pytest

from ebook_converter import calibre, formats, runner
from ebook_converter.jobs import Job, Status

EPUB = formats.OUTPUT_BY_EXT["epub"]
KEPUB = formats.OUTPUT_BY_EXT["kepub"]


@pytest.fixture
def fake_calibre(monkeypatch):
    """Replace the subprocess call with something that just writes the file."""
    calls: list[tuple[Path, Path]] = []

    def convert(source, target, **kwargs):
        calls.append((Path(source), Path(target)))
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_text("converted", encoding="utf-8")
        return "ok"

    monkeypatch.setattr(calibre, "convert", convert)
    return calls


def test_success_records_the_output_size(tmp_path, fake_calibre):
    job = Job(source=tmp_path / "book.mobi", target=tmp_path / "book.epub")
    runner.execute(job, EPUB)
    assert job.status is Status.DONE
    assert job.target.exists()


def test_kepub_is_written_as_kepub_then_renamed(tmp_path, fake_calibre):
    """Calibre picks its plugin from the extension, so the rename is required."""
    job = Job(source=tmp_path / "book.mobi", target=tmp_path / "book.kepub.epub")
    runner.execute(job, KEPUB)

    _, written_to = fake_calibre[0]
    assert written_to.name == "book.kepub"
    assert job.status is Status.DONE
    assert job.target.name == "book.kepub.epub"
    assert job.target.exists()
    assert not written_to.exists()


def test_failure_is_recorded_not_raised(tmp_path, monkeypatch):
    def explode(source, target, **kwargs):
        raise calibre.ConversionFailed("bad input file", "…full log…")

    monkeypatch.setattr(calibre, "convert", explode)
    job = Job(source=tmp_path / "book.pdf", target=tmp_path / "book.epub")
    runner.execute(job, EPUB)

    assert job.status is Status.FAILED
    assert job.detail == "bad input file"
    assert job.log == "…full log…"


def test_a_missing_calibre_fails_the_job_with_the_install_hint(tmp_path, monkeypatch):
    def missing(source, target, **kwargs):
        raise calibre.CalibreNotFound

    monkeypatch.setattr(calibre, "convert", missing)
    job = Job(source=tmp_path / "book.pdf", target=tmp_path / "book.epub")
    runner.execute(job, EPUB)

    assert job.status is Status.FAILED
    assert "brew install --cask calibre" in job.log


def test_an_empty_output_from_a_failed_run_is_cleaned_up(tmp_path, monkeypatch):
    def half_write(source, target, **kwargs):
        Path(target).write_bytes(b"")
        raise calibre.ConversionFailed("died halfway")

    monkeypatch.setattr(calibre, "convert", half_write)
    job = Job(source=tmp_path / "book.pdf", target=tmp_path / "book.epub")
    runner.execute(job, EPUB)

    assert job.status is Status.FAILED
    assert not job.target.exists()


class TestCalibreEnvironment:
    def test_pyinstaller_library_paths_are_restored_for_the_child(self, monkeypatch):
        """A child inheriting the bundle's DYLD_LIBRARY_PATH loads the wrong libs."""
        monkeypatch.setattr("sys.frozen", True, raising=False)
        monkeypatch.setenv("DYLD_LIBRARY_PATH", "/inside/the/bundle")
        monkeypatch.setenv("DYLD_LIBRARY_PATH_ORIG", "/usr/lib")

        env = calibre.subprocess_env()
        assert env["DYLD_LIBRARY_PATH"] == "/usr/lib"
        assert "DYLD_LIBRARY_PATH_ORIG" not in env

    def test_injected_paths_are_dropped_when_there_is_no_original(self, monkeypatch):
        monkeypatch.setattr("sys.frozen", True, raising=False)
        monkeypatch.setenv("DYLD_LIBRARY_PATH", "/inside/the/bundle")
        monkeypatch.delenv("DYLD_LIBRARY_PATH_ORIG", raising=False)

        assert "DYLD_LIBRARY_PATH" not in calibre.subprocess_env()

    def test_homebrew_is_on_the_path_even_when_launched_from_finder(self, monkeypatch):
        monkeypatch.setenv("PATH", "/usr/bin:/bin")
        assert "/opt/homebrew/bin" in calibre.subprocess_env()["PATH"].split(":")

    def test_the_bundled_lookup_covers_calibres_own_installer(self):
        locations = {str(path) for path in calibre.SEARCH_PATHS}
        assert "/opt/homebrew/bin/ebook-convert" in locations
        assert "/Applications/calibre.app/Contents/MacOS/ebook-convert" in locations

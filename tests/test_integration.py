"""Real conversions through the installed Calibre.

Skipped when Calibre is absent so the suite still runs on a bare machine.
Marked ``slow`` because each conversion spawns Calibre's interpreter:

    pytest -m "not slow"     unit tests only
"""

import pytest

from ebook_converter import calibre, formats, runner
from ebook_converter.jobs import Job, OutputMode, Status, plan

pytestmark = pytest.mark.skipif(
    calibre.find_ebook_convert() is None, reason="Calibre's ebook-convert is not installed"
)

SAMPLE = "Chapter 1\n\nThe quick brown fox jumps over the lazy dog.\n\nChapter 2\n\nAnd again.\n"


@pytest.fixture(scope="module")
def seed_epub(tmp_path_factory):
    """A real EPUB to convert out of, built from plain text."""
    directory = tmp_path_factory.mktemp("seed")
    source = directory / "sample.txt"
    source.write_text(SAMPLE, encoding="utf-8")
    job = Job(source=source, target=directory / "sample.epub")
    runner.execute(job, formats.OUTPUT_BY_EXT["epub"])
    assert job.status is Status.DONE, job.detail
    return job.target


@pytest.mark.slow
@pytest.mark.parametrize("target_ext", ["pdf", "azw3", "mobi", "docx", "txt", "rtf", "fb2"])
def test_epub_converts_to_every_headline_format(seed_epub, tmp_path, target_ext):
    output_format = formats.OUTPUT_BY_EXT[target_ext]
    (job,) = plan(
        [seed_epub], output_format, mode=OutputMode.CUSTOM_FOLDER, output_dir=tmp_path
    )

    runner.execute(job, output_format)

    assert job.status is Status.DONE, job.detail
    assert job.target.parent == tmp_path
    assert job.target.stat().st_size > 0


@pytest.mark.slow
@pytest.mark.parametrize("source_ext", ["docx", "azw3", "mobi"])
def test_other_formats_convert_back_to_epub(seed_epub, tmp_path, source_ext):
    """The 'any to any' claim needs the reverse direction to work too."""
    intermediate = Job(source=seed_epub, target=tmp_path / f"sample.{source_ext}")
    runner.execute(intermediate, formats.OUTPUT_BY_EXT[source_ext])
    assert intermediate.status is Status.DONE, intermediate.detail

    back = Job(source=intermediate.target, target=tmp_path / "roundtrip.epub")
    runner.execute(back, formats.OUTPUT_BY_EXT["epub"])

    assert back.status is Status.DONE, back.detail
    assert back.target.stat().st_size > 0


@pytest.mark.slow
def test_kepub_is_named_for_kobo(seed_epub, tmp_path):
    output_format = formats.OUTPUT_BY_EXT["kepub"]
    job = Job(source=seed_epub, target=tmp_path / "sample.kepub.epub")
    runner.execute(job, output_format)

    assert job.status is Status.DONE, job.detail
    assert job.target.name == "sample.kepub.epub"
    assert not (tmp_path / "sample.kepub").exists()


@pytest.mark.slow
def test_a_corrupt_file_fails_without_taking_the_queue_down(tmp_path):
    broken = tmp_path / "broken.epub"
    broken.write_bytes(b"this is not an epub")
    job = Job(source=broken, target=tmp_path / "broken.pdf")

    runner.execute(job, formats.OUTPUT_BY_EXT["pdf"])

    assert job.status is Status.FAILED
    assert job.detail


def test_pinned_format_lists_match_the_installed_calibre():
    """Guards against a Calibre update quietly adding formats the UI hides."""
    drift = formats.missing_from_calibre()
    if drift is None:
        pytest.skip("Calibre's Python packages are not importable from this interpreter")
    missing_inputs, missing_outputs = drift
    assert not missing_inputs, f"Calibre reads these but formats.py does not list them: {missing_inputs}"
    assert not missing_outputs, f"Calibre writes these but the picker omits them: {missing_outputs}"

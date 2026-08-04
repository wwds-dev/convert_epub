"""Planning rules — what gets queued, where it lands, what is skipped."""

import pytest

from ebook_converter import formats
from ebook_converter.jobs import OutputMode, Status, collect_sources, plan, summarize

EPUB = formats.OUTPUT_BY_EXT["epub"]
PDF = formats.OUTPUT_BY_EXT["pdf"]
KEPUB = formats.OUTPUT_BY_EXT["kepub"]


def touch(path, content="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestCollectSources:
    def test_takes_single_files(self, tmp_path):
        book = touch(tmp_path / "book.epub")
        assert collect_sources([book]) == [book.resolve()]

    def test_rejects_formats_calibre_cannot_read(self, tmp_path):
        assert collect_sources([touch(tmp_path / "notes.xyz")]) == []

    def test_accepts_the_formats_the_app_advertises(self, tmp_path):
        wanted = [touch(tmp_path / f"book.{ext}") for ext in ("epub", "azw3", "mobi", "docx", "pdf", "txt")]
        assert len(collect_sources(wanted)) == len(wanted)

    def test_scans_folders_recursively(self, tmp_path):
        touch(tmp_path / "a.epub")
        touch(tmp_path / "nested" / "deep" / "b.mobi")
        assert len(collect_sources([tmp_path])) == 2

    def test_recursion_can_be_turned_off(self, tmp_path):
        touch(tmp_path / "a.epub")
        touch(tmp_path / "nested" / "b.epub")
        assert [path.name for path in collect_sources([tmp_path], recurse=False)] == ["a.epub"]

    def test_ignores_hidden_files_and_resource_forks(self, tmp_path):
        touch(tmp_path / "._Book.epub")
        touch(tmp_path / ".hidden.epub")
        touch(tmp_path / "Book.epub")
        assert [path.name for path in collect_sources([tmp_path])] == ["Book.epub"]

    def test_ignores_hidden_folders(self, tmp_path):
        touch(tmp_path / ".Trash" / "old.epub")
        touch(tmp_path / "keep.epub")
        assert [path.name for path in collect_sources([tmp_path])] == ["keep.epub"]

    def test_a_file_dropped_twice_is_queued_once(self, tmp_path):
        book = touch(tmp_path / "book.epub")
        assert collect_sources([book, tmp_path, book]) == [book.resolve()]


class TestPlan:
    def test_output_lands_beside_the_source_by_default(self, tmp_path):
        source = touch(tmp_path / "sub" / "book.epub")
        (job,) = plan([source], PDF)
        assert job.target == tmp_path / "sub" / "book.pdf"

    def test_custom_folder_flattens_output(self, tmp_path):
        source = touch(tmp_path / "sub" / "book.epub")
        out = tmp_path / "out"
        (job,) = plan([source], PDF, mode=OutputMode.CUSTOM_FOLDER, output_dir=out)
        assert job.target == out / "book.pdf"

    def test_skips_files_already_in_the_target_format(self, tmp_path):
        (job,) = plan([touch(tmp_path / "book.epub")], EPUB)
        assert job.status is Status.SKIPPED
        assert "already" in job.detail

    def test_skips_existing_output_unless_overwriting(self, tmp_path):
        source = touch(tmp_path / "book.epub")
        touch(tmp_path / "book.pdf")

        (skipped,) = plan([source], PDF)
        assert skipped.status is Status.SKIPPED
        assert skipped.detail == "output exists"

        (queued,) = plan([source], PDF, overwrite=True)
        assert queued.status is Status.QUEUED

    def test_same_name_from_different_folders_does_not_collide(self, tmp_path):
        sources = [touch(tmp_path / "one" / "Book.epub"), touch(tmp_path / "two" / "Book.epub")]
        first, second = plan(sources, PDF, mode=OutputMode.CUSTOM_FOLDER, output_dir=tmp_path / "out")
        assert first.target.name == "Book.pdf"
        assert second.target.name == "Book-2.pdf"

    def test_kepub_keeps_its_compound_extension_when_deduplicated(self, tmp_path):
        sources = [touch(tmp_path / "one" / "Book.epub"), touch(tmp_path / "two" / "Book.epub")]
        first, second = plan(sources, KEPUB, mode=OutputMode.CUSTOM_FOLDER, output_dir=tmp_path / "out")
        assert first.target.name == "Book.kepub.epub"
        assert second.target.name == "Book-2.kepub.epub"

    def test_an_epub_is_not_treated_as_an_existing_kepub(self, tmp_path):
        """The KEPUB suffix ends in '.epub' — a plain EPUB must not match it."""
        (job,) = plan([touch(tmp_path / "book.mobi")], KEPUB)
        assert job.status is Status.QUEUED
        assert job.target.name == "book.kepub.epub"


class TestSummarize:
    def test_reports_each_outcome(self, tmp_path):
        jobs = plan([touch(tmp_path / f"b{i}.mobi") for i in range(3)], PDF)
        jobs[0].status = Status.DONE
        jobs[1].status = Status.FAILED
        jobs[2].status = Status.SKIPPED
        assert summarize(jobs) == "1 converted, 1 skipped, 1 failed"

    def test_empty_plan(self):
        assert summarize([]) == "nothing to do"


@pytest.mark.parametrize("ext", ["epub", "azw3", "mobi", "docx", "pdf", "txt", "rtf", "fb2"])
def test_every_headline_format_converts_both_ways(ext):
    """The formats named in the UI must be readable and writable."""
    assert formats.is_convertible(ext)
    assert ext in formats.OUTPUT_BY_EXT

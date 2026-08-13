"""The drag-and-drop path, driven by real Qt events.

Everywhere else the tests call `add_paths` directly, which proves the planning
but not the plumbing in front of it: whether the widget accepts a drag at all,
and whether the drop is decoded into the right files. A dropped file that never
arrives would be invisible to every other test here.

These send genuine QDragEnterEvent/QDropEvent objects through
`QApplication.sendEvent`, reproducing the real sequence as closely as a test
can:

* to the **viewport**, not the widget — the table is a scroll area, and that is
  where the window server delivers a drop; Qt forwards it up to the widget's
  own handler;
* **DragEnter first**, then Drop, because a drop is only offered after the
  enter is accepted;
* against a **shown** window, since an unshown one does not route viewport
  events the same way.

The only uncovered step is the window server originating the drag.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDragEnterEvent, QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ebook_converter import config  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def window(app):
    """One shown window for the whole module.

    Built once rather than per test: repeatedly constructing and destroying a
    QMainWindow with events still in flight crashes the interpreter, and the
    window carries no state between tests that `reset` does not clear.
    """
    original_save = config.save
    config.save = lambda settings: None  # never touch the user's real settings
    from ui.main_window import MainWindow

    window = MainWindow()
    window.resize(900, 600)
    window.show()
    app.processEvents()
    yield window
    window.close()
    config.save = original_save


@pytest.fixture(autouse=True)
def reset(window, app):
    window._sources.clear()
    window._replan()
    window.statusBar().clearMessage()
    app.processEvents()


def mime_for(paths) -> QMimeData:
    """What a file manager puts on a drag: file:// URLs."""
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    return mime


def drag_enter(widget, mime) -> QDragEnterEvent:
    event = QDragEnterEvent(
        QPoint(20, 20),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(widget, event)
    return event


def drop_on(widget, paths, app) -> None:
    """Drag over `widget` and let go — the full two-event sequence."""
    # Held in locals for the duration of the send: the events reference the
    # QMimeData without owning it.
    enter_mime = mime_for(paths)
    drag_enter(widget, enter_mime)

    drop_mime = mime_for(paths)
    event = QDropEvent(
        QPointF(20, 20),
        Qt.DropAction.CopyAction,
        drop_mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(widget, event)
    app.processEvents()


def book(directory, ext="epub", name="Dropped Book"):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{name}.{ext}"
    target.write_text("not a real book, but a real file", encoding="utf-8")
    return target


class TestDragEnter:
    def test_a_file_drag_is_accepted(self, window, tmp_path):
        """If the widget refuses the drag, no drop is ever offered."""
        event = drag_enter(window.table.viewport(), mime_for([book(tmp_path)]))
        assert event.isAccepted()

    def test_a_drag_carrying_no_urls_is_not_hijacked(self, window):
        mime = QMimeData()
        mime.setText("just some text")
        event = drag_enter(window.table.viewport(), mime)
        assert not event.isAccepted()


class TestDrop:
    def test_dropping_a_single_file_queues_it(self, window, app, tmp_path):
        """The headline request: one file, dragged in — not a folder scan."""
        dropped = book(tmp_path)
        drop_on(window.table.viewport(), [dropped], app)

        assert [job.source for job in window._jobs] == [dropped.resolve()]
        assert window.table.topLevelItemCount() == 1

    def test_dropping_several_files_at_once_queues_all_of_them(self, window, app, tmp_path):
        files = [book(tmp_path, ext) for ext in ("epub", "mobi", "azw3", "docx")]
        drop_on(window.table.viewport(), files, app)

        assert len(window._jobs) == len(files)

    def test_dropping_a_folder_scans_it(self, window, app, tmp_path):
        book(tmp_path)
        book(tmp_path / "nested", "mobi")

        drop_on(window.table.viewport(), [tmp_path], app)

        assert len(window._jobs) == 2

    def test_files_and_a_folder_in_one_drop(self, window, app, tmp_path):
        single = book(tmp_path / "loose", "docx")
        book(tmp_path / "library", "mobi")

        drop_on(window.table.viewport(), [single, tmp_path / "library"], app)

        assert {job.source.name for job in window._jobs} == {
            "Dropped Book.docx",
            "Dropped Book.mobi",
        }

    def test_a_second_drop_adds_to_the_queue(self, window, app, tmp_path):
        drop_on(window.table.viewport(), [book(tmp_path / "a", "mobi")], app)
        drop_on(window.table.viewport(), [book(tmp_path / "b", "azw3")], app)

        assert len(window._jobs) == 2

    def test_dropping_the_same_file_twice_queues_it_once(self, window, app, tmp_path):
        dropped = book(tmp_path)
        drop_on(window.table.viewport(), [dropped], app)
        drop_on(window.table.viewport(), [dropped], app)

        assert len(window._jobs) == 1

    def test_an_unreadable_format_is_rejected_out_loud(self, window, app, tmp_path):
        """Silently ignoring a dropped file is indistinguishable from a bug."""
        junk = tmp_path / "notes.xyz"
        junk.write_text("nope", encoding="utf-8")

        drop_on(window.table.viewport(), [junk], app)

        assert window._jobs == []
        assert ".xyz" in window.statusBar().currentMessage()

    def test_the_window_itself_accepts_drops(self, window, app, tmp_path):
        """Dropping on the options area below the list should work too."""
        dropped = book(tmp_path, "mobi")
        drop_on(window, [dropped], app)

        assert [job.source for job in window._jobs] == [dropped.resolve()]

    def test_a_drop_while_converting_is_ignored(self, window, app, tmp_path, monkeypatch):
        """The worker owns the queue mid-run; mutating it underneath would race."""
        monkeypatch.setattr(window, "_is_running", lambda: True)
        drop_on(window.table.viewport(), [book(tmp_path)], app)

        assert window._jobs == []

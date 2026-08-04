"""The Ebook Converter window.

Layout, top to bottom: a drop target that doubles as the job queue, the file
buttons, the conversion options, and a details pane that stays collapsed until
something needs explaining.
"""

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QFont, QIcon, QKeySequence, QPainter, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ebook_converter import APP_NAME, asset_path, calibre, config, formats, jobs as jobs_mod
from ebook_converter.jobs import Job, OutputMode, Status
from ui.worker import ConversionWorker

STATUS_TEXT = {
    Status.QUEUED: "Queued",
    Status.RUNNING: "Converting…",
    Status.DONE: "Done",
    Status.SKIPPED: "Skipped",
    Status.FAILED: "Failed",
    Status.CANCELLED: "Cancelled",
}

STATUS_MARK = {
    Status.QUEUED: "•",
    Status.RUNNING: "▶",
    Status.DONE: "✓",
    Status.SKIPPED: "–",
    Status.FAILED: "✗",
    Status.CANCELLED: "✗",
}


class DropTable(QTreeWidget):
    """The job queue, which is also the drop target.

    Accepting drops on the table rather than a separate dashed rectangle means
    the drop zone stays available once files are queued — dropping a second
    batch onto a full list is the common case, not an edge case.
    """

    pathsDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setRootIsDecorated(False)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setHeaderLabels(["File", "From", "To", "Status"])
        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

    # Qt only offers the drop if the drag is accepted at every stage, so all
    # three handlers have to agree.
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            super().dropEvent(event)
            return
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile() and url.toLocalFile()
        ]
        event.acceptProposedAction()
        if paths:
            self.pathsDropped.emit(paths)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.topLevelItemCount():
            return
        painter = QPainter(self.viewport())
        colour = self.palette().color(QPalette.ColorRole.PlaceholderText)
        painter.setPen(colour)
        font = self.font()
        font.setPointSizeF(font.pointSizeF() + 3)
        painter.setFont(font)
        painter.drawText(
            self.viewport().rect(),
            Qt.AlignmentFlag.AlignCenter,
            "Drop files or folders here\n\nEPUB · AZW3 · MOBI · DOCX · PDF · TXT · RTF · FB2 · and more",
        )
        painter.end()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = config.load()
        self.binary = calibre.find_ebook_convert()
        self._sources: list[Path] = []
        self._jobs: list[Job] = []
        self._worker: ConversionWorker | None = None

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(QSize(820, 560))
        self.resize(QSize(960, 660))
        self.setAcceptDrops(True)

        icon = asset_path("icon.icns")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        self._build_ui()
        self._build_menu()
        self._apply_settings()
        self._refresh_calibre_status()
        self._replan()

    # ---------------------------------------------------------------- layout

    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(14, 14, 14, 10)
        outer.setSpacing(10)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = DropTable()
        self.table.pathsDropped.connect(self.add_paths)
        self.table.itemDoubleClicked.connect(self._on_row_activated)
        self.splitter.addWidget(self.table)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setFont(QFont("Menlo", 11))
        self.details.setVisible(False)
        self.splitter.addWidget(self.details)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        outer.addWidget(self.splitter, 1)

        outer.addLayout(self._build_file_buttons())
        outer.addWidget(self._build_options())

        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        outer.addWidget(self.warning_label)

        outer.addLayout(self._build_action_row())
        self.setCentralWidget(central)

        self.status_label = QLabel()
        self.status_label.setContentsMargins(6, 0, 6, 0)
        self.statusBar().addWidget(self.status_label, 1)
        self.recheck_button = QPushButton("Recheck")
        self.recheck_button.setVisible(False)
        self.recheck_button.clicked.connect(self._recheck_calibre)
        self.statusBar().addPermanentWidget(self.recheck_button)

    def _build_file_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self.add_files_button = QPushButton("Add Files…")
        self.add_files_button.clicked.connect(self.choose_files)
        self.add_folder_button = QPushButton("Add Folder…")
        self.add_folder_button.clicked.connect(self.choose_folder)
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_all)

        for button in (self.add_files_button, self.add_folder_button, self.remove_button, self.clear_button):
            row.addWidget(button)

        row.addStretch(1)

        self.details_button = QPushButton("Show Details")
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self._toggle_details)
        row.addWidget(self.details_button)
        return row

    def _build_options(self) -> QWidget:
        box = QFrame()
        box.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        format_row = QHBoxLayout()
        format_row.setSpacing(8)
        format_row.addWidget(QLabel("Convert to:"))
        self.format_box = QComboBox()
        for output_format in formats.OUTPUT_FORMATS:
            self.format_box.addItem(output_format.label, output_format.ext)
        self.format_box.currentIndexChanged.connect(self._on_format_changed)
        format_row.addWidget(self.format_box)
        self.format_note = QLabel()
        self.format_note.setEnabled(False)
        format_row.addWidget(self.format_note, 1)
        layout.addLayout(format_row)

        output_row = QHBoxLayout()
        output_row.setSpacing(8)
        output_row.addWidget(QLabel("Save to:"))
        self.beside_radio = QRadioButton("Beside the original")
        self.folder_radio = QRadioButton("Folder:")
        self.output_group = QButtonGroup(self)
        self.output_group.addButton(self.beside_radio)
        self.output_group.addButton(self.folder_radio)
        self.output_group.buttonToggled.connect(self._on_output_mode_changed)
        output_row.addWidget(self.beside_radio)
        output_row.addWidget(self.folder_radio)

        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("Choose a destination folder…")
        self.output_dir_edit.editingFinished.connect(self._on_output_dir_edited)
        output_row.addWidget(self.output_dir_edit, 1)
        self.browse_button = QPushButton("Choose…")
        self.browse_button.clicked.connect(self.choose_output_dir)
        output_row.addWidget(self.browse_button)
        layout.addLayout(output_row)

        toggles = QHBoxLayout()
        toggles.setSpacing(16)
        self.overwrite_check = QCheckBox("Overwrite existing files")
        self.overwrite_check.toggled.connect(self._on_overwrite_changed)
        self.recurse_check = QCheckBox("Include subfolders")
        self.recurse_check.toggled.connect(self._on_recurse_changed)
        toggles.addWidget(self.overwrite_check)
        toggles.addWidget(self.recurse_check)
        toggles.addStretch(1)
        layout.addLayout(toggles)
        return box

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        row.addWidget(self.progress, 1)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel_conversion)
        row.addWidget(self.cancel_button)

        self.convert_button = QPushButton("Convert")
        self.convert_button.setDefault(True)
        self.convert_button.clicked.connect(self.start_conversion)
        row.addWidget(self.convert_button)
        return row

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        add_files = QAction("Add Files…", self)
        add_files.setShortcut(QKeySequence.StandardKey.Open)
        add_files.triggered.connect(self.choose_files)
        file_menu.addAction(add_files)

        add_folder = QAction("Add Folder…", self)
        add_folder.setShortcut(QKeySequence("Ctrl+Shift+O"))
        add_folder.triggered.connect(self.choose_folder)
        file_menu.addAction(add_folder)

        file_menu.addSeparator()

        remove = QAction("Remove Selected", self)
        remove.setShortcut(QKeySequence.StandardKey.Delete)
        remove.triggered.connect(self.remove_selected)
        file_menu.addAction(remove)

        clear = QAction("Clear List", self)
        clear.triggered.connect(self.clear_all)
        file_menu.addAction(clear)

        file_menu.addSeparator()

        convert = QAction("Convert", self)
        convert.setShortcut(QKeySequence("Ctrl+Return"))
        convert.triggered.connect(self.start_conversion)
        file_menu.addAction(convert)

        reveal = QAction("Reveal Output in Finder", self)
        reveal.setShortcut(QKeySequence("Ctrl+R"))
        reveal.triggered.connect(self.reveal_selected)
        file_menu.addAction(reveal)

    def _apply_settings(self) -> None:
        index = self.format_box.findData(self.settings.output_format.ext)
        self.format_box.setCurrentIndex(max(index, 0))
        self.beside_radio.setChecked(self.settings.mode is OutputMode.BESIDE_SOURCE)
        self.folder_radio.setChecked(self.settings.mode is OutputMode.CUSTOM_FOLDER)
        self.output_dir_edit.setText(self.settings.output_dir)
        self.overwrite_check.setChecked(self.settings.overwrite)
        self.recurse_check.setChecked(self.settings.recurse)
        self._update_output_widgets()
        self._update_format_note()

    # ------------------------------------------------------------ drag/drop

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile() and url.toLocalFile()
        ]
        event.acceptProposedAction()
        if paths:
            self.add_paths(paths)

    # -------------------------------------------------------------- sources

    def add_paths(self, paths: list[Path]) -> None:
        """Queue everything convertible under ``paths``.

        Reports what was rejected: silently dropping a file the user just
        dragged in looks like the app is broken.
        """
        if self._is_running():
            return

        found = jobs_mod.collect_sources(paths, recurse=self.recurse_check.isChecked())
        known = {source.resolve() for source in self._sources}
        added = [path for path in found if path not in known]
        self._sources.extend(added)

        if added:
            self.settings.last_source_dir = str(added[-1].parent)
            self._save_settings()

        if not found:
            self._report_nothing_added(paths)
        self._replan()

    def _report_nothing_added(self, paths: list[Path]) -> None:
        files = [path for path in paths if path.is_file()]
        unsupported = sorted({path.suffix.lower() or "(no extension)" for path in files if not formats.is_convertible(path.suffix)})
        if unsupported:
            self._flash_status(f"Calibre cannot read {', '.join(unsupported)} — nothing added.")
        elif any(path.is_dir() for path in paths):
            scope = "" if self.recurse_check.isChecked() else " (subfolders are off)"
            self._flash_status(f"No convertible files found in that folder{scope}.")
        else:
            self._flash_status("Nothing to add.")

    def choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add files",
            self.settings.last_source_dir or str(Path.home()),
            formats.file_dialog_filter(),
        )
        if paths:
            self.add_paths([Path(path) for path in paths])

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Add folder", self.settings.last_source_dir or str(Path.home())
        )
        if folder:
            self.add_paths([Path(folder)])

    def remove_selected(self) -> None:
        if self._is_running():
            return
        rows = sorted((self.table.indexOfTopLevelItem(item) for item in self.table.selectedItems()), reverse=True)
        for row in dict.fromkeys(rows):
            if 0 <= row < len(self._sources):
                del self._sources[row]
        self._replan()

    def clear_all(self) -> None:
        if self._is_running():
            return
        self._sources.clear()
        self.details.clear()
        self._replan()

    # -------------------------------------------------------------- options

    def _on_format_changed(self) -> None:
        self.settings.output_ext = self.format_box.currentData() or formats.DEFAULT_OUTPUT_EXT
        self._save_settings()
        self._update_format_note()
        self._replan()

    def _on_output_mode_changed(self) -> None:
        mode = OutputMode.CUSTOM_FOLDER if self.folder_radio.isChecked() else OutputMode.BESIDE_SOURCE
        self.settings.output_mode = mode.value
        self._save_settings()
        self._update_output_widgets()
        self._replan()

    def _on_output_dir_edited(self) -> None:
        self.settings.output_dir = self.output_dir_edit.text().strip()
        self._save_settings()
        self._replan()

    def _on_overwrite_changed(self, checked: bool) -> None:
        self.settings.overwrite = checked
        self._save_settings()
        self._replan()

    def _on_recurse_changed(self, checked: bool) -> None:
        self.settings.recurse = checked
        self._save_settings()

    def choose_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose destination folder", self.settings.output_dir or str(Path.home())
        )
        if folder:
            self.output_dir_edit.setText(folder)
            self.settings.output_dir = folder
            self.folder_radio.setChecked(True)
            self._save_settings()
            self._replan()

    def _update_output_widgets(self) -> None:
        custom = self.folder_radio.isChecked()
        self.output_dir_edit.setEnabled(custom)
        self.browse_button.setEnabled(custom)

    def _update_format_note(self) -> None:
        output_format = self._current_format()
        self.format_note.setText(output_format.note)
        self.format_box.setToolTip(output_format.note)

    def _current_format(self) -> formats.OutputFormat:
        ext = self.format_box.currentData() or formats.DEFAULT_OUTPUT_EXT
        return formats.OUTPUT_BY_EXT[ext]

    def _save_settings(self) -> None:
        config.save(self.settings)

    # ----------------------------------------------------------------- plan

    def _replan(self) -> None:
        """Recompute the queue and redraw it.

        Cheap enough to run on every settings change, which is what keeps the
        'To' and 'Status' columns honest before anything is converted.
        """
        mode = OutputMode.CUSTOM_FOLDER if self.folder_radio.isChecked() else OutputMode.BESIDE_SOURCE
        output_dir = Path(self.output_dir_edit.text().strip()).expanduser() if self.output_dir_edit.text().strip() else None
        self._jobs = jobs_mod.plan(
            self._sources,
            self._current_format(),
            mode=mode,
            output_dir=output_dir,
            overwrite=self.overwrite_check.isChecked(),
        )
        self._render_jobs()
        self._update_warning()
        self._update_buttons()
        self._explain_empty_queue()

    def _explain_empty_queue(self) -> None:
        """Say why a full list has nothing to do — the queue alone looks broken.

        Only on replans: after a run, the status bar belongs to the summary.
        """
        if self._is_running() or not self._jobs:
            return
        if any(job.is_pending for job in self._jobs):
            self._refresh_calibre_status()
            return
        skipped = sum(1 for job in self._jobs if job.status is Status.SKIPPED)
        if skipped:
            self._set_status(
                f"Nothing to convert — {skipped} file(s) skipped. "
                "Turn on overwrite, or pick a different format."
            )

    def _render_jobs(self) -> None:
        self.table.clear()
        for job in self._jobs:
            item = QTreeWidgetItem(
                [
                    job.source.name,
                    job.source_ext.upper(),
                    self._current_format().label,
                    self._status_text(job),
                ]
            )
            item.setToolTip(0, str(job.source))
            item.setToolTip(2, str(job.target))
            self.table.addTopLevelItem(item)

    def _update_row(self, index: int) -> None:
        item = self.table.topLevelItem(index)
        if item is None:
            return
        job = self._jobs[index]
        item.setText(3, self._status_text(job))
        item.setToolTip(2, str(job.target))
        self.table.scrollToItem(item)

    def _status_text(self, job: Job) -> str:
        text = f"{STATUS_MARK[job.status]}  {STATUS_TEXT[job.status]}"
        return f"{text} — {job.detail}" if job.detail else text

    def _update_warning(self) -> None:
        lossy = sorted({job.source_ext.upper() for job in self._jobs if formats.is_lossy_input(job.source_ext)})
        if not lossy:
            self.warning_label.setVisible(False)
            return
        self.warning_label.setText(
            f"⚠︎  {', '.join(lossy)} has no reliable text structure — Calibre will convert it, "
            "but expect broken paragraphs and lost formatting in the result."
        )
        self.warning_label.setVisible(True)

    def _update_buttons(self) -> None:
        running = self._is_running()
        pending = sum(1 for job in self._jobs if job.is_pending)
        retryable = sum(1 for job in self._jobs if job.status in (Status.FAILED, Status.CANCELLED))

        # With nothing pending but something failed, the button becomes a retry
        # rather than going dead — otherwise a transient failure can only be
        # cleared by emptying the list and starting over.
        if pending:
            label, enabled = f"Convert {pending} File{'s' if pending != 1 else ''}", True
        elif retryable:
            label, enabled = f"Retry {retryable} File{'s' if retryable != 1 else ''}", True
        else:
            label, enabled = "Convert", False

        self.convert_button.setText(label)
        self.convert_button.setEnabled(enabled and self.binary is not None and not running)
        for button in (self.add_files_button, self.add_folder_button, self.remove_button, self.clear_button):
            button.setEnabled(not running)
        self.format_box.setEnabled(not running)

    # ----------------------------------------------------------- conversion

    def start_conversion(self) -> None:
        if self._is_running() or self.binary is None:
            return

        pending = [job for job in self._jobs if job.is_pending]
        if not pending:
            pending = self._requeue_failures()
        if not pending:
            return

        if self.folder_radio.isChecked():
            output_dir = Path(self.output_dir_edit.text().strip()).expanduser()
            if not self.output_dir_edit.text().strip():
                QMessageBox.warning(self, APP_NAME, "Choose a destination folder first.")
                return
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                QMessageBox.critical(self, APP_NAME, f"Cannot write to that folder:\n{exc}")
                return

        self.details.clear()
        self.progress.setRange(0, len(pending))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.cancel_button.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.convert_button.setVisible(False)

        self._worker = ConversionWorker(self._jobs, self._current_format(), self.binary, self)
        self._worker.job_started.connect(self._on_job_started)
        self._worker.job_finished.connect(self._on_job_finished)
        self._worker.finished.connect(self._on_run_finished)
        self._update_buttons()
        self._worker.start()

    def _requeue_failures(self) -> list[Job]:
        """Put failed and cancelled jobs back in the queue for another attempt."""
        retryable = [job for job in self._jobs if job.status in (Status.FAILED, Status.CANCELLED)]
        for job in retryable:
            job.status = Status.QUEUED
            job.detail = ""
            job.log = ""
        if retryable:
            self._render_jobs()
        return retryable

    def cancel_conversion(self) -> None:
        if self._worker is not None:
            self.cancel_button.setEnabled(False)
            self._set_status("Cancelling…")
            self._worker.cancel()

    def _on_job_started(self, index: int) -> None:
        self._update_row(index)
        self._set_status(f"Converting {self._jobs[index].source.name}…")

    def _on_job_finished(self, index: int) -> None:
        job = self._jobs[index]
        self._update_row(index)
        self.progress.setValue(self.progress.value() + 1)
        if job.status is Status.FAILED:
            self._append_details(f"✗ {job.source.name}\n    {job.detail}\n")

    def _on_run_finished(self) -> None:
        cancelled = self._worker is not None and self._worker.cancelled
        self._worker = None
        self.progress.setVisible(False)
        self.cancel_button.setVisible(False)
        self.convert_button.setVisible(True)

        summary = jobs_mod.summarize(self._jobs)
        self._set_status(("Cancelled — " if cancelled else "Finished — ") + summary)

        failures = [job for job in self._jobs if job.status is Status.FAILED]
        if failures and not self.details_button.isChecked():
            self.details_button.setChecked(True)
        self._update_buttons()

    def _is_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    # -------------------------------------------------------------- details

    def _toggle_details(self, checked: bool) -> None:
        self.details.setVisible(checked)
        self.details_button.setText("Hide Details" if checked else "Show Details")
        if checked and self.splitter.sizes()[1] == 0:
            height = self.splitter.height()
            self.splitter.setSizes([int(height * 0.65), int(height * 0.35)])

    def _append_details(self, text: str) -> None:
        self.details.append(text)

    def _on_row_activated(self, item: QTreeWidgetItem) -> None:
        """Double-click: show the log for a failure, reveal the file otherwise."""
        index = self.table.indexOfTopLevelItem(item)
        if not 0 <= index < len(self._jobs):
            return
        job = self._jobs[index]
        if job.status is Status.FAILED:
            self.details_button.setChecked(True)
            self.details.setPlainText(f"{job.source}\n\n{job.detail}\n\n{job.log}")
        elif job.status is Status.DONE:
            self._reveal(job.target)
        else:
            self._reveal(job.source)

    def reveal_selected(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        index = self.table.indexOfTopLevelItem(items[0])
        if 0 <= index < len(self._jobs):
            job = self._jobs[index]
            self._reveal(job.target if job.status is Status.DONE else job.source)

    def _reveal(self, path: Path) -> None:
        target = path if path.exists() else path.parent
        if target.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.parent if target.is_file() else target)))

    # --------------------------------------------------------------- status

    def _refresh_calibre_status(self) -> None:
        if self.binary is None:
            self._set_status("Calibre not found — conversion is unavailable.")
            self.recheck_button.setVisible(True)
            return
        self.recheck_button.setVisible(False)
        version = calibre.version(self.binary) or "unknown version"
        self._set_status(f"{version} · {self.binary}")

    def _recheck_calibre(self) -> None:
        self.binary = calibre.find_ebook_convert()
        self._refresh_calibre_status()
        self._update_buttons()
        if self.binary is None:
            QMessageBox.information(self, APP_NAME, calibre.INSTALL_HINT)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _flash_status(self, text: str) -> None:
        self.statusBar().showMessage(text, 6000)

    # --------------------------------------------------------------- window

    def closeEvent(self, event):
        if self._is_running():
            answer = QMessageBox.question(
                self,
                APP_NAME,
                "A conversion is still running. Stop it and quit?",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Close,
                QMessageBox.StandardButton.Cancel,
            )
            if answer is not QMessageBox.StandardButton.Close:
                event.ignore()
                return
            self._worker.cancel()
            self._worker.wait(10_000)
        self._save_settings()
        super().closeEvent(event)


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)

    icon = asset_path("icon.icns")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    window = MainWindow()
    window.show()

    if window.binary is None:
        QMessageBox.warning(window, APP_NAME, calibre.INSTALL_HINT)

    return app.exec()

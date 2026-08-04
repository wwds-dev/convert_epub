"""Background conversion thread.

Calibre takes seconds to minutes per file, so conversions cannot run on the GUI
thread. The worker owns the queue while it runs; the window only reads jobs
back when told a job finished.
"""

import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ebook_converter import formats, runner
from ebook_converter.jobs import Job, Status


class ConversionWorker(QThread):
    """Runs a list of jobs one at a time, reporting each by index."""

    job_started = Signal(int)
    job_finished = Signal(int)

    def __init__(self, jobs: list[Job], output_format: formats.OutputFormat, binary: Path | None, parent=None):
        super().__init__(parent)
        self._jobs = jobs
        self._output_format = output_format
        self._binary = binary
        self._cancelled = threading.Event()
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def run(self) -> None:
        for index, job in enumerate(self._jobs):
            if not job.is_pending:
                continue
            if self._cancelled.is_set():
                job.status = Status.CANCELLED
                job.detail = "cancelled"
                self.job_finished.emit(index)
                continue

            self.job_started.emit(index)
            runner.execute(job, self._output_format, binary=self._binary, register=self._register)

            # A killed child looks like a failure; report it as the cancellation
            # it actually was.
            if self._cancelled.is_set() and job.status is Status.FAILED:
                job.status = Status.CANCELLED
                job.detail = "cancelled"

            with self._lock:
                self._process = None
            self.job_finished.emit(index)

    def cancel(self) -> None:
        """Stop after the current file, killing it if it is still running."""
        self._cancelled.set()
        with self._lock:
            process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def _register(self, process: subprocess.Popen) -> None:
        with self._lock:
            self._process = process
        # Cancelled between the check in run() and the process starting.
        if self._cancelled.is_set():
            try:
                process.terminate()
            except OSError:
                pass

"""Hilo de trabajo (QThread): procesa una carpeta entera sin bloquear la interfaz."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .batch import BatchSummary, process_files
from .scanner import find_mkv_files


class BatchWorker(QThread):
    progress = Signal(int, int)
    result = Signal(object)       # ApplyResult de cada episodio
    log = Signal(str)
    done = Signal(object)         # BatchSummary

    def __init__(self, tools, root, recursive, clear_other, dry_run, files=None, parent=None):
        super().__init__(parent)
        self.tools, self.root, self.recursive = tools, root, recursive
        self.clear_other, self.dry_run, self.files = clear_other, dry_run, files
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            files = self.files if self.files is not None else find_mkv_files(self.root, self.recursive)
        except OSError as exc:
            self.log.emit(f"No se pudo leer la carpeta: {exc}")
            self.done.emit(BatchSummary(dry_run=self.dry_run))
            return
        self.log.emit(f"Archivos MKV encontrados: {len(files)}")
        self.progress.emit(0, max(len(files), 1))

        def on_result(res, i, total):
            self.result.emit(res)
            self.progress.emit(i, total)

        summary = process_files(self.tools, files, self.clear_other, self.dry_run,
                                on_result, lambda: self._cancel)
        if summary.cancelled:
            self.log.emit("Operación cancelada.")
        self.done.emit(summary)


# ---------------------------------------------------------------------------
# Modo procesamiento completo (renombrado + subtítulos)
# ---------------------------------------------------------------------------
class FullPreviewWorker(QThread):
    """Construye la previsualización (nombres nuevos + pista que se elegirá). No modifica nada."""
    progress = Signal(int, int)
    log = Signal(str)
    done = Signal(object)         # FullPlan (o None si falló)

    def __init__(self, tools, root, recursive, rules, extensions, clear_other, parent=None):
        super().__init__(parent)
        self.tools, self.root, self.recursive = tools, root, recursive
        self.rules, self.extensions, self.clear_other = rules, extensions, clear_other
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        from .fullmode import build_full_plan
        try:
            plan = build_full_plan(self.tools, self.root, self.recursive, self.rules, self.extensions,
                                   self.clear_other, lambda i, n: self.progress.emit(i, n), lambda: self._cancel)
        except Exception as exc:       # carpeta ilegible, permisos...
            self.log.emit(f"No se pudo preparar la previsualización: {exc}")
            self.done.emit(None)
            return
        self.done.emit(plan)


class FullRunWorker(QThread):
    """Ejecuta el plan aprobado: renombra y después fija la pista predeterminada de cada MKV."""
    progress = Signal(int, int)
    result = Signal(object)       # EntryResult
    log = Signal(str)
    done = Signal(object)         # FullReport (o None si falló)

    def __init__(self, tools, plan, parent=None):
        super().__init__(parent)
        self.tools, self.plan = tools, plan
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        from .fullmode import execute_full_plan
        try:
            report = execute_full_plan(self.tools, self.plan,
                                       on_progress=lambda i, n: self.progress.emit(i, n),
                                       on_result=lambda r: self.result.emit(r),
                                       cancelled=lambda: self._cancel)
        except Exception as exc:
            self.log.emit(f"Error inesperado durante el procesamiento: {exc}")
            self.done.emit(None)
            return
        self.done.emit(report)


# ---------------------------------------------------------------------------
# Renombrado masivo: ejecución y deshacer fuera del hilo de la interfaz
# ---------------------------------------------------------------------------
class RenameWorker(QThread):
    """Ejecuta un RenamePlan ya revisado y lo guarda en el historial."""
    progress = Signal(int, int)
    done = Signal(object, str)    # (lista de RenameOutcome, aviso del historial o "")

    def __init__(self, plan, folder, parent=None):
        super().__init__(parent)
        self.plan, self.folder = plan, folder

    def run(self):
        from . import rename_history
        from .renamer import execute_plan
        outcomes = execute_plan(self.plan, lambda i, n: self.progress.emit(i, n))
        warning = ""
        try:
            rename_history.record_rename(outcomes, self.folder, mode="rename")
        except OSError as exc:
            warning = f"Se renombró, pero no se pudo guardar el historial: {exc}"
        self.done.emit(outcomes, warning)


class UndoWorker(QThread):
    """Deshace el último renombrado pendiente (rename_history.undo_last)."""
    done = Signal(object)         # UndoReport (o la excepción si falló)

    def run(self):
        from . import rename_history
        try:
            self.done.emit(rename_history.undo_last())
        except Exception as exc:  # historial ilegible, permisos...
            self.done.emit(exc)

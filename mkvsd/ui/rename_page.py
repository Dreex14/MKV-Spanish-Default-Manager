"""Sección «Renombrado masivo»: limpia y modifica los nombres de los archivos de una carpeta por lotes.

Distribución: reglas a la izquierda, previsualización en vivo a la derecha. La previsualización se recalcula
sola al cambiar cualquier regla y SIEMPRE coincide con lo que se ejecutará: antes de renombrar se vuelve a
leer la carpeta y, si ha cambiado, se pide revisar de nuevo. El renombrado y el deshacer se ejecutan en un
hilo aparte para no bloquear la ventana.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QStyledItemDelegate, QTableWidget,
    QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import rename_history
from ..renamer import RenameRules, RStatus, build_plan, list_files, parse_extensions
from ..workers import RenameWorker, UndoWorker
from . import icons, styles
from .base import BasePage
from .widgets import (
    KIND_CHANGE, KIND_REVIEW, KIND_SAME, ROLE_KIND, EmptyState, FolderBar, ResultsView, ToggleSwitch, brush,
    button, label, stacked,
)

COMMON_EXTENSIONS = [".mkv", ".mp4", ".avi", ".srt", ".ass"]
STATUS_TEXT = {
    RStatus.CHANGE: "Se renombrará",
    RStatus.SAME: "Sin cambios",
    RStatus.CONFLICT_DUP: "Conflicto: nombre duplicado",
    RStatus.CONFLICT_EXISTS: "Conflicto: ya existe",
    RStatus.INVALID: "No válido",
}
STATUS_COLOR = {
    RStatus.CHANGE: styles.COLOR_CASTELLANO,
    RStatus.SAME: styles.COLOR_OTRO,
    RStatus.CONFLICT_DUP: styles.COLOR_AMBIGUO,
    RStatus.CONFLICT_EXISTS: styles.COLOR_AMBIGUO,
    RStatus.INVALID: styles.COLOR_AMBIGUO,
}
MODE_TEXT = {"rename": "Renombrado masivo", "full": "Procesamiento completo"}


def _signature(plan):
    return [(str(i.path), i.new_name, i.status.value) for i in plan.items]


class LiveEditDelegate(QStyledItemDelegate):
    """Confirma la celda a cada pulsación de tecla, para que la previsualización se actualice mientras escribes."""

    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            editor.textChanged.connect(lambda _text, e=editor: self.commitData.emit(e))
        return editor


class HistoryDialog(QDialog):
    """Historial de renombrados: consulta, «Guardar historial» y «Borrar historial»."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Historial de renombrados")
        self.resize(980, 580)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)
        lay.addWidget(label("Historial de renombrados", "pageTitle"))
        self.info = label("", "muted", wrap=True)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.info)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Fecha / archivo", "Tipo / nombre nuevo", "Carpeta", "Estado"])
        self.tree.setAlternatingRowColors(True)
        for col, w in enumerate([300, 330, 220]):
            self.tree.setColumnWidth(col, w)
        lay.addWidget(self.tree, 1)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.save = ToggleSwitch("Guardar historial")
        self.save.setChecked(ctx.save_history())
        self.save.setToolTip("Si lo desactivas, los próximos renombrados no se guardan y no se podrán deshacer. "
                             "Lo que ya está guardado se conserva.")
        self.save.toggled.connect(self._toggle_save)
        row.addWidget(self.save)
        row.addStretch(1)
        self.btn_clear = button("Borrar historial", "danger", "close", icon_color=styles.DANGER)
        self.btn_clear.clicked.connect(self._clear)
        row.addWidget(self.btn_clear)
        close = button("Cerrar")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        self._fill()

    def _fill(self):
        self.tree.clear()
        entries = rename_history.load_history()
        state = "" if self.ctx.save_history() else " · Guardado desactivado: los nuevos renombrados no se anotan."
        self.info.setText(f"{len(entries)} operación(es) guardadas en {rename_history.history_path()}{state}")
        for e in reversed(entries):
            top = QTreeWidgetItem(self.tree)
            top.setText(0, e.time.replace("T", " "))
            top.setText(1, f"{MODE_TEXT.get(e.mode, e.mode)} · {len(e.renames)} archivo(s)")
            top.setText(2, e.folder)
            top.setToolTip(2, e.folder)
            if e.fully_undone:
                st, color = "Deshecho", styles.COLOR_OTRO
            elif len(e.pending) < len(e.renames):
                st, color = f"Parcialmente deshecho ({len(e.pending)} pendientes)", styles.COLOR_LATINO
            else:
                st, color = "Aplicado", styles.COLOR_CASTELLANO
            top.setText(3, st)
            top.setForeground(3, brush(color))
            for r in e.renames[:500]:
                child = QTreeWidgetItem(top)
                child.setText(0, Path(r["old"]).name)
                child.setText(1, "→ " + Path(r["new"]).name)
                child.setToolTip(0, r["old"])
                child.setToolTip(1, r["new"])
            if len(e.renames) > 500:
                more = QTreeWidgetItem(top)
                more.setText(0, f"… y {len(e.renames) - 500} más")
        if not entries:
            QTreeWidgetItem(self.tree).setText(0, "No hay renombrados guardados.")
        self.btn_clear.setEnabled(bool(entries) or rename_history.history_path().exists())

    def _toggle_save(self, on):
        self.ctx.set_save_history(on)
        self._fill()

    def _clear(self):
        if confirm_clear_history(self, self.ctx):
            self._fill()


def confirm_clear_history(parent, ctx) -> bool:
    """Pide confirmación y borra el historial de renombrados. Devuelve True si se borró."""
    n = len(rename_history.load_history())
    pending = rename_history.last_undoable() is not None
    msg = f"Se borrarán {n} operación(es) del historial de renombrados."
    if pending:
        msg += "\n\nDespués ya no podrás deshacer ninguno de esos renombrados."
    msg += "\nLos archivos no se tocan.\n\n¿Borrar el historial?"
    if QMessageBox.question(parent, "Borrar historial", msg) != QMessageBox.StandardButton.Yes:
        return False
    try:
        ctx.clear_history()
    except OSError as exc:
        QMessageBox.warning(parent, "Borrar historial", f"No se pudo borrar el historial: {exc}")
        return False
    return True


def _section(title: str, hint: str = ""):
    """Bloque del panel de reglas: título, ayuda opcional y layout para el contenido."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lay.addWidget(label(title, "sectionTitle"))
    if hint:
        lay.addWidget(label(hint, "subtle", wrap=True))
    return w, lay


class RenamePage(BasePage):
    def __init__(self, ctx, parent=None):
        super().__init__(ctx, "Renombrado masivo",
                         "Limpia y cambia los nombres de muchos archivos a la vez. La previsualización se "
                         "actualiza mientras escribes.", "Registro de renombrados", parent)
        self._files = []
        self._listing_key = None
        self._plan = None
        self.worker = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._update_preview)
        self._build_ui()
        self._load_settings()
        self._connect_changes()
        self._update_preview()
        ctx.history_changed.connect(self._refresh_undo_button)

    # ---------- construcción ----------
    def _build_ui(self):
        hist = button("Historial", "subtle", "history", "Ver todas las operaciones de renombrado guardadas")
        hist.clicked.connect(self._on_history)
        self.header.add_right(hist)
        self.btn_history = hist

        self.folder_bar = FolderBar("Carpeta con los archivos", "Elige la carpeta con los archivos que quieres renombrar")
        self.folder_bar.folder_chosen.connect(lambda _f: self.refresh())
        self.folder_bar.recursive_changed.connect(self._schedule_update)
        self.btn_reload = QPushButton()
        self.btn_reload.setObjectName("iconButton")
        self.btn_reload.setIcon(self._icon("refresh"))
        self.btn_reload.setToolTip("Recargar la lista de archivos")
        self.btn_reload.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reload.clicked.connect(self.refresh)
        self.folder_bar.layout().insertWidget(2, self.btn_reload)
        self.body_lay.addWidget(self.folder_bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self._build_rules_panel())

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)
        rl.setSpacing(8)
        self.summary = QLabel()
        self.summary.setObjectName("summary")
        self.summary.setWordWrap(True)
        rl.addWidget(self.summary)
        self.empty = EmptyState("rename", "Elige una carpeta para empezar",
                                "Verás el nombre original y el nuevo de cada archivo antes de renombrar. "
                                "Nada se sobrescribe y podrás deshacerlo.")
        b = button("Elegir carpeta…", "primary", "folder")
        b.clicked.connect(self.folder_bar._browse)
        self.empty.add_button(b)
        self.results = ResultsView(["Nombre original", "Nombre nuevo", "Estado"], [40, 40, 20], filters=[
            ("all", "Todos"), (KIND_CHANGE, "Se renombrarán"), (KIND_REVIEW, "Bloqueados")])
        self.tree = self.results.tree
        self.tree.setRootIsDecorated(False)
        self.stack = stacked(self.empty, self.results)
        rl.addWidget(self.stack, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([360, 800])
        self.body_lay.addWidget(split, 1)

        self.btn_undo = button("Deshacer último renombrado", icon_name="undo")
        self.btn_undo.clicked.connect(self._on_undo)
        self.btn_rename = button("Renombrar archivos", "primary", "rename")
        self.btn_rename.clicked.connect(self._on_rename)
        self.actions.add_button(self.btn_undo)
        self.actions.add_button(self.btn_rename)

    def _icon(self, name):
        return icons.icon(name, styles.MUTED, 16)

    def _build_rules_panel(self):
        panel = QFrame()
        panel.setObjectName("card")
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(16)

        # Extensiones
        w, sl = _section("Archivos incluidos")
        chips = QGridLayout()
        chips.setHorizontalSpacing(6)
        chips.setVerticalSpacing(6)
        self.ext_checks = {}
        for i, ext in enumerate(COMMON_EXTENSIONS):
            cb = button(ext[1:].upper(), "chip")
            cb.setCheckable(True)
            self.ext_checks[ext] = cb
            chips.addWidget(cb, 0, i)
        sl.addLayout(chips)
        self.extra_edit = QLineEdit()
        self.extra_edit.setPlaceholderText("Otras extensiones: ssa, sub, idx…")
        sl.addWidget(self.extra_edit)
        self.chk_all = ToggleSwitch("Todos los archivos")
        self.chk_all.setToolTip("Ignora el filtro de extensiones (los archivos ocultos y de sistema nunca se incluyen).")
        sl.addWidget(self.chk_all)
        lay.addWidget(w)

        # Eliminar
        w, sl = _section("Eliminar texto", "Uno por línea. Ejemplo: [1080p_]")
        self.removals_edit = QPlainTextEdit()
        self.removals_edit.setPlaceholderText("[1080p_]\nWEB-DL\nx264")
        self.removals_edit.setFixedHeight(92)
        sl.addWidget(self.removals_edit)
        lay.addWidget(w)

        # Sustituir
        w, sl = _section("Sustituir texto")
        self.repl_table = QTableWidget(0, 2)
        self.repl_table.setHorizontalHeaderLabels(["Buscar", "Reemplazar por"])
        self.repl_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.repl_table.verticalHeader().setVisible(False)
        self.repl_table.verticalHeader().setDefaultSectionSize(28)
        self.repl_table.setItemDelegate(LiveEditDelegate(self.repl_table))
        self.repl_table.setFixedHeight(118)
        sl.addWidget(self.repl_table)
        brow = QHBoxLayout()
        brow.setSpacing(4)
        btn_add = button("Añadir", "subtle", "plus")
        btn_add.clicked.connect(lambda _checked=False: self._add_repl_row())
        btn_del = button("Quitar", "subtle", "minus")
        btn_del.clicked.connect(self._del_repl_row)
        brow.addWidget(btn_add)
        brow.addWidget(btn_del)
        brow.addStretch(1)
        sl.addLayout(brow)
        lay.addWidget(w)

        # Limpieza
        w, sl = _section("Limpieza automática")
        self.chk_spaces = QCheckBox("Quitar espacios sobrantes")
        self.chk_dupes = QCheckBox("Quitar caracteres duplicados (.. -- __ ,,)")
        self.chk_brackets = QCheckBox("Quitar corchetes y paréntesis vacíos")
        self.chk_edges = QCheckBox("Quitar separadores sueltos en los extremos")
        self.chk_edges.setToolTip("Quita - _ . , ; al principio o al final del nombre (la extensión no se toca).")
        for c in (self.chk_spaces, self.chk_dupes, self.chk_brackets, self.chk_edges):
            sl.addWidget(c)
        lay.addWidget(w)

        # Prefijo y sufijo
        w, sl = _section("Prefijo y sufijo")
        pr = QHBoxLayout()
        pr.setSpacing(6)
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText("Prefijo")
        self.suffix_edit = QLineEdit()
        self.suffix_edit.setPlaceholderText("Sufijo")
        self.suffix_edit.setToolTip("Se añade antes de la extensión")
        pr.addWidget(self.prefix_edit)
        pr.addWidget(self.suffix_edit)
        sl.addLayout(pr)
        lay.addWidget(w)

        # Avanzado
        w, sl = _section("Opciones avanzadas")
        self.chk_regex = QCheckBox("Usar expresiones regulares")
        self.chk_regex.setToolTip("Aplica a «eliminar» y «sustituir». Ejemplo: \\[\\d+p_?\\] elimina [1080p_] y [720p]. "
                                  "En el reemplazo se pueden usar grupos: \\1")
        self.chk_case = QCheckBox("Distinguir mayúsculas y minúsculas")
        sl.addWidget(self.chk_regex)
        sl.addWidget(self.chk_case)
        lay.addWidget(w)

        lay.addWidget(label("Orden: eliminar → sustituir → limpieza → prefijo/sufijo. La extensión nunca se "
                            "modifica y nada se sobrescribe jamás.", "subtle", wrap=True))
        lay.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        panel.setMinimumWidth(320)
        panel.setMaximumWidth(440)
        return panel

    def _connect_changes(self):
        for w in [self.chk_all, self.chk_regex, self.chk_case, self.chk_spaces,
                  self.chk_dupes, self.chk_brackets, self.chk_edges, *self.ext_checks.values()]:
            w.toggled.connect(self._schedule_update)
        for w in (self.extra_edit, self.prefix_edit, self.suffix_edit):
            w.textChanged.connect(self._schedule_update)
        self.removals_edit.textChanged.connect(self._schedule_update)
        self.repl_table.itemChanged.connect(self._schedule_update)
        self.chk_all.toggled.connect(self._sync_ext_enabled)

    # ---------- configuración (también la usa el modo completo) ----------
    def folder(self) -> str:
        return self.folder_bar.folder()

    def set_folder(self, path: str):
        if path and path != self.folder():
            self.folder_bar.set_folder(path)
            self._schedule_update()

    def current_rules(self) -> RenameRules:
        removals = [ln for ln in self.removals_edit.toPlainText().splitlines() if ln != ""]
        repl = []
        for r in range(self.repl_table.rowCount()):
            a, b = self.repl_table.item(r, 0), self.repl_table.item(r, 1)
            find = a.text() if a else ""
            if find != "":
                repl.append((find, b.text() if b else ""))
        return RenameRules(
            removals=removals, replacements=repl, use_regex=self.chk_regex.isChecked(),
            case_sensitive=self.chk_case.isChecked(), collapse_spaces=self.chk_spaces.isChecked(),
            collapse_duplicates=self.chk_dupes.isChecked(), remove_empty_brackets=self.chk_brackets.isChecked(),
            trim_edge_separators=self.chk_edges.isChecked(),
            prefix=self.prefix_edit.text(), suffix=self.suffix_edit.text(),
        )

    def current_extensions(self):
        """None = todos los archivos; si no, frozenset de extensiones (con punto, en minúsculas)."""
        if self.chk_all.isChecked():
            return None
        return parse_extensions(self.extra_edit.text(), [e for e, cb in self.ext_checks.items() if cb.isChecked()])

    def config_error(self):
        err = self.current_rules().validate()
        if err:
            return err
        exts = self.current_extensions()
        if exts is not None and not exts:
            return "Selecciona al menos una extensión (o «Todos los archivos»)."
        return None

    def describe_config(self) -> str:
        exts = self.current_extensions()
        ext_text = "todos los archivos" if exts is None else ", ".join(sorted(exts)) or "ninguna"
        return f"Extensiones: {ext_text}. Reglas: {self.current_rules().describe()}."

    def _sync_ext_enabled(self):
        enabled = not self.chk_all.isChecked()
        for w in (*self.ext_checks.values(), self.extra_edit):
            w.setEnabled(enabled)

    # ---------- persistencia ----------
    def _load_settings(self):
        s = self.settings
        self.folder_bar.set_folder(s.value("folder", ""))
        self.folder_bar.set_recursive(s.value("rename/recursive", True, type=bool))
        saved = s.value("rename/exts", None)
        try:
            saved = json.loads(saved) if saved else [".mkv"]
        except (TypeError, ValueError):
            saved = [".mkv"]
        for ext, cb in self.ext_checks.items():
            cb.setChecked(ext in saved)
        self.extra_edit.setText(s.value("rename/extra_exts", ""))
        self.chk_all.setChecked(s.value("rename/all_files", False, type=bool))
        self.removals_edit.setPlainText(s.value("rename/removals", ""))
        try:
            pairs = json.loads(s.value("rename/replacements", "[]") or "[]")
        except (TypeError, ValueError):
            pairs = []
        self.repl_table.blockSignals(True)
        for a, b in pairs:
            self._add_repl_row(a, b, edit=False)
        if not pairs:
            self._add_repl_row(edit=False)
        self.repl_table.blockSignals(False)
        self.chk_regex.setChecked(s.value("rename/regex", False, type=bool))
        self.chk_case.setChecked(s.value("rename/case", False, type=bool))
        self.chk_spaces.setChecked(s.value("rename/spaces", True, type=bool))
        self.chk_dupes.setChecked(s.value("rename/dupes", True, type=bool))
        self.chk_brackets.setChecked(s.value("rename/brackets", True, type=bool))
        self.chk_edges.setChecked(s.value("rename/edges", True, type=bool))
        self.prefix_edit.setText(s.value("rename/prefix", ""))
        self.suffix_edit.setText(s.value("rename/suffix", ""))
        self._sync_ext_enabled()

    def save_settings(self):
        s = self.settings
        s.setValue("folder", self.folder())
        s.setValue("rename/recursive", self.folder_bar.is_recursive())
        s.setValue("rename/exts", json.dumps([e for e, cb in self.ext_checks.items() if cb.isChecked()]))
        s.setValue("rename/extra_exts", self.extra_edit.text())
        s.setValue("rename/all_files", self.chk_all.isChecked())
        s.setValue("rename/removals", self.removals_edit.toPlainText())
        s.setValue("rename/replacements", json.dumps(self.current_rules().replacements, ensure_ascii=False))
        s.setValue("rename/regex", self.chk_regex.isChecked())
        s.setValue("rename/case", self.chk_case.isChecked())
        s.setValue("rename/spaces", self.chk_spaces.isChecked())
        s.setValue("rename/dupes", self.chk_dupes.isChecked())
        s.setValue("rename/brackets", self.chk_brackets.isChecked())
        s.setValue("rename/edges", self.chk_edges.isChecked())
        s.setValue("rename/prefix", self.prefix_edit.text())
        s.setValue("rename/suffix", self.suffix_edit.text())

    def shutdown(self):
        self.save_settings()
        if self._busy():
            self.worker.wait(10000)     # un renombrado a medias nunca se interrumpe

    def on_activated(self):
        self._schedule_update()

    def busy(self) -> bool:
        return self._busy()

    def _busy(self):
        return self.worker is not None and self.worker.isRunning()

    # ---------- tabla de sustituciones ----------
    def _add_repl_row(self, find: str = "", repl: str = "", edit: bool = True):
        r = self.repl_table.rowCount()
        self.repl_table.insertRow(r)
        for col, text in enumerate((find, repl)):
            self.repl_table.setItem(r, col, QTableWidgetItem(text))
        if edit:
            self.repl_table.setCurrentCell(r, 0)
            self.repl_table.editItem(self.repl_table.item(r, 0))

    def _del_repl_row(self):
        rows = sorted({i.row() for i in self.repl_table.selectedIndexes()}, reverse=True)
        if not rows and self.repl_table.rowCount():
            rows = [self.repl_table.rowCount() - 1]
        for r in rows:
            self.repl_table.removeRow(r)
        self._schedule_update()

    # ---------- carpeta y lista ----------
    def refresh(self):
        """Vuelve a leer la carpeta y recalcula la previsualización."""
        self._listing_key = None
        self._update_preview()

    def _schedule_update(self, *_):
        self._timer.start()

    def _relative(self, path) -> str:
        try:
            return str(Path(path).relative_to(self.folder()))
        except ValueError:
            return str(path)

    def _reload_files(self) -> bool:
        folder = self.folder()
        key = (folder, self.folder_bar.is_recursive(), self.current_extensions())
        if key == self._listing_key:
            return True
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._files = list_files(folder, key[1], key[2])
        except OSError as exc:
            self._files, self._listing_key = [], None
            self.summary.setText(f"No se pudo leer la carpeta: {exc}")
            return False
        finally:
            QApplication.restoreOverrideCursor()
        self._listing_key = key
        return True

    def _set_idle_state(self, message: str, error: bool = False, empty_title: str = ""):
        self._plan = None
        self.results.clear()
        self.summary.setText("")
        self.summary.hide()
        self.stack.setCurrentWidget(self.empty)
        if empty_title:
            self.empty.set_content(empty_title, message, "rename", "error" if error else "")
        self.actions.set_status(message, "error" if error else "")
        self.btn_rename.setText("Renombrar archivos")
        self.btn_rename.setEnabled(False)
        self._refresh_undo_button()

    def _update_preview(self):
        if self._busy():
            return
        try:
            self._update_preview_impl()
        except Exception as exc:                    # nunca dejar la previsualización congelada sin avisar
            traceback.print_exc(file=sys.stderr)
            self._set_idle_state(f"Error al calcular la previsualización: {exc}", True, "No se pudo previsualizar")

    def _update_preview_impl(self):
        folder = self.folder()
        if not folder:
            self._set_idle_state("Elige una carpeta para ver la previsualización.", False,
                                 "Elige una carpeta para empezar")
            return
        if not Path(folder).is_dir():
            self._set_idle_state("La carpeta no existe o no es accesible.", True, "Carpeta no válida")
            return
        err = self.config_error()
        if err:
            self._set_idle_state(err, True, "Revisa las reglas")
            return
        if not self._reload_files():
            self._set_idle_state(self.summary.text(), True, "No se pudo leer la carpeta")
            return
        plan = build_plan(self._files, self.current_rules())
        self._plan = plan
        if not plan.items:
            self._set_idle_state("No hay archivos con las extensiones elegidas.", False, "Sin archivos")
            self.empty.set_content("Sin archivos", "La carpeta no contiene archivos con las extensiones elegidas.",
                                   "folder", "warning")
            return
        self.stack.setCurrentWidget(self.results)
        self._fill_tree(plan)
        n_change = plan.count(RStatus.CHANGE)
        n_block = len(plan.blocked)
        parts = [f"<b>{len(plan.items)}</b> archivo(s)",
                 f"<span style='color:{styles.SUCCESS}'><b>{n_change}</b> se renombrarán</span>",
                 f"<b>{plan.count(RStatus.SAME)}</b> sin cambios"]
        if n_block:
            parts.append(f"<span style='color:{styles.COLOR_LATINO}'><b>{n_block}</b> bloqueados "
                         "(conflicto o nombre no válido: no se tocarán)</span>")
        self.summary.setText(" &nbsp;·&nbsp; ".join(parts))
        self.summary.show()
        self.btn_rename.setText(f"Renombrar {n_change} archivo(s)" if n_change else "Renombrar archivos")
        self.btn_rename.setEnabled(n_change > 0)
        if n_change:
            self.actions.set_status("Revisa la previsualización y pulsa «Renombrar».", "info")
        else:
            self.actions.set_status("Con estas reglas no cambia ningún nombre.")
        self._refresh_undo_button()

    def _refresh_undo_button(self):
        try:
            entry = rename_history.last_undoable()
        except OSError:
            entry = None
        self.btn_undo.setEnabled(entry is not None and not self._busy())
        if entry:
            tip = f"Último renombrado: {entry.time.replace('T', ' ')} · {len(entry.pending)} archivo(s)"
        elif not self.ctx.save_history():
            tip = "El historial está desactivado: los renombrados nuevos no se pueden deshacer."
        else:
            tip = "No hay renombrados que deshacer."
        self.btn_undo.setToolTip(tip)

    def _fill_tree(self, plan):
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        bold = QFont(self.tree.font())
        bold.setWeight(QFont.Weight.DemiBold)
        for it in plan.items:
            row = QTreeWidgetItem(self.tree)
            row.setText(0, self._relative(it.path))
            row.setToolTip(0, str(it.path))
            row.setText(1, it.new_name)
            row.setToolTip(1, it.new_name)
            text = STATUS_TEXT[it.status] + (f" — {it.message}" if it.message else "")
            row.setText(2, text)
            row.setToolTip(2, text)
            color = brush(STATUS_COLOR[it.status])
            row.setForeground(2, color)
            if it.status == RStatus.CHANGE:
                row.setForeground(1, color)
                row.setFont(1, bold)
                row.setData(0, ROLE_KIND, KIND_CHANGE)
            elif it.status == RStatus.SAME:
                row.setForeground(1, brush(styles.SUBTLE))
                row.setForeground(0, brush(styles.MUTED))
                row.setData(0, ROLE_KIND, KIND_SAME)
            else:
                row.setForeground(1, color)
                row.setData(0, ROLE_KIND, KIND_REVIEW)
        self.tree.setUpdatesEnabled(True)
        self.results.recount()

    # ---------- acciones ----------
    def _set_working(self, working: bool, text: str = ""):
        for w in (self.btn_rename, self.btn_undo, self.folder_bar, self.btn_history):
            w.setEnabled(not working)
        if working:
            self.actions.start_progress(text)
        else:
            self.actions.stop_progress()

    def _on_rename(self):
        if self._plan is None or self.config_error() or self._busy():
            return
        shown = _signature(self._plan)
        self._listing_key = None                    # se vuelve a leer la carpeta justo ahora
        if not self._reload_files():
            return
        fresh = build_plan(self._files, self.current_rules())
        if _signature(fresh) != shown:
            self._update_preview()
            self.notify("warning", "La carpeta ha cambiado",
                        "Los archivos han cambiado desde la previsualización. Revisa la lista actualizada "
                        "y vuelve a pulsar «Renombrar».")
            return
        n, blocked = fresh.count(RStatus.CHANGE), len(fresh.blocked)
        msg = f"Se renombrarán {n} archivo(s)."
        if blocked:
            msg += f"\n{blocked} archivo(s) con conflicto o nombre no válido NO se tocarán."
        if self.ctx.save_history():
            msg += "\n\nNo se sobrescribirá ningún archivo y podrás deshacerlo con «Deshacer último renombrado»."
        else:
            msg += ("\n\nNo se sobrescribirá ningún archivo. El historial está desactivado: "
                    "este renombrado NO se podrá deshacer.")
        msg += "\n\n¿Continuar?"
        if QMessageBox.question(self, "Confirmar renombrado", msg) != QMessageBox.StandardButton.Yes:
            return
        self.save_settings()
        self.infobar.hide()
        self._log(f"Renombrando {n} archivo(s) en {self.folder()}")
        self._set_working(True, "Renombrando…")
        self.worker = RenameWorker(fresh, self.folder(), self)
        self.worker.progress.connect(lambda i, t: self.actions.set_progress(i, t, "Renombrando"))
        self.worker.done.connect(self._on_rename_done)
        self.worker.start()

    def _on_rename_done(self, outcomes, warning):
        self._set_working(False)
        ok = sum(1 for o in outcomes if o.ok)
        failed = [o for o in outcomes if not o.ok]
        for o in outcomes:
            self._log(f"{o.old.name} → {o.new.name}" if o.ok else f"ERROR {o.old.name}: {o.error}")
        self.refresh()
        if warning:
            self._log(warning)
        if failed:
            lines = " · ".join(f"{o.old.name}: {o.error}" for o in failed[:3])
            more = f" … y {len(failed) - 3} más" if len(failed) > 3 else ""
            self.notify("error", "Renombrado terminado con errores",
                        f"Renombrados: {ok} · con error: {len(failed)}. {lines}{more}", "Ver registro", self.show_log)
            self.actions.set_status(f"{ok} renombrados, {len(failed)} con error.", "error")
        else:
            can_undo = self.ctx.save_history() and not warning
            self.notify("warning" if warning else "success", "Renombrado terminado",
                        f"Archivos renombrados: {ok}." + (f" {warning}" if warning else ""),
                        "Deshacer" if can_undo else "", self._on_undo if can_undo else None)
            self.actions.set_status(f"{ok} archivo(s) renombrados.", "success")

    def _on_undo(self):
        if self._busy():
            return
        entry = rename_history.last_undoable()
        if entry is None:
            self.notify("info", "Nada que deshacer", "No hay renombrados pendientes de deshacer.")
            self._refresh_undo_button()
            return
        extra = ""
        if entry.mode == "full":
            extra = ("\n\nFue un procesamiento completo: se devuelven los nombres, pero el cambio de pista "
                     "de subtítulos predeterminada no se revierte (queda anotado en journal.jsonl).")
        ans = QMessageBox.question(
            self, "Deshacer último renombrado",
            f"Se devolverán sus nombres anteriores a {len(entry.pending)} archivo(s)\n"
            f"({entry.time.replace('T', ' ')} · {entry.folder}).{extra}\n\n¿Continuar?")
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.infobar.hide()
        self._log(f"Deshaciendo el renombrado del {entry.time.replace('T', ' ')} ({len(entry.pending)} archivo(s))")
        self._set_working(True, "Deshaciendo el último renombrado…")
        self.worker = UndoWorker(self)
        self.worker.done.connect(self._on_undo_done)
        self.worker.start()

    def _on_undo_done(self, rep):
        self._set_working(False)
        self.refresh()
        if isinstance(rep, Exception):
            self._log(f"ERROR al deshacer: {rep}")
            self.notify("error", "No se pudo deshacer", str(rep))
            return
        if rep.failed:
            for n, why in rep.failed:
                self._log(f"No restaurado {n}: {why}")
            lines = " · ".join(f"{n}: {why}" for n, why in rep.failed[:3])
            self.notify("warning", "Deshacer parcial",
                        f"Restaurados: {rep.reverted} · no se pudieron restaurar: {len(rep.failed)}. {lines} "
                        "Los pendientes siguen disponibles: corrige el problema y vuelve a pulsar «Deshacer».",
                        "Ver registro", self.show_log)
        else:
            self._log(f"Restaurados {rep.reverted} archivo(s)")
            self.notify("success", "Renombrado deshecho", f"Archivos restaurados: {rep.reverted}.")
            self.actions.set_status(f"{rep.reverted} archivo(s) restaurados.", "success")

    def _on_history(self):
        HistoryDialog(self.ctx, self).exec()

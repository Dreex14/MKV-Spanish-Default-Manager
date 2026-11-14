"""Sección «Procesamiento completo»: renombrado masivo + selección de subtítulos en un único proceso.

Flujo: elegir carpeta → análisis automático de solo lectura (nombres nuevos y pista que se seleccionará,
FullPreviewWorker) → revisar la previsualización en la propia página → «Ejecutar» (con confirmación) →
ejecución por lotes (FullRunWorker) → informe final.
Usa las reglas de renombrado configuradas en la sección «Renombrado masivo».
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QTreeWidgetItem, QVBoxLayout

from ..classifier import describe
from ..fullmode import describe_entry_result, describe_selection
from ..models import Status
from ..renamer import RStatus, build_plan, list_files
from ..selector_full import Pick
from ..workers import FullPreviewWorker, FullRunWorker
from . import icons, styles
from .base import BasePage
from .rename_page import STATUS_COLOR as RENAME_COLOR, STATUS_TEXT as RENAME_TEXT, _signature
from .subtitle_page import CATEGORY_COLOR, SELECTED_BG
from .widgets import (
    KIND_CHANGE, KIND_ERROR, KIND_REVIEW, KIND_SAME, ROLE_KIND, EmptyState, FolderBar, OptionRow, ResultsView,
    SummaryPanel, brush, button, card, divider, label, set_bold, stacked,
)

PICK_COLOR = {
    Pick.CASTELLANO: styles.COLOR_CASTELLANO,
    Pick.LATINO: styles.COLOR_LATINO,
    Pick.OTHER_SINGLE: styles.COLOR_CAMBIO,
    Pick.KEEP: styles.COLOR_OTRO,
    Pick.NO_SUBS: styles.COLOR_OTRO,
    Pick.REVIEW: styles.COLOR_REVISAR,
    Pick.ERROR: styles.COLOR_AMBIGUO,
}
RESULT_RENAME_TEXT = {"renamed": "Renombrado", "same": "Sin cambios de nombre", "none": "—"}
RESULT_RENAME_COLOR = {"renamed": styles.COLOR_CASTELLANO, "same": styles.COLOR_OTRO, "none": styles.COLOR_OTRO,
                       "blocked": styles.COLOR_AMBIGUO, "error": styles.COLOR_AMBIGUO}
HEADERS = ["Archivo / pista", "Nombre nuevo / tipo", "Subtítulo elegido / idioma", "Estado / predeterminada"]
WIDTHS = [30, 24, 26, 20]
SUBTITLE_RULES = (
    "<b>Orden de prioridad de los subtítulos</b><ol style='margin-left:-20px'>"
    "<li>Castellano, ESP, Español o Spanish.</li>"
    "<li>Latino (ESP LAT, Latino, LATAM) <b>solo si no hay castellano</b>.</li>"
    "<li>Otro idioma, solo si es la única pista.</li></ol>"
    "Con varios idiomas y ninguno español, o sin subtítulos, no se cambia nada. Forzados y comentarios no se "
    "eligen salvo que sean la única pista. Con pistas ambiguas o empates, el archivo queda «a revisar» y no se "
    "modifica.<br><br>Solo se cambia el indicador de pista predeterminada con mkvpropedit: el vídeo y el audio "
    "no se recodifican."
)


def _add_track_children(parent, analysis):
    d = analysis.decision
    changes = {c.track.index: c.new_default for c in d.changes}
    for t in analysis.tracks:
        child = QTreeWidgetItem(parent)
        child.setText(0, f"#{t.index}  {t.name or '(sin nombre)'}")
        child.setText(1, describe(t))
        child.setText(2, t.language + (f" / {t.ietf}" if t.ietf else ""))
        before = "Sí" if t.default else "No"
        if t.index in changes:
            child.setText(3, f"Predet.: {before} → {'Sí' if changes[t.index] else 'No'}  (cambia)")
            child.setForeground(3, brush(styles.COLOR_CAMBIO))
        else:
            child.setText(3, f"Predet.: {before}")
            child.setForeground(3, brush(styles.MUTED))
        child.setForeground(0, brush(styles.MUTED))
        child.setForeground(2, brush(styles.MUTED))
        child.setForeground(1, brush(CATEGORY_COLOR[t.category]))
        if t.notes:
            child.setToolTip(0, "\n".join(t.notes))
        if d.selected is not None and t.index == d.selected.index:
            for col in range(4):
                child.setBackground(col, QColor(*SELECTED_BG))
            child.setForeground(0, brush(styles.TEXT))


def _plan_kind(e) -> str:
    if e.pick == Pick.ERROR:
        return KIND_ERROR
    if e.pick == Pick.REVIEW or (e.rename is not None and e.rename.blocked):
        return KIND_REVIEW
    if (e.rename is not None and e.rename.status == RStatus.CHANGE) or (
            e.analysis is not None and not e.analysis.error and e.analysis.decision.status == Status.TO_CHANGE):
        return KIND_CHANGE
    return KIND_SAME


def fill_plan_tree(tree, plan, relative):
    """Previsualización: una fila por archivo con su nombre nuevo y la pista que se elegirá."""
    tree.setUpdatesEnabled(False)
    tree.clear()
    for e in plan.entries:
        row = QTreeWidgetItem(tree)
        row.setText(0, relative(e.path))
        row.setToolTip(0, str(e.path))
        set_bold(row)
        row.setData(0, ROLE_KIND, _plan_kind(e))
        status = []
        item = e.rename
        if item is None:
            row.setText(1, "—")
            row.setToolTip(1, "Fuera del filtro de extensiones del renombrado")
            row.setForeground(1, brush(styles.SUBTLE))
        elif item.status == RStatus.CHANGE:
            row.setText(1, item.new_name)
            row.setToolTip(1, item.new_name)
            row.setForeground(1, brush(RENAME_COLOR[item.status]))
            status.append(("Se renombrará", styles.COLOR_CASTELLANO))
        elif item.status == RStatus.SAME:
            row.setText(1, "Sin cambios")
            row.setForeground(1, brush(styles.SUBTLE))
        else:
            row.setText(1, item.new_name)
            row.setForeground(1, brush(RENAME_COLOR[item.status]))
            status.append((RENAME_TEXT[item.status] + (f" — {item.message}" if item.message else ""),
                           RENAME_COLOR[item.status]))
        if e.is_mkv and e.analysis is not None:
            row.setText(2, describe_selection(e.analysis))
            row.setToolTip(2, row.text(2))
            row.setForeground(2, brush(PICK_COLOR.get(e.pick, styles.TEXT)))
            if not e.analysis.error:
                if e.analysis.decision.status == Status.TO_CHANGE:
                    status.append(("Se modificará el MKV", styles.COLOR_CAMBIO))
                elif e.pick == Pick.REVIEW:
                    status.append(("Revisar subtítulos", styles.COLOR_REVISAR))
                _add_track_children(row, e.analysis)
            else:
                status.append(("Error al leer el MKV", styles.COLOR_AMBIGUO))
            row.setExpanded(e.pick in (Pick.REVIEW, Pick.ERROR))
        elif not e.is_mkv:
            row.setText(2, "No es MKV")
            row.setForeground(2, brush(styles.SUBTLE))
        _set_status(row, status)
    tree.setUpdatesEnabled(True)


def _set_status(row, parts):
    if not parts:
        row.setText(3, "Sin cambios")
        row.setForeground(3, brush(styles.SUBTLE))
        return
    row.setText(3, " · ".join(p for p, _c in parts))
    row.setToolTip(3, row.text(3))
    worst = [c for _p, c in parts]
    color = next((c for c in (styles.COLOR_AMBIGUO, styles.COLOR_REVISAR) if c in worst), parts[0][1])
    row.setForeground(3, brush(color))


def add_result_row(tree, er, relative):
    """Resultado real de un archivo ya procesado."""
    row = QTreeWidgetItem(tree)
    row.setText(0, relative(er.entry.path))
    row.setToolTip(0, str(er.entry.path))
    set_bold(row)
    final = er.final_path.name if er.final_path else er.entry.path.name
    row.setText(1, final if er.rename_state == "renamed" else "Sin cambios" if er.rename_state == "same" else final)
    row.setToolTip(1, final)
    row.setForeground(1, brush(styles.COLOR_CASTELLANO if er.rename_state == "renamed" else styles.SUBTLE))
    status = []
    text = RESULT_RENAME_TEXT.get(er.rename_state)
    if text is None:
        text = ("No renombrado" if er.rename_state == "blocked" else "Error al renombrar") + \
               (f": {er.rename_message}" if er.rename_message else "")
    if er.rename_state in ("renamed", "blocked", "error"):
        status.append((text, RESULT_RENAME_COLOR[er.rename_state]))
    ap = er.apply
    kind = KIND_SAME
    if er.rename_state == "renamed":
        kind = KIND_CHANGE
    if ap is not None:
        if ap.outcome == "error":
            row.setText(2, f"Error: {ap.message}")
            row.setForeground(2, brush(styles.COLOR_AMBIGUO))
            status.append(("Error en subtítulos", styles.COLOR_AMBIGUO))
        else:
            row.setText(2, describe_selection(ap.analysis))
            row.setForeground(2, brush(PICK_COLOR.get(er.pick, styles.TEXT)))
            if ap.outcome == "ok":
                status.append(("MKV modificado", styles.COLOR_CAMBIO))
                kind = KIND_CHANGE
            elif er.pick == Pick.REVIEW:
                status.append(("Revisar subtítulos", styles.COLOR_REVISAR))
            _add_track_children(row, ap.analysis)
            row.setExpanded(er.pick in (Pick.REVIEW, Pick.ERROR))
        row.setToolTip(2, row.text(2))
    elif er.entry.is_mkv:
        row.setText(2, "No procesado (cancelado)")
        row.setForeground(2, brush(styles.SUBTLE))
    else:
        row.setText(2, "No es MKV")
        row.setForeground(2, brush(styles.SUBTLE))
    if er.rename_state == "blocked" or er.pick == Pick.REVIEW:
        kind = KIND_REVIEW
    if er.rename_state == "error" or (ap is not None and ap.outcome == "error"):
        kind = KIND_ERROR
    row.setData(0, ROLE_KIND, kind)
    _set_status(row, status)
    return row


class FullProcessPage(BasePage):
    def __init__(self, ctx, rename_page, subtitle_page, goto_rename=None, parent=None):
        super().__init__(ctx, "Procesamiento completo",
                         "Renombra los archivos y deja el castellano como subtítulo predeterminado en todos los "
                         "episodios, en un solo paso.", "Registro: qué se hizo en cada archivo", parent)
        self.ren, self.sub, self.goto_rename = rename_page, subtitle_page, goto_rename
        self.pworker = None
        self.rworker = None
        self.plan = None
        self.plan_key = None
        self._build_ui()
        self._refresh_rules()
        self._update_buttons()

    # ---------- construcción ----------
    def _build_ui(self):
        s = self.settings
        how = button("¿Cómo se eligen los subtítulos?", "subtle", "info")
        how.clicked.connect(self._show_rules_help)
        self.header.add_right(how)

        self.folder_bar = FolderBar("Carpeta de la serie", "Elige la carpeta de la serie o temporada")
        self.folder_bar.set_folder(s.value("folder", ""))
        self.folder_bar.set_recursive(s.value("full/recursive", s.value("recursive", True, type=bool), type=bool))
        self.folder_bar.folder_chosen.connect(lambda _f: self._analyze())
        self.folder_bar.recursive_changed.connect(lambda _v: self._options_changed())
        self.body_lay.addWidget(self.folder_bar)

        opts, ol = card((16, 10, 16, 10), 18, horizontal=True)
        rules = QVBoxLayout()
        rules.setSpacing(1)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(label("Reglas de renombrado"))
        edit = button("Editar", "link")
        edit.setToolTip("Las reglas se configuran en «Renombrado masivo»")
        edit.clicked.connect(lambda _c=False: self.goto_rename and self.goto_rename())
        head.addWidget(edit)
        head.addStretch(1)
        rules.addLayout(head)
        self.rules_label = label("", "subtle", wrap=True)
        self.rules_label.setTextFormat(Qt.TextFormat.PlainText)
        rules.addWidget(self.rules_label)
        ol.addLayout(rules, 1)
        sep = divider()
        sep.setFixedWidth(1)
        sep.setMaximumHeight(16777215)
        ol.addWidget(sep)
        self.opt_clear = OptionRow(
            "Quitar «predeterminada» al resto de pistas",
            "Actívalo solo si algún reproductor sigue eligiendo otra pista.",
            "Por defecto solo se tocan la pista elegida y otras pistas españolas que compitan.")
        self.opt_clear.switch.setChecked(s.value("full/clear_other", s.value("clear_other", False, type=bool), type=bool))
        self.opt_clear.switch.toggled.connect(lambda _v: self._options_changed())
        ol.addWidget(self.opt_clear, 1)
        self.body_lay.addWidget(opts)

        self.summary = SummaryPanel()
        self.body_lay.addWidget(self.summary)

        self.empty = EmptyState("full", "Elige la carpeta de la serie",
                                "Se analizará automáticamente: verás el nombre nuevo de cada archivo y el "
                                "subtítulo que quedará como predeterminado. No se cambia nada hasta que lo "
                                "confirmes.")
        b = button("Elegir carpeta…", "primary", "folder")
        b.clicked.connect(self.folder_bar._browse)
        self.empty.add_button(b)
        self.results = ResultsView(HEADERS, WIDTHS)
        self.tree = self.results.tree
        self.stack = stacked(self.empty, self.results)
        self.body_lay.addWidget(self.stack, 1)

        self.btn_cancel = button("Cancelar", icon_name="stop")
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_analyze = button("Analizar carpeta", icon_name="refresh")
        self.btn_analyze.clicked.connect(self._analyze)
        self.btn_run = button("Ejecutar proceso completo", "primary", "play")
        self.btn_run.setToolTip("1) Renombra según las reglas · 2) Analiza los subtítulos de todos los MKV · "
                                "3) Fija la pista predeterminada.")
        self.btn_run.clicked.connect(self._on_run)
        for w in (self.btn_cancel, self.btn_analyze, self.btn_run):
            self.actions.add_button(w)
        self.actions.set_status("Elige una carpeta para analizarla.")

    def _show_rules_help(self):
        box = QMessageBox(self)
        box.setWindowTitle("Selección de subtítulos")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(SUBTITLE_RULES)
        box.setIcon(QMessageBox.Icon.Information)
        box.exec()

    # ---------- estado ----------
    def folder(self) -> str:
        return self.folder_bar.folder()

    def set_folder(self, path: str):
        if path and path != self.folder():
            self.folder_bar.set_folder(path)
            self._discard_plan("Carpeta pendiente de analizar.")

    def _key(self):
        return (self.folder(), self.folder_bar.is_recursive(), self.opt_clear.switch.isChecked(),
                self.ren.describe_config())

    def _refresh_rules(self):
        text = self.ren.describe_config()
        self.rules_label.setText(text)
        self.rules_label.setToolTip(text)

    def on_activated(self):
        self._refresh_rules()
        if self.plan is not None and self.plan_key != self._key():
            self._discard_plan("Las reglas han cambiado: vuelve a analizar la carpeta.", "warning")
        self._update_buttons()

    def _options_changed(self):
        if self.plan is not None and not self._busy():
            self._analyze()            # el análisis es de solo lectura: se rehace solo
        self._update_buttons()

    def _discard_plan(self, status: str, severity: str = ""):
        self.plan = self.plan_key = None
        self.results.clear()
        self.summary.hide()
        self.stack.setCurrentWidget(self.empty)
        if self.folder():
            self.empty.set_content("Carpeta pendiente de analizar", self.folder(), "full",
                                   "warning" if severity else "")
        self.actions.set_status(status, severity)
        self._update_buttons()

    def _busy(self):
        return any(w is not None and w.isRunning() for w in (self.pworker, self.rworker))

    def busy(self) -> bool:
        return self._busy()

    def _update_buttons(self):
        busy = self._busy()
        has_plan = self.plan is not None and self.plan_key == self._key()
        self.btn_cancel.setVisible(busy)
        self.btn_analyze.setEnabled(not busy and bool(self.folder()))
        self.btn_analyze.setText("Volver a analizar" if has_plan else "Analizar carpeta")
        self.btn_run.setVisible(has_plan or busy)
        self.btn_run.setEnabled(not busy and has_plan and self.plan.has_work())
        self.folder_bar.setEnabled(not busy)
        self.opt_clear.setEnabled(not busy)
        # Sin análisis, la acción principal es analizar
        primary = not (has_plan or busy)
        self.btn_analyze.setObjectName("primary" if primary else "")
        self.btn_analyze.setIcon(icons.icon("refresh", styles.ACCENT_TEXT if primary else styles.MUTED, 16))
        self.btn_analyze.style().unpolish(self.btn_analyze)
        self.btn_analyze.style().polish(self.btn_analyze)

    def _cancel(self):
        for w in (self.pworker, self.rworker):
            if w is not None and w.isRunning():
                w.cancel()
        self.actions.set_status("Cancelando…")

    def _relative(self, path):
        try:
            return str(Path(path).relative_to(self.folder()))
        except ValueError:
            return str(path)

    def save_settings(self):
        self.settings.setValue("folder", self.folder())
        self.settings.setValue("full/recursive", self.folder_bar.is_recursive())
        self.settings.setValue("full/clear_other", self.opt_clear.switch.isChecked())

    def shutdown(self):
        self.save_settings()
        self._cancel()
        for w in (self.pworker, self.rworker):
            if w is not None and w.isRunning():
                w.wait(5000)

    # ---------- flujo ----------
    def _validate(self):
        folder = self.folder()
        if not folder or not Path(folder).is_dir():
            self.notify("warning", "Carpeta no válida", "Elige una carpeta existente.")
            return None
        err = self.ren.config_error()
        if err:
            self.notify("warning", "Reglas de renombrado", err, "Corregir", self.goto_rename)
            return None
        tools = self.ctx.get_tools()
        if not tools:
            self.notify("error", "MKVToolNix no encontrado", "Instálalo o indica su carpeta en Ajustes.")
            return None
        return tools

    def _analyze(self):
        if self._busy():
            return
        tools = self._validate()
        if tools is None:
            return
        self.save_settings()
        self._refresh_rules()
        self.infobar.hide()
        self.plan = self.plan_key = None
        self.results.clear()
        self.summary.hide()
        self.stack.setCurrentWidget(self.results)
        self._log(f"Previsualización: {self.folder()}")
        self._log("Reglas — " + self.ren.describe_config())
        self._key_at_start = self._key()
        self._plan_rules = self.ren.current_rules()
        self._plan_exts = self.ren.current_extensions()
        self.actions.start_progress("Leyendo la carpeta…")
        self.pworker = FullPreviewWorker(tools, self.folder(), self.folder_bar.is_recursive(),
                                         self.ren.current_rules(), self.ren.current_extensions(),
                                         self.opt_clear.switch.isChecked(), self)
        self.pworker.progress.connect(lambda i, n: self.actions.set_progress(i, n, "Analizando MKV"))
        self.pworker.log.connect(self._log)
        self.pworker.done.connect(self._on_preview_done)
        self.pworker.start()
        self._update_buttons()

    def _on_preview_done(self, plan):
        self.actions.stop_progress()
        if plan is None:
            self._discard_plan("No se pudo preparar la previsualización.", "error")
            self.notify("error", "No se pudo analizar la carpeta", "Mira el registro para ver el motivo.",
                        "Ver registro", self.show_log)
            return
        if plan.cancelled:
            self._log("Previsualización cancelada.")
            self._discard_plan("Análisis cancelado.", "warning")
            return
        self._log("Previsualización — " + " · ".join(f"{k}: {v}" for k, v in plan.rows()))
        if not plan.entries:
            self._discard_plan("No se encontró ningún archivo.", "warning")
            self.empty.set_content("Sin archivos", "No se encontró ningún archivo con las extensiones elegidas.",
                                   "folder", "warning")
            return
        self.plan, self.plan_key = plan, self._key_at_start
        rows = dict(plan.rows())
        to_rename = rows["Archivos que se renombrarán"]
        to_modify = rows["MKV que se modificarán"]
        review = rows["Archivos que necesitan revisión"]
        errors = rows["Errores"]
        self.summary.set_data("Previsualización · todavía no se ha modificado nada", [
            ("Se renombrarán", to_rename, styles.SUCCESS if to_rename else ""),
            ("MKV a modificar", to_modify, styles.COLOR_CAMBIO if to_modify else ""),
            ("A revisar", review, styles.WARNING if review else ""),
            ("Errores", errors, styles.DANGER if errors else ""),
        ], plan.rows())
        fill_plan_tree(self.tree, plan, self._relative)
        self.results.recount()
        if plan.has_work():
            self.actions.set_status(f"Listo: {to_rename} renombrado(s) y {to_modify} MKV a modificar.", "info")
        else:
            self.actions.set_status("No hay nada que cambiar en esta carpeta.", "success")
        self._update_buttons()

    def _on_run(self):
        if self._busy() or self.plan is None:
            return
        if self.plan_key != self._key():
            self._discard_plan("Las opciones han cambiado: vuelve a analizar la carpeta.", "warning")
            return
        tools = self._validate()
        if tools is None:
            return
        # Se comprueba que los archivos a renombrar siguen como en la previsualización
        try:
            fresh = build_plan(list_files(self.plan.root, self.folder_bar.is_recursive(), self._plan_exts),
                               self._plan_rules)
        except OSError as exc:
            self.notify("error", "No se pudo leer la carpeta", str(exc))
            return
        if _signature(fresh) != _signature(self.plan.rename_plan):
            self.notify("warning", "La carpeta ha cambiado",
                        "Los archivos han cambiado desde la previsualización. Se ha vuelto a analizar: revisa la "
                        "lista y pulsa de nuevo «Ejecutar».")
            self._analyze()
            return
        rows = dict(self.plan.rows())
        msg = (f"Se renombrarán {rows['Archivos que se renombrarán']} archivo(s) y se fijará el subtítulo "
               f"predeterminado en {rows['MKV que se modificarán']} MKV.\n\n"
               "Nunca se sobrescribe ningún archivo y los marcados «a revisar» no se tocan. "
               + ("El renombrado se puede deshacer desde «Renombrado masivo»." if self.ctx.save_history() else
                  "El historial está desactivado: el renombrado NO se podrá deshacer.")
               + "\n\n¿Ejecutar el proceso completo?")
        if QMessageBox.question(self, "Confirmar proceso completo", msg) != QMessageBox.StandardButton.Yes:
            return
        plan = self.plan
        self.results.clear()
        self.summary.hide()
        self.infobar.hide()
        self._log("Ejecutando proceso completo…")
        self.actions.start_progress("Procesando…")
        self.rworker = FullRunWorker(tools, plan, self)
        self.rworker.progress.connect(lambda i, n: self.actions.set_progress(i, n, "Procesando paso"))
        self.rworker.result.connect(self._on_entry_result)
        self.rworker.log.connect(self._log)
        self.rworker.done.connect(self._on_run_done)
        self.rworker.start()
        self._update_buttons()

    def _on_entry_result(self, er):
        add_result_row(self.tree, er, self._relative)
        self._log(describe_entry_result(er))

    def _on_run_done(self, report):
        self.actions.stop_progress()
        self.plan = self.plan_key = None        # la carpeta ha cambiado: el plan ya no vale
        # El estado de la carpeta ha cambiado: se refrescan las otras secciones
        self.sub.invalidate_preview()
        self.ren.refresh()
        if report is None:
            self.notify("error", "El proceso se interrumpió", "Ocurrió un error inesperado. Mira el registro.",
                        "Ver registro", self.show_log)
            self.actions.set_status("Proceso interrumpido.", "error")
            self._update_buttons()
            return
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        for er in report.results:
            add_result_row(self.tree, er, self._relative)
        self.tree.setUpdatesEnabled(True)
        self.results.recount()
        rows = dict(report.rows())
        review, errors = rows["Archivos que necesitan revisión"], rows["Errores"]
        self.summary.set_data("Informe final" + (" · cancelado" if report.cancelled else ""), [
            ("Renombrados", report.renamed, styles.SUCCESS if report.renamed else ""),
            ("MKV modificados", report.mkv_modified, styles.COLOR_CAMBIO if report.mkv_modified else ""),
            ("A revisar", review, styles.WARNING if review else ""),
            ("Errores", errors, styles.DANGER if errors else ""),
        ], report.rows())
        self._log("Informe — " + " · ".join(f"{k}: {v}" for k, v in report.rows()))
        for p, why in report.review:
            self._log(f"REVISAR {Path(p).name}: {why}")
        for p, why in report.errors:
            self._log(f"ERROR {Path(p).name}: {why}")
        sev = "error" if errors else ("warning" if review or report.cancelled else "success")
        title = "Proceso cancelado" if report.cancelled else "Proceso completado"
        text = f"{report.renamed} archivo(s) renombrados · {report.mkv_modified} MKV modificados"
        if review:
            text += f" · {review} a revisar"
        if errors:
            text += f" · {errors} con error"
        if errors:
            action = ("Ver errores", lambda: self.results.set_filter(KIND_ERROR))
        elif review:
            action = ("Ver pendientes", lambda: self.results.set_filter(KIND_REVIEW))
        else:
            action = ("", None)
        self.notify(sev, title, text + ".", *action)
        self.actions.set_status(title + ".", sev)
        self._update_buttons()

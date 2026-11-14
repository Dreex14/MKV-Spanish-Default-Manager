"""Sección «Gestión de subtítulos»: fija el castellano como subtítulo predeterminado en los MKV de una carpeta.

Flujo: elegir carpeta → análisis automático (simulación silenciosa, no modifica nada) → revisar la
previsualización → «Procesar carpeta» (con confirmación) → resultado. La lógica es la del módulo original
(BatchWorker / batch.process_files / selector.decide): solo cambia la presentación.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QMenu, QMessageBox, QTreeWidgetItem

from ..batch import BatchSummary, describe_result
from ..classifier import describe
from ..models import Category, Status
from ..workers import BatchWorker
from . import styles
from .base import BasePage
from .widgets import (
    KIND_CHANGE, KIND_ERROR, KIND_REVIEW, KIND_SAME, ROLE_KIND, ROLE_PATH, EmptyState, FolderBar, OptionRow,
    ResultsView, SummaryPanel, brush, button, card, divider, set_bold, stacked,
)

STATUS_TEXT = {
    Status.TO_CHANGE: "Se modificará",
    Status.ALREADY_OK: "Ya correcto",
    Status.NO_SPANISH: "Sin subtítulos españoles",
    Status.ONLY_LATINO: "Solo latino (no se toca)",
    Status.REVIEW: "Revisar manualmente",
    Status.ERROR: "Error",
}
STATUS_COLOR = {
    Status.TO_CHANGE: styles.COLOR_CAMBIO, Status.ALREADY_OK: styles.COLOR_CASTELLANO,
    Status.NO_SPANISH: styles.COLOR_OTRO, Status.ONLY_LATINO: styles.COLOR_LATINO,
    Status.REVIEW: styles.COLOR_REVISAR, Status.ERROR: styles.COLOR_AMBIGUO,
}
CATEGORY_COLOR = {
    Category.CASTELLANO: styles.COLOR_CASTELLANO, Category.GENERICO: styles.COLOR_CASTELLANO,
    Category.LATINO: styles.COLOR_LATINO, Category.AMBIGUO: styles.COLOR_AMBIGUO,
    Category.OTRO: styles.COLOR_OTRO,
}
SELECTED_BG = (76, 195, 138, 38)
LEGEND = (
    f'<span style="color:{styles.COLOR_CASTELLANO}">●</span> Castellano / español genérico &nbsp; '
    f'<span style="color:{styles.COLOR_LATINO}">●</span> Latino &nbsp; '
    f'<span style="color:{styles.COLOR_AMBIGUO}">●</span> Ambiguo &nbsp; '
    f'<span style="color:{styles.COLOR_OTRO}">●</span> Otro idioma &nbsp;·&nbsp; '
    "Fondo verde: pista que queda como predeterminada · Clic derecho en un episodio: aplicar solo a ese archivo"
)


class SubtitleManagerPage(BasePage):
    def __init__(self, ctx, parent=None):
        super().__init__(ctx, "Gestión de subtítulos",
                         "Deja el castellano como subtítulo predeterminado en los MKV, sin tocar los nombres "
                         "ni recodificar nada.", "Registro: pista seleccionada en cada episodio", parent)
        self.worker = None
        self.items = {}
        self.preview_key = None
        self.preview_summary = None
        self.run_preview = False
        self.run_single = False
        self._build_ui()
        self._update_buttons()

    # ---------- construcción ----------
    def _build_ui(self):
        s = self.settings
        self.folder_bar = FolderBar("Carpeta con los episodios", "Elige la carpeta de una temporada o serie")
        self.folder_bar.set_folder(s.value("folder", ""))
        self.folder_bar.set_recursive(s.value("recursive", True, type=bool))
        self.folder_bar.folder_chosen.connect(lambda _f: self._preview())
        self.folder_bar.recursive_changed.connect(lambda _v: self._options_changed())
        self.body_lay.addWidget(self.folder_bar)

        opts, ol = card((16, 10, 16, 10), 18, horizontal=True)
        self.opt_dry = OptionRow("Modo simulación", "Muestra lo que se haría sin modificar ningún archivo.")
        self.opt_dry.switch.setChecked(s.value("dry", False, type=bool))
        self.opt_dry.switch.toggled.connect(lambda _v: self._update_buttons())
        self.opt_clear = OptionRow(
            "Quitar «predeterminada» al resto de pistas",
            "Actívalo solo si algún reproductor sigue eligiendo otra pista.",
            "Por defecto solo se tocan la pista castellana, las latinas y otras pistas españolas completas.")
        self.opt_clear.switch.setChecked(s.value("clear_other", False, type=bool))
        self.opt_clear.switch.toggled.connect(lambda _v: self._options_changed())
        ol.addWidget(self.opt_dry, 1)
        sep = divider()
        sep.setFixedWidth(1)
        sep.setMaximumHeight(16777215)
        ol.addWidget(sep)
        ol.addWidget(self.opt_clear, 1)
        self.body_lay.addWidget(opts)

        self.summary = SummaryPanel()
        self.body_lay.addWidget(self.summary)

        self.empty = EmptyState("subtitles", "Elige una carpeta para empezar",
                                "Se analizarán todos los MKV automáticamente y verás qué pista quedará como "
                                "predeterminada en cada episodio antes de cambiar nada. También puedes soltar "
                                "la carpeta sobre el selector.")
        btn = button("Elegir carpeta…", "primary", "folder")
        btn.clicked.connect(self.folder_bar._browse)
        self.empty.add_button(btn)
        self.results = ResultsView(["Episodio / pista", "Tipo", "Idioma", "Predet. antes", "Predet. después",
                                    "Resultado"], [33, 17, 10, 9, 11, 20], LEGEND)
        self.tree = self.results.tree
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.stack = stacked(self.empty, self.results)
        self.body_lay.addWidget(self.stack, 1)

        self.btn_cancel = button("Cancelar", icon_name="stop")
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_cancel.hide()
        self.btn_reanalyze = button("Volver a analizar", icon_name="refresh")
        self.btn_reanalyze.clicked.connect(self._preview)
        self.btn_process = button("Procesar carpeta", "primary", "play")
        self.btn_process.clicked.connect(self._on_process)
        for b in (self.btn_cancel, self.btn_reanalyze, self.btn_process):
            self.actions.add_button(b)
        self.actions.set_status("Elige una carpeta para analizarla.")

    # ---------- utilidades ----------
    def _clear_other(self) -> bool:
        return self.opt_clear.switch.isChecked()

    def _dry(self) -> bool:
        return self.opt_dry.switch.isChecked()

    def _update_buttons(self):
        busy = self._busy()
        has_folder = bool(self.folder())
        ps = self.preview_summary if self.preview_key == self._key() else None
        if self._dry():
            text = "Simular cambios"
        elif ps is not None and ps.modified:
            text = f"Procesar {ps.modified} episodio(s)"
        else:
            text = "Procesar carpeta"
        self.btn_process.setText(text)
        self.btn_process.setEnabled(not busy and has_folder)
        self.btn_reanalyze.setEnabled(not busy and has_folder)
        self.btn_reanalyze.setVisible(has_folder)
        self.btn_cancel.setVisible(busy)
        self.folder_bar.setEnabled(not busy)

    def _key(self):
        return (self.folder(), self.folder_bar.is_recursive(), self._clear_other())

    def _options_changed(self):
        self._invalidate_preview()
        if self.folder() and self.tree.topLevelItemCount() and not self._busy():
            self._preview()           # el análisis es de solo lectura: se rehace solo

    def _invalidate_preview(self):
        self.preview_key = None
        self._update_buttons()

    def _validate(self) -> bool:
        folder = self.folder()
        if not folder or not Path(folder).is_dir():
            self.notify("warning", "Carpeta no válida", "Elige una carpeta existente.")
            return False
        if not self.ctx.get_tools():
            self.notify("error", "MKVToolNix no encontrado",
                        "Instálalo o indica su carpeta en Ajustes. " + self.ctx.tools_error)
            return False
        return True

    def _busy(self):
        return self.worker is not None and self.worker.isRunning()

    def _cancel(self):
        if self.worker:
            self.worker.cancel()
            self.actions.set_status("Cancelando…")

    def _relative(self, path):
        try:
            return str(Path(path).relative_to(self.folder()))
        except ValueError:
            return str(path)

    def _save_settings(self):
        self.settings.setValue("folder", self.folder())
        self.settings.setValue("recursive", self.folder_bar.is_recursive())
        self.settings.setValue("dry", self._dry())
        self.settings.setValue("clear_other", self._clear_other())

    # ---------- resumen ----------
    def _show_summary(self, s: BatchSummary, title: str):
        tiles = [
            ("Archivos MKV", s.found, ""),
            ("Se modificarían" if s.dry_run else "Modificados", s.modified, styles.COLOR_CAMBIO if s.modified else ""),
            ("Ya correctos", s.already_ok, ""),
            ("A revisar", s.review, styles.WARNING if s.review else ""),
            ("Errores", s.errors, styles.DANGER if s.errors else ""),
        ]
        self.summary.set_data(title, tiles, s.rows())

    # ---------- flujo principal ----------
    def _preview(self):
        """Al elegir la carpeta: análisis automático (simulación silenciosa)."""
        if self._busy() or not self._validate():
            return
        self._start(dry=True, preview=True)

    def _on_process(self):
        if self._busy() or not self._validate():
            return
        if self._dry():
            self._start(dry=True, preview=False)
            return
        ps = self.preview_summary if self.preview_key == self._key() else None
        if ps is not None and ps.modified == 0:
            self.notify("info", "Nada que modificar",
                        "Ningún episodio necesita cambios. Revisa el resumen para ver el motivo.")
            return
        what = f"{ps.modified} episodio(s)" if ps is not None else "todos los episodios compatibles de la carpeta"
        ans = QMessageBox.question(
            self, "Confirmar procesamiento",
            f"Se establecerá el castellano como subtítulo predeterminado en {what}.\n"
            "Solo cambia el indicador de predeterminada: no se elimina ni se reconstruye nada.\n\n¿Procesar la carpeta?")
        if ans == QMessageBox.StandardButton.Yes:
            self._start(dry=False, preview=False)

    def _tree_menu(self, pos):
        it = self.tree.itemAt(pos)
        if it is None or self._busy():
            return
        top = it.parent() or it
        menu = QMenu(self)
        act = menu.addAction("Aplicar solo a este archivo")
        if menu.exec(self.tree.viewport().mapToGlobal(pos)) == act:
            dry = self._dry()
            if not dry and QMessageBox.question(self, "Confirmar", f"¿Modificar {top.text(0)}?") != QMessageBox.StandardButton.Yes:
                return
            if not self._validate():
                return
            self._start(dry=dry, preview=False, files=[Path(top.data(0, ROLE_PATH))], single=True)

    def _start(self, dry, preview, files=None, single=False):
        self._save_settings()
        self.infobar.hide()
        self.run_preview, self.run_single = preview, single
        if not single:
            self.results.clear()
            self.items.clear()
        self.stack.setCurrentWidget(self.results)
        folder = self.folder()
        mode = "Análisis" if preview else ("Simulación" if dry else "Procesando")
        self._log(f"{mode}: {folder}")
        self._verb = "Analizando" if (preview or dry) else "Procesando"
        self.actions.start_progress(f"{self._verb} la carpeta…")
        self.worker = BatchWorker(self.ctx.get_tools(), folder, self.folder_bar.is_recursive(), self._clear_other(),
                                  dry, files, self)
        self.worker.result.connect(self._on_result)
        self.worker.progress.connect(lambda i, n: self.actions.set_progress(i, n, self._verb))
        self.worker.log.connect(self._log)
        self.worker.done.connect(self._on_done)
        self.worker.start()
        self._update_buttons()

    def _on_result(self, res):
        self._add_item(res)
        self._log(describe_result(res))

    def _on_done(self, s: BatchSummary):
        self.actions.stop_progress()
        self.results.recount()
        if self.run_preview:
            title = "Vista previa · no se ha modificado nada"
        elif s.dry_run:
            title = "Simulación · no se ha modificado nada"
        else:
            title = "Resultado del procesamiento"
        self._show_summary(s, title)
        self._log("Resumen — " + " · ".join(f"{k}: {v}" for k, v in s.rows()))
        if not s.found and not s.cancelled:
            self.stack.setCurrentWidget(self.empty)
            self.empty.set_content("No hay archivos MKV", "La carpeta elegida no contiene archivos MKV"
                                   + ("." if self.folder_bar.is_recursive() else " (prueba a activar «Subcarpetas»)."),
                                   "folder", "warning")
            self.summary.hide()
        if self.run_preview:
            self.preview_key, self.preview_summary = self._key(), s
            self._update_buttons()
            if s.cancelled:
                self.actions.set_status("Análisis cancelado.", "warning")
            elif s.modified:
                self.actions.set_status(f"Listo para procesar: {s.modified} episodio(s) cambiarán.", "info")
            elif s.found:
                self.actions.set_status("Ningún episodio necesita cambios.", "success")
            else:
                self.actions.set_status("No se encontraron archivos MKV.", "warning")
            return
        self._update_buttons()
        if s.dry_run:
            self.actions.set_status("Simulación terminada.", "info")
            if s.modified and not s.cancelled:
                text = "\n".join(f"{k}: {v}" for k, v in s.rows())
                ans = QMessageBox.question(self, "Simulación terminada",
                                           f"{text}\n\n¿Aplicar ahora estos cambios a {s.modified} episodio(s)?")
                if ans == QMessageBox.StandardButton.Yes:
                    self._start(dry=False, preview=False)
            return
        sev = "error" if s.errors else ("warning" if s.review or s.cancelled else "success")
        title = "Procesamiento cancelado" if s.cancelled else "Procesamiento terminado"
        parts = [f"{s.modified} episodio(s) modificados", f"{s.already_ok} ya estaban correctos"]
        if s.review:
            parts.append(f"{s.review} a revisar")
        if s.errors:
            parts.append(f"{s.errors} con error")
        action = ("Ver errores", lambda: self.results.set_filter(KIND_ERROR)) if s.errors else \
                 (("Ver pendientes", lambda: self.results.set_filter(KIND_REVIEW)) if s.review else ("", None))
        self.notify(sev, title, " · ".join(parts) + ".", *action)
        self.actions.set_status(title + ".", sev)
        if self.run_single:
            self._start(dry=True, preview=True)   # refresca la lista con el estado real

    def _add_item(self, res):
        a = res.analysis
        d = a.decision
        key = str(a.path)
        old = self.items.pop(key, None)
        if old is not None:
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(old))
        item = QTreeWidgetItem(self.tree)
        self.items[key] = item
        item.setText(0, self._relative(a.path))
        item.setToolTip(0, key)
        item.setData(0, ROLE_PATH, key)
        set_bold(item)

        if res.outcome == "ok":
            status, color = "Modificado", styles.COLOR_CASTELLANO
        else:
            status, color = STATUS_TEXT[d.status], STATUS_COLOR[d.status]
        item.setText(5, f"{status} — {d.message}" if d.message else status)
        item.setToolTip(5, item.text(5))
        item.setForeground(5, brush(color))
        if res.outcome == "error" or d.status == Status.ERROR:
            kind = KIND_ERROR
        elif d.status == Status.REVIEW:
            kind = KIND_REVIEW
        elif d.status == Status.TO_CHANGE or res.outcome == "ok":
            kind = KIND_CHANGE
        else:
            kind = KIND_SAME
        item.setData(0, ROLE_KIND, kind)

        new_defaults = {c.track.index: c.new_default for c in d.changes}
        for t in a.tracks:
            child = QTreeWidgetItem(item)
            child.setText(0, f"#{t.index}  {t.name or '(sin nombre)'}")
            child.setText(1, describe(t))
            child.setText(2, t.language + (f" / {t.ietf}" if t.ietf else ""))
            child.setText(3, "Sí" if t.default else "No")
            if t.index in new_defaults:
                child.setText(4, ("Sí" if new_defaults[t.index] else "No") + "  (cambia)")
                child.setForeground(4, brush(styles.COLOR_CAMBIO))
            else:
                child.setText(4, "Sí" if t.default else "No")
            child.setForeground(1, brush(CATEGORY_COLOR[t.category]))
            for col in (0, 2, 3):
                child.setForeground(col, brush(styles.MUTED))
            if t.notes:
                child.setToolTip(0, "\n".join(t.notes))
                child.setToolTip(1, "\n".join(t.notes))
            if d.selected is not None and t.index == d.selected.index:
                for col in range(6):
                    child.setBackground(col, QColor(*SELECTED_BG))
                child.setForeground(0, brush(styles.TEXT))
        item.setExpanded(d.status in (Status.REVIEW, Status.ERROR))
        if self.run_single:
            self.results.recount()

    # ---------- interfaz para la ventana principal ----------
    def folder(self) -> str:
        return self.folder_bar.folder()

    def set_folder(self, path: str):
        """Fija la carpeta sin lanzar análisis (se usa al cambiar de sección)."""
        if path and path != self.folder():
            self.folder_bar.set_folder(path)
            self.results.clear()
            self.summary.hide()
            self.stack.setCurrentWidget(self.empty)
            self.empty.set_content("Carpeta lista para analizar", path, "subtitles")
            self.actions.set_status("Carpeta pendiente de analizar.")
            self._invalidate_preview()

    def invalidate_preview(self):
        """Los archivos han cambiado (p. ej. tras el procesamiento completo)."""
        self._invalidate_preview()

    def on_activated(self):
        self._update_buttons()
        # Al llegar con una carpeta ya elegida (desde otra sección), se analiza sola: es de solo lectura.
        if (self.folder() and Path(self.folder()).is_dir() and not self._busy()
                and self.tree.topLevelItemCount() == 0 and self.ctx.tools):
            self._preview()

    def busy(self) -> bool:
        return self._busy()

    def shutdown(self):
        self._save_settings()
        if self._busy():
            self.worker.cancel()
            self.worker.wait(5000)

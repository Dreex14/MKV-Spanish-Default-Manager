"""Sección «Ajustes»: ubicación de MKVToolNix, datos que guarda la aplicación e información del programa."""
from __future__ import annotations

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from .. import __version__
from ..journal import journal_path
from ..mkvtools import bundled_dir, is_bundled
from ..paths import app_data_dir
from ..rename_history import history_path
from . import icons, styles
from .rename_page import HistoryDialog, confirm_clear_history
from .widgets import PageHeader, ToggleSwitch, button, card, divider, label


class SettingsPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner.setObjectName("content")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(14)
        lay.addWidget(PageHeader("Ajustes", "Opciones técnicas y datos de la aplicación."))

        # ---- MKVToolNix ----
        lay.addWidget(label("Herramientas", "sectionTitle"))
        c, cl = card((16, 14, 16, 14), 10)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.tools_icon = QLabel()
        row.addWidget(self.tools_icon, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label("Ubicación de MKVToolNix"))
        self.tools_text = label("", "subtle", wrap=True)
        self.tools_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        col.addWidget(self.tools_text)
        row.addLayout(col, 1)
        self.btn_auto = button("Detectar automáticamente", "subtle")
        self.btn_auto.setToolTip("Olvida la carpeta elegida y busca MKVToolNix en las rutas habituales y en el PATH")
        self.btn_auto.clicked.connect(self.ctx.clear_tools_dir)
        row.addWidget(self.btn_auto, 0, Qt.AlignmentFlag.AlignTop)
        self.btn_licence = button("Licencia", "subtle", "open")
        self.btn_licence.setToolTip("Abre la carpeta de la copia incluida: licencia GPL-2.0 (COPYING.txt), "
                                    "licencias de sus bibliotecas y LEEME.txt con la versión y el código fuente")
        self.btn_licence.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(bundled_dir()))))
        row.addWidget(self.btn_licence, 0, Qt.AlignmentFlag.AlignTop)
        b = button("Elegir carpeta…", icon_name="folder")
        b.clicked.connect(self._browse_tools)
        row.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        cl.addLayout(row)
        cl.addWidget(divider())
        cl.addWidget(label("Se usa mkvmerge para leer las pistas y mkvpropedit para cambiar solo el indicador de "
                           "pista predeterminada: el vídeo y el audio nunca se recodifican.", "subtle", wrap=True))
        lay.addWidget(c)

        # ---- Datos ----
        lay.addWidget(label("Datos de la aplicación", "sectionTitle"))
        c, cl = card((16, 8, 16, 8), 0)
        items = [
            ("Historial de renombrados", "Permite deshacer los renombrados.", history_path(), "history", None),
            ("Diario de cambios de pistas", "Valores anteriores de cada pista modificada (journal.jsonl).",
             journal_path(), "", None),
            ("Registro de la aplicación", "Errores internos (app.log).", app_data_dir() / "app.log", "", None),
        ]
        for i, (title, desc, path, action, cb) in enumerate(items):
            if i:
                cl.addWidget(divider())
            r = QHBoxLayout()
            r.setContentsMargins(0, 8, 0, 8)
            t = QVBoxLayout()
            t.setSpacing(1)
            t.addWidget(label(title))
            p = label(f"{desc}  ·  {path}", "subtle", wrap=True)
            p.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            t.addWidget(p)
            r.addLayout(t, 1)
            if action == "history":
                self.save_history = ToggleSwitch("Guardar")
                self.save_history.setToolTip("Si lo desactivas, los próximos renombrados no se guardan y no se "
                                             "podrán deshacer. Lo que ya está guardado se conserva.")
                self.save_history.setChecked(self.ctx.save_history())
                self.save_history.toggled.connect(self.ctx.set_save_history)
                r.addWidget(self.save_history)
                r.addSpacing(16)
                vb = button("Ver", icon_name="history")
                vb.clicked.connect(lambda: HistoryDialog(self.ctx, self).exec())
                r.addWidget(vb)
                r.addSpacing(10)
                self.btn_clear = button("Borrar", "danger", "close", icon_color=styles.DANGER)
                self.btn_clear.clicked.connect(lambda: confirm_clear_history(self, self.ctx))
                r.addWidget(self.btn_clear)
            cl.addLayout(r)
        cl.addWidget(divider())
        r = QHBoxLayout()
        r.setContentsMargins(0, 8, 0, 6)
        r.addStretch(1)
        ob = button("Abrir carpeta de datos", icon_name="open")
        ob.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(app_data_dir()))))
        r.addWidget(ob)
        cl.addLayout(r)
        lay.addWidget(c)

        # ---- Acerca de ----
        lay.addWidget(label("Acerca de", "sectionTitle"))
        c, cl = card((16, 14, 16, 14), 14, horizontal=True)
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(48, 48))
        cl.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)
        t = QVBoxLayout()
        t.setSpacing(2)
        t.addWidget(label(f"MKV Spanish Default Manager {__version__}", "sectionTitle"))
        t.addWidget(label("Hecho por Dreex.", "muted"))
        t.addWidget(label("Usa MKVToolNix (mkvmerge y mkvpropedit) y Qt for Python (PySide6).", "subtle", wrap=True))
        cl.addLayout(t, 1)
        lay.addWidget(c)
        lay.addStretch(1)

        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self.ctx.tools_changed.connect(self._refresh_tools)
        self.ctx.history_changed.connect(self._refresh_history)
        self._refresh_tools()
        self._refresh_history()

    def _refresh_history(self):
        self.save_history.blockSignals(True)
        self.save_history.setChecked(self.ctx.save_history())
        self.save_history.blockSignals(False)
        self.btn_clear.setEnabled(history_path().exists())

    def _browse_tools(self):
        d = QFileDialog.getExistingDirectory(self, "Carpeta de MKVToolNix (con mkvmerge y mkvpropedit)",
                                             self.ctx.tools_dir())
        if d:
            self.ctx.set_tools_dir(d)

    def _refresh_tools(self):
        dpr = self.devicePixelRatioF()
        if self.ctx.tools:
            self.tools_icon.setPixmap(icons.pixmap("success", styles.SUCCESS, 20, dpr))
            if is_bundled(self.ctx.tools.mkvmerge):
                self.tools_text.setText("Se usa la copia incluida en la aplicación. Si instalas MKVToolNix, "
                                        "se usará la versión instalada.")
            else:
                origin = "carpeta elegida" if self.ctx.custom_tools_dir() else "detectado automáticamente"
                self.tools_text.setText(f"Encontrado en {self.ctx.tools_dir()} ({origin}).")
        else:
            self.tools_icon.setPixmap(icons.pixmap("error", styles.DANGER, 20, dpr))
            self.tools_text.setText("No encontrado. Instálalo (winget install MoritzBunkus.MKVToolNix o "
                                    "https://mkvtoolnix.download) o indica su carpeta.")
        self.btn_auto.setVisible(bool(self.ctx.custom_tools_dir()))
        bundled = bundled_dir()
        self.btn_licence.setVisible(bundled is not None and (bundled / "COPYING.txt").is_file())

    # interfaz común de las páginas
    def folder(self) -> str:
        return ""

    def set_folder(self, _path: str):
        pass

    def on_activated(self):
        self._refresh_tools()
        self._refresh_history()

    def busy(self) -> bool:
        return False

    def shutdown(self):
        pass

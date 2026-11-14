"""Ventana principal: barra lateral compacta con las tres secciones de trabajo y los ajustes.

  · Procesamiento completo — renombra y selecciona los subtítulos en un solo paso (abierta por defecto).
  · Renombrado masivo      — limpia y modifica los nombres de los archivos por lotes.
  · Gestión de subtítulos  — fija el castellano como subtítulo predeterminado en los MKV.
  · Ajustes                — MKVToolNix, datos de la aplicación y versión.

La carpeta elegida se comparte entre secciones al cambiar de una a otra.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from .. import __version__
from . import icons, styles
from .context import AppContext
from .full_page import FullProcessPage
from .rename_page import RenamePage
from .settings_page import SettingsPage
from .subtitle_page import SubtitleManagerPage

SIDEBAR_WIDE, SIDEBAR_NARROW, NARROW_BELOW = 232, 60, 980


class NavButton(QToolButton):
    """Elemento de navegación con el indicador de acento a la izquierda (estilo Windows 11)."""

    def __init__(self, text: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("nav")
        self.setText(text)
        self.setToolTip(text)
        self.setCheckable(True)
        self.setIcon(icons.icon(icon_name, styles.MUTED, 20, active_color=styles.ACCENT))
        self.setIconSize(QSize(20, 20))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setMinimumHeight(40)

    def set_compact(self, compact: bool):
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly if compact
                                else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.isChecked():
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(styles.BRAND))
            h = 16
            p.drawRoundedRect(QRectF(0, (self.height() - h) / 2, 3, h), 1.5, 1.5)
            p.end()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MKV Spanish Default Manager")
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(860, 600)
        self.resize(1240, 800)

        self.ctx = AppContext(self)
        self.subtitles = SubtitleManagerPage(self.ctx)
        self.renamer = RenamePage(self.ctx)
        self.full = FullProcessPage(self.ctx, self.renamer, self.subtitles, goto_rename=lambda: self.select(self.renamer))
        self.settings_page = SettingsPage(self.ctx)
        self.pages = [self.full, self.renamer, self.subtitles, self.settings_page]

        self.stack = QStackedWidget()
        for p in self.pages:
            self.stack.addWidget(p)

        # ---- Barra lateral ----
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        sl = QVBoxLayout(self.sidebar)
        sl.setContentsMargins(10, 16, 10, 12)
        sl.setSpacing(2)
        self.brand = QWidget()
        bl = QHBoxLayout(self.brand)
        bl.setContentsMargins(8, 0, 4, 14)
        bl.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(28, 28))
        bl.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        t1 = QLabel("MKV Spanish")
        t1.setObjectName("brand")
        t2 = QLabel("Default Manager")
        t2.setObjectName("brandSub")
        names.addWidget(t1)
        names.addWidget(t2)
        self.brand_names = QWidget()
        self.brand_names.setLayout(names)
        bl.addWidget(self.brand_names, 1)
        sl.addWidget(self.brand)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.nav = {}
        entries = [
            (self.full, "Procesamiento completo", "full"),
            (self.renamer, "Renombrado masivo", "rename"),
            (self.subtitles, "Gestión de subtítulos", "subtitles"),
        ]
        for page, text, ic in entries:
            sl.addWidget(self._nav_button(page, text, ic))
        sl.addStretch(1)
        sl.addWidget(self._nav_button(self.settings_page, "Ajustes", "settings"))
        self.version = QLabel(f"Versión {__version__}")
        self.version.setObjectName("brandSub")
        self.version.setContentsMargins(10, 8, 0, 0)
        sl.addWidget(self.version)

        root = QWidget()
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.sidebar)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.ctx.tools_changed.connect(self._tools_banner)
        self._compact = None
        self._last = self.full
        self.select(self.full)
        self._apply_sidebar_width()
        self._tools_banner()

    def _nav_button(self, page, text, ic):
        b = NavButton(text, ic)
        b.clicked.connect(lambda _c=False, p=page: self.select(p))
        self.group.addButton(b)
        self.nav[page] = b
        return b

    def _tools_banner(self):
        """Si falta MKVToolNix se avisa en las secciones que lo necesitan, con acceso directo a Ajustes."""
        for page in (self.full, self.subtitles):
            if self.ctx.tools is None:
                page.notify("error", "MKVToolNix no encontrado",
                            "Hace falta para leer y modificar los subtítulos.", "Configurar",
                            lambda: self.select(self.settings_page))
            elif page.infobar.title.text() == "MKVToolNix no encontrado":
                page.infobar.hide()

    def select(self, page):
        """Muestra una sección; la carpeta de la anterior se pasa a la nueva."""
        prev = self._last
        if page is not self.settings_page:
            folder = prev.folder() if prev is not None and prev is not page else ""
            if folder:
                page.set_folder(folder)
            self._last = page
        self.stack.setCurrentWidget(page)
        self.nav[page].setChecked(True)
        if hasattr(page, "on_activated"):
            page.on_activated()

    # ---- barra lateral adaptable ----
    def _apply_sidebar_width(self):
        compact = self.width() < NARROW_BELOW
        if compact == self._compact:
            return
        self._compact = compact
        self.sidebar.setFixedWidth(SIDEBAR_NARROW if compact else SIDEBAR_WIDE)
        self.brand_names.setVisible(not compact)
        self.version.setVisible(not compact)
        for b in self.nav.values():
            b.set_compact(compact)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_sidebar_width()

    def showEvent(self, e):
        super().showEvent(e)
        if sys.platform == "win32":
            _dark_title_bar(self)

    def closeEvent(self, event):
        for page in self.pages:
            page.shutdown()
        current = self._last                      # la carpeta de la sección activa es la más reciente
        if current is not None and current.folder():
            self.ctx.settings.setValue("folder", current.folder())
        super().closeEvent(event)


def _dark_title_bar(window):
    """Barra de título oscura y del mismo tono que la barra lateral (Windows 10 20H1+ / Windows 11)."""
    try:
        import ctypes
        hwnd = int(window.winId())
        dwm = ctypes.windll.dwmapi
        on = ctypes.c_int(1)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))       # modo oscuro
        c = QColor(styles.SIDEBAR)
        colorref = ctypes.c_int(c.red() | (c.green() << 8) | (c.blue() << 16))
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colorref), ctypes.sizeof(colorref))  # color (Win 11)
    except Exception:
        pass

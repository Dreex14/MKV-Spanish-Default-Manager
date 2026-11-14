"""Estado compartido por todas las páginas: ajustes persistentes y localización de MKVToolNix."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal

from .. import rename_history
from ..mkvtools import MkvToolError, MkvTools


class AppContext(QObject):
    tools_changed = Signal()
    history_changed = Signal()      # se borró el historial o cambió «guardar historial»

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("MKVSpanishDefaultManager", "App")
        self.tools = None
        self.tools_error = ""
        self.locate_tools()
        rename_history.set_enabled(self.save_history())

    # ---------- historial de renombrados ----------
    def save_history(self) -> bool:
        return self.settings.value("rename/save_history", True, type=bool)

    def set_save_history(self, enabled: bool):
        self.settings.setValue("rename/save_history", bool(enabled))
        rename_history.set_enabled(enabled)
        self.history_changed.emit()

    def clear_history(self) -> int:
        count = rename_history.clear_history()
        self.history_changed.emit()
        return count

    # ---------- MKVToolNix ----------
    def custom_tools_dir(self) -> str:
        return self.settings.value("mkv_dir", "") or ""

    def locate_tools(self):
        try:
            self.tools = MkvTools.locate(self.custom_tools_dir() or None)
            self.tools_error = ""
        except MkvToolError as exc:
            self.tools = None
            self.tools_error = str(exc)
        self.tools_changed.emit()
        return self.tools

    def get_tools(self):
        """MKVToolNix localizado, o None (se reintenta por si se instaló con la aplicación abierta)."""
        return self.tools or self.locate_tools()

    def set_tools_dir(self, folder: str):
        self.settings.setValue("mkv_dir", folder)
        self.locate_tools()

    def clear_tools_dir(self):
        self.settings.remove("mkv_dir")
        self.locate_tools()

    def tools_dir(self) -> str:
        return str(Path(self.tools.mkvmerge).parent) if self.tools else ""

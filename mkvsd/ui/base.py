"""Esqueleto común de las páginas de trabajo: cabecera, aviso, contenido, registro desplegable y barra de acciones."""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from .widgets import ActionBar, InfoBar, LogPanel, PageHeader


class BasePage(QWidget):
    def __init__(self, ctx, title: str, subtitle: str, log_placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
        self.settings = ctx.settings
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.body = QWidget()
        self.body.setObjectName("content")
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(28, 22, 28, 16)
        self.body_lay.setSpacing(14)
        self.header = PageHeader(title, subtitle)
        self.body_lay.addWidget(self.header)
        self.infobar = InfoBar()
        self.body_lay.addWidget(self.infobar)
        outer.addWidget(self.body, 1)

        self.log_panel = LogPanel(log_placeholder or "Aquí aparecerá el detalle de cada operación.")
        self.actions = ActionBar(self.log_panel)
        if log_placeholder is None:
            self.actions.log_btn.hide()
        outer.addWidget(self.log_panel)
        outer.addWidget(self.actions)

    def _log(self, msg: str):
        self.log_panel.append(msg)

    def notify(self, severity: str, title: str, text: str = "", action_text: str = "", on_action=None):
        self.infobar.show_message(severity, title, text, action_text, on_action)

    def show_log(self):
        self.actions.log_btn.setChecked(True)

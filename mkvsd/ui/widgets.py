"""Componentes reutilizables de la interfaz: cabecera, selector de carpeta, interruptor, barra de acciones,
avisos, resumen, estado vacío, vista de resultados con filtros y registro desplegable.

No contienen lógica de procesamiento: solo presentación.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Property, QEasingCurve, QEvent, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QProgressBar,
    QPushButton, QSizePolicy, QStackedWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import icons, styles

# Tipo de cada fila de resultados (para los filtros)
KIND_CHANGE, KIND_SAME, KIND_REVIEW, KIND_ERROR = "change", "same", "review", "error"
ROLE_KIND = Qt.ItemDataRole.UserRole + 10
ROLE_PATH = Qt.ItemDataRole.UserRole

SEVERITY_ICON = {"success": ("success", styles.SUCCESS), "warning": ("warning", styles.WARNING),
                 "error": ("error", styles.DANGER), "info": ("info", styles.ACCENT)}


def brush(color: str) -> QBrush:
    return QBrush(QColor(color))


def set_bold(item: QTreeWidgetItem, col: int = 0, weight=QFont.Weight.DemiBold):
    f = QFont(item.font(col))
    f.setWeight(weight)
    item.setFont(col, f)


def label(text: str = "", name: str = "", wrap: bool = False) -> QLabel:
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    w.setWordWrap(wrap)
    return w


def button(text: str, kind: str = "", icon_name: str = "", tooltip: str = "", icon_color: str = "") -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    if icon_name:
        color = icon_color or (styles.ACCENT_TEXT if kind == "primary" else styles.MUTED)
        b.setIcon(icons.icon(icon_name, color, 16))
        b.setIconSize(QSize(16, 16))
    if tooltip:
        b.setToolTip(tooltip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def card(margins=(16, 12, 16, 12), spacing=10, horizontal=False):
    """Devuelve (frame, layout) con el estilo de tarjeta."""
    frame = QFrame()
    frame.setObjectName("card")
    lay = QHBoxLayout(frame) if horizontal else QVBoxLayout(frame)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return frame, lay


def divider() -> QFrame:
    d = QFrame()
    d.setObjectName("divider")
    return d


# ---------------------------------------------------------------------------
# Interruptor estilo Windows 11 (sustituye a las casillas en las opciones)
# ---------------------------------------------------------------------------
class ToggleSwitch(QCheckBox):
    """QCheckBox dibujado como interruptor. Mantiene la API (toggled, isChecked, setChecked)."""

    TRACK_W, TRACK_H = 38, 20

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._offset = 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def _get_offset(self):
        return self._offset

    def _set_offset(self, v):
        self._offset = v
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def setChecked(self, checked):   # sin animación al fijar el valor inicial
        super().setChecked(checked)
        self._anim.stop()
        self._offset = 1.0 if checked else 0.0
        self.update()

    def _animate(self, checked):
        if not self.isVisible():
            self._offset = 1.0 if checked else 0.0
            return
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def sizeHint(self):
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self.text()) + 10 if self.text() else 0
        return QSize(self.TRACK_W + text_w + 2, max(self.TRACK_H + 4, fm.height() + 4))

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.TRACK_H
        y = (self.height() - h) / 2
        track = QRectF(1, y, self.TRACK_W - 2, h)
        enabled = self.isEnabled()
        on = self._offset
        if self.isChecked() or on > 0.5:
            fill = QColor(styles.ACCENT if enabled else "#3a3a3d")
            if enabled and self.underMouse():
                fill = QColor(styles.ACCENT_HOVER)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            knob_color = QColor(styles.ACCENT_TEXT if enabled else "#77777c")
        else:
            p.setPen(QPen(QColor("#7a7a80" if enabled else styles.BORDER_STRONG), 1.2))
            p.setBrush(QColor(styles.SURFACE_3 if self.underMouse() and enabled else styles.SURFACE_2))
            knob_color = QColor("#cfcfd4" if enabled else styles.SUBTLE)
        p.drawRoundedRect(track, h / 2, h / 2)
        r = 6.0 if not self.underMouse() else 7.0
        cx = track.left() + h / 2 + on * (track.width() - h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(knob_color)
        p.drawEllipse(QRectF(cx - r, y + h / 2 - r, 2 * r, 2 * r))
        if self.hasFocus():
            p.setPen(QPen(QColor(styles.ACCENT), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(track.adjusted(-2, -2, 2, 2), h / 2 + 2, h / 2 + 2)
        if self.text():
            p.setPen(QColor(styles.TEXT if enabled else styles.SUBTLE))
            p.setFont(self.font())
            p.drawText(QRectF(self.TRACK_W + 10, 0, self.width() - self.TRACK_W - 10, self.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        p.end()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


class OptionRow(QWidget):
    """Interruptor con título y descripción breve (para Ajustes y opciones de cada modo)."""

    def __init__(self, title: str, description: str = "", tooltip: str = "", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(14)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(label(title))
        if description:
            text.addWidget(label(description, "subtle", wrap=True))
        lay.addLayout(text, 1)
        self.switch = ToggleSwitch()
        lay.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignVCenter)
        if tooltip:
            self.setToolTip(tooltip)


# ---------------------------------------------------------------------------
# Cabecera de página
# ---------------------------------------------------------------------------
class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label(title, "pageTitle"))
        self.subtitle = label(subtitle, "pageSubtitle", wrap=True)
        col.addWidget(self.subtitle)
        lay.addLayout(col, 1)
        self.right = QHBoxLayout()
        self.right.setSpacing(6)
        lay.addLayout(self.right)

    def add_right(self, w):
        self.right.addWidget(w, 0, Qt.AlignmentFlag.AlignTop)


# ---------------------------------------------------------------------------
# Selector de carpeta compacto (con arrastrar y soltar)
# ---------------------------------------------------------------------------
class FolderBar(QFrame):
    """Carpeta seleccionada + «Cambiar…» + interruptor de subcarpetas. Acepta soltar una carpeta encima."""

    folder_chosen = Signal(str)      # el usuario eligió/escribió una carpeta (Enter, diálogo o soltar)
    recursive_changed = Signal(bool)

    def __init__(self, dialog_title: str, placeholder: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setAcceptDrops(True)
        self._dialog_title = dialog_title
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 10, 8)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("folder", styles.ACCENT, 20, self.devicePixelRatioF()))
        lay.addWidget(ic)
        self.edit = QLineEdit()
        self.edit.setObjectName("pathEdit")
        self.edit.setPlaceholderText(placeholder)
        self.edit.setStyleSheet("QLineEdit#pathEdit { background: transparent; border: 1px solid transparent; "
                                "padding: 4px 6px; } QLineEdit#pathEdit:hover { background: %s; } "
                                "QLineEdit#pathEdit:focus { background: %s; border-bottom: 2px solid %s; }"
                                % (styles.SURFACE_2, styles.SURFACE_2, styles.ACCENT))
        self.edit.setToolTip("Puedes escribir o pegar una ruta y pulsar Intro, o soltar aquí una carpeta.")
        self.edit.returnPressed.connect(self._commit_text)
        lay.addWidget(self.edit, 1)
        self.recursive = ToggleSwitch("Subcarpetas")
        self.recursive.setToolTip("Incluir también los archivos de las subcarpetas")
        self.recursive.toggled.connect(self.recursive_changed)
        lay.addWidget(self.recursive)
        self.btn = button("Elegir carpeta…", icon_name="folder")
        self.btn.clicked.connect(self._browse)
        lay.addWidget(self.btn)
        self._sync_button()

    def folder(self) -> str:
        return self.edit.text().strip()

    def set_folder(self, path: str):
        self.edit.setText(path or "")
        self.edit.setCursorPosition(0)
        self.edit.setToolTip(path or "")
        self._sync_button()

    def is_recursive(self) -> bool:
        return self.recursive.isChecked()

    def set_recursive(self, value: bool):
        self.recursive.blockSignals(True)
        self.recursive.setChecked(bool(value))
        self.recursive.blockSignals(False)

    def _sync_button(self):
        self.btn.setText("Cambiar…" if self.folder() else "Elegir carpeta…")

    def _commit_text(self):
        self._sync_button()
        self.folder_chosen.emit(self.folder())

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, self._dialog_title, self.folder())
        if d:
            self.set_folder(str(Path(d)))
            self.folder_chosen.emit(self.folder())

    def dragEnterEvent(self, e):
        urls = e.mimeData().urls() if e.mimeData().hasUrls() else []
        if urls and Path(urls[0].toLocalFile()).is_dir():
            e.acceptProposedAction()

    def dropEvent(self, e):
        path = e.mimeData().urls()[0].toLocalFile()
        if Path(path).is_dir():
            self.set_folder(str(Path(path)))
            self.folder_chosen.emit(self.folder())


# ---------------------------------------------------------------------------
# Aviso en línea (InfoBar de Fluent)
# ---------------------------------------------------------------------------
class InfoBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("infobar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 9, 8, 9)
        lay.setSpacing(10)
        self.ic = QLabel()
        lay.addWidget(self.ic, 0, Qt.AlignmentFlag.AlignTop)
        col = QHBoxLayout()
        col.setSpacing(8)
        self.title = label("", "infoTitle")
        self.text = label("", wrap=True)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        col.addWidget(self.title, 0, Qt.AlignmentFlag.AlignTop)
        col.addWidget(self.text, 1)
        lay.addLayout(col, 1)
        self.action = button("", "link")
        self.action.hide()
        lay.addWidget(self.action, 0, Qt.AlignmentFlag.AlignTop)
        close = QPushButton()
        close.setObjectName("iconButton")
        close.setIcon(icons.icon("close", styles.MUTED, 14))
        close.setToolTip("Cerrar")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.hide)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        self._action_cb = None
        self.action.clicked.connect(lambda: self._action_cb and self._action_cb())
        self.hide()

    def show_message(self, severity: str, title: str, text: str = "", action_text: str = "", on_action=None):
        name, color = SEVERITY_ICON.get(severity, SEVERITY_ICON["info"])
        self.ic.setPixmap(icons.pixmap(name, color, 18, self.devicePixelRatioF()))
        self.setProperty("severity", severity)
        self.style().unpolish(self)
        self.style().polish(self)
        self.title.setText(title)
        self.text.setText(text)
        self.text.setVisible(bool(text))
        self._action_cb = on_action
        self.action.setText(action_text)
        self.action.setVisible(bool(action_text and on_action))
        self.show()


# ---------------------------------------------------------------------------
# Resumen: cifras clave + desglose completo desplegable
# ---------------------------------------------------------------------------
class StatTile(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("stat")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 9, 14, 10)
        lay.setSpacing(0)
        self.value = label("0", "statValue")
        self.caption = label("", "statLabel")
        lay.addWidget(self.value)
        lay.addWidget(self.caption)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set(self, caption: str, value, color: str = ""):
        self.caption.setText(caption)
        self.value.setText(str(value))
        self.value.setStyleSheet(f"color: {color};" if color else "")


class SummaryPanel(QWidget):
    """Fila de cifras clave y, bajo «Ver desglose», todas las filas del resumen original (sin perder datos)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        head = QHBoxLayout()
        self.title = label("", "sectionTitle")
        head.addWidget(self.title)
        head.addStretch(1)
        self.toggle = button("Ver desglose", "link")
        self.toggle.clicked.connect(self._toggle)
        head.addWidget(self.toggle)
        lay.addLayout(head)
        self.tiles_row = QHBoxLayout()
        self.tiles_row.setSpacing(8)
        lay.addLayout(self.tiles_row)
        self.tiles = []
        self.details, dl = card((16, 10, 16, 10), 0)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(28)
        self.grid.setVerticalSpacing(3)
        dl.addLayout(self.grid)
        self.details.hide()
        lay.addWidget(self.details)
        self.hide()

    def _toggle(self):
        vis = not self.details.isVisible()
        self.details.setVisible(vis)
        self.toggle.setText("Ocultar desglose" if vis else "Ver desglose")

    def set_data(self, title: str, tiles, rows):
        """tiles: [(texto, valor, color)]; rows: [(texto, valor)] — el resumen completo."""
        self.title.setText(title)
        while len(self.tiles) < len(tiles):
            t = StatTile()
            self.tiles.append(t)
            self.tiles_row.addWidget(t)
        for t, data in zip(self.tiles, tiles):
            t.set(*data)
            t.show()
        for t in self.tiles[len(tiles):]:
            t.hide()
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        half = (len(rows) + 1) // 2
        for i, (name, value) in enumerate(rows):
            r, c = i % half, (i // half) * 2
            n = label(name, "muted")
            v = label(str(value))
            f = QFont(v.font())
            f.setWeight(QFont.Weight.DemiBold)
            v.setFont(f)
            if value and ("revisión" in name.lower()):
                v.setStyleSheet(f"color: {styles.WARNING};")
            if value and name.lower().startswith("errores"):
                v.setStyleSheet(f"color: {styles.DANGER};")
            self.grid.addWidget(n, r, c)
            self.grid.addWidget(v, r, c + 1, Qt.AlignmentFlag.AlignRight)
        self.grid.setColumnMinimumWidth(1, 40)
        self.toggle.setVisible(bool(rows))
        self.show()


# ---------------------------------------------------------------------------
# Estado vacío
# ---------------------------------------------------------------------------
class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, text: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.addStretch(1)
        self.ic = QLabel()
        self.ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon = icon_name
        lay.addWidget(self.ic)
        lay.addSpacing(6)
        self.title = label(title, "emptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.title)
        self.text = label(text, "emptyText", wrap=True)
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text.setMaximumWidth(460)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.text)
        row.addStretch(1)
        lay.addLayout(row)
        self.btn_row = QHBoxLayout()
        self.btn_row.addStretch(1)
        lay.addSpacing(6)
        lay.addLayout(self.btn_row)
        lay.addStretch(2)
        self._render_icon()

    def _render_icon(self):
        self.ic.setPixmap(icons.pixmap(self._icon, styles.SUBTLE, 40, self.devicePixelRatioF()))

    def set_content(self, title: str, text: str, icon_name: str = "", severity: str = ""):
        if icon_name:
            self._icon = icon_name
        color = {"error": styles.DANGER, "warning": styles.WARNING}.get(severity, styles.SUBTLE)
        self.ic.setPixmap(icons.pixmap(self._icon, color, 40, self.devicePixelRatioF()))
        self.title.setText(title)
        self.text.setText(text)

    def add_button(self, b: QPushButton):
        self.btn_row.addWidget(b)
        self.btn_row.addStretch(1)


# ---------------------------------------------------------------------------
# Vista de resultados con filtros
# ---------------------------------------------------------------------------
class ResultsView(QWidget):
    """Árbol de resultados: una fila por archivo (con detalles de pistas plegados) y filtros rápidos.

    `ratios` reparte el ancho entre las columnas y se reajusta con la ventana hasta que el usuario
    redimensiona una columna a mano.
    """

    FILTERS = [("all", "Todos"), (KIND_CHANGE, "Con cambios"), (KIND_REVIEW, "A revisar"), (KIND_ERROR, "Errores")]

    def __init__(self, headers, ratios, legend_html: str = "", filters=None, parent=None):
        super().__init__(parent)
        if filters is not None:
            self.FILTERS = filters
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.chips = {}
        for key, text in self.FILTERS:
            b = button(text, "chip")
            b.setCheckable(True)
            b.clicked.connect(lambda _c=False, k=key: self.set_filter(k))
            self.chips[key] = (b, text)
            bar.addWidget(b)
        bar.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar archivo…")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icons.icon("search", styles.SUBTLE, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setMaximumWidth(260)
        self.search.textChanged.connect(lambda _t: self._apply_filter())
        bar.addWidget(self.search)
        lay.addLayout(bar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(headers)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(18)
        self.tree.header().setStretchLastSection(True)
        self.tree.header().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        total = float(sum(ratios))
        self._ratios = [r / total for r in ratios]
        self._auto_fit, self._fitting = True, False
        self.tree.header().sectionResized.connect(self._on_section_resized)
        self.tree.installEventFilter(self)
        lay.addWidget(self.tree, 1)
        self.legend = label(legend_html, "subtle", wrap=True)
        self.legend.setVisible(bool(legend_html))
        lay.addWidget(self.legend)
        self._filter = "all"
        self.chips["all"][0].setChecked(True)

    def clear(self):
        self.tree.clear()
        self.recount()

    def _on_section_resized(self, index, _old, _new):
        if not self._fitting and index < len(self._ratios) - 1:
            self._auto_fit = False          # el usuario ha ajustado una columna: se respeta

    def eventFilter(self, obj, event):
        if obj is self.tree and event.type() in (QEvent.Type.Resize, QEvent.Type.Show) and self._auto_fit:
            self._fit_columns()
        return super().eventFilter(obj, event)

    def _fit_columns(self):
        if not self.tree.isVisible():
            return                          # se ajusta al mostrarse, con el ancho real
        width = self.tree.viewport().width()
        self._fitting = True
        for col, r in enumerate(self._ratios[:-1]):
            self.tree.setColumnWidth(col, max(70, int(width * r)))
        self._fitting = False

    def set_filter(self, key: str):
        self._filter = key
        for k, (b, _t) in self.chips.items():
            b.setChecked(k == key)
        self._apply_filter()

    def recount(self):
        counts = {k: 0 for k, _ in self.FILTERS}
        for i in range(self.tree.topLevelItemCount()):
            kind = self.tree.topLevelItem(i).data(0, ROLE_KIND)
            counts["all"] += 1
            if kind in counts:
                counts[kind] += 1
        for k, (b, text) in self.chips.items():
            b.setText(f"{text}  {counts[k]}")
            b.setEnabled(k == "all" or counts[k] > 0 or self._filter == k)
        self._apply_filter()
        if self._auto_fit:
            self._fit_columns()

    def _apply_filter(self):
        needle = self.search.text().strip().casefold()
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            ok = self._filter == "all" or it.data(0, ROLE_KIND) == self._filter
            if ok and needle:
                ok = needle in it.text(0).casefold() or needle in it.text(1).casefold()
            it.setHidden(not ok)


# ---------------------------------------------------------------------------
# Registro técnico desplegable
# ---------------------------------------------------------------------------
class LogPanel(QWidget):
    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        head = QFrame()
        head.setObjectName("actionBar")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(20, 4, 12, 4)
        hl.addWidget(label("Registro técnico", "sectionTitle"))
        hl.addStretch(1)
        clear = button("Limpiar", "subtle")
        clear.clicked.connect(lambda: self.view.clear())
        hl.addWidget(clear)
        lay.addWidget(head)
        self.view = QPlainTextEdit()
        self.view.setObjectName("log")
        self.view.setReadOnly(True)
        self.view.setPlaceholderText(placeholder)
        self.view.setMaximumBlockCount(20000)
        lay.addWidget(self.view)
        self.setFixedHeight(190)
        self.hide()

    def append(self, msg: str):
        self.view.appendPlainText(f"[{datetime.now():%H:%M:%S}] {msg}")


# ---------------------------------------------------------------------------
# Barra de acciones inferior: estado/progreso a la izquierda, acciones a la derecha
# ---------------------------------------------------------------------------
class ActionBar(QFrame):
    def __init__(self, log_panel: LogPanel, parent=None):
        super().__init__(parent)
        self.setObjectName("actionBar")
        self.log_panel = log_panel
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 10, 20, 10)
        lay.setSpacing(8)
        self.log_btn = button("Registro", "subtle", "log")
        self.log_btn.setCheckable(True)
        self.log_btn.setToolTip("Mostrar u ocultar el registro técnico detallado")
        self.log_btn.toggled.connect(self._toggle_log)
        lay.addWidget(self.log_btn)
        lay.addSpacing(6)
        status_col = QVBoxLayout()
        status_col.setSpacing(5)
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self.status_icon = QLabel()
        self.status_icon.hide()
        self.status = label("", "muted")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        status_row.addWidget(self.status_icon)
        status_row.addWidget(self.status, 1)
        status_col.addLayout(status_row)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        status_col.addWidget(self.progress)
        lay.addLayout(status_col, 1)
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(8)
        lay.addLayout(self.buttons)

    def add_button(self, b: QPushButton):
        b.setMinimumHeight(34)
        self.buttons.addWidget(b)

    def _toggle_log(self, on):
        self.log_panel.setVisible(on)

    def set_status(self, text: str, severity: str = ""):
        self.status.setText(text)
        self.status.setToolTip(text)
        if severity in SEVERITY_ICON:
            name, color = SEVERITY_ICON[severity]
            self.status_icon.setPixmap(icons.pixmap(name, color, 16, self.devicePixelRatioF()))
            self.status_icon.show()
        else:
            self.status_icon.hide()

    def start_progress(self, text: str):
        self.set_status(text)
        self.progress.setRange(0, 0)          # indeterminado hasta conocer el total real
        self.progress.show()

    def set_progress(self, i: int, total: int, verb: str):
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(i)
        self.set_status(f"{verb} {i} de {total}…")

    def stop_progress(self):
        self.progress.hide()


def stacked(*widgets) -> QStackedWidget:
    s = QStackedWidget()
    for w in widgets:
        s.addWidget(w)
    return s

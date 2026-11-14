"""Iconografía de línea propia (SVG inline) renderizada con QtSvg, nítida a cualquier escala de Windows.

Todos los iconos comparten rejilla de 24×24, trazo de 1,7 px y extremos redondeados.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QDir, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import styles

_PATHS = {
    # Procesamiento completo: capas apiladas (renombrar + subtítulos en un paso)
    "full": '<path d="M12 3.5 21 8l-9 4.5L3 8z"/><path d="m3 12.2 9 4.5 9-4.5"/><path d="m3 16.2 9 4.5 9-4.5"/>',
    # Renombrado: cursor de texto sobre una línea
    "rename": '<path d="M4 7h9"/><path d="M4 12h6"/><path d="M4 17h9"/><path d="M17 4v16"/>'
              '<path d="M15 4h4"/><path d="M15 20h4"/>',
    # Subtítulos: pantalla con dos líneas de texto
    "subtitles": '<rect x="2.8" y="4.5" width="18.4" height="15" rx="2.6"/><path d="M6.5 12.5h4"/>'
                 '<path d="M13 12.5h4.5"/><path d="M6.5 16h7"/><path d="M16 16h1.5"/>',
    # Ajustes: deslizadores
    "settings": '<path d="M4 7h9"/><path d="M17 7h3"/><circle cx="15" cy="7" r="2"/><path d="M4 17h3"/>'
                '<path d="M11 17h9"/><circle cx="9" cy="17" r="2"/>',
    "folder": '<path d="M3.5 7.5a2 2 0 0 1 2-2h3.6l2 2.2h7.4a2 2 0 0 1 2 2v7.8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
    "refresh": '<path d="M20 11a8 8 0 1 0-2.4 5.7"/><path d="M20 4.5V11h-6.5"/>',
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    "history": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5"/><path d="M12 8h.01"/>',
    "success": '<circle cx="12" cy="12" r="8.5"/><path d="m8.3 12.2 2.5 2.5 5-5.2"/>',
    "warning": '<path d="M10.3 4.3 2.9 17.2A2 2 0 0 0 4.6 20h14.8a2 2 0 0 0 1.7-2.8L13.7 4.3a2 2 0 0 0-3.4 0z"/>'
               '<path d="M12 9.5v4"/><path d="M12 16.8h.01"/>',
    "error": '<circle cx="12" cy="12" r="8.5"/><path d="m9.2 9.2 5.6 5.6"/><path d="m14.8 9.2-5.6 5.6"/>',
    "close": '<path d="m6.5 6.5 11 11"/><path d="m17.5 6.5-11 11"/>',
    "chevron-down": '<path d="m6.5 9.5 5.5 5.5 5.5-5.5"/>',
    "chevron-up": '<path d="m6.5 14.5 5.5-5.5 5.5 5.5"/>',
    "log": '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="m7.5 10 2.5 2-2.5 2"/><path d="M12.5 14.5h4"/>',
    "open": '<path d="M14 4h6v6"/><path d="M20 4 11 13"/><path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>',
    "plus": '<path d="M12 5v14"/><path d="M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
    "play": '<path d="M7.5 5.2v13.6a.8.8 0 0 0 1.2.7l11-6.8a.8.8 0 0 0 0-1.4l-11-6.8a.8.8 0 0 0-1.2.7z"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "tool": '<path d="M14.5 6.5a4 4 0 0 0-5.3 5.3L4 17v3h3l5.2-5.2a4 4 0 0 0 5.3-5.3l-2.6 2.6-2.4-.6-.6-2.4z"/>',
}

CHECK_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="m3.6 8.3 2.8 2.8 6-6.2" '
             'fill="none" stroke="#0c0c0d" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def _svg(name: str, color: str, stroke: float = 1.7) -> bytes:
    body = _PATHS[name]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>').encode()


def _render(data: bytes, size: int, ratio: float) -> QPixmap:
    px = max(1, round(size * ratio))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(data))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, px, px))
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm


@lru_cache(maxsize=256)
def icon(name: str, color: str = styles.MUTED, size: int = 18, active_color: str = "") -> QIcon:
    """QIcon nítido en pantallas al 100–300 %. `active_color` se usa en los estados activo/seleccionado."""
    ic = QIcon()
    for ratio in (1.0, 1.25, 1.5, 2.0, 3.0):
        ic.addPixmap(_render(_svg(name, color), size, ratio), QIcon.Mode.Normal, QIcon.State.Off)
        ic.addPixmap(_render(_svg(name, styles.SUBTLE), size, ratio), QIcon.Mode.Disabled, QIcon.State.Off)
        if active_color:
            ic.addPixmap(_render(_svg(name, active_color), size, ratio), QIcon.Mode.Normal, QIcon.State.On)
            ic.addPixmap(_render(_svg(name, active_color), size, ratio), QIcon.Mode.Active, QIcon.State.On)
    return ic


def pixmap(name: str, color: str, size: int, ratio: float = 1.0) -> QPixmap:
    return _render(_svg(name, color), size, ratio)


def resource_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "assets"


def app_icon() -> QIcon:
    ico = resource_dir() / "icon.ico"
    return QIcon(str(ico)) if ico.exists() else QIcon()


def register_resources() -> None:
    """Permite usar url(mkvsd:archivo) en la hoja de estilos (la marca de las casillas)."""
    from ..paths import app_data_dir
    target = app_data_dir() / "ui"
    target.mkdir(parents=True, exist_ok=True)
    check = target / "check.svg"
    if not check.exists() or check.read_text(encoding="utf-8") != CHECK_SVG:
        check.write_text(CHECK_SVG, encoding="utf-8")
    QDir.addSearchPath("mkvsd", str(target))


ICON_SIZE = QSize(18, 18)

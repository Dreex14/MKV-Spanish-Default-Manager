"""Genera assets/icon.ico (16–256 px) y assets/icon.png (512 px) a partir de los SVG de assets/.

Usa solo PySide6 (QtSvg), que ya es dependencia de la aplicación:
    .venv\\Scripts\\python.exe tools\\make_icon.py

· 16, 20, 24 y 32 px se dibujan desde icon-small.svg (versión simplificada, legible en la barra de tareas).
· 40 px o más se dibujan desde icon.svg.
El .ico guarda cada tamaño como PNG (formato admitido por Windows desde Vista).
"""
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ASSETS = Path(__file__).resolve().parent.parent / "assets"
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
SMALL_MAX = 32


def render(svg: Path, size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    QSvgRenderer(str(svg)).render(p, QRectF(0, 0, size, size))
    p.end()
    return img


def png_bytes(img: QImage) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(data)


def write_ico(path: Path, images: dict) -> None:
    sizes = sorted(images)
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries, blobs = b"", b""
    for s in sizes:
        blob = images[s]
        dim = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        blobs += blob
        offset += len(blob)
    path.write_bytes(header + entries + blobs)


def main() -> int:
    QGuiApplication(sys.argv[:1])
    big, small = ASSETS / "icon.svg", ASSETS / "icon-small.svg"
    images = {s: png_bytes(render(small if s <= SMALL_MAX else big, s)) for s in ICO_SIZES}
    write_ico(ASSETS / "icon.ico", images)
    render(big, 512).save(str(ASSETS / "icon.png"))
    print(f"Generados {ASSETS / 'icon.ico'} ({', '.join(map(str, ICO_SIZES))} px) y icon.png (512 px)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

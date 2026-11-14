"""Prepara vendor/MKVToolNix para incluirlo dentro del EXE (lo usa build_exe.bat).

Copia de la instalación local de MKVToolNix solo lo que necesita la aplicación:
  · mkvmerge.exe y mkvpropedit.exe (son ejecutables independientes, sin DLL),
  · su licencia (COPYING.txt, GPL-2.0) y las de las bibliotecas que llevan dentro (licenses/),
  · LEEME.txt con la versión incluida y dónde obtener su código fuente.

Uso:  python tools/bundle_mkvtoolnix.py [carpeta_de_MKVToolNix]
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from mkvsd.mkvtools import find_tool  # noqa: E402

DEST = ROOT / "vendor" / "MKVToolNix"
TOOLS = ("mkvmerge", "mkvpropedit")


def source_dir(arg: str = "") -> Path:
    if arg:
        return Path(arg)
    found = find_tool("mkvmerge")
    if not found:
        raise SystemExit("No se encuentra MKVToolNix instalado. Instálalo (winget install MoritzBunkus.MKVToolNix) "
                         "o indica su carpeta: python tools/bundle_mkvtoolnix.py \"C:\\ruta\\MKVToolNix\"")
    return Path(found).parent


def main() -> int:
    src = source_dir(sys.argv[1] if len(sys.argv) > 1 else "")
    exe = ".exe" if os.name == "nt" else ""
    missing = [t for t in TOOLS if not (src / f"{t}{exe}").is_file()]
    if missing:
        raise SystemExit(f"Faltan {', '.join(missing)} en {src}")
    licence = src / "doc" / "COPYING.txt"
    if not licence.is_file():
        raise SystemExit(f"No se encuentra la licencia de MKVToolNix ({licence}): no se puede redistribuir sin ella.")

    shutil.rmtree(DEST, ignore_errors=True)
    DEST.mkdir(parents=True)
    for t in TOOLS:
        shutil.copy2(src / f"{t}{exe}", DEST / f"{t}{exe}")
    shutil.copy2(licence, DEST / "COPYING.txt")
    if (src / "doc" / "licenses").is_dir():
        shutil.copytree(src / "doc" / "licenses", DEST / "licenses")

    version = subprocess.run([str(DEST / f"mkvmerge{exe}"), "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout.strip()
    (DEST / "LEEME.txt").write_text(
        "MKVToolNix incluido en MKV Spanish Default Manager\n"
        "==================================================\n\n"
        f"Versión: {version}\n"
        "Archivos: mkvmerge y mkvpropedit, sin modificar, tal como los distribuye su autor.\n"
        "Autor: Moritz Bunkus y colaboradores — https://mkvtoolnix.download\n"
        "Licencia: GNU GPL versión 2 (COPYING.txt). Las licencias de las bibliotecas que incluyen están en licenses/.\n"
        "Código fuente de esta versión: https://mkvtoolnix.download/source.html\n\n"
        "MKV Spanish Default Manager solo ejecuta estos programas como herramientas externas para leer las pistas\n"
        "(mkvmerge -J) y cambiar el indicador de pista predeterminada (mkvpropedit). Si hay un MKVToolNix\n"
        "instalado en el equipo, la aplicación usa ese en lugar de esta copia.\n",
        encoding="utf-8")
    print(f"MKVToolNix preparado en {DEST} ({version})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

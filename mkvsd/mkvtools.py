"""Envoltorio de MKVToolNix: mkvmerge -J (lectura) y mkvpropedit (edición in situ)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .classifier import classify_track
from .models import SubtitleTrack

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class MkvToolError(Exception):
    pass


def bundled_dir() -> Optional[Path]:
    """Carpeta de MKVToolNix incluida dentro del EXE (PyInstaller la extrae en sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / "MKVToolNix" if base else None


def find_tool(name: str, custom_dir: Optional[str] = None) -> Optional[str]:
    """Busca una herramienta de MKVToolNix. Orden:

    1. La carpeta elegida en Ajustes.
    2. El PATH.
    3. Las instalaciones habituales (Archivos de programa, AppData local).
    4. Una carpeta «MKVToolNix» junto a la aplicación.
    5. La copia incluida dentro del EXE (así la aplicación funciona aunque no haya nada instalado).
    """
    exe = name + (".exe" if os.name == "nt" else "")
    if custom_dir and (Path(custom_dir) / exe).is_file():
        return str(Path(custom_dir) / exe)
    found = shutil.which(name)
    if found:
        return found
    candidates = []
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            candidates.append(Path(base) / "MKVToolNix" / exe)
    app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    candidates.append(app_dir / "MKVToolNix" / exe)
    bundled = bundled_dir()
    if bundled is not None:
        candidates.append(bundled / exe)
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def is_bundled(path: str) -> bool:
    """¿La ruta es la copia de MKVToolNix incluida en el EXE?"""
    bundled = bundled_dir()
    try:
        return bundled is not None and Path(path).resolve().is_relative_to(bundled.resolve())
    except OSError:
        return False


def _run(cmd):
    proc = subprocess.run(cmd, capture_output=True, creationflags=CREATE_NO_WINDOW)
    return (
        proc.returncode,
        proc.stdout.decode("utf-8", errors="replace"),
        proc.stderr.decode("utf-8", errors="replace"),
    )


def parse_tracks(data: dict) -> list:
    """Convierte la salida JSON de `mkvmerge -J` en pistas de subtítulos clasificadas."""
    container = data.get("container", {})
    if container and container.get("recognized") is False:
        raise MkvToolError("Formato de archivo no reconocido")
    tracks = []
    index = 0
    for tr in data.get("tracks", []):
        if tr.get("type") != "subtitles":
            continue
        index += 1
        p = tr.get("properties", {})
        track = SubtitleTrack(
            id=tr.get("id", -1),
            index=index,
            uid=p.get("uid"),
            name=p.get("track_name") or "",
            language=p.get("language") or "und",
            ietf=p.get("language_ietf") or "",
            codec=tr.get("codec", ""),
            default=bool(p.get("default_track", False)),
            forced=bool(p.get("forced_track", False)),
        )
        tracks.append(classify_track(track))
    return tracks


@dataclass
class MkvTools:
    mkvmerge: str
    mkvpropedit: str

    @classmethod
    def locate(cls, custom_dir: Optional[str] = None) -> "MkvTools":
        merge = find_tool("mkvmerge", custom_dir)
        propedit = find_tool("mkvpropedit", custom_dir)
        if not merge or not propedit:
            raise MkvToolError(
                "No se encontraron mkvmerge y mkvpropedit. Instala MKVToolNix "
                "(https://mkvtoolnix.download) o indica su carpeta."
            )
        return cls(merge, propedit)

    def probe(self, path) -> list:
        rc, out, err = _run([self.mkvmerge, "-J", str(path)])
        if rc == 2 or not out.strip():
            raise MkvToolError((err or out).strip() or "mkvmerge no pudo leer el archivo")
        try:
            data = json.loads(out)
        except json.JSONDecodeError as exc:
            raise MkvToolError(f"Salida de mkvmerge no válida: {exc}") from exc
        return parse_tracks(data)

    def build_propedit_cmd(self, path, changes) -> list:
        cmd = [self.mkvpropedit, "--output-charset", "utf-8", str(path)]
        for ch in changes:
            sel = f"track:={ch.track.uid}" if ch.track.uid is not None else f"track:s{ch.track.index}"
            cmd += ["--edit", sel, "--set", f"flag-default={1 if ch.new_default else 0}"]
        return cmd

    def run_propedit(self, cmd) -> None:
        rc, out, err = _run(cmd)
        if rc == 2:
            raise MkvToolError((err or out).strip() or "mkvpropedit falló")

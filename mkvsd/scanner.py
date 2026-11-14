"""Búsqueda de archivos MKV y análisis de cada uno."""
from __future__ import annotations

import os
from pathlib import Path

from .models import Decision, FileAnalysis, Status
from .selector import decide


def find_mkv_files(root, recursive: bool = True) -> list:
    root = Path(root)
    found = []
    if recursive:
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                if f.lower().endswith(".mkv"):
                    found.append(Path(dirpath) / f)
    else:
        found = [p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".mkv"]
    return sorted(found, key=lambda p: str(p).lower())


def analyze_file(tools, path, clear_other_defaults: bool = False, decider=decide) -> FileAnalysis:
    analysis = FileAnalysis(path=Path(path))
    try:
        analysis.tracks = tools.probe(path)
    except Exception as exc:  # MkvToolError, OSError...
        analysis.error = str(exc)
        analysis.decision = Decision(Status.ERROR, str(exc))
        return analysis
    analysis.decision = decider(analysis.tracks, clear_other_defaults)
    return analysis

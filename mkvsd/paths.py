"""Rutas de datos de la aplicación (registro e historial de cambios)."""
from __future__ import annotations

import os
from pathlib import Path


def app_data_dir() -> Path:
    override = os.environ.get("MKVSD_DATA_DIR")
    if override:
        base = Path(override)
    elif os.environ.get("APPDATA"):
        base = Path(os.environ["APPDATA"]) / "MKVSpanishDefaultManager"
    else:
        base = Path.home() / ".local" / "share" / "MKVSpanishDefaultManager"
    base.mkdir(parents=True, exist_ok=True)
    return base

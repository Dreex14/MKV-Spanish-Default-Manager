"""Historial de cambios reales (JSON Lines) con los valores anteriores, por si hay que revertir."""
from __future__ import annotations

import json
import threading
from datetime import datetime

from .paths import app_data_dir

_lock = threading.Lock()


def journal_path():
    return app_data_dir() / "journal.jsonl"


def write_entry(path, changes) -> None:
    entry = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "file": str(path),
        "changes": [
            {
                "track_uid": c.track.uid,
                "subtitle_index": c.track.index,
                "name": c.track.name,
                "old_default": c.track.default,
                "new_default": c.new_default,
            }
            for c in changes
        ],
    }
    with _lock, open(journal_path(), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

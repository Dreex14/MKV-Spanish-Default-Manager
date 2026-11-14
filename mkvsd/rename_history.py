"""Historial de renombrados (JSON Lines) y deshacer del último renombrado.

Es un archivo aparte (`rename_history.jsonl`): no interfiere con el `journal.jsonl` de subtítulos.
Cada renombrado se guarda como una entrada {"type": "rename", ...}. Al deshacer se añade un registro
{"type": "undo", ...} con lo revertido, de modo que el archivo solo crece y nunca se reescribe.
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .paths import app_data_dir
from .renamer import RenameOutcome, apply_renames

_lock = threading.Lock()
_enabled = True          # «No guardar historial»: la interfaz lo desactiva según los ajustes


def history_path() -> Path:
    return app_data_dir() / "rename_history.jsonl"


def set_enabled(enabled: bool) -> None:
    """Activa o desactiva el guardado de nuevos renombrados (lo ya guardado no se toca)."""
    global _enabled
    _enabled = bool(enabled)


def is_enabled() -> bool:
    return _enabled


def clear_history() -> int:
    """Borra el historial entero. Devuelve cuántas operaciones había. Después ya no se puede deshacer nada."""
    count = len(load_history())
    with _lock:
        history_path().unlink(missing_ok=True)
    return count


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _append(record: dict) -> None:
    with _lock, open(history_path(), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def record_rename(outcomes, folder: str = "", mode: str = "rename") -> Optional[str]:
    """Guarda los renombrados que sí se hicieron. Devuelve el id de la entrada (o None si no hubo ninguno)."""
    done = [o for o in outcomes if o.ok]
    if not done or not _enabled:
        return None
    entry_id = uuid.uuid4().hex[:12]
    _append({
        "type": "rename", "id": entry_id, "time": _now(), "mode": mode, "folder": str(folder),
        "renames": [{"old": str(o.old), "new": str(o.new)} for o in done],
    })
    return entry_id


@dataclass
class HistoryEntry:
    id: str
    time: str
    mode: str
    folder: str
    renames: list                       # [{"old":..., "new":...}] originales
    pending: list = field(default_factory=list)   # los que aún se pueden deshacer

    @property
    def fully_undone(self) -> bool:
        return not self.pending


def load_history() -> list:
    """Entradas en orden cronológico, con lo que queda pendiente de deshacer en cada una."""
    path = history_path()
    if not path.is_file():
        return []
    entries, by_id = [], {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue                     # línea dañada: se ignora, el resto sigue siendo válido
            if rec.get("type") == "rename":
                e = HistoryEntry(rec["id"], rec.get("time", ""), rec.get("mode", "rename"),
                                 rec.get("folder", ""), rec.get("renames", []), list(rec.get("renames", [])))
                entries.append(e)
                by_id[e.id] = e
            elif rec.get("type") == "undo" and rec.get("id") in by_id:
                gone = {(r["old"], r["new"]) for r in rec.get("reverted", [])}
                e = by_id[rec["id"]]
                e.pending = [r for r in e.pending if (r["old"], r["new"]) not in gone]
    return entries


def last_undoable() -> Optional[HistoryEntry]:
    for e in reversed(load_history()):
        if e.pending:
            return e
    return None


@dataclass
class UndoReport:
    entry: Optional[HistoryEntry] = None
    reverted: int = 0
    failed: list = field(default_factory=list)     # [(nombre_actual, motivo)]

    @property
    def nothing_to_undo(self) -> bool:
        return self.entry is None


def undo_last() -> UndoReport:
    """Deshace el último renombrado que tenga cambios pendientes. Nunca sobrescribe nada."""
    entry = last_undoable()
    if entry is None:
        return UndoReport()
    # Se invierte el orden: lo último renombrado es lo primero que se devuelve.
    pairs = [(Path(r["new"]), Path(r["old"])) for r in reversed(entry.pending)]
    outcomes = apply_renames(pairs)
    reverted = [o for o in outcomes if o.ok]
    if reverted:
        _append({
            "type": "undo", "id": entry.id, "time": _now(),
            "reverted": [{"old": str(o.new), "new": str(o.old)} for o in reverted],
        })
    failed = [(o.old.name, o.error) for o in outcomes if not o.ok]
    return UndoReport(entry, len(reverted), failed)

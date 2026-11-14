"""Procesamiento masivo: una carpeta entera (temporada o serie) en una sola operación."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Optional

from .applier import ApplyResult, apply_file
from .models import Status


@dataclass
class BatchSummary:
    found: int = 0                # archivos MKV encontrados
    analyzed: int = 0             # leídos correctamente
    castellano_found: int = 0     # episodios con pista castellana/genérica válida
    modified: int = 0             # modificados (o que se modificarían en simulación)
    already_ok: int = 0           # ya estaban correctos
    without_castellano: int = 0   # sin castellano (sin español o solo latino): no se tocan
    review: int = 0
    errors: int = 0
    dry_run: bool = False
    cancelled: bool = False

    def add(self, res: ApplyResult) -> None:
        if res.analysis.error:
            self.errors += 1
            return
        self.analyzed += 1
        status = res.analysis.decision.status
        if status == Status.TO_CHANGE:
            self.castellano_found += 1
            if res.outcome in ("ok", "simulated"):
                self.modified += 1
            else:
                self.errors += 1
        elif status == Status.ALREADY_OK:
            self.castellano_found += 1
            self.already_ok += 1
        elif status in (Status.NO_SPANISH, Status.ONLY_LATINO):
            self.without_castellano += 1
        elif status == Status.REVIEW:
            self.review += 1

    def rows(self) -> list:
        modified_label = "Episodios que se modificarían" if self.dry_run else "Episodios modificados correctamente"
        return [
            ("Archivos MKV encontrados", self.found),
            ("Archivos analizados", self.analyzed),
            ("Episodios con castellano encontrado", self.castellano_found),
            (modified_label, self.modified),
            ("Ya estaban correctos (sin cambios)", self.already_ok),
            ("Episodios sin castellano", self.without_castellano),
            ("Episodios que necesitan revisión", self.review),
            ("Errores", self.errors),
        ]


def _t(track) -> str:
    return f"#{track.index} «{track.name or 'sin nombre'}»"


def describe_result(res: ApplyResult) -> str:
    """Línea de registro: qué pista se ha seleccionado en el episodio."""
    a, d = res.analysis, res.analysis.decision
    name = a.path.name
    if res.outcome == "error":
        return f"{name}: ERROR — {res.message}"
    if d.status == Status.ALREADY_OK:
        return f"{name}: ya correcto, predeterminada {_t(d.selected)}"
    if d.status == Status.TO_CHANGE:
        sim = res.outcome == "simulated"
        text = f"{name}: castellano → {_t(d.selected)}"
        off = [_t(c.track) for c in d.changes if not c.new_default]
        if off:
            text += (" · se desactiva " if sim else " · desactivada ") + ", ".join(off)
        return text + (" (simulado)" if sim else " (modificado)")
    return f"{name}: {d.message}"


def process_files(tools, files, clear_other: bool = False, dry_run: bool = True,
                  on_result: Optional[Callable] = None,
                  cancelled: Callable[[], bool] = lambda: False,
                  workers: Optional[int] = None) -> BatchSummary:
    files = list(files)
    summary = BatchSummary(found=len(files), dry_run=dry_run)
    workers = workers or (4 if dry_run else 2)

    def work(path):
        return None if cancelled() else apply_file(tools, path, clear_other, dry_run)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, res in enumerate(pool.map(work, files), 1):
            if res is None:
                summary.cancelled = True
                break
            summary.add(res)
            if on_result:
                on_result(res, i, len(files))
    return summary

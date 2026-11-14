"""MODO PROCESAMIENTO COMPLETO: renombrado masivo + selección de subtítulos en un único proceso.

Flujo:
  1. build_full_plan()   -> previsualización: nombres nuevos y pista que se seleccionará en cada MKV.
                            No modifica nada.
  2. execute_full_plan() -> renombra (con historial para deshacer), después analiza de nuevo cada MKV
                            en su ruta final y fija la pista predeterminada. Devuelve un FullReport.

Los dos módulos siguen siendo independientes: este solo los combina.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import rename_history
from .applier import ApplyResult, apply_file
from .models import FileAnalysis, Status
from .renamer import RenamePlan, RenameRules, RStatus, build_plan, execute_plan, list_files, natural_key
from .scanner import analyze_file, find_mkv_files
from .selector_full import PICK_TEXT, Pick, decide_full


@dataclass
class FullEntry:
    path: Path                                  # ruta original
    rename: Optional[object] = None             # RenameItem, o None si el filtro de extensiones no lo incluye
    analysis: Optional[FileAnalysis] = None     # solo los MKV
    is_mkv: bool = False

    @property
    def target_path(self) -> Path:
        if self.rename is not None and self.rename.status == RStatus.CHANGE:
            return self.rename.new_path
        return self.path

    @property
    def pick(self) -> Optional[Pick]:
        if self.analysis is None:
            return None
        if self.analysis.error:
            return Pick.ERROR
        return getattr(self.analysis.decision, "pick", None)


@dataclass
class FullPlan:
    root: str
    entries: list = field(default_factory=list)
    rename_plan: RenamePlan = field(default_factory=RenamePlan)
    clear_other: bool = False
    cancelled: bool = False

    @property
    def mkv_entries(self) -> list:
        return [e for e in self.entries if e.is_mkv]

    def rows(self) -> list:
        """Resumen de lo que ocurrirá al ejecutar."""
        rp = self.rename_plan
        mk = [e for e in self.mkv_entries if e.analysis is not None]
        picks = [e.pick for e in mk]
        to_modify = sum(1 for e in mk if not e.analysis.error and e.analysis.decision.status == Status.TO_CHANGE)
        return [
            ("Archivos que se renombrarán", rp.count(RStatus.CHANGE)),
            ("Archivos sin cambios de nombre", rp.count(RStatus.SAME)),
            ("MKV que se modificarán", to_modify),
            ("Episodios con castellano seleccionado", picks.count(Pick.CASTELLANO)),
            ("Episodios con latino seleccionado por ausencia de castellano", picks.count(Pick.LATINO)),
            ("Episodios con otro idioma seleccionado por ser la única pista", picks.count(Pick.OTHER_SINGLE)),
            ("Episodios sin español y con varios idiomas (se conserva)", picks.count(Pick.KEEP)),
            ("Episodios sin subtítulos", picks.count(Pick.NO_SUBS)),
            ("Archivos que necesitan revisión", len(self.review_items())),
            ("Errores", picks.count(Pick.ERROR)),
        ]

    def review_items(self) -> list:
        out = []
        for e in self.entries:
            if e.rename is not None and e.rename.blocked:
                out.append((e.path, "Renombrado: " + (e.rename.message or e.rename.status.value)))
            if e.pick == Pick.REVIEW:
                out.append((e.path, "Subtítulos: " + e.analysis.decision.message))
        return out

    def has_work(self) -> bool:
        """¿Hay algo que hacer? (renombrar o modificar algún MKV)"""
        if self.rename_plan.count(RStatus.CHANGE):
            return True
        return any(e.analysis is not None and not e.analysis.error
                   and e.analysis.decision.status == Status.TO_CHANGE for e in self.mkv_entries)


def build_full_plan(tools, root, recursive: bool, rules: RenameRules, extensions,
                    clear_other: bool = False, on_progress: Optional[Callable] = None,
                    cancelled: Callable[[], bool] = lambda: False, workers: int = 4) -> FullPlan:
    """Previsualización completa. No modifica ningún archivo."""
    plan = FullPlan(root=str(root), clear_other=clear_other)
    rename_files = list_files(root, recursive, extensions)
    mkv_files = find_mkv_files(root, recursive)
    plan.rename_plan = build_plan(rename_files, rules)
    by_path = plan.rename_plan.by_path()

    entries = {}
    for p in rename_files:
        entries[str(p)] = FullEntry(p, by_path.get(str(p)), is_mkv=False)
    for p in mkv_files:
        e = entries.setdefault(str(p), FullEntry(p))
        e.is_mkv = True
    plan.entries = sorted(entries.values(), key=lambda e: natural_key(e.path))

    mkvs = plan.mkv_entries
    if on_progress:
        on_progress(0, max(len(mkvs), 1))

    def work(entry):
        if cancelled():
            return None
        return analyze_file(tools, entry.path, clear_other, decide_full)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (entry, analysis) in enumerate(zip(mkvs, pool.map(work, mkvs)), 1):
            if analysis is None:
                plan.cancelled = True
                break
            entry.analysis = analysis
            if on_progress:
                on_progress(i, len(mkvs))
    return plan


# ---------------------------------------------------------------------------
# Texto descriptivo (usado por la interfaz y el registro)
# ---------------------------------------------------------------------------
def _t(track) -> str:
    return f"#{track.index} «{track.name or 'sin nombre'}»"


def describe_selection(analysis: Optional[FileAnalysis]) -> str:
    """Qué pista se seleccionará / se seleccionó, en una línea."""
    if analysis is None:
        return ""
    if analysis.error:
        return f"Error: {analysis.error}"
    d = analysis.decision
    pick = getattr(d, "pick", None)
    ok = " (ya era la predeterminada)" if d.status == Status.ALREADY_OK else ""
    if pick == Pick.CASTELLANO:
        return f"Castellano → {_t(d.selected)}{ok}"
    if pick == Pick.LATINO:
        return f"Latino → {_t(d.selected)} (no hay castellano){ok}"
    if pick == Pick.OTHER_SINGLE:
        return f"Otro idioma → {_t(d.selected)} (única pista){ok}"
    if pick == Pick.REVIEW:
        return f"Revisar: {d.message}"
    if pick in PICK_TEXT:
        return PICK_TEXT[pick]
    return d.message


# ---------------------------------------------------------------------------
# Ejecución e informe
# ---------------------------------------------------------------------------
@dataclass
class EntryResult:
    entry: FullEntry
    rename_state: str                    # renamed | same | blocked | error | none
    rename_message: str = ""
    final_path: Optional[Path] = None
    apply: Optional[ApplyResult] = None  # solo MKV

    @property
    def pick(self) -> Optional[Pick]:
        if self.apply is None:
            return None
        if self.apply.outcome == "error":
            return Pick.ERROR
        return getattr(self.apply.analysis.decision, "pick", None)


@dataclass
class FullReport:
    results: list = field(default_factory=list)
    renamed: int = 0
    unchanged_names: int = 0
    mkv_modified: int = 0
    castellano: int = 0
    latino: int = 0
    other_single: int = 0
    keep_multiple: int = 0
    no_subs: int = 0
    review: list = field(default_factory=list)    # [(ruta, motivo)]
    errors: list = field(default_factory=list)    # [(ruta, motivo)]
    cancelled: bool = False
    history_id: Optional[str] = None

    def rows(self) -> list:
        return [
            ("Archivos renombrados", self.renamed),
            ("Archivos sin cambios de nombre", self.unchanged_names),
            ("MKV modificados", self.mkv_modified),
            ("Episodios con castellano seleccionado", self.castellano),
            ("Episodios con latino seleccionado por ausencia de castellano", self.latino),
            ("Episodios con otro idioma seleccionado por ser la única pista", self.other_single),
            ("Episodios sin español y con varios idiomas (se conserva)", self.keep_multiple),
            ("Episodios sin subtítulos", self.no_subs),
            ("Archivos que necesitan revisión", len({str(p) for p, _ in self.review})),
            ("Errores", len({str(p) for p, _ in self.errors})),
        ]

    def summary_text(self) -> str:
        return "\n".join(f"{k}: {v}" for k, v in self.rows())

    def details_text(self) -> str:
        lines = []
        if self.review:
            lines += ["Necesitan revisión:"] + [f"  · {Path(p).name}: {why}" for p, why in self.review]
        if self.errors:
            lines += ([""] if lines else []) + ["Errores:"] + [f"  · {Path(p).name}: {why}" for p, why in self.errors]
        return "\n".join(lines)

    def text(self) -> str:
        parts = [self.summary_text()]
        if self.details_text():
            parts.append(self.details_text())
        if self.cancelled:
            parts.append("La operación se canceló antes de terminar.")
        return "\n\n".join(parts)


def describe_entry_result(r: EntryResult) -> str:
    name = r.entry.path.name
    parts = []
    if r.rename_state == "renamed":
        parts.append(f"renombrado → {r.final_path.name}")
    elif r.rename_state == "blocked":
        parts.append(f"NO renombrado ({r.rename_message})")
    elif r.rename_state == "error":
        parts.append(f"ERROR al renombrar ({r.rename_message})")
    if r.apply is not None:
        if r.apply.outcome == "error":
            parts.append(f"ERROR en subtítulos ({r.apply.message})")
        else:
            verb = " [modificado]" if r.apply.outcome == "ok" else ""
            parts.append(describe_selection(r.apply.analysis) + verb)
    return f"{name}: " + (" · ".join(parts) if parts else "sin cambios")


def execute_full_plan(tools, plan: FullPlan, on_progress: Optional[Callable] = None,
                      on_result: Optional[Callable] = None,
                      cancelled: Callable[[], bool] = lambda: False,
                      workers: int = 2) -> FullReport:
    """Renombra y después fija la pista de subtítulos de cada MKV en su ruta definitiva."""
    report = FullReport()
    to_rename = plan.rename_plan.to_rename
    mkvs = plan.mkv_entries
    total = len(to_rename) + len(mkvs)
    step = 0

    def progress(done_in_phase, offset):
        if on_progress:
            on_progress(offset + done_in_phase, max(total, 1))

    # ---- Fase 1: renombrado ----
    outcomes = {}
    if to_rename:
        results = execute_plan(plan.rename_plan, lambda i, n: progress(i, 0), cancelled)
        outcomes = {str(o.old): o for o in results}
        report.history_id = rename_history.record_rename(results, plan.root, mode="full")
    step = len(to_rename)

    entry_results = {}
    for e in plan.entries:
        item = e.rename
        if item is None:
            state, msg, final = "none", "", e.path
        elif item.status == RStatus.SAME:
            state, msg, final = "same", "", e.path
            report.unchanged_names += 1
        elif item.blocked:
            state, msg, final = "blocked", item.message, e.path
            report.review.append((e.path, "Renombrado: " + (item.message or "bloqueado")))
        else:
            o = outcomes.get(str(e.path))
            if o is not None and o.ok:
                state, msg, final = "renamed", "", o.new
                report.renamed += 1
            else:
                state, msg, final = "error", (o.error if o else "No se ejecutó"), e.path
                report.errors.append((e.path, "Renombrado: " + msg))
        entry_results[str(e.path)] = EntryResult(e, state, msg, final)
        if on_result and not e.is_mkv:      # los archivos que no son MKV ya están terminados
            on_result(entry_results[str(e.path)])

    # ---- Fase 2: subtítulos de cada MKV, ya con su nombre definitivo ----
    def work(entry):
        if cancelled():
            return None
        final = entry_results[str(entry.path)].final_path
        return apply_file(tools, final, plan.clear_other, dry_run=False, decider=decide_full)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (entry, res) in enumerate(zip(mkvs, pool.map(work, mkvs)), 1):
            if res is None:
                report.cancelled = True
                break
            er = entry_results[str(entry.path)]
            er.apply = res
            progress(i, step)
            if on_result:
                on_result(er)
            if res.outcome == "error":
                report.errors.append((er.final_path, "Subtítulos: " + res.message))
                continue
            pick = er.pick
            if res.outcome == "ok":
                report.mkv_modified += 1
            if pick == Pick.CASTELLANO:
                report.castellano += 1
            elif pick == Pick.LATINO:
                report.latino += 1
            elif pick == Pick.OTHER_SINGLE:
                report.other_single += 1
            elif pick == Pick.KEEP:
                report.keep_multiple += 1
            elif pick == Pick.NO_SUBS:
                report.no_subs += 1
            elif pick == Pick.REVIEW:
                report.review.append((er.final_path, "Subtítulos: " + res.message))

    report.results = [entry_results[str(e.path)] for e in plan.entries]
    return report

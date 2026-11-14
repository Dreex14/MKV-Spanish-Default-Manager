"""Aplicación de los cambios (o simulación) sobre un archivo."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

from . import journal
from .models import FileAnalysis, Status
from .mkvtools import MkvToolError
from .scanner import analyze_file
from .selector import decide


@dataclass
class ApplyResult:
    outcome: str   # ok | simulated | unchanged | review | skipped | error
    message: str
    analysis: FileAnalysis
    command: list = field(default_factory=list)


def apply_file(tools, path, clear_other_defaults: bool = False, dry_run: bool = True,
               decider=decide) -> ApplyResult:
    # Se vuelve a analizar justo antes de modificar para no actuar con datos obsoletos.
    analysis = analyze_file(tools, path, clear_other_defaults, decider)
    d = analysis.decision
    if analysis.error:
        return ApplyResult("error", analysis.error, analysis)
    if d.status == Status.ALREADY_OK:
        return ApplyResult("unchanged", d.message, analysis)
    if d.status == Status.REVIEW:
        return ApplyResult("review", d.message, analysis)
    if d.status != Status.TO_CHANGE:
        return ApplyResult("skipped", d.message, analysis)

    cmd = tools.build_propedit_cmd(path, d.changes)
    if dry_run:
        return ApplyResult("simulated", "Simulación: " + subprocess.list2cmdline(cmd), analysis, cmd)

    try:
        tools.run_propedit(cmd)
        after = {t.index: t for t in tools.probe(path)}
        for ch in d.changes:
            if after[ch.track.index].default != ch.new_default:
                raise MkvToolError(f"Verificación fallida en la pista #{ch.track.index}")
    except (MkvToolError, KeyError, OSError) as exc:
        return ApplyResult("error", str(exc), analysis, cmd)
    try:
        journal.write_entry(path, d.changes)
    except OSError:
        pass
    return ApplyResult("ok", d.message, analysis, cmd)

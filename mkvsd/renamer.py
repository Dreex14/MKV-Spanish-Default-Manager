"""Renombrado masivo: reglas, plan de renombrado (previsualización) y ejecución segura.

Principios de seguridad:
  * Las reglas solo se aplican al nombre SIN la extensión: la extensión nunca se toca.
  * Nunca se sobrescribe un archivo: los conflictos se detectan al planificar y se vuelven a
    comprobar justo antes de cada renombrado.
  * Los renombrados encadenados o cruzados (a->b, b->c, o intercambios) se hacen en dos fases
    con nombres temporales, así que no se pierde ni se pisa ningún archivo.
"""
from __future__ import annotations

import os
import re
import stat
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Optional

INVALID_CHARS = frozenset('<>:"/\\|?*')
RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
MAX_NAME_LEN = 255
DUPLICATE_CHARS_RE = re.compile(r"([ .\-_,;()\[\]{}&+])\1+")
EMPTY_BRACKETS_RE = re.compile(r"\[\s*\]|\(\s*\)|\{\s*\}")
EDGE_SEPARATORS = " .-_,;"
TMP_PREFIX = ".mkvsd_tmp_"


# ---------------------------------------------------------------------------
# Reglas
# ---------------------------------------------------------------------------
@dataclass
class RenameRules:
    removals: list = field(default_factory=list)       # textos o patrones a eliminar
    replacements: list = field(default_factory=list)   # pares (buscar, reemplazar)
    use_regex: bool = False                            # removals y replacements como regex
    case_sensitive: bool = False
    collapse_spaces: bool = True                       # espacios dobles y en los extremos
    collapse_duplicates: bool = True                   # .. -- __ ,, ((  ))  etc.
    remove_empty_brackets: bool = True                 # [] () {} que quedan vacíos
    trim_edge_separators: bool = True                  # - _ . , sueltos al inicio o al final
    prefix: str = ""
    suffix: str = ""

    # --- validación ---
    def validate(self) -> Optional[str]:
        """Devuelve un mensaje de error si alguna regex no es válida (o None)."""
        if not self.use_regex:
            return None
        flags = 0 if self.case_sensitive else re.IGNORECASE
        for pat in self.removals:
            if pat == "":
                continue
            try:
                re.compile(pat, flags)
            except re.error as exc:
                return f"Expresión regular no válida «{pat}»: {exc}"
        for find, repl in self.replacements:
            if find == "":
                continue
            try:
                rx = re.compile(find, flags)
                rx.sub(repl, "")           # detecta referencias de grupo inexistentes (\3)
            except (re.error, IndexError) as exc:
                return f"Expresión regular no válida «{find}»: {exc}"
        return None

    def is_noop(self) -> bool:
        return not (
            any(r != "" for r in self.removals)
            or any(f != "" for f, _ in self.replacements)
            or self.collapse_spaces or self.collapse_duplicates
            or self.remove_empty_brackets or self.trim_edge_separators
            or self.prefix or self.suffix
        )

    # --- aplicación ---
    def _sub(self, text: str, find: str, repl: str) -> str:
        flags = 0 if self.case_sensitive else re.IGNORECASE
        if self.use_regex:
            return re.sub(find, repl, text, flags=flags)
        # Texto literal: el reemplazo también es literal (sin interpretar barras invertidas)
        return re.sub(re.escape(find), lambda _m: repl, text, flags=flags)

    def apply(self, stem: str) -> str:
        """Aplica todas las reglas al nombre sin extensión. Orden: eliminar, sustituir, limpiar, prefijo/sufijo."""
        s = stem
        for pat in self.removals:
            if pat != "":
                s = self._sub(s, pat, "")
        for find, repl in self.replacements:
            if find != "":
                s = self._sub(s, find, repl)
        if self.remove_empty_brackets:
            prev = None
            while prev != s:                       # "[ ( ) ]" -> "[ ]" -> ""
                prev = s
                s = EMPTY_BRACKETS_RE.sub("", s)
        if self.collapse_spaces:
            s = re.sub(r"\s+", " ", s).strip()
        if self.collapse_duplicates:
            s = DUPLICATE_CHARS_RE.sub(r"\1", s)
        if self.collapse_spaces:
            s = re.sub(r"\s+", " ", s).strip()
        if self.trim_edge_separators:
            s = s.strip(EDGE_SEPARATORS)
        return f"{self.prefix}{s}{self.suffix}"

    def describe(self) -> str:
        parts = []
        rem = [r for r in self.removals if r != ""]
        if rem:
            parts.append("eliminar " + ", ".join(f"«{r}»" for r in rem))
        rep = [(f, r) for f, r in self.replacements if f != ""]
        if rep:
            parts.append("sustituir " + ", ".join(f"«{f}»→«{r}»" for f, r in rep))
        if (rem or rep) and self.use_regex:
            parts.append("con expresiones regulares")
        cleanup = []
        if self.collapse_spaces:
            cleanup.append("espacios sobrantes")
        if self.collapse_duplicates:
            cleanup.append("caracteres duplicados")
        if self.remove_empty_brackets:
            cleanup.append("corchetes vacíos")
        if self.trim_edge_separators:
            cleanup.append("separadores en los extremos")
        if cleanup:
            parts.append("limpiar " + ", ".join(cleanup))
        if self.prefix:
            parts.append(f"prefijo «{self.prefix}»")
        if self.suffix:
            parts.append(f"sufijo «{self.suffix}»")
        return "; ".join(parts) if parts else "sin reglas activas"


def split_name(name: str):
    """Separa nombre y extensión (la extensión incluye el punto). '.oculto' no tiene extensión."""
    stem, ext = os.path.splitext(name)
    return stem, ext


def name_problem(name: str) -> Optional[str]:
    """Motivo por el que un nombre de archivo no sería válido en Windows (o None)."""
    stem, _ext = split_name(name)
    if not stem.strip() or name.startswith("."):
        return "El nombre quedaría vacío (o empezaría por punto)"
    bad = sorted({c for c in name if c in INVALID_CHARS or ord(c) < 32})
    if bad:
        shown = " ".join(c if ord(c) >= 32 else "?" for c in bad)
        return f"Contiene caracteres no permitidos: {shown}"
    if name.endswith((" ", ".")):
        return "No puede terminar en espacio o punto"
    if stem.split(".")[0].strip().lower() in RESERVED_NAMES:
        return "Nombre reservado de Windows"
    if len(name) > MAX_NAME_LEN:
        return f"Nombre demasiado largo ({len(name)} caracteres)"
    return None


# ---------------------------------------------------------------------------
# Extensiones y listado de archivos
# ---------------------------------------------------------------------------
def parse_extensions(text: str, extra: Iterable = ()) -> Optional[frozenset]:
    """'mkv, .MP4 srt' -> frozenset({'.mkv', '.mp4', '.srt'}). Sin extensiones -> frozenset() (nada)."""
    exts = set()
    for raw in list(extra) + re.split(r"[,\s;]+", text or ""):
        raw = raw.strip().lower().lstrip("*")
        if not raw:
            continue
        exts.add(raw if raw.startswith(".") else "." + raw)
    return frozenset(exts)


def _is_hidden(path: str, name: str) -> bool:
    if name.startswith("."):
        return True
    mask = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0) | getattr(stat, "FILE_ATTRIBUTE_SYSTEM", 0)
    if not mask:          # no es Windows
        return False
    try:
        return bool(getattr(os.stat(path), "st_file_attributes", 0) & mask)
    except OSError:
        return False


def natural_key(path) -> list:
    """Orden natural: E2 antes que E10."""
    parts = re.split(r"(\d+)", str(path).lower())
    return [int(p) if p.isdigit() else p for p in parts]


def list_files(root, recursive: bool = True, extensions: Optional[frozenset] = None) -> list:
    """Archivos de la carpeta. extensions=None -> todos. Se omiten los archivos ocultos/de sistema."""
    root = Path(root)
    found = []

    def accept(dirpath, name):
        full = os.path.join(dirpath, name)
        if _is_hidden(full, name):
            return False
        if extensions is not None and os.path.splitext(name)[1].lower() not in extensions:
            return False
        return os.path.isfile(full)

    if recursive:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            found.extend(Path(dirpath) / f for f in files if accept(dirpath, f))
    else:
        found = [root / f for f in os.listdir(root) if accept(str(root), f)]
    return sorted(found, key=natural_key)


# ---------------------------------------------------------------------------
# Plan (previsualización)
# ---------------------------------------------------------------------------
class RStatus(str, Enum):
    CHANGE = "change"                  # se renombrará
    SAME = "same"                      # el nombre no cambia
    CONFLICT_DUP = "conflict_dup"      # varios archivos acabarían con el mismo nombre
    CONFLICT_EXISTS = "conflict_exists"  # ya existe otro archivo con ese nombre
    INVALID = "invalid"                # nombre no válido o regla errónea


@dataclass
class RenameItem:
    path: Path
    new_name: str
    status: RStatus
    message: str = ""

    @property
    def new_path(self) -> Path:
        return self.path.with_name(self.new_name)

    @property
    def blocked(self) -> bool:
        return self.status in (RStatus.CONFLICT_DUP, RStatus.CONFLICT_EXISTS, RStatus.INVALID)


@dataclass
class RenamePlan:
    items: list = field(default_factory=list)

    def count(self, *statuses) -> int:
        return sum(1 for i in self.items if i.status in statuses)

    @property
    def to_rename(self) -> list:
        return [i for i in self.items if i.status == RStatus.CHANGE]

    @property
    def blocked(self) -> list:
        return [i for i in self.items if i.blocked]

    def by_path(self) -> dict:
        return {str(i.path): i for i in self.items}


def _ci(name: str) -> str:
    return name.casefold()


def build_plan(files, rules: RenameRules) -> RenamePlan:
    """Calcula el nombre nuevo de cada archivo y detecta duplicados y colisiones con archivos existentes."""
    items = []
    for p in files:
        p = Path(p)
        stem, ext = split_name(p.name)
        try:
            new_stem = rules.apply(stem)
        except (re.error, IndexError) as exc:
            items.append(RenameItem(p, p.name, RStatus.INVALID, f"Regla no válida: {exc}"))
            continue
        new_name = new_stem + ext
        if not new_stem.strip():          # ".mkv" no tiene "extensión" para splitext: se comprueba aquí
            items.append(RenameItem(p, new_name, RStatus.INVALID, "El nombre quedaría vacío"))
            continue
        if new_name == p.name:
            items.append(RenameItem(p, new_name, RStatus.SAME))
            continue
        problem = name_problem(new_name)
        if problem:
            items.append(RenameItem(p, new_name, RStatus.INVALID, problem))
        else:
            items.append(RenameItem(p, new_name, RStatus.CHANGE))

    existing = {}   # carpeta -> nombres existentes (sin distinguir mayúsculas, como Windows)
    for it in items:
        d = str(it.path.parent)
        if d not in existing:
            try:
                existing[d] = {_ci(n) for n in os.listdir(d)}
            except OSError:
                existing[d] = {_ci(i.path.name) for i in items if str(i.path.parent) == d}

    # Se repite hasta estabilizar: un archivo bloqueado ya no libera su nombre antiguo.
    changed = True
    while changed:
        changed = False
        cands = [i for i in items if i.status == RStatus.CHANGE]
        groups = defaultdict(list)
        for it in cands:
            groups[(str(it.path.parent), _ci(it.new_name))].append(it)
        for group in groups.values():
            if len(group) > 1:
                for it in group:
                    others = [o.path.name for o in group if o is not it]
                    it.status = RStatus.CONFLICT_DUP
                    it.message = "Mismo nombre nuevo que: " + ", ".join(others[:2]) + ("…" if len(others) > 2 else "")
                changed = True
        vacating = {(str(i.path.parent), _ci(i.path.name)) for i in items if i.status == RStatus.CHANGE}
        for it in [i for i in items if i.status == RStatus.CHANGE]:
            key = (str(it.path.parent), _ci(it.new_name))
            if _ci(it.new_name) in existing[key[0]] and key not in vacating:
                it.status = RStatus.CONFLICT_EXISTS
                it.message = "Ya existe un archivo con ese nombre: no se sobrescribe"
                changed = True
    return RenamePlan(items)


# ---------------------------------------------------------------------------
# Ejecución segura
# ---------------------------------------------------------------------------
@dataclass
class RenameOutcome:
    old: Path
    new: Path
    ok: bool
    error: str = ""


def _safe_move(src: Path, dst: Path) -> None:
    """Renombra sin sobrescribir jamás (en POSIX os.rename pisaría el destino, así que se comprueba antes).

    Excepción: un cambio solo de mayúsculas (a.mkv -> A.mkv) en un sistema que no distingue mayúsculas
    (Windows) ve el "destino" como existente, pero es el mismo archivo, así que se permite.
    """
    if not os.path.lexists(src):
        raise FileNotFoundError(f"No existe el archivo de origen: {src.name}")
    if os.path.lexists(dst):
        case_only = (src.parent == dst.parent and src.name != dst.name
                     and src.name.casefold() == dst.name.casefold() and os.path.samefile(src, dst))
        if not case_only:
            raise FileExistsError(f"Ya existe «{dst.name}»")
    os.rename(src, dst)


def apply_renames(pairs, on_progress: Optional[Callable] = None,
                  cancelled: Callable[[], bool] = lambda: False) -> list:
    """Renombra una lista de pares (origen, destino) de forma segura.

    Los pares cuyo destino es el nombre actual de otro archivo que también se renombra (cadenas,
    intercambios) pasan por un nombre temporal. Cada archivo es
    independiente: si uno falla se restaura y se sigue con el resto. Devuelve un RenameOutcome por par.
    """
    pairs = [(Path(s), Path(d)) for s, d in pairs]
    outcomes = {}
    old_keys = {(str(s.parent), _ci(s.name)) for s, _d in pairs}
    direct, via_tmp = [], []
    for s, d in pairs:
        target = (str(d.parent), _ci(d.name))
        if target in old_keys and target != (str(s.parent), _ci(s.name)):   # no cuenta su propio nombre
            via_tmp.append((s, d))
        else:
            direct.append((s, d))

    total = len(pairs)
    done = 0

    def tick():
        nonlocal done
        done += 1
        if on_progress:
            on_progress(done, total)

    staged = []
    for s, d in via_tmp:                                   # fase 1: a nombre temporal
        tmp = s.with_name(f"{TMP_PREFIX}{uuid.uuid4().hex}{s.suffix}")
        try:
            _safe_move(s, tmp)
            staged.append((s, tmp, d))
        except OSError as exc:
            outcomes[(s, d)] = RenameOutcome(s, d, False, str(exc))
            tick()
    for s, d in direct:                                    # fase 2: renombrados directos
        if cancelled():
            outcomes[(s, d)] = RenameOutcome(s, d, False, "Cancelado")
            tick()
            continue
        try:
            _safe_move(s, d)
            outcomes[(s, d)] = RenameOutcome(s, d, True)
        except OSError as exc:
            outcomes[(s, d)] = RenameOutcome(s, d, False, str(exc))
        tick()
    for s, tmp, d in staged:                               # fase 3: del temporal al nombre final
        try:
            _safe_move(tmp, d)
            outcomes[(s, d)] = RenameOutcome(s, d, True)
        except OSError as exc:
            try:                                           # se devuelve al nombre original
                _safe_move(tmp, s)
                msg = str(exc)
            except OSError as exc2:
                msg = f"{exc}. ATENCIÓN: el archivo quedó como «{tmp.name}» ({exc2})"
            outcomes[(s, d)] = RenameOutcome(s, d, False, msg)
        tick()
    return [outcomes[(s, d)] for s, d in pairs]


def execute_plan(plan: RenamePlan, on_progress: Optional[Callable] = None,
                 cancelled: Callable[[], bool] = lambda: False) -> list:
    """Ejecuta solo los elementos CHANGE del plan (los bloqueados nunca se tocan)."""
    return apply_renames([(i.path, i.new_path) for i in plan.to_rename], on_progress, cancelled)

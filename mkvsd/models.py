"""Modelos de datos compartidos por el núcleo y la interfaz."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class Category(str, Enum):
    CASTELLANO = "castellano"   # indicado explícitamente como castellano / es-ES
    GENERICO = "generico"       # ESP / Español / Spanish sin región (se trata como castellano)
    LATINO = "latino"
    AMBIGUO = "ambiguo"         # evidencias contradictorias en el propio nombre
    OTRO = "otro"               # no es español


class Status(str, Enum):
    TO_CHANGE = "to_change"
    ALREADY_OK = "already_ok"
    NO_SPANISH = "no_spanish"
    ONLY_LATINO = "only_latino"
    REVIEW = "review"
    ERROR = "error"


@dataclass
class SubtitleTrack:
    id: int                      # id de pista de mkvmerge (0-based, todas las pistas)
    index: int                   # posición 1-based entre las pistas de subtítulos
    uid: Optional[int]
    name: str
    language: str
    ietf: str
    codec: str
    default: bool
    forced: bool                 # indicador "forced" del contenedor
    category: Category = Category.OTRO
    is_forced: bool = False      # indicador forced O nombre tipo "Forzados"
    is_commentary: bool = False
    is_sdh: bool = False
    notes: list = field(default_factory=list)


@dataclass
class TrackChange:
    track: SubtitleTrack
    new_default: bool
    reason: str


@dataclass
class Decision:
    status: Status
    message: str
    selected: Optional[SubtitleTrack] = None
    changes: list = field(default_factory=list)


@dataclass
class FileAnalysis:
    path: Path
    tracks: list = field(default_factory=list)
    decision: Optional[Decision] = None
    error: str = ""

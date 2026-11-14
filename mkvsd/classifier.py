"""Clasificación de pistas de subtítulos basada en nombre y metadatos (nunca en el contenido).

Prioridad de evidencias:
  1. Nombre de la pista (ESP LAT, Castellano, Español (México)...).
  2. Etiqueta IETF (es-419, es-MX -> latino; es-ES -> castellano).
  3. Código de idioma (spa) -> español genérico.
Español genérico (ESP, Español, Spanish) se trata como castellano salvo indicios latinos.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .models import Category, SubtitleTrack

LATAM_REGIONS = frozenset({
    "419", "mx", "ar", "cl", "co", "pe", "ve", "uy", "ec", "bo", "py",
    "cr", "pa", "gt", "hn", "ni", "sv", "do", "cu", "pr", "us",
})

SPANISH_TOKENS = frozenset({
    "esp", "espanol", "spa", "spanish", "es",
    "castellano", "castilian", "cast", "castilla", "espana", "spain",
})

LATINO_TOKENS = frozenset({
    "lat", "latino", "latina", "latam", "latinoamerica", "latinoamericano",
    "latinoamericana", "hispanoamerica", "hispanoamericano", "hispanoamericana",
    "mexico", "mexicano", "mexicana", "mexican", "mex",
    "argentina", "argentino", "colombia", "colombiano", "chile", "chileno",
    "peru", "peruano", "venezuela", "uruguay",
})

CASTELLANO_TOKENS = frozenset({"castellano", "castilian", "cast", "castilla", "espana", "spain"})
# Solo cuentan como castellano si el nombre ya es claramente español ("European Spanish")
CASTELLANO_NEEDS_SPANISH = frozenset({"european", "europeo", "iberico", "iberian", "peninsular"})
AMERICA_TOKENS = frozenset({"america", "american", "americano", "americana"})

OTHER_LANGUAGE_TOKENS = frozenset({
    "english", "ingles", "eng", "french", "frances", "fre", "german", "aleman", "ger",
    "italian", "italiano", "ita", "portuguese", "portugues", "catalan", "catala",
    "galician", "gallego", "galego", "basque", "euskera", "euskara", "japanese",
    "japones", "jpn", "chinese", "korean", "russian", "arabic", "dutch", "polish",
})

FORCED_TOKENS = frozenset({"forced", "forzado", "forzados", "forzada", "forzadas", "forzosos"})
SDH_TOKENS = frozenset({"sdh", "cc", "hoh"})

_REGION_RE = re.compile(r"(?<![a-z0-9])(?:es|spa)[-_](419|[a-z]{2})(?![a-z0-9])")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


@dataclass
class _NameEvidence:
    spanish: bool
    latino: bool
    castellano: bool
    other_language: bool


def _name_evidence(name: str) -> _NameEvidence:
    s = _normalize(name)
    tokens = set(re.findall(r"[a-z0-9]+", s))

    reg_lat = reg_cast = False
    for m in _REGION_RE.finditer(s):
        region = m.group(1)
        if region == "es":
            reg_cast = True
        elif region in LATAM_REGIONS:
            reg_lat = True

    spanish_tok = bool(tokens & SPANISH_TOKENS)
    latino = reg_lat or bool(tokens & LATINO_TOKENS)
    # "Latin" suelto podría ser el idioma latín: solo cuenta junto a "America" o a un token español
    if "latin" in tokens and (spanish_tok or tokens & AMERICA_TOKENS):
        latino = True
    castellano = reg_cast or bool(tokens & CASTELLANO_TOKENS)
    if (spanish_tok or latino) and tokens & CASTELLANO_NEEDS_SPANISH:
        castellano = True

    return _NameEvidence(
        spanish=spanish_tok or latino or castellano,
        latino=latino,
        castellano=castellano,
        other_language=bool(tokens & OTHER_LANGUAGE_TOKENS),
    )


def _ietf_info(ietf: str):
    """Devuelve (es_español, indica_latino, indica_castellano) a partir de la etiqueta IETF."""
    parts = re.split(r"[-_]", (ietf or "").lower())
    if not parts or parts[0] not in ("es", "spa"):
        return False, False, False
    rest = parts[1:]
    return True, any(p in LATAM_REGIONS for p in rest), "es" in rest


def _flags(name: str, forced_flag: bool):
    s = _normalize(name)
    tokens = set(re.findall(r"[a-z0-9]+", s))
    forced = forced_flag or bool(tokens & FORCED_TOKENS)
    commentary = "comment" in s or "comentari" in s
    sdh = bool(tokens & SDH_TOKENS) or "hearing" in s or "sordos" in s
    return forced, commentary, sdh


def classify_track(track: SubtitleTrack) -> SubtitleTrack:
    """Rellena categoría, indicadores y notas de la pista (modifica y devuelve la misma)."""
    ev = _name_evidence(track.name)
    ietf_spanish, ietf_lat, ietf_cast = _ietf_info(track.ietf)
    lang_spanish = (track.language or "").lower() in ("spa", "es")
    meta_spanish = lang_spanish or ietf_spanish
    notes = []

    track.is_forced, track.is_commentary, track.is_sdh = _flags(track.name, track.forced)

    if not (ev.spanish or meta_spanish):
        category = Category.OTRO
    elif not ev.spanish and ev.other_language and track.name.strip():
        category = Category.AMBIGUO
        notes.append("El idioma indica español pero el nombre indica otro idioma")
    elif ev.latino and ev.castellano:
        category = Category.AMBIGUO
        notes.append("El nombre menciona a la vez latino y castellano")
    elif ev.latino:
        category = Category.LATINO
        if ietf_cast and not ietf_lat:
            notes.append("El nombre dice latino pero IETF dice es-ES: prevalece el nombre")
    elif ev.castellano:
        category = Category.CASTELLANO
        if ietf_lat and not ietf_cast:
            notes.append("El nombre dice castellano pero IETF indica Latinoamérica: prevalece el nombre")
    elif ietf_lat and not ietf_cast:
        category = Category.LATINO
        notes.append("Latino indicado por la etiqueta IETF")
    elif ietf_cast and not ietf_lat:
        category = Category.CASTELLANO
        notes.append("Castellano indicado por la etiqueta IETF")
    else:
        category = Category.GENERICO

    track.category = category
    track.notes = notes
    return track


def describe(track: SubtitleTrack) -> str:
    base = {
        Category.CASTELLANO: "Castellano",
        Category.GENERICO: "Español genérico (castellano)",
        Category.LATINO: "Latino",
        Category.AMBIGUO: "Ambiguo",
        Category.OTRO: "Otro idioma",
    }[track.category]
    tags = []
    if track.is_forced:
        tags.append("forzada")
    if track.is_commentary:
        tags.append("comentarios")
    if track.is_sdh:
        tags.append("SDH")
    return base + (" (" + ", ".join(tags) + ")" if tags else "")

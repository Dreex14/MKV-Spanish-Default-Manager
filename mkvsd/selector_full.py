"""Reglas de selección del MODO PROCESAMIENTO COMPLETO.

Amplía `selector.decide` (que no se modifica) con las reglas de respaldo:

  1. Castellano explícito o español genérico (ESP / Español / Spanish)  -> misma decisión que el gestor de subtítulos.
  2. Si no hay ninguna pista castellana válida pero sí latina              -> la latina (nunca si hay castellana).
  3. Sin ninguna pista española y una única pista candidata de otro idioma -> esa pista.
  4. Sin ninguna pista española y varias de otros idiomas                  -> se conserva la configuración original.
  5. Sin subtítulos                                                        -> no se toca nada.

Los subtítulos forzados y de comentarios no cuentan como candidatos de la selección principal,
salvo que sean la única pista del archivo (regla de pista única).
Si hay pistas ambiguas, empates sin resolver o solo castellano/latino forzado junto a otras pistas,
el archivo se marca para revisión y no se modifica.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import Category, Decision, Status, TrackChange
from .selector import decide


class Pick(str, Enum):
    CASTELLANO = "castellano"        # castellano o español genérico
    LATINO = "latino"                # latino por ausencia de castellano
    OTHER_SINGLE = "otro_unico"      # otro idioma por ser la única pista
    KEEP = "conservar"               # varias pistas de otros idiomas: se conserva lo que había
    NO_SUBS = "sin_subtitulos"
    REVIEW = "revision"
    ERROR = "error"


PICK_TEXT = {
    Pick.CASTELLANO: "Castellano",
    Pick.LATINO: "Latino (no hay castellano)",
    Pick.OTHER_SINGLE: "Otro idioma (única pista)",
    Pick.KEEP: "Varios idiomas sin español: se conserva",
    Pick.NO_SUBS: "Sin subtítulos",
    Pick.REVIEW: "Revisar",
    Pick.ERROR: "Error",
}


@dataclass
class FullDecision(Decision):
    pick: Pick = Pick.KEEP


def _label(track) -> str:
    return f"#{track.index} «{track.name or 'sin nombre'}»"


def _select(chosen, tracks, peers, clear_other, pick, why) -> FullDecision:
    changes = []
    if not chosen.default:
        changes.append(TrackChange(chosen, True, why))
    for t in tracks:
        if t is chosen or not t.default:
            continue
        if t in peers:
            changes.append(TrackChange(t, False, "Otra pista española: solo puede haber una predeterminada"))
        elif clear_other:
            changes.append(TrackChange(t, False, "Opción activada: se quita la predeterminada al resto"))
    if changes:
        return FullDecision(Status.TO_CHANGE, f"Predeterminada: {_label(chosen)}", chosen, changes, pick)
    return FullDecision(Status.ALREADY_OK, f"Ya correcto: {_label(chosen)} es la predeterminada", chosen, [], pick)


def _single_track(tracks, clear_other) -> FullDecision:
    """El archivo tiene una única pista de subtítulos: se selecciona, sea del tipo que sea."""
    t = tracks[0]
    if t.category in (Category.CASTELLANO, Category.GENERICO):
        pick = Pick.CASTELLANO
    elif t.category == Category.LATINO:
        pick = Pick.LATINO
    else:
        pick = Pick.OTHER_SINGLE
    return _select(t, tracks, [], clear_other, pick, "Única pista de subtítulos del archivo")


def decide_full(tracks, clear_other_defaults: bool = False) -> FullDecision:
    if not tracks:
        return FullDecision(Status.NO_SPANISH, "Sin subtítulos: no se modifica nada.", pick=Pick.NO_SUBS)

    base = decide(tracks, clear_other_defaults)

    # 1) Castellano / español genérico
    if base.status in (Status.TO_CHANGE, Status.ALREADY_OK):
        return FullDecision(base.status, base.message, base.selected, base.changes, Pick.CASTELLANO)

    # Casos dudosos: con una única pista no hay nada que decidir; con varias, se revisan a mano.
    if base.status == Status.REVIEW:
        if len(tracks) == 1:
            return _single_track(tracks, clear_other_defaults)
        return FullDecision(Status.REVIEW, base.message, pick=Pick.REVIEW)

    # 2) Solo latino
    if base.status == Status.ONLY_LATINO:
        latinos = [t for t in tracks if t.category == Category.LATINO and not t.is_commentary]
        full = [t for t in latinos if not t.is_forced]
        if not full:
            if len(tracks) == 1:
                return _single_track(tracks, clear_other_defaults)
            return FullDecision(Status.REVIEW, "Solo hay subtítulos latinos forzados; no hay una pista completa.",
                                pick=Pick.REVIEW)
        best_key = min(1 if t.is_sdh else 0 for t in full)
        best = [t for t in full if (1 if t.is_sdh else 0) == best_key]
        if len(best) > 1:
            defaults = [t for t in best if t.default]
            if len(defaults) != 1:
                return FullDecision(Status.REVIEW, "Hay varias pistas latinas equivalentes y no se puede elegir con seguridad.",
                                    pick=Pick.REVIEW)
            best = defaults
        return _select(best[0], tracks, latinos, clear_other_defaults, Pick.LATINO,
                       "No hay castellano: se elige la pista latina")

    # 3-4) Ninguna pista española válida
    candidates = [t for t in tracks if not t.is_forced and not t.is_commentary]
    if len(candidates) == 1:
        return _select(candidates[0], tracks, [], clear_other_defaults, Pick.OTHER_SINGLE,
                       "Única pista de subtítulos disponible")
    if not candidates and len(tracks) == 1:
        return _single_track(tracks, clear_other_defaults)
    return FullDecision(Status.NO_SPANISH,
                        "Sin pistas españolas y con varias de otros idiomas: se conserva la configuración original.",
                        pick=Pick.KEEP)

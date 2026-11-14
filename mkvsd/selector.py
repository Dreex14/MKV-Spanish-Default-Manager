"""Lógica de decisión: qué pista de subtítulos debe quedar como predeterminada.

Orden de prioridad:
  1. Castellano explícito.
  2. Español genérico (ESP / Español / Spanish).
  3. Latino, solo si no hay ninguna pista castellana o genérica válida (en ese caso no se toca nada).
Una pista "válida" es completa: los comentarios se descartan y las forzadas nunca se eligen solas.
"""
from __future__ import annotations

from .models import Category, Decision, Status, TrackChange


def _rank(track):
    return (0 if track.category == Category.CASTELLANO else 1, 1 if track.is_sdh else 0)


def _label(track):
    return f"#{track.index} «{track.name or 'sin nombre'}»"


def decide(tracks, clear_other_defaults: bool = False) -> Decision:
    if not any(t.category != Category.OTRO for t in tracks):
        return Decision(Status.NO_SPANISH, "No hay subtítulos en español: no se modifica nada.")

    usable = [t for t in tracks if not t.is_commentary]
    ambiguous = [t for t in usable if t.category == Category.AMBIGUO]
    pool = [t for t in usable if t.category in (Category.CASTELLANO, Category.GENERICO)]
    latinos = [t for t in usable if t.category == Category.LATINO]

    if not pool:
        if ambiguous:
            return Decision(Status.REVIEW, "Hay pistas con nombre ambiguo y ninguna castellana clara.")
        if latinos:
            return Decision(Status.ONLY_LATINO, "Solo hay subtítulos latinos: se mantienen como están.")
        return Decision(Status.NO_SPANISH, "Los únicos subtítulos en español son comentarios: no se modifica nada.")

    full = [t for t in pool if not t.is_forced]
    if not full:
        return Decision(Status.REVIEW, "Solo hay subtítulos castellanos forzados; no hay una pista completa.")

    best_key = min(_rank(t) for t in full)
    best = [t for t in full if _rank(t) == best_key]
    if len(best) > 1:
        defaults = [t for t in best if t.default]
        if len(defaults) != 1:
            return Decision(Status.REVIEW, "Hay varias pistas castellanas equivalentes y no se puede elegir con seguridad.")
        best = defaults
    chosen = best[0]

    if ambiguous and chosen.category != Category.CASTELLANO:
        return Decision(Status.REVIEW, "Hay una pista ambigua que podría ser castellano explícito.")

    full_ids = {t.index for t in full}
    changes = []
    if not chosen.default:
        changes.append(TrackChange(chosen, True, "Pista castellana elegida como predeterminada"))
    for t in tracks:
        if t is chosen or not t.default:
            continue
        if t.category == Category.LATINO and not t.is_commentary:
            changes.append(TrackChange(t, False, "Pista latina: se quita como predeterminada"))
        elif t.index in full_ids:
            changes.append(TrackChange(t, False, "Otra pista española completa: solo puede haber una predeterminada"))
        elif clear_other_defaults:
            changes.append(TrackChange(t, False, "Opción activada: se quita la predeterminada al resto"))

    if changes:
        msg = f"Predeterminada: {_label(chosen)}"
    else:
        msg = f"Ya correcto: {_label(chosen)} es la predeterminada"
    return Decision(Status.TO_CHANGE if changes else Status.ALREADY_OK, msg, chosen, changes)

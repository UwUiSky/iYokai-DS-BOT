"""
core/music_capitoli_player.py
=============================
Video lunghi (MUS-017): le voci della coda che vengono da un elenco di brani con orari sono lo stesso video, con un
inizio e una fine in `extras`. Il player le fa partire dal punto giusto (`start`) e le ferma all'orario del brano
dopo (`end`) con le funzioni di Lavalink: il video non si scarica e non si taglia. Posizione e `seek` sono
relativi al brano, cosi' barra di avanzamento, `vai-a` e `ricomincia` non cambiano.
Funzioni coperte: SPEC §9 (catalogo MUS-017)
Dipende da: core/music_capitoli_logic.py
"""

from __future__ import annotations

import copy
import time

import wavelink

from core.music_capitoli_logic import Voce

CHIAVE_INIZIO = "capitolo_inizio_ms"
CHIAVE_FINE = "capitolo_fine_ms"


def limiti_del_brano(traccia) -> tuple[int, int] | None:
    """(inizio, fine) in millisecondi del video, se la traccia e' una voce di un elenco; altrimenti None."""
    extras = getattr(traccia, "extras", None)
    inizio, fine = getattr(extras, CHIAVE_INIZIO, None), getattr(extras, CHIAVE_FINE, None)
    ok = lambda v: isinstance(v, int) and not isinstance(v, bool) and v >= 0  # noqa: E731
    return (inizio, fine) if ok(inizio) and ok(fine) and fine > inizio else None


def brani_da_voci(video, voci: list[Voce], richiedente: int) -> list[wavelink.Playable]:
    """Una traccia per voce: lo stesso video (stesso `encoded`), titolo della voce, durata della voce."""
    brani = []
    for voce in voci:
        dati = copy.deepcopy(video.raw_data)
        dati["info"]["title"] = voce.titolo
        dati["info"]["length"] = voce.fine_ms - voce.inizio_ms
        brano = wavelink.Playable(dati)
        brano.extras = {
            "requester_id": richiedente, CHIAVE_INIZIO: voce.inizio_ms, CHIAVE_FINE: voce.fine_ms,
        }
        brani.append(brano)
    return brani


class PlayerCapitoli(wavelink.Player):
    """Un `wavelink.Player` che capisce le voci di un elenco (stessa cosa per ogni altra traccia)."""

    async def play(self, track, *, start: int = 0, end: int | None = None, **opzioni):
        limiti = limiti_del_brano(track)
        if limiti is not None:
            inizio, fine = limiti
            start = min(inizio + max(0, start), fine)
            end = fine if end is None else min(inizio + end, fine)
        return await super().play(track, start=start, end=end, **opzioni)

    @property
    def position(self) -> int:
        limiti = limiti_del_brano(self.current)
        if limiti is None:
            return super().position
        if self.current is None or not self.playing or not self.connected or self._last_update is None:
            return 0
        assoluta = self._last_position
        if not self.paused:
            assoluta += int((time.monotonic_ns() - self._last_update) / 1_000_000)
        return max(0, min(assoluta - limiti[0], self.current.length))

    async def seek(self, position: int = 0, /) -> None:
        limiti = limiti_del_brano(self.current)
        if limiti is not None:
            position = min(limiti[0] + max(0, position), limiti[1])
        await super().seek(position)

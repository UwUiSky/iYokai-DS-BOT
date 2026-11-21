"""
core/music_dj_logic.py
======================
Chi può comandare la musica (ruolo DJ e modalità DJ, MUS-051) e il voto per saltare (MUS-052).
Funzioni pure, provabili senza Discord: il cog legge utente e canale e chiama qui.
Funzioni coperte: SPEC §9 (catalogo MUS-051, MUS-052)
Dipende da: core/music_settings_logic.py (MusicSettings)
"""

from __future__ import annotations

import math
import time
from collections.abc import Iterable
from dataclasses import dataclass, field

VOTO_SALTO_DEFAULT = 50  # percentuale degli ascoltatori umani
SCADENZA_VOTI_SECONDI = 600  # un voto non resta valido all'infinito


def e_privilegiato(
    settings, utente_id: int, ruoli_ids: Iterable[int], e_staff: bool, ascoltatori_umani: Iterable[int]
) -> bool:
    """Vero per un DJ (ruolo scelto dal server), lo staff, o chi è da solo nel canale con il bot."""
    if e_staff:
        return True
    if settings.dj_role_id is not None and settings.dj_role_id in set(ruoli_ids):
        return True
    umani = set(ascoltatori_umani)
    return umani == {utente_id}


def puo_comandare(
    settings, utente_id: int, ruoli_ids: Iterable[int], e_staff: bool, ascoltatori_umani: Iterable[int]
) -> bool:
    """MUS-051: con la modalità DJ spenta tutti; accesa, solo i privilegiati."""
    if not settings.dj_mode:
        return True
    return e_privilegiato(settings, utente_id, ruoli_ids, e_staff, ascoltatori_umani)


def puo_toccare_brano(privilegiato: bool, richiedente_id: int | None, utente_id: int) -> bool:
    """MUS-024/028: togliere o spostare. Gli altri solo i brani che hanno messo loro."""
    return privilegiato or (richiedente_id is not None and richiedente_id == utente_id)


def voti_necessari(percentuale: int, ascoltatori: int) -> int:
    """Quanti voti servono per saltare: la percentuale degli ascoltatori, arrotondata in su, mai meno di 1."""
    percentuale = max(1, min(100, int(percentuale)))
    return max(1, math.ceil(ascoltatori * percentuale / 100))


@dataclass
class EsitoVoto:
    gia_votato: bool
    voti: int
    necessari: int

    @property
    def raggiunto(self) -> bool:
        return self.voti >= self.necessari


@dataclass
class VotiSalto:
    """I voti per saltare il brano in corso di un canale. Uno per persona, solo di chi è nel canale."""

    chiave_brano: object = None
    votanti: set[int] = field(default_factory=set)
    iniziato: float = 0.0

    def vota(
        self, chiave_brano: object, utente_id: int, ascoltatori_umani: Iterable[int], percentuale: int,
        adesso: float | None = None,
    ) -> EsitoVoto:
        adesso = time.monotonic() if adesso is None else adesso
        if chiave_brano != self.chiave_brano or adesso - self.iniziato > SCADENZA_VOTI_SECONDI:
            self.chiave_brano, self.votanti, self.iniziato = chiave_brano, set(), adesso
        presenti = set(ascoltatori_umani)
        self.votanti &= presenti  # chi è uscito dal canale non conta più
        necessari = voti_necessari(percentuale, len(presenti))
        if utente_id not in presenti:
            return EsitoVoto(False, len(self.votanti), necessari)
        gia = utente_id in self.votanti
        self.votanti.add(utente_id)
        return EsitoVoto(gia, len(self.votanti), necessari)

    def azzera(self) -> None:
        self.chiave_brano, self.votanti, self.iniziato = None, set(), 0.0


def parse_posizione(testo: str, corrente_ms: int, durata_ms: int) -> int | None:
    """MUS-034: «1:30», «1:02:03», «90» (secondi), «+30», «-0:15». Restituisce i millisecondi, o None se non valido.

    Con + o - il punto è relativo alla posizione corrente. Il risultato resta tra 0 e la durata meno un secondo.
    """
    pulito = (testo or "").strip()
    if not pulito or len(pulito) > 12:
        return None
    segno = 0
    if pulito[0] in "+-":
        segno = 1 if pulito[0] == "+" else -1
        pulito = pulito[1:].strip()
    parti = pulito.split(":")
    if not 1 <= len(parti) <= 3 or not all(p.isascii() and p.isdigit() and len(p) <= 4 for p in parti):
        return None
    numeri = [int(p) for p in parti]
    if len(numeri) > 1 and any(n >= 60 for n in numeri[1:]):
        return None
    secondi = 0
    for n in numeri:
        secondi = secondi * 60 + n
    ms = secondi * 1000
    if segno:
        ms = corrente_ms + segno * ms
    massimo = max(0, durata_ms - 1000) if durata_ms > 0 else ms
    return max(0, min(ms, massimo))

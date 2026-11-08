"""
core/account_rubato_logic.py
============================
Riconosce un account probabilmente rubato (D67), in logica pura: immagini malevole, oppure lo stesso messaggio
(o lo stesso inoltro) in 3 canali diversi, anche di server diversi, in 2 minuti. Tiene in memoria, con tetto,
gli ultimi invii di ogni persona; non conta mai il bot stesso (il chiamante scarta bot e webhook).
Funzioni coperte: SPEC §6.20 (D67, #153)
"""

from __future__ import annotations

import hashlib
import re
from collections import deque
from dataclasses import dataclass, field

from core.bounded_cache import BoundedCache

FINESTRA_S = 120
MIN_CANALI_UGUALI = 3
MIN_CARATTERI = 12  # sotto, un messaggio uguale non dice nulla («ok», «ciao»)
MAX_INVII_PER_PERSONA = 60
MAX_PERSONE = 20_000
TIMEOUT_MALEVOLE_S = 86_400
TIMEOUT_UGUALI_S = 3_600

MOTIVO_MALEVOLE = "malevole"
MOTIVO_UGUALI = "uguali"

_SPAZI = re.compile(r"\s+")


@dataclass(frozen=True)
class Sintesi:
    """Cosa è successo finora per una persona: serve all'avviso unico per lo staff."""

    user_id: int
    invii: int
    canali: int
    server: int
    guild_ids: tuple[int, ...]
    motivi: tuple[str, ...]
    messaggi: tuple[tuple[int, int, int], ...]  # (server, canale, messaggio) contati e non ancora passati: da cancellare
    prima_volta: bool  # True solo alla prima segnalazione: da lì in poi l'avviso si aggiorna

    @property
    def malevole(self) -> bool:
        return MOTIVO_MALEVOLE in self.motivi

    @property
    def timeout_secondi(self) -> int:
        return TIMEOUT_MALEVOLE_S if self.malevole else TIMEOUT_UGUALI_S


def firma_messaggio(testo: str | None, allegati: list[tuple[str, int]] = (), inoltrati: list[str] = ()) -> str | None:
    """
    Impronta del contenuto: testo normalizzato, nomi e misure degli allegati, testo degli inoltri. None se
    non c'è niente di abbastanza specifico (testo breve senza allegati né inoltri).
    """
    parti = [_SPAZI.sub(" ", (testo or "")).strip().casefold()]
    parti += [_SPAZI.sub(" ", i).strip().casefold() for i in inoltrati if i]
    parti += [f"{nome.casefold()}:{misura}" for nome, misura in allegati]
    specifico = bool(allegati) or any(len(p) >= MIN_CARATTERI for p in parti if p)
    if not specifico:
        return None
    return hashlib.sha1("\x1f".join(parti).encode("utf-8", "replace")).hexdigest()


@dataclass
class _Invio:
    ora: float
    guild_id: int
    canale_id: int
    messaggio_id: int
    firma: str
    malevola: bool
    gestito: bool = False  # già passato in una sintesi: non si cancella una seconda volta


@dataclass
class _Persona:
    invii: deque = field(default_factory=lambda: deque(maxlen=MAX_INVII_PER_PERSONA))
    segnalata_fino: float = 0.0
    firme_segnalate: set = field(default_factory=set)


class RegistroInvii:
    """Ultimi invii per persona. Un solo oggetto per processo; i test ne fanno uno nuovo."""

    def __init__(self, finestra_s: int = FINESTRA_S) -> None:
        self._finestra = finestra_s
        self._persone: BoundedCache[int, _Persona] = BoundedCache(MAX_PERSONE)

    def registra(self, user_id: int, guild_id: int, canale_id: int, messaggio_id: int, firma: str, ora: float, *,
                 malevola: bool = False) -> Sintesi | None:
        """Segna l'invio. Restituisce la sintesi se l'account sembra rubato (e a ogni invio dopo), altrimenti None."""
        persona = self._persone.get(user_id)
        if persona is None:
            persona = _Persona()
            self._persone.set(user_id, persona)
        self._pota(persona, ora)
        for gia in persona.invii:
            if gia.messaggio_id == messaggio_id:  # lo stesso messaggio visto da due filtri
                gia.malevola = gia.malevola or malevola
                break
        else:
            persona.invii.append(_Invio(ora, guild_id, canale_id, messaggio_id, firma, malevola))
        return self._sintesi(user_id, persona, ora)

    def _pota(self, persona: _Persona, ora: float) -> None:
        while persona.invii and ora - persona.invii[0].ora > self._finestra:
            persona.invii.popleft()

    def _sintesi(self, user_id: int, persona: _Persona, ora: float) -> Sintesi | None:
        if ora >= persona.segnalata_fino:
            persona.firme_segnalate.clear()
        malevoli = [i for i in persona.invii if i.malevola]
        per_firma: dict[str, list[_Invio]] = {}
        for i in persona.invii:
            per_firma.setdefault(i.firma, []).append(i)
        uguali = [g for f, g in per_firma.items() if len({i.canale_id for i in g}) >= MIN_CANALI_UGUALI or f in persona.firme_segnalate]
        if not malevoli and not uguali:
            return None
        gia = ora < persona.segnalata_fino
        contati = malevoli + [i for g in uguali for i in g if not i.malevola]
        for gruppo in uguali:
            persona.firme_segnalate.add(gruppo[0].firma)
        nuovi = [i for i in contati if not i.gestito]
        for i in nuovi:
            i.gestito = True
        motivi = tuple(m for m, presente in ((MOTIVO_MALEVOLE, bool(malevoli)), (MOTIVO_UGUALI, bool(uguali))) if presente)
        persona.segnalata_fino = ora + self._finestra
        return Sintesi(
            user_id=user_id,
            invii=len(contati),
            canali=len({i.canale_id for i in contati}),
            server=len({i.guild_id for i in contati}),
            guild_ids=tuple(sorted({i.guild_id for i in contati})),
            motivi=motivi,
            messaggi=tuple((i.guild_id, i.canale_id, i.messaggio_id) for i in nuovi),
            prima_volta=not gia,
        )

"""
core/guild_clan_boost_logic.py
===================================
Boost XP/Coin acquistabili (SPEC.md §15.14, D23) — logica pura,
nessun DB/Discord qui. Tre tipi: `exp` (×2 ai punti esperienza),
`coin` (×2 alle coin) e `super` (tutti e due). Durata 24h, nessuna
somma delle durate: un boost si compra solo se nessuno dei suoi
benefici è già attivo. Il boost
INDIVIDUALE (comprato dal saldo PERSONALE, si applica SOLO al
proprio tick vocale di gilda — resta scoped al Sistema Gilde/Clan,
NON al leveling generale del server) sia per il boost DI GILDA
(comprato dalla TESORERIA del clan, si applica al tick di TUTTI i
membri). I due si moltiplicano tra loro se entrambi attivi nello
stesso istante — non c'è motivo di escluderli a vicenda, hanno fonti
e portata diverse (uno paga per sé, l'altro per tutta la gilda).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

BOOST_MULTIPLIER = 2
BOOST_DURATION_HOURS = 24


class Beneficio(str, Enum):
    EXP = "exp"
    COIN = "coin"


class TipoBoost(str, Enum):
    EXP = "exp"
    COIN = "coin"
    SUPER = "super"

    @property
    def benefici(self) -> tuple[Beneficio, ...]:
        if self is TipoBoost.SUPER:
            return (Beneficio.EXP, Beneficio.COIN)
        return (Beneficio(self.value),)


INDIVIDUAL_BOOST_COSTS: dict[TipoBoost, int] = {
    TipoBoost.EXP: 6_000,
    TipoBoost.COIN: 6_000,
    TipoBoost.SUPER: 10_000,
}
GUILD_BOOST_COSTS: dict[TipoBoost, int] = {
    TipoBoost.EXP: 60_000,
    TipoBoost.COIN: 60_000,
    TipoBoost.SUPER: 100_000,
}


def is_boost_active(expires_at: datetime | None, now: datetime) -> bool:
    """Vero se un beneficio è ancora attivo a `now` — None o una
    scadenza già passata significa non attivo."""
    if expires_at is None:
        return False
    return expires_at > now


def benefici_attivi(
    scad_exp: datetime | None, scad_coin: datetime | None, now: datetime
) -> dict[Beneficio, datetime]:
    """I benefici attivi a `now` con la loro scadenza."""
    attivi: dict[Beneficio, datetime] = {}
    if scad_exp is not None and is_boost_active(scad_exp, now):
        attivi[Beneficio.EXP] = scad_exp
    if scad_coin is not None and is_boost_active(scad_coin, now):
        attivi[Beneficio.COIN] = scad_coin
    return attivi


def tipi_acquistabili(
    scad_exp: datetime | None, scad_coin: datetime | None, now: datetime
) -> list[TipoBoost]:
    """I tipi comprabili ora: solo quelli i cui benefici sono tutti
    spenti (D23)."""
    attivi = benefici_attivi(scad_exp, scad_coin, now)
    return [t for t in TipoBoost if not any(b in attivi for b in t.benefici)]


def nuove_scadenze(tipo: TipoBoost, now: datetime) -> dict[Beneficio, datetime]:
    """Scadenza di ciascun beneficio del tipo comprato: sempre
    now + durata (niente somma con un boost precedente)."""
    scadenza = now + timedelta(hours=BOOST_DURATION_HOURS)
    return {b: scadenza for b in tipo.benefici}


def compute_boosted_reward(
    xp: int,
    coin: int,
    *,
    individuale_exp: bool = False,
    individuale_coin: bool = False,
    gilda_exp: bool = False,
    gilda_coin: bool = False,
) -> tuple[int, int]:
    """Applica ×BOOST_MULTIPLIER separatamente a xp e coin: una volta
    per ogni boost attivo su quel beneficio (individuale e di gilda si
    moltiplicano tra loro) alla ricompensa già calcolata di un tick."""
    fattore_xp = BOOST_MULTIPLIER ** (int(individuale_exp) + int(gilda_exp))
    fattore_coin = BOOST_MULTIPLIER ** (int(individuale_coin) + int(gilda_coin))
    return xp * fattore_xp, coin * fattore_coin


class StatoBoost(str, Enum):
    ACQUISTATO = "acquistato"
    NON_ABBASTANZA_FONDI = "non_abbastanza_fondi"
    GIA_ATTIVO = "gia_attivo"
    NON_MEMBRO = "non_membro"  # il membro non è (più) in questa gilda
    ASSENTE = "assente"  # la gilda non esiste (più) in questo server


@dataclass(frozen=True)
class EsitoBoost:
    """Esito di un acquisto. `scadenza` solo se ACQUISTATO; `attivi`
    (beneficio -> fino a quando) solo se GIA_ATTIVO."""

    stato: StatoBoost
    scadenza: datetime | None = None
    attivi: tuple[tuple[Beneficio, datetime], ...] = ()

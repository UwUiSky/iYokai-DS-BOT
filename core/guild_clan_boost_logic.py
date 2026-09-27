"""
core/guild_clan_boost_logic.py
===================================
Boost XP/Coin acquistabili (SPEC.md §15.14) — logica pura, nessun
DB/Discord qui. Numeri confermati con l'utente prima di scrivere
questo file: moltiplicatore ×2 per 24h, sia per il boost
INDIVIDUALE (comprato dal saldo PERSONALE, si applica SOLO al
proprio tick vocale di gilda — resta scoped al Sistema Gilde/Clan,
NON al leveling generale del server) sia per il boost DI GILDA
(comprato dalla TESORERIA del clan, si applica al tick di TUTTI i
membri). I due si moltiplicano tra loro se entrambi attivi nello
stesso istante — non c'è motivo di escluderli a vicenda, hanno fonti
e portata diverse (uno paga per sé, l'altro per tutta la gilda).
"""

from __future__ import annotations

from datetime import datetime, timedelta

BOOST_MULTIPLIER = 2
BOOST_DURATION_HOURS = 24

INDIVIDUAL_BOOST_COST = 10_000
GUILD_BOOST_COST = 100_000


def is_boost_active(expires_at: datetime | None, now: datetime) -> bool:
    """Vero se un boost (individuale o di gilda) è ancora attivo a
    `now` — None o una scadenza già passata significa non attivo."""
    if expires_at is None:
        return False
    return expires_at > now


def compute_boosted_reward(
    xp: int, coin: int, *, individual_active: bool, guild_active: bool
) -> tuple[int, int]:
    """Applica ×BOOST_MULTIPLIER una volta per ciascun boost attivo
    (individuale e di gilda si moltiplicano tra loro se entrambi
    attivi) alla ricompensa già calcolata di un singolo tick."""
    fattore = 1
    if individual_active:
        fattore *= BOOST_MULTIPLIER
    if guild_active:
        fattore *= BOOST_MULTIPLIER
    return xp * fattore, coin * fattore


def extend_boost_expiry(current_expiry: datetime | None, now: datetime) -> datetime:
    """La nuova scadenza dopo l'acquisto di un boost — se uno è già
    attivo, la nuova durata si estende da lì (non da `now`, altrimenti
    si comprerebbe tempo già pagato in precedenza); altrimenti parte
    da `now`. Stesso pattern già usato per l'estensione mensile del
    premium (`GuildPremiumRepository.record_purchase`)."""
    base = current_expiry if (current_expiry is not None and current_expiry > now) else now
    return base + timedelta(hours=BOOST_DURATION_HOURS)

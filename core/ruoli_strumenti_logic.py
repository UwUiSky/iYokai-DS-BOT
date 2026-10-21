"""
core/ruoli_strumenti_logic.py
=============================
Strumenti sui ruoli per lo staff: chi tocca un'operazione di massa, quanto
dura, le date scritte dall'admin, il ripristino dei ruoli a tempo e la
diagnosi di un ruolo che il bot non riesce a dare. Funzioni pure.
Funzioni coperte: SPEC §14 (catalogo #123: RUO-042, 043, 092-109, 113)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Sequence

import discord

# Una richiesta ogni secondo: Discord accetta circa 10 cambi di ruolo ogni
# 10 secondi per server; così resta spazio per il resto del bot.
PAUSA_MASSA_SECONDI = 1.0
# Un'operazione di massa non tocca più di questi membri (un'ora e mezza circa).
MAX_MEMBRI_MASSA = 5000
# Ruoli a tempo: al massimo 30 giorni.
MAX_DURATA_TEMPORANEO = 30 * 86400
# Ruoli che un membro può prendersi da solo (una tendina ne mostra 25).
MAX_RUOLI_SCELTA = 25
# Tetto di Discord sui ruoli di un server.
MAX_RUOLI_SERVER = 250

# Azione dello scheduler che, a fine tempo, rimette i ruoli come prima.
RUOLI_TEMPORANEI_ACTION_TYPE = "ruoli_temporanei"

CHI_TUTTI = "tutti"
CHI_UMANI = "umani"
CHI_BOT = "bot"

AZIONE_DAI = "dai"
AZIONE_TOGLI = "togli"


@dataclass(frozen=True)
class FiltroMassa:
    chi: str = CHI_TUTTI
    con_ruolo: int | None = None
    senza_ruolo: int | None = None
    entrati_dopo: datetime | None = None
    entrati_prima: datetime | None = None


def leggi_data(testo: str | None) -> datetime | None:
    """'AAAA-MM-GG' in una data UTC; None se vuoto. ValueError se scritta male."""
    if testo is None or not testo.strip():
        return None
    try:
        giorno = datetime.strptime(testo.strip(), "%Y-%m-%d")
    except ValueError:
        raise ValueError("La data va scritta come AAAA-MM-GG, per esempio 2026-01-31.") from None
    return giorno.replace(tzinfo=timezone.utc)


def membro_nel_filtro(membro, filtro: FiltroMassa) -> bool:
    """True se il membro rientra nel filtro (chi, ruoli, data di ingresso)."""
    if filtro.chi == CHI_UMANI and membro.bot:
        return False
    if filtro.chi == CHI_BOT and not membro.bot:
        return False
    ruoli = {r.id for r in membro.roles}
    if filtro.con_ruolo is not None and filtro.con_ruolo not in ruoli:
        return False
    if filtro.senza_ruolo is not None and filtro.senza_ruolo in ruoli:
        return False
    entrato = getattr(membro, "joined_at", None)
    if filtro.entrati_dopo is not None and (entrato is None or entrato < filtro.entrati_dopo):
        return False
    if filtro.entrati_prima is not None and (entrato is None or entrato >= filtro.entrati_prima):
        return False
    return True


def membri_da_toccare(membri: Iterable, filtro: FiltroMassa, ruolo_id: int, azione: str) -> list:
    """I membri nel filtro a cui l'azione cambia qualcosa (chi ha già il ruolo non si tocca)."""
    scelti = []
    for membro in membri:
        if not membro_nel_filtro(membro, filtro):
            continue
        ha_ruolo = any(r.id == ruolo_id for r in membro.roles)
        if (azione == AZIONE_DAI) != ha_ruolo:
            scelti.append(membro)
    return scelti


def stima_secondi(quanti: int) -> int:
    """Quanto dura un'operazione di massa su `quanti` membri."""
    return int(quanti * PAUSA_MASSA_SECONDI)


def stima_in_parole(secondi: int) -> str:
    """'circa 3 min' / 'meno di un minuto' / 'circa 1 h 20 min'."""
    if secondi < 60:
        return "meno di un minuto"
    minuti = round(secondi / 60)
    if minuti < 60:
        return f"circa {minuti} min"
    return f"circa {minuti // 60} h {minuti % 60} min"


def ruoli_unici(ruoli: Sequence) -> list:
    """I ruoli passati, senza i None e senza doppioni, nell'ordine dato."""
    visti: dict[int, object] = {}
    for ruolo in ruoli:
        if ruolo is not None and ruolo.id not in visti:
            visti[ruolo.id] = ruolo
    return list(visti.values())


def ripristino(dati: Sequence[int], tolti: Sequence[int], posseduti: set[int]) -> tuple[list[int], list[int]]:
    """
    Alla scadenza di un cambio a tempo: (ruoli da togliere, ruoli da ridare).
    Si toglie solo ciò che il membro ha ancora; si ridà solo ciò che non ha.
    """
    da_togliere = [r for r in dati if r in posseduti]
    da_ridare = [r for r in tolti if r not in posseduti]
    return da_togliere, da_ridare


def ruoli_da_azzerare(ruoli: Iterable, ruolo_bot_piu_alto) -> list:
    """I ruoli che il bot può togliere: niente @everyone, gestiti o sopra il bot."""
    return [r for r in ruoli if not r.is_default() and not r.managed and r < ruolo_bot_piu_alto]


def diagnosi_ruolo(
    ruolo,
    *,
    bot_gestisce_ruoli: bool,
    ruolo_bot_piu_alto,
) -> list[str]:
    """
    Perché il bot non può dare il ruolo. Lista vuota = può darlo.
    """
    problemi: list[str] = []
    if ruolo.is_default():
        problemi.append("È @everyone: ce l'hanno tutti, non si dà.")
        return problemi
    if ruolo.managed:
        problemi.append("È gestito da un'integrazione (un bot, i boost, un abbonamento): solo Discord lo dà.")
    if not bot_gestisce_ruoli:
        problemi.append("Al bot manca il permesso «Gestire i ruoli».")
    if ruolo >= ruolo_bot_piu_alto:
        problemi.append(
            f"È pari o sopra il ruolo più alto del bot ({ruolo_bot_piu_alto.name}): "
            "sposta il ruolo del bot più in alto in Impostazioni server → Ruoli."
        )
    return problemi


def colore_ruolo(testo: str | None) -> discord.Colour | None:
    """'#RRGGBB' in un colore; None se il testo è vuoto. ValueError se scritto male."""
    from core.leveling_logic import colore_valido

    if testo is None or not testo.strip():
        return None
    valore = colore_valido(testo.strip())
    if valore is None:
        raise ValueError("Il colore va scritto come #RRGGBB, per esempio #FF8800.")
    return discord.Colour(int(valore[1:], 16))

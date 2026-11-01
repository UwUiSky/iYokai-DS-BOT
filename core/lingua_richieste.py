"""
core/lingua_richieste.py
========================
Richiesta di una lingua mancante: un utente scrive il nome della lingua (e una nota) e la richiesta
arriva in DM all'owner del bot. Un solo punto per controlli e invio (D16, D58).
Funzioni coperte: SPEC §21 (NF-06, #77).
Il tetto di una richiesta al giorno per utente sta in memoria: si azzera al riavvio del bot.
"""

from __future__ import annotations

import datetime as dt
import logging
from enum import Enum
from typing import Any

import discord

from core.config import config
from core.bounded_cache import BoundedCache
from core.i18n import t

logger = logging.getLogger("iyokai.lingua_richieste")

MAX_NOME_LINGUA = 50
MAX_NOTA = 300
_MAX_UTENTI_IN_MEMORIA = 5000

# user_id -> giorno (UTC) dell'ultima richiesta riuscita
_ultimo_giorno: BoundedCache[int, dt.date] = BoundedCache(_MAX_UTENTI_IN_MEMORIA)


class Esito(Enum):
    INVIATA = "inviata"
    LIMITE = "limite"
    NOME_VUOTO = "nome_vuoto"
    NON_INVIATA = "non_inviata"


def _oggi(adesso: dt.datetime | None) -> dt.date:
    return (adesso or dt.datetime.now(dt.timezone.utc)).date()


def ha_gia_richiesto(user_id: int, adesso: dt.datetime | None = None) -> bool:
    return _ultimo_giorno.get(user_id) == _oggi(adesso)


def pulisci(testo: str | None, massimo: int) -> str:
    """Spazi tolti, a capo ridotti a uno, taglio al massimo; menzioni disinnescate."""
    pulito = " ".join(str(testo or "").split())[:massimo]
    return discord.utils.escape_mentions(pulito)


def messaggio_per_owner(utente: Any, server: Any, nome: str, nota: str) -> str:
    """Il DM per l'owner (in italiano). Sta entro i 2000 caratteri di Discord."""
    dove = f"{getattr(server, 'name', '?')} (`{server.id}`)" if server is not None else "DM"
    righe = [
        t("lingua_richiesta_dm_titolo", "it"),
        t("lingua_richiesta_dm_lingua", "it", lingua=nome),
        t("lingua_richiesta_dm_da", "it", utente=f"{utente} (`{utente.id}`)", dove=dove),
    ]
    if nota:
        righe.append(t("lingua_richiesta_dm_nota", "it", nota=nota))
    return "\n".join(righe)[:2000]


async def invia_richiesta(
    bot: Any, utente: Any, server: Any, nome_grezzo: str | None, nota_grezza: str | None,
    adesso: dt.datetime | None = None,
) -> Esito:
    """
    Controlla, manda il DM all'owner e segna il giorno. Il giorno si segna PRIMA del DM (due moduli
    inviati insieme non passano entrambi) e si toglie se il DM non parte: il tetto si consuma solo se arriva.
    """
    nome = pulisci(nome_grezzo, MAX_NOME_LINGUA)
    if not nome:
        return Esito.NOME_VUOTO
    if ha_gia_richiesto(utente.id, adesso):
        return Esito.LIMITE
    _ultimo_giorno.set(utente.id, _oggi(adesso))
    nota = pulisci(nota_grezza, MAX_NOTA)
    try:
        owner = bot.get_user(config.OWNER_ID) or await bot.fetch_user(config.OWNER_ID)
        await owner.send(
            messaggio_per_owner(utente, server, nome, nota), allowed_mentions=discord.AllowedMentions.none()
        )
    except (discord.HTTPException, AttributeError) as exc:
        logger.warning("Richiesta di lingua non recapitata all'owner (%s).", type(exc).__name__)
        _ultimo_giorno.delete(utente.id)
        return Esito.NON_INVIATA
    return Esito.INVIATA

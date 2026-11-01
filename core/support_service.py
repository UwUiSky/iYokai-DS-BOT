"""
core/support_service.py
=======================
Assistenza di iYokai da qualsiasi server (SPEC §B.9) e segnalazioni alla rete (§B.2): ogni richiesta apre un
thread nel canale dello staff (`SUPPORT_CHANNEL_ID`); le risposte dello staff arrivano all'utente in DM e
l'utente risponde con il comando dell'app. Il client che scrive nel thread è il bot principale (ha il canale).
Funzioni coperte: SPEC §B.9, §B.2 (NF-36, #107)
Dipende da: core/repositories/user_app_repo.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import discord

from core.desktop_eventi import avvisa_utente
from core.repositories.user_app_repo import user_app_repo

logger = logging.getLogger("iyokai.support")

MAX_OGGETTO = 80
MAX_TESTO = 1500
NESSUNA_MENZIONE = discord.AllowedMentions.none()


class SupportoNonAttivo(Exception):
    """Manca `SUPPORT_CHANNEL_ID` o il canale non si raggiunge."""


class TroppeRichieste(Exception):
    """L'utente ha già il massimo di richieste aperte."""


class RichiestaNonTrovata(Exception):
    """Numero inesistente, chiuso o di un'altra persona."""


@dataclass(frozen=True)
class RichiestaAperta:
    numero: int
    thread_id: int


async def _canale_staff(client: discord.Client, canale_id: int):
    if not canale_id:
        raise SupportoNonAttivo()
    canale = client.get_channel(canale_id)
    if canale is None:
        try:
            canale = await client.fetch_channel(canale_id)
        except discord.HTTPException as exc:
            raise SupportoNonAttivo() from exc
    if not isinstance(canale, discord.TextChannel):
        raise SupportoNonAttivo()
    return canale


def titolo_thread(numero: int, oggetto: str) -> str:
    return f"#{numero} {oggetto}"[:100]


async def apri_richiesta(
    client: discord.Client, canale_id: int, user_id: int, nome: str, oggetto: str, testo: str
) -> RichiestaAperta:
    """Salva la richiesta e apre il thread per lo staff. Senza canale non salva nulla."""
    canale = await _canale_staff(client, canale_id)
    numero = await user_app_repo.apri_richiesta(user_id, oggetto[:MAX_OGGETTO], testo[:MAX_TESTO])
    if numero is None:
        raise TroppeRichieste()
    try:
        thread = await canale.create_thread(name=titolo_thread(numero, oggetto), type=discord.ChannelType.public_thread)
        await thread.send(
            f"**Richiesta #{numero}** di {nome[:80]} (ID {user_id})\n**{oggetto[:MAX_OGGETTO]}**\n{testo[:MAX_TESTO]}\n\n"
            "Le risposte scritte qui arrivano all'utente in DM. Chiudi la richiesta archiviando il thread.",
            allowed_mentions=NESSUNA_MENZIONE,
        )
    except discord.HTTPException as exc:
        await user_app_repo.chiudi_richiesta(numero)
        raise SupportoNonAttivo() from exc
    await user_app_repo.imposta_thread_richiesta(numero, thread.id)
    return RichiestaAperta(numero, thread.id)


async def risposta_dell_utente(client: discord.Client, user_id: int, numero: int, testo: str) -> None:
    """Il testo dell'utente nel thread della sua richiesta (solo se è sua e aperta)."""
    riga = await user_app_repo.richiesta(numero)
    if riga is None or riga["user_id"] != user_id or riga["stato"] != "aperta" or not riga["thread_id"]:
        raise RichiestaNonTrovata()
    thread = client.get_channel(riga["thread_id"])
    if thread is None:
        try:
            thread = await client.fetch_channel(riga["thread_id"])
        except discord.HTTPException as exc:
            raise SupportoNonAttivo() from exc
    try:
        await thread.send(f"**Risposta dell'utente:**\n{testo[:MAX_TESTO]}", allowed_mentions=NESSUNA_MENZIONE)
    except discord.HTTPException as exc:
        raise SupportoNonAttivo() from exc


async def inoltra_risposta_staff(client: discord.Client, message: discord.Message) -> bool:
    """Un messaggio dello staff in un thread di assistenza va in DM all'utente. True se l'ha inoltrato."""
    if message.author.bot or not message.content or not isinstance(message.channel, discord.Thread):
        return False
    riga = await user_app_repo.richiesta_da_thread(message.channel.id)
    if riga is None or riga["stato"] != "aperta":
        return False
    await avvisa_utente(riga["user_id"], "assistenza", f"Risposta alla richiesta #{riga['id']}")
    try:
        utente = await client.fetch_user(riga["user_id"])
        await utente.send(
            f"**Assistenza iYokai, richiesta #{riga['id']}:**\n{message.content[:1800]}", allowed_mentions=NESSUNA_MENZIONE
        )
    except discord.HTTPException:
        logger.info("DM per la richiesta %s non consegnato.", riga["id"])
        return False
    return True


async def chiudi_se_archiviato(client: discord.Client, thread: discord.Thread) -> bool:
    """Un thread di assistenza archiviato chiude la richiesta e lo dice all'utente. True se l'ha chiusa."""
    riga = await user_app_repo.richiesta_da_thread(thread.id)
    if riga is None or riga["stato"] != "aperta":
        return False
    await user_app_repo.chiudi_richiesta(riga["id"])
    try:
        utente = await client.fetch_user(riga["user_id"])
        await utente.send(f"La richiesta #{riga['id']} all'assistenza iYokai è stata chiusa.")
    except discord.HTTPException:
        pass
    return True

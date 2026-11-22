"""
core/web_panel_ticket.py
========================
Risposta a un ticket dal sito (TKT-085): elenco dei ticket aperti, scheda con il modulo di risposta e invio nel canale
del ticket. Possono rispondere solo i membri dello staff di quel ticket (come `_membro_staff` dei comandi: «Gestisci
server», oppure un ruolo della squadra del pannello o i ruoli di supporto del server; con «solo admin» solo gli admin dei
ticket), riletti a ogni richiesta. Il messaggio esce dal bot con il nome di chi risponde e «dal sito», con tutte le
menzioni spente. Il testo dei messaggi del ticket non si salva e non si mostra: la pagina scrive soltanto.
Ticket inesistente, di un altro server, chiuso o non tuo da gestire: la stessa pagina «non trovato».
Funzioni coperte: SPEC §24.9 (TKT-085, issue #120)
Dipende da: core/ticket_logic.py, core/repositories/ticket_repo.py, core/repositories/ticket_opzioni_repo.py
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import discord
from aiohttp import web

from core import panel_bridge, web_panel_logic as regole
from core.database import db
from core.ticket_logic import e_admin_ticket, merge_support_role_ids
from core.repositories.ticket_opzioni_repo import ticket_opzioni_repo
from core.repositories.ticket_repo import ticket_repo

logger = logging.getLogger("iyokai.web_panel_ticket")

# Le stesse chiavi di `cogs/tickets/tickets.py` (ruoli di supporto del server).
SETTING_SUPPORT_ROLE = "ticket_support_role_id"
SETTING_SUPPORT_ROLES = "ticket_support_role_ids"
MAX_TESTO = 1500  # il messaggio intero (con il nome) resta sotto i 2000 caratteri di Discord
MAX_NOME = 60
RIGHE_ELENCO = 25
_CONTROLLO = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​-‏‪-‮⁦-⁩]")


def nome_pulito(nome: str) -> str:
    """Il nome di chi risponde, senza markdown, menzioni o caratteri invisibili."""
    pulito = _CONTROLLO.sub("", str(nome or "")).replace("@", "＠").replace("<", "‹").replace(">", "›")
    return discord.utils.escape_markdown(pulito.strip())[:MAX_NOME] or "Staff"


def testo_valido(testo: object) -> str | None:
    """Il testo da inviare, o None se è vuoto o troppo lungo."""
    pulito = _CONTROLLO.sub("", str(testo or "")).strip()
    return pulito if pulito and len(pulito) <= MAX_TESTO else None


def messaggio(nome: str, testo: str) -> str:
    return f"**{nome_pulito(nome)}** (dal sito):\n{testo}"


async def ruoli_staff(guild_id: int, panel_id: int | None) -> list[int]:
    """TKT-044: la squadra del pannello, se ne ha una; altrimenti i ruoli di supporto del server."""
    if panel_id is not None:
        squadra = (await ticket_opzioni_repo.opzioni(panel_id)).ruoli_staff
        if squadra:
            return list(squadra)
    legacy = await db.get_guild_setting(guild_id, SETTING_SUPPORT_ROLE)
    extra = await db.get_guild_setting(guild_id, SETTING_SUPPORT_ROLES, default=[])
    return merge_support_role_ids(legacy, extra)


async def e_staff_del_ticket(guild: discord.Guild, user_id: int, ticket) -> bool:
    """Staff di questo ticket ADESSO; con «solo admin» servono i ruoli admin dei ticket."""
    membro = await panel_bridge.membro_del_server(guild, user_id)
    if not isinstance(membro, discord.Member) or getattr(membro, "bot", False) is True:
        return False
    ruoli = {r.id for r in membro.roles}
    staff = await ruoli_staff(guild.id, ticket.panel_id)
    gestisce = bool(membro.guild_permissions.manage_guild)
    if not (gestisce or ruoli & set(staff)):
        return False
    if ticket.solo_admin:
        return e_admin_ticket(gestisce, ruoli, staff, set(await ticket_repo.ruoli_admin(guild.id)))
    return True


def registra_rotte(app: web.Application, *, bot, pagina, errore, server, scrittura, chiave_utente) -> None:
    limite_risposte = regole.LimiteFrequenza(10, 60)  # per utente: ogni risposta è un messaggio sul server

    def vai(url: str) -> web.Response:
        return web.Response(status=302, headers={"Location": url})

    def non_trovato(request: web.Request) -> web.Response:
        return errore(request, 404, "Ticket non trovato", "Questo ticket non esiste, è chiuso o non puoi rispondere.")

    async def ticket_di(request: web.Request, guild):
        """Il ticket aperto di questo server e il permesso di rispondere; altrimenti None."""
        try:
            numero = int(request.match_info["ticket"])
        except ValueError:
            return None
        ticket = await ticket_repo.get_ticket_by_id(numero) if 0 < numero <= 2**31 - 1 else None
        if ticket is None or ticket.guild_id != guild.id or ticket.status != "open":
            return None
        if not await e_staff_del_ticket(guild, request[chiave_utente], ticket):
            return None
        return ticket

    async def elenco(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        visibili = []
        for t in await ticket_repo.list_open_tickets(guild.id, RIGHE_ELENCO):
            if await e_staff_del_ticket(guild, request[chiave_utente], t):
                visibili.append(t)
        return pagina(request, "ticket_elenco.html", guild=guild, ticket=visibili)

    async def scheda(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        ticket = await ticket_di(request, guild)
        if ticket is None:
            return non_trovato(request)
        return pagina(request, "ticket_scheda.html", guild=guild, t=ticket, massimo=MAX_TESTO)

    async def rispondi(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        ticket = await ticket_di(request, guild)
        if ticket is None:
            return non_trovato(request)
        indietro = f"/server/{guild.id}/ticket/{ticket.id}?esito="
        testo = testo_valido(form.get("testo"))
        if testo is None:
            return vai(indietro + "non_valido")
        if not limite_risposte.consenti(f"tk:{request[chiave_utente]}"):
            return errore(request, 429, "Troppe risposte", "Aspetta un minuto e riprova.")
        canale = guild.get_channel_or_thread(ticket.channel_id)
        membro = await panel_bridge.membro_del_server(guild, request[chiave_utente])
        if canale is None or membro is None:
            return vai(indietro + "ticket_non_inviato")
        try:
            await canale.send(
                content=messaggio(membro.display_name, testo), allowed_mentions=discord.AllowedMentions.none()
            )
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            logger.warning("Risposta dal sito non inviata (server %s, ticket %s).", guild.id, ticket.id)
            return vai(indietro + "ticket_non_inviato")
        if ticket.first_response_at is None:
            await ticket_repo.record_first_response(ticket.channel_id, datetime.now(timezone.utc))
        await ticket_repo.touch_activity(ticket.channel_id, datetime.now(timezone.utc))
        logger.info("Risposta dal sito: utente %s, server %s, ticket %s.", request[chiave_utente], guild.id, ticket.id)
        return vai(indietro + "ticket_inviato")

    base = r"/server/{guild_id:\d{1,20}}/ticket"
    app.router.add_get(base, elenco)
    app.router.add_get(base + r"/{ticket:\d{1,10}}", scheda)
    app.router.add_post(base + r"/{ticket:\d{1,10}}/rispondi", rispondi)

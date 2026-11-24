"""
core/web_panel_ticket.py
========================
Risposta a un ticket dal sito (TKT-085, D127): elenco dei ticket aperti, scheda con il modulo di risposta e invio nel
canale del ticket. Possono rispondere solo i membri dello staff di quel ticket (come `_membro_staff` dei comandi: «Gestisci
server», oppure un ruolo della squadra del pannello o i ruoli di supporto del server; con «solo admin» solo gli admin dei
ticket), riletti a ogni richiesta. Il messaggio esce con un webhook del bot (nome e avatar di chi risponde, «dal sito»; in
forma anonima nome «Staff» e avatar del server, come il modmail), con tutte le menzioni spente; senza il permesso sui
webhook esce come messaggio del bot. Tempo reale: la scheda interroga ogni pochi secondi `.../stato` (JSON con ETag, 304 se
non cambia nulla): stato, chi ha in carico, ultimo messaggio dell'utente. Il testo dei messaggi del ticket non si salva e
non si mostra (D74): la pagina scrive soltanto. Ticket inesistente, di un altro server, chiuso o non tuo da gestire: la
stessa pagina «non trovato».
Funzioni coperte: SPEC §24.9 (TKT-085, issue #120), §24.14 (D127)
Dipende da: core/ticket_logic.py, core/repositories/ticket_repo.py, core/repositories/ticket_opzioni_repo.py
"""

from __future__ import annotations

import hashlib
import json
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
NOME_WEBHOOK = "iYokai Ticket"
NOME_ANONIMO = "Staff"
MAX_USERNAME_WEBHOOK = 80
MAX_WEBHOOK_IN_MEMORIA = 500
_webhook_per_canale: dict[int, discord.Webhook] = {}  # solo in memoria: il token del webhook non si salva
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


def nome_webhook(nome: str, anonimo: bool) -> str:
    """Il nome con cui esce il webhook: «Staff» se anonimo; altrimenti il nome pulito e «dal sito»."""
    if anonimo:
        return NOME_ANONIMO
    return f"{nome_pulito(nome)} (dal sito)"[:MAX_USERNAME_WEBHOOK]


def corpo_stato(ticket, nome_staff: str | None) -> dict:
    """Quello che la pagina aggiorna in tempo reale. Mai il testo dei messaggi (D74)."""
    def quando(t):
        return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if t is not None else None

    return {
        "stato": "open" if ticket.status == "open" else "closed",
        "presa_da": nome_pulito(nome_staff) if nome_staff else None,
        "utente_scritto": quando(ticket.utente_scritto_at),
        "attivita": quando(ticket.last_activity_at),
        "prima_risposta": ticket.first_response_at is not None,
    }


def etag_di(corpo: dict) -> str:
    return '"' + hashlib.sha256(json.dumps(corpo, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24] + '"'


async def webhook_del_ticket(canale, bot_user_id: int) -> discord.Webhook | None:
    """Il webhook del bot per il canale (o per il canale padre di un thread); si crea se manca. None se non si può."""
    base = canale.parent if isinstance(canale, discord.Thread) else canale
    if base is None:
        return None
    me = canale.guild.me
    if me is None or not base.permissions_for(me).manage_webhooks:
        return None
    noto = _webhook_per_canale.get(base.id)
    if noto is not None:
        return noto
    try:
        for w in await base.webhooks():  # solo quelli creati da noi e con il token (gli altri non si usano)
            if w.token and w.user is not None and w.user.id == bot_user_id and w.name == NOME_WEBHOOK:
                nuovo = w
                break
        else:
            nuovo = await base.create_webhook(name=NOME_WEBHOOK, reason="Risposte dal sito ai ticket")
    except discord.HTTPException:
        return None
    if len(_webhook_per_canale) >= MAX_WEBHOOK_IN_MEMORIA:
        _webhook_per_canale.clear()
    _webhook_per_canale[base.id] = nuovo
    return nuovo


async def invia_risposta(guild, canale, membro, testo: str, anonimo: bool, bot_user_id: int) -> str:
    """Manda la risposta nel canale del ticket. «webhook» o «messaggio»; solleva `discord.HTTPException` se non parte."""
    senza_menzioni = discord.AllowedMentions.none()
    for _ in range(2):
        webhook = await webhook_del_ticket(canale, bot_user_id)
        if webhook is None:
            break
        avatar = (guild.icon.url if guild.icon else None) if anonimo else membro.display_avatar.url
        extra = {"thread": canale} if isinstance(canale, discord.Thread) else {}
        try:
            await webhook.send(
                testo, username=nome_webhook(membro.display_name, anonimo), avatar_url=avatar,
                allowed_mentions=senza_menzioni, **extra,
            )
            return "webhook"
        except discord.NotFound:  # webhook cancellato da qualcuno: se ne cerca o crea un altro
            _webhook_per_canale.pop((canale.parent if isinstance(canale, discord.Thread) else canale).id, None)
        except discord.HTTPException as errore:
            if errore.status == 400:  # nome non accettato da Discord: ripiega sul messaggio del bot
                break
            raise
    contenuto = f"**{NOME_ANONIMO}** (dal sito):\n{testo}" if anonimo else messaggio(membro.display_name, testo)
    await canale.send(content=contenuto, allowed_mentions=senza_menzioni)
    return "messaggio"


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
    limite_stato = regole.LimiteFrequenza(40, 60)  # per utente: la pagina aperta chiede ogni 5-30 secondi

    def vai(url: str) -> web.Response:
        return web.Response(status=302, headers={"Location": url})

    def non_trovato(request: web.Request) -> web.Response:
        return errore(request, 404, "Ticket non trovato", "Questo ticket non esiste, è chiuso o non puoi rispondere.")

    async def ticket_di(request: web.Request, guild, anche_chiuso: bool = False):
        """Il ticket aperto di questo server e il permesso di rispondere; altrimenti None."""
        try:
            numero = int(request.match_info["ticket"])
        except ValueError:
            return None
        ticket = await ticket_repo.get_ticket_by_id(numero) if 0 < numero <= 2**31 - 1 else None
        if ticket is None or ticket.guild_id != guild.id or (ticket.status != "open" and not anche_chiuso):
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

    async def stato(request: web.Request) -> web.StreamResponse:
        """Tempo reale: JSON piccolo con ETag. 304 se non è cambiato niente. Non esiste e non puoi: la stessa 404."""
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        if not limite_stato.consenti(f"st:{request[chiave_utente]}"):
            return web.Response(status=429, text="Troppe richieste.", headers={"Retry-After": "30"})
        ticket = await ticket_di(request, guild, anche_chiuso=True)
        if ticket is None:
            return web.json_response({"stato": "assente"}, status=404)
        presa = guild.get_member(ticket.claimed_by) if ticket.claimed_by else None
        corpo = corpo_stato(ticket, presa.display_name if presa else None)
        etag = etag_di(corpo)
        if request.headers.get("If-None-Match") == etag:
            return web.Response(status=304, headers={"ETag": etag})
        return web.json_response(corpo, headers={"ETag": etag})

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
        anonimo = str(form.get("anonimo", "")) in ("1", "on", "si")
        try:
            come = await invia_risposta(guild, canale, membro, testo, anonimo, bot.user.id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            logger.warning("Risposta dal sito non inviata (server %s, ticket %s).", guild.id, ticket.id)
            return vai(indietro + "ticket_non_inviato")
        if ticket.first_response_at is None:
            await ticket_repo.record_first_response(ticket.channel_id, datetime.now(timezone.utc))
        await ticket_repo.touch_activity(ticket.channel_id, datetime.now(timezone.utc))
        # Anche la risposta anonima ha un autore nei log del bot: lo staff del server può chiederlo a chi gestisce il bot.
        logger.info("Risposta dal sito (%s%s): utente %s, server %s, ticket %s.", come, ", anonima" if anonimo else "",
                    request[chiave_utente], guild.id, ticket.id)
        return vai(indietro + "ticket_inviato")

    base = r"/server/{guild_id:\d{1,20}}/ticket"
    app.router.add_get(base, elenco)
    app.router.add_get(base + r"/{ticket:\d{1,10}}", scheda)
    app.router.add_get(base + r"/{ticket:\d{1,10}}/stato", stato)
    app.router.add_post(base + r"/{ticket:\d{1,10}}/rispondi", rispondi)

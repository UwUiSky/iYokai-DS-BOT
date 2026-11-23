"""
core/web_panel_ticket_trascrizioni.py
=====================================
Trascrizioni dei ticket nel pannello (TKT-072, D111): elenco con ricerca per utente, pannello, voto e motivo, apertura
della singola trascrizione (la pagina HTML decifrata, con una CSP sua: niente script, niente risorse remote, solo
immagini incorporate) e le opzioni del server (accesa o spenta, giorni, al massimo 90).
Vedono solo i membri dello staff di QUEL ticket (stessa regola di `web_panel_ticket`), riletti a ogni richiesta.
Trascrizione inesistente, scaduta, di un altro server, di un ticket non tuo o illeggibile: la stessa pagina «non trovata».
Funzioni coperte: SPEC §24.9 (TKT-072, issue #120)
Dipende da: core/web_panel_ticket.py, core/ticket_trascrizioni_logic.py, core/repositories/ticket_trascrizioni_repo.py
"""

from __future__ import annotations

import logging

from aiohttp import web

from core import panel_bridge, ticket_trascrizioni_logic as logica
from core.config import config
from core.repositories.ticket_repo import ticket_repo
from core.repositories.ticket_trascrizioni_repo import ticket_trascrizioni_repo as repo
from core.ticket_logic import e_admin_ticket
from core.web_panel_ticket import ruoli_staff

logger = logging.getLogger("iyokai.web_panel_ticket_trascrizioni")

CANDIDATE = 300  # righe lette prima di togliere quelle che non puoi vedere
# La pagina della trascrizione ha le sue regole: solo stile interno e immagini incorporate, niente altro.
INTESTAZIONI_TRASCRIZIONE = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
                               "base-uri 'none'; form-action 'none'; frame-ancestors 'none'; sandbox",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
}


async def vedibili(guild, utente_id: int, righe) -> list:
    """Le righe dei ticket dove `utente_id` è staff ADESSO. I ruoli si leggono una volta per pannello."""
    membro = await panel_bridge.membro_del_server(guild, utente_id)
    if membro is None or getattr(membro, "bot", False) is True or not hasattr(membro, "roles"):
        return []
    ruoli = {r.id for r in membro.roles}
    gestisce = bool(membro.guild_permissions.manage_guild)
    staff_per_pannello: dict = {}
    admin = None
    visibili = []
    for r in righe:
        if r.panel_id not in staff_per_pannello:
            staff_per_pannello[r.panel_id] = set(await ruoli_staff(guild.id, r.panel_id))
        staff = staff_per_pannello[r.panel_id]
        if not (gestisce or ruoli & staff):
            continue
        if r.solo_admin:
            if admin is None:
                admin = set(await ticket_repo.ruoli_admin(guild.id))
            if not e_admin_ticket(gestisce, ruoli, staff, admin):
                continue
        visibili.append(r)
    return visibili


def registra_rotte(app: web.Application, *, pagina, errore, server, scrittura, chiave_utente, chiave_intestazioni) -> None:
    def vai(url: str) -> web.Response:
        return web.Response(status=302, headers={"Location": url})

    def non_trovata(request: web.Request) -> web.Response:
        return errore(request, 404, "Trascrizione non trovata", "Questa trascrizione non esiste, è scaduta o non puoi vederla.")

    async def elenco(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        q = request.query
        filtro = logica.filtro_da_form(q.get("utente"), q.get("pannello"), q.get("voto"), q.get("motivo"))
        try:
            numero = max(0, min(int(q.get("pagina", "0")), 1000))
        except ValueError:
            numero = 0
        # Si leggono più righe di quelle mostrate: quelle che non puoi vedere si tolgono dopo, per ruolo.
        righe = await vedibili(guild, request[chiave_utente], await repo.elenco(guild.id, filtro, CANDIDATE, 0))
        mostrate = righe[numero * logica.RIGHE_PAGINA:(numero + 1) * logica.RIGHE_PAGINA]
        _, no_admin = await server(request, solo_admin=True)
        return pagina(
            request, "ticket_trascrizioni.html", guild=guild, righe=mostrate, filtro=filtro, numero=numero,
            altre=len(righe) > (numero + 1) * logica.RIGHE_PAGINA, pannelli=await repo.pannelli(guild.id),
            opzioni=await repo.opzioni(guild.id), puo_configurare=no_admin is None, max_giorni=logica.MAX_GIORNI,
            con_chiave=bool(logica.chiave_da_config(config)), righe_max=logica.RIGHE_PAGINA,
            utente_q=q.get("utente", "")[:40], motivo_q=filtro.motivo,
        )

    async def apri(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        try:
            numero = int(request.match_info["id"])
        except ValueError:
            return non_trovata(request)
        letta = await repo.leggi(guild.id, numero) if 0 < numero < 2**62 else None
        if letta is None or not await vedibili(guild, request[chiave_utente], [letta[0]]):
            return non_trovata(request)
        riga, cifrato = letta
        parti = logica.apri(cifrato, guild.id, riga.ticket_id, logica.chiave_da_config(config))
        if parti is None:
            logger.warning("Trascrizione %s (server %s) non si decifra: chiave cambiata o dato alterato.", riga.id, guild.id)
            return non_trovata(request)
        try:
            indice = max(1, min(int(request.query.get("parte", "1")), len(parti)))
        except ValueError:
            indice = 1
        request[chiave_intestazioni] = dict(INTESTAZIONI_TRASCRIZIONE)
        logger.info("Trascrizione %s aperta: utente %s, server %s.", riga.id, request[chiave_utente], guild.id)
        return web.Response(text=parti[indice - 1], content_type="text/html", headers=INTESTAZIONI_TRASCRIZIONE)

    async def opzioni(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request, solo_admin=True)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        base = f"/server/{guild.id}/ticket/trascrizioni"
        giorni = logica.giorni_validi(form.get("giorni"))
        if giorni is None:
            return vai(base + "?esito=trascrizioni_giorni")
        await repo.imposta_opzioni(guild.id, form.get("attiva") == "1", giorni)
        logger.info("Opzioni delle trascrizioni cambiate: utente %s, server %s.", request[chiave_utente], guild.id)
        return vai(base + "?esito=trascrizioni_salvate")

    base = r"/server/{guild_id:\d{1,20}}/ticket/trascrizioni"
    app.router.add_get(base, elenco)
    app.router.add_post(base + "/opzioni", opzioni)
    app.router.add_get(base + r"/{id:\d{1,18}}", apri)

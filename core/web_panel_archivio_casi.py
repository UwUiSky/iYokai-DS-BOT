"""
core/web_panel_archivio_casi.py
===============================
Pagina dell'archivio di un caso di moderazione nel pannello (LOG-029, D122): i messaggi dell'utente degli ultimi 3 giorni
copiati al momento della sanzione, decifrati SOLO all'apertura, con una CSP sua (niente script, niente risorse esterne,
niente cache), come le trascrizioni dei ticket (`web_panel_ticket_trascrizioni`).
Vede solo chi ADESSO ha su Discord «Gestisci server» o «Modera i membri» (stesso livello di `/mod-casi`), riletto a ogni
richiesta. Caso inesistente, senza testo, di un altro server, utente non autorizzato o dato illeggibile: la stessa pagina.
Funzioni coperte: SPEC §8.18 (LOG-029, D122)
Dipende da: core/moderation_archivio_utente.py, core/log_testi_logic.py, core/panel_bridge.py
"""

from __future__ import annotations

import logging

from aiohttp import web

from core import log_testi_logic as logica, moderation_archivio_utente as archivio, panel_bridge

logger = logging.getLogger("iyokai.web_panel_archivio_casi")


async def e_staff_di_moderazione(guild, utente_id: int) -> bool:
    """«Gestisci server» o «Modera i membri» adesso. Un bot o un utente uscito dal server non passa."""
    membro = await panel_bridge.membro_del_server(guild, utente_id)
    if membro is None or getattr(membro, "bot", False) is True:
        return False
    permessi = getattr(membro, "guild_permissions", None)
    return bool(permessi and (permessi.manage_guild or permessi.moderate_members or permessi.administrator))


def registra_rotte(app: web.Application, *, errore, server, chiave_utente, chiave_intestazioni) -> None:
    def non_trovata(request: web.Request) -> web.Response:
        return errore(request, 404, "Archivio non trovato", "Questo archivio non esiste, non ha testo o non puoi vederlo.")

    async def apri(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        try:
            numero = int(request.match_info["caso"])
        except ValueError:
            return non_trovata(request)
        if not 0 < numero < 2**31 or not await e_staff_di_moderazione(guild, request[chiave_utente]):
            return non_trovata(request)
        letto = await archivio.leggi_testi(guild.id, numero)
        if letto is None:
            return non_trovata(request)
        utente_id, messaggi = letto
        request[chiave_intestazioni] = dict(logica.INTESTAZIONI_PAGINA)
        logger.info("Archivio del caso %s aperto: staff %s, server %s.", numero, request[chiave_utente], guild.id)
        return web.Response(
            text=logica.pagina_html(messaggi, numero, utente_id), content_type="text/html",
            headers=logica.INTESTAZIONI_PAGINA,
        )

    app.router.add_get(r"/server/{guild_id:\d{1,20}}/moderazione/archivio/{caso:\d{1,10}}", apri)

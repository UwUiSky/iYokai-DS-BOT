"""
core/web_panel_istantanee.py
============================
Pagina del pannello web per le istantanee di un canale (LOG-028): `/istantanea/<segreto>`. Serve l'accesso con
Discord; chi può vedere lo si ricontrolla a ogni apertura (gestori del server, oppure chi è nel server e, a seconda
della scelta, ha un ruolo o ha solo il link). Segreto sbagliato, scaduto, server sparito o accesso negato danno la
stessa risposta: la pagina non dice se un link esiste. Mai visibile a tutti: senza Discord non si apre.
Si registra con una riga da `core/web_panel_server.py`.
Funzioni coperte: SPEC §8.21 (LOG-028)
Dipende da: core/log_istantanee_logic.py, core/repositories/log_istantanee_repo.py
"""

from __future__ import annotations

import logging

import discord
from aiohttp import web

from core import log_istantanee_logic as logica, web_panel_logic as regole
from core.repositories.log_istantanee_repo import log_istantanee_repo

logger = logging.getLogger("iyokai.web_panel_istantanee")

NON_TROVATA = (404, "Pagina non trovata", "Questo link non esiste, è scaduto o non puoi aprirlo.")


async def puo_aprire(bot, ponte, riga, utente_id: int) -> discord.Guild | None:
    """Il server dell'istantanea se `utente_id` la può vedere ADESSO, altrimenti None."""
    guild = bot.get_guild(riga.guild_id)
    if guild is None:
        return None
    e_gestore = await ponte.server_gestibile(bot, guild.id, utente_id) is not None
    membro = guild.get_member(utente_id)
    if membro is None and not e_gestore and riga.accesso != "gestori":
        try:
            membro = await guild.fetch_member(utente_id)
        except discord.HTTPException:
            membro = None  # nel dubbio: chiuso
    ruoli = frozenset(r.id for r in membro.roles) if membro is not None else frozenset()
    ammesso = logica.puo_vedere(
        riga.accesso, riga.role_id, e_gestore=e_gestore, e_membro=membro is not None, ruoli_membro=ruoli
    )
    return guild if ammesso else None


def registra_rotte(app: web.Application, *, bot, ponte, pagina, errore, chiave_utente) -> None:
    """`pagina(request, modello, codice_http, **dati)` e `errore(request, codice, titolo, testo)` sono gli aiuti di `build_app`."""
    limite = regole.LimiteFrequenza(30, 60)  # per utente: ogni apertura legge righe dal database

    async def mostra(request: web.Request) -> web.StreamResponse:
        utente_id = request.get(chiave_utente)
        if utente_id is None:
            return web.Response(status=302, headers={"Location": "/accedi"})
        if not limite.consenti(f"u:{utente_id}"):
            return errore(request, 429, "Troppe richieste", "Aspetta un minuto e riprova.")
        segreto = request.match_info["segreto"]
        if not logica.segreto_valido(segreto):
            return errore(request, *NON_TROVATA)
        riga = await log_istantanee_repo.per_impronta(logica.impronta(segreto))
        if riga is None:
            return errore(request, *NON_TROVATA)
        guild = await puo_aprire(bot, ponte, riga, utente_id)
        if guild is None:
            return errore(request, *NON_TROVATA)
        righe = await log_istantanee_repo.righe(riga.id)
        return pagina(request, "istantanea.html", istantanea=riga, server=guild.name, righe=righe)

    app.router.add_get(r"/istantanea/{segreto:[A-Za-z0-9_\-]{43}}", mostra)

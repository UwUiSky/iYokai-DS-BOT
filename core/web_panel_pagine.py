"""
core/web_panel_pagine.py
========================
Pagine del pannello web per area: vocali temporanei (VOC-020), statistiche pubbliche (STA-012), classifica web con
indirizzo breve (LIV-062), avvisi del pannello (CFG-006), chiave e API di sola lettura (STA-061). Le pagine pubbliche e l'API non usano la sessione:
hanno limiti di frequenza propri e rispondono uguale a «non esiste» e «non puoi». Ogni pagina legge e scrive solo dai punti unici
della sua area (D16), mai SQL diretto. I controlli (accesso con il livello giusto, CSRF, limite) arrivano da
`server` e `scrittura` di `core/web_panel_server.py`.
Funzioni coperte: SPEC §24.8 (VOC-020, issue #127; STA-012, STA-061, issue #130; LIV-062, issue #124; CFG-006, issue #122)
"""

from __future__ import annotations

import logging

from aiohttp import web

from core import web_panel_avvisi as avvisi, web_panel_logic as regole, web_panel_pubblico as pubblico, web_panel_vocali
from core.config_schema import ImpostazioneNonValida
from core.database import db
from core.repositories.web_panel_avvisi_repo import web_panel_avvisi_repo
from core.repositories.web_panel_pubblico_repo import web_panel_pubblico_repo

logger = logging.getLogger("iyokai.web_panel_pagine")

MAX_VOCI_SELECT = 250


def registra_rotte(app: web.Application, *, bot, pagina, errore, server, scrittura, chiave_utente, ip) -> None:
    limite_pubbliche = regole.LimiteFrequenza(30, 60)  # per IP: ogni pagina pubblica interroga il database
    limite_api_ip = regole.LimiteFrequenza(60, 60)  # per IP, prima ancora di guardare la chiave
    limite_api_server = regole.LimiteFrequenza(30, 60)  # per server: chiavi diverse non aggirano il tetto

    def vai(url: str) -> web.Response:
        return web.Response(status=302, headers={"Location": url})

    # ------------------------------------------------ vocali temporanei (VOC-020)
    async def pagina_vocali(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        canali = sorted(guild.text_channels, key=lambda c: c.position)[:MAX_VOCI_SELECT]
        return pagina(request, "vocali.html", guild=guild, v=await web_panel_vocali.leggi(guild), canali=canali)

    async def salva_vocali(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        indietro = f"/server/{guild.id}/vocali?esito="
        campi = {n: str(form.get(n, ""))[:1100] for n in ("nome", "bloccati", "registro", "cap", "clona", "titolo", "testo", "colore")}
        try:
            cambiato = await web_panel_vocali.applica(guild, campi, request[chiave_utente])
        except ImpostazioneNonValida:
            return vai(indietro + "non_valido")
        return vai(indietro + ("salvato" if cambiato else "invariato"))

    app.router.add_get(r"/server/{guild_id:\d{1,20}}/vocali", pagina_vocali)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/vocali", salva_vocali)

    async def _avvisa_sicurezza(guild, request, testo: str) -> None:
        """Un avviso di sicurezza a chi l'ha chiesto (mai alla persona che ha fatto l'azione)."""
        autore = guild.get_member(request[chiave_utente])
        nome = autore.display_name[:50] if autore is not None else f"utente {request[chiave_utente]}"
        await avvisi.avvisa(bot, guild, "sicurezza", f"{testo} ({nome})", escludi_user=request[chiave_utente])

    # ------------------------------------------- pagine di impostazione (solo admin)
    async def pagina_statistiche(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request, solo_admin=True)
        if rifiuto is not None:
            return rifiuto
        return pagina(request, "statistiche_impostazioni.html", guild=guild, p=await web_panel_pubblico_repo.leggi(guild.id))

    async def salva_statistiche(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request, solo_admin=True)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        indietro = f"/server/{guild.id}/statistiche?esito="
        if form.get("pubbliche") not in ("0", "1") or form.get("membri") not in ("0", "1"):
            return vai(indietro + "non_valido")
        cambiato = await pubblico.imposta_statistiche(
            guild.id, form["pubbliche"] == "1", form["membri"] == "1", request[chiave_utente]
        )
        if cambiato:
            await _avvisa_sicurezza(guild, request, "Le statistiche pubbliche sono cambiate")
        return vai(indietro + ("salvato" if cambiato else "invariato"))

    async def pagina_classifica(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request, solo_admin=True)
        if rifiuto is not None:
            return rifiuto
        return pagina(request, "classifica_impostazioni.html", guild=guild, p=await web_panel_pubblico_repo.leggi(guild.id))

    async def salva_classifica(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request, solo_admin=True)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        indietro = f"/server/{guild.id}/classifica?esito="
        try:
            await pubblico.imposta_slug(guild.id, str(form.get("indirizzo", ""))[:64], request[chiave_utente])
        except ImpostazioneNonValida:
            return vai(indietro + "non_valido")
        await _avvisa_sicurezza(guild, request, "L'indirizzo pubblico della classifica è cambiato")
        return vai(indietro + "salvato")

    async def pagina_api(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request, solo_admin=True)
        if rifiuto is not None:
            return rifiuto
        return pagina(request, "api_chiave.html", guild=guild, p=await web_panel_pubblico_repo.leggi(guild.id), nuova=None)

    async def azione_api(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request, solo_admin=True)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        azione = form.get("azione")
        if azione == "crea":
            # La chiave si vede SOLO in questa risposta (mai in un indirizzo, mai di nuovo): `no-store` è già negli header.
            nuova = await pubblico.crea_chiave(guild.id, request[chiave_utente])
            await _avvisa_sicurezza(guild, request, "È stata creata una nuova chiave API")
            return pagina(request, "api_chiave.html", guild=guild, p=await web_panel_pubblico_repo.leggi(guild.id), nuova=nuova)
        if azione == "revoca":
            await pubblico.revoca_chiave(guild.id, request[chiave_utente])
            await _avvisa_sicurezza(guild, request, "La chiave API è stata revocata")
            return vai(f"/server/{guild.id}/api?esito=salvato")
        return vai(f"/server/{guild.id}/api?esito=non_valido")

    # ------------------------------------------------- avvisi del pannello (CFG-006)
    async def pagina_avvisi(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request, personale=True)
        if rifiuto is not None:
            return rifiuto
        utente = request[chiave_utente]
        scelte = await web_panel_avvisi_repo.preferenze(guild.id, utente)
        return pagina(
            request, "avvisi.html", guild=guild, categorie=list(avvisi.CATEGORIE.items()), scelte=scelte,
            canali=avvisi.canali_disponibili(), email=avvisi.email_disponibile(),
            elenco=await web_panel_avvisi_repo.elenco(guild.id, utente),
        )

    async def salva_avvisi(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request, personale=True)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        utente = request[chiave_utente]
        indietro = f"/server/{guild.id}/avvisi?esito="
        if form.get("azione") == "letti":
            await web_panel_avvisi_repo.segna_letti(guild.id, utente)
            return vai(indietro + "salvato")
        try:
            for categoria in avvisi.CATEGORIE:
                await avvisi.imposta_preferenza(guild.id, utente, categoria, str(form.get(f"canale_{categoria}", avvisi.SPENTO)))
        except ImpostazioneNonValida:
            return vai(indietro + "non_valido")
        return vai(indietro + "salvato")

    # ------------------------------------------------------- pagine pubbliche
    def _non_trovata(request: web.Request) -> web.Response:
        return errore(request, 404, "Pagina non trovata", "Questa pagina non esiste o non è pubblica.")

    async def statistiche_pubbliche(request: web.Request) -> web.StreamResponse:
        if not limite_pubbliche.consenti(ip(request)):
            return errore(request, 429, "Troppe richieste", "Aspetta un minuto e riprova.")
        guild_id = int(request.match_info["guild_id"])
        guild = bot.get_guild(guild_id)
        scelte = await web_panel_pubblico_repo.leggi(guild_id) if guild is not None else None
        if guild is None or not scelte.stat_pubbliche or not await db.is_module_active_for_guild(guild_id, "server_stats"):
            return _non_trovata(request)
        dati = await pubblico.dati_statistiche(guild, con_membri=scelte.stat_membri)
        return pagina(request, "statistiche_pubbliche.html", d=dati, massimo=max([g["messaggi"] for g in dati["messaggi_per_giorno"]] or [1]))

    async def classifica_pubblica(request: web.Request) -> web.StreamResponse:
        if not limite_pubbliche.consenti(ip(request)):
            return errore(request, 429, "Troppe richieste", "Aspetta un minuto e riprova.")
        guild_id = await web_panel_pubblico_repo.guild_da_slug(request.match_info["slug"])
        guild = bot.get_guild(guild_id) if guild_id is not None else None
        if guild is None or not await db.is_module_active_for_guild(guild_id, "leveling"):
            return _non_trovata(request)
        return pagina(request, "classifica_pubblica.html", guild=guild, voci=await pubblico.dati_classifica(guild))

    # --------------------------------------------------------------- API (STA-061)
    def _json(stato: int, corpo: dict) -> web.Response:
        return web.json_response(corpo, status=stato)

    async def api_statistiche(request: web.Request) -> web.StreamResponse:
        if not limite_api_ip.consenti(ip(request)):
            return _json(429, {"errore": "troppe richieste"})
        intestazione = request.headers.get("Authorization", "")
        chiave = intestazione[7:].strip() if intestazione[:7].lower() == "bearer " else ""
        guild_id = await pubblico.guild_della_chiave(chiave) if chiave else None
        guild = bot.get_guild(guild_id) if guild_id is not None else None
        if guild is None:
            return _json(401, {"errore": "non autorizzato"})
        if not limite_api_server.consenti(f"g:{guild_id}"):
            return _json(429, {"errore": "troppe richieste"})
        scelte = await web_panel_pubblico_repo.leggi(guild_id)
        dati = await pubblico.dati_statistiche(guild, con_membri=scelte.stat_membri, con_id=True)
        return _json(200, dati)

    app.router.add_get(r"/server/{guild_id:\d{1,20}}/statistiche", pagina_statistiche)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/statistiche", salva_statistiche)
    app.router.add_get(r"/server/{guild_id:\d{1,20}}/classifica", pagina_classifica)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/classifica", salva_classifica)
    app.router.add_get(r"/server/{guild_id:\d{1,20}}/api", pagina_api)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/api", azione_api)
    app.router.add_get(r"/server/{guild_id:\d{1,20}}/avvisi", pagina_avvisi)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/avvisi", salva_avvisi)
    app.router.add_get(r"/stats/{guild_id:\d{1,20}}", statistiche_pubbliche)
    app.router.add_get(r"/c/{slug:[a-z0-9\-]{3,32}}", classifica_pubblica)
    app.router.add_get("/api/v1/stats", api_statistiche)

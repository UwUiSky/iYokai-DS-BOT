"""
core/web_panel_pagine.py
========================
Pagine del pannello web per area: vocali temporanei (VOC-020). Ogni pagina legge e scrive solo dai punti unici
della sua area (D16), mai SQL diretto. I controlli (accesso con il livello giusto, CSRF, limite) arrivano da
`server` e `scrittura` di `core/web_panel_server.py`.
Funzioni coperte: SPEC §24.8 (VOC-020, issue #127)
"""

from __future__ import annotations

from aiohttp import web

from core import web_panel_vocali
from core.config_schema import ImpostazioneNonValida

MAX_VOCI_SELECT = 250


def registra_rotte(app: web.Application, *, pagina, errore, server, scrittura, chiave_utente) -> None:
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

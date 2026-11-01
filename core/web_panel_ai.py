"""
core/web_panel_ai.py
====================
Pagine AI del pannello web, oltre a quella base: `/server/<id>/admin-ai/altro` (lore, limiti, parole vietate, canali spenti),
`/server/<id>/admin-ai/riepilogo` (l'ultimo riepilogo del server) e `/server/<id>/admin-ai/uso` («Uso dell'AI»: cosa tiene l'AI,
per quanto, e quali servizi esterni usa). Le scelte passano dagli stessi punti dei comandi `/admin-ai` (D16).
Si registra con una riga da `core/web_panel_server.py`; sessione, permessi, CSRF e limiti sono quelli del pannello.
Funzioni coperte: SPEC §25.91, §25.92, §25.93 (AI-R-098, AI-R-099, AI-R-100)
Dipende da: core/ai_impostazioni.py, core/ai_pannello_logic.py
"""

from __future__ import annotations

import logging

import discord
from aiohttp import web

from core import ai_impostazioni as impostazioni
from core.ai_pannello_logic import numeri, righe_uso
from core.ai_servizio import servizio_ai
from core.ai_testi_logic import TEMI
from core.config_schema import ImpostazioneNonValida
from core.repositories.ai_repo import ai_repo
from core.repositories.ai_riepilogo_repo import ai_riepilogo_repo

logger = logging.getLogger("iyokai.web_panel_ai")

ESITI = {"salvato": ("Salvato.", False), "non_valido": ("Valore non valido: controlla i campi.", True)}
CAMPI_LIMITI = (
    "tetto_mensile_cent", "quota_utente_giorno", "quota_utente_30g", "quota_funzione_giorno", "quota_immagini_settimana",
)


def registra_rotte(app: web.Application, *, bot, pagina, errore, server, scrittura, chiave_utente) -> None:
    def vai(guild_id: int, esito: str) -> web.Response:
        return web.Response(status=302, headers={"Location": f"/server/{guild_id}/ai/altro?esito={esito}"})

    def esito_di(request: web.Request) -> dict:
        voce = ESITI.get(request.query.get("esito", ""))
        return {"messaggio": voce[0], "errore": voce[1]} if voce else {}

    async def altro(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        cfg = await ai_repo.get_config(guild.id)
        canali = [(c.id, c.name) for c in guild.text_channels[:200]]
        return pagina(
            request, "ai_altro.html", guild=guild, cfg=cfg, temi=TEMI, canali=canali, vietate="\n".join(cfg.parole_vietate),
            spenti=set(cfg.canali_spenti), **esito_di(request),
        )

    async def salva_altro(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        azione = form.get("azione")
        try:
            if azione == "lore":
                tema = str(form.get("tema", "")) or None
                await impostazioni.imposta_lore(
                    guild.id, None if tema == "nessuno" else tema, str(form.get("testo", ""))[:1000],
                    nomi_a_tema=form.get("nomi_a_tema") == "1",
                )
            elif azione == "limiti":
                await impostazioni.imposta_scelte(guild.id, **{k: int(str(form.get(k, ""))) for k in CAMPI_LIMITI})
            elif azione == "vietate":
                await impostazioni.imposta_parole_vietate(guild.id, str(form.get("parole", ""))[:4000])
            elif azione == "canali":
                validi = {c.id for c in guild.text_channels}
                await impostazioni.imposta_canali_spenti(guild.id, numeri(form.getall("spenti", [])), validi)
            else:
                return vai(guild.id, "non_valido")
        except (ImpostazioneNonValida, ValueError):
            return vai(guild.id, "non_valido")
        return vai(guild.id, "salvato")

    async def riepilogo(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        cfg = await ai_riepilogo_repo.config(guild.id)
        canale = guild.get_channel(cfg.canale_id) if cfg.canale_id else None
        return pagina(request, "ai_riepilogo.html", guild=guild, cfg=cfg, canale=canale)

    async def uso(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        cfg = await ai_repo.get_config(guild.id)
        fornitori = sorted({f.nome for f in servizio_ai().motore.fornitori})
        return pagina(request, "ai_uso.html", guild=guild, cfg=cfg, righe=righe_uso(), fornitori=fornitori)

    app.router.add_get(r"/server/{guild_id:\d{1,20}}/ai/altro", altro)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/ai/altro", salva_altro)
    app.router.add_get(r"/server/{guild_id:\d{1,20}}/ai/riepilogo", riepilogo)
    app.router.add_get(r"/server/{guild_id:\d{1,20}}/ai/uso", uso)

"""
core/web_panel_tela.py
======================
Pagina pubblica in sola lettura della tela di pixel di un server: `/tela/<id server>` (HTML senza script) e
la sua immagine PNG, servita sotto lo stesso indirizzo, disegnata fuori dal ciclo principale). Esiste solo se il server la accende
(`/admin-giochi tela impostazioni pubblica:sì`); altrimenti, come per un server che non esiste, è «Pagina non trovata».
Il nome del server passa dall'escape di Jinja2, i numeri della richiesta sono tagliati a interi dentro la tela, nessuno
script e nessuna risorsa esterna (la CSP del pannello vale anche qui), limite di frequenza per indirizzo e una piccola
memoria di 15 secondi per non ridisegnare la stessa immagine a ogni richiesta. Si registra con una riga da
`core/web_panel_server.py`.
Funzioni coperte: FUN-013, FUN-014
Dipende da: core/tela_logic.py, core/tela_image.py, core/repositories/tela_repo.py
"""

from __future__ import annotations

import time

from aiohttp import web

from core import tela_logic as tl
from core import web_panel_logic as regole
from core.database import db
from core.repositories.tela_repo import tela_repo
from core.safe_image import run_image_task
from core.tela_image import disegna

SECONDI_MEMORIA = 15
MAX_IMMAGINI_IN_MEMORIA = 64


def _intero(valore: str | None, minimo: int, massimo: int, base: int) -> int:
    try:
        return min(max(int(valore or ""), minimo), massimo)
    except ValueError:
        return base


def parametri(query) -> tuple[int, int, int]:
    """(x, y, zoom) dalla richiesta: mai fuori dalla tela, mai un errore."""
    return _intero(query.get("x"), 0, tl.LATO - 1, 50), _intero(query.get("y"), 0, tl.LATO - 1, 50), _intero(query.get("zoom"), 1, len(tl.ZOOM), 1)


def registra_rotte(app: web.Application, *, bot, pagina, errore, ip) -> None:
    limite_pagina = regole.LimiteFrequenza(30, 60)
    limite_immagine = regole.LimiteFrequenza(20, 60)
    memoria: dict[tuple[int, int, int, int], tuple[float, bytes]] = {}

    def _non_trovata(request: web.Request) -> web.Response:
        return errore(request, 404, "Pagina non trovata", "Questa pagina non esiste o non è pubblica.")

    async def _server_pubblico(guild_id: int):
        guild = bot.get_guild(guild_id)
        if guild is None or not await db.is_module_active_for_guild(guild_id, "fun"):
            return None
        return guild if (await tela_repo.impostazioni(guild_id)).pubblica else None

    async def pagina_tela(request: web.Request) -> web.StreamResponse:
        if not limite_pagina.consenti(ip(request)):
            return errore(request, 429, "Troppe richieste", "Aspetta un minuto e riprova.")
        guild_id = int(request.match_info["guild_id"])
        guild = await _server_pubblico(guild_id)
        if guild is None:
            return _non_trovata(request)
        x, y, zoom = parametri(request.query)
        x0, y0, lato = tl.finestra(x, y, zoom)
        return pagina(request, "tela_pubblica.html", guild=guild, x=x, y=y, zoom=zoom, x0=x0, y0=y0, x1=x0 + lato - 1, y1=y0 + lato - 1,
                      n=await tela_repo.conta(guild_id), livelli=list(tl.ZOOM), lato_immagine=lato * tl.scala(lato) + 28)

    async def immagine_tela(request: web.Request) -> web.StreamResponse:
        if not limite_immagine.consenti(ip(request)):
            return web.Response(text="Troppe richieste.", status=429)
        guild_id = int(request.match_info["guild_id"])
        if await _server_pubblico(guild_id) is None:
            return web.Response(text="Non trovata.", status=404)
        x, y, zoom = parametri(request.query)
        x0, y0, lato = tl.finestra(x, y, zoom)
        chiave = (guild_id, x0, y0, lato)
        ora = time.monotonic()
        trovata = memoria.get(chiave)
        if trovata is None or ora - trovata[0] > SECONDI_MEMORIA:
            png = await run_image_task(disegna, await tela_repo.caselle(guild_id, x0, y0, lato), x0, y0, lato)
            if len(memoria) >= MAX_IMMAGINI_IN_MEMORIA:
                memoria.pop(min(memoria, key=lambda k: memoria[k][0]))
            memoria[chiave] = trovata = (ora, png)
        return web.Response(body=trovata[1], content_type="image/png")

    app.router.add_get(r"/tela/{guild_id:\d{1,20}}", pagina_tela)
    app.router.add_get(r"/tela/{guild_id:\d{1,20}}/immagine.png", immagine_tela)

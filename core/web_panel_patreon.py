"""
core/web_panel_patreon.py
=========================
Pagina personale «Premium» del pannello (`/premium`) con i pulsanti «Collega Patreon» e «Scollega» (CFG-036, #122).
Il collegamento passa da `core/patreon_service.py` (stato monouso di 10 minuti, token cifrati); il ritorno da Patreon
lo riceve il piccolo server di `core/patreon_server.py`, che rimanda qui con `?patreon=ok`. Ogni POST ha il CSRF.
Senza le chiavi di Patreon le rotte non esistono: stessa 404 di una pagina inventata.
Funzioni coperte: CFG-036
Dipende da: core/patreon_service.py, core/piani.py
"""

from __future__ import annotations

from aiohttp import web

from core import patreon_service, piani, web_panel_logic as regole

ESITI = {"ok": "Account Patreon collegato.", "scollegato": "Account Patreon scollegato."}


def registra_rotte(app: web.Application, *, pagina, errore, scrittura, chiave_utente) -> None:
    if not patreon_service.acceso():
        return
    limite = regole.LimiteFrequenza(10, 60)  # per persona: ogni collegamento scrive nel database

    def vai(url: str) -> web.Response:
        return web.Response(status=302, headers={"Location": url})

    def spento() -> None:
        if not patreon_service.acceso():  # le chiavi possono sparire dopo l'avvio
            raise web.HTTPNotFound()

    async def mostra(request: web.Request) -> web.StreamResponse:
        spento()
        utente = request.get(chiave_utente)
        if utente is None:
            return vai("/accedi")
        return pagina(
            request, "premium_utente.html", collegato=await patreon_service.collegato(utente),
            livello=piani.ETICHETTE.get(await piani.livello_utente(utente), ""),
            esito=ESITI.get(request.query.get("patreon", ""), ""),
        )

    async def collega(request: web.Request) -> web.StreamResponse:
        spento()
        utente = request.get(chiave_utente)
        if utente is None:
            return vai("/accedi")
        _, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        if not limite.consenti(f"patreon:{utente}"):
            return errore(request, 429, "Troppi tentativi", "Aspetta un minuto e riprova.")
        return vai(patreon_service.url_collegamento(await patreon_service.crea_stato(utente)))

    async def scollega(request: web.Request) -> web.StreamResponse:
        spento()
        utente = request.get(chiave_utente)
        if utente is None:
            return vai("/accedi")
        _, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        await patreon_service.scollega(utente)
        return vai("/premium?patreon=scollegato")

    app.router.add_get("/premium", mostra)
    app.router.add_post("/premium/patreon/collega", collega)
    app.router.add_post("/premium/patreon/scollega", scollega)

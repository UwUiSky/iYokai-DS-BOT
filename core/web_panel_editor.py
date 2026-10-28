"""
core/web_panel_editor.py
========================
Le pagine degli editor del pannello (SPEC §24.5): embed salvati del server e messaggio di benvenuto, con
anteprima. Le regole sono in `core/web_editor.py` (le stesse dei comandi, D16); qui si leggono i moduli e si
disegnano le pagine. Le immagini non si caricano nella pagina (il pannello non apre indirizzi esterni): si
mostra l'indirizzo.
Funzioni coperte: SPEC §24.5 (NF-20, issue #91)
Dipende da: core/web_editor.py
"""

from __future__ import annotations

from aiohttp import web

from core import web_editor as editor

MAX_NOME_EMBED = 40


def registra_rotte(app: web.Application, *, pagina, server, scrittura, chiave_utente) -> None:
    """`pagina(request, modello, codice_http, **dati)`, `server(request)` -> (guild, rifiuto), `scrittura(request)` -> (modulo, rifiuto)."""

    def vuoto() -> dict:
        return {"nome": "", "titolo": "", "descrizione": "", "colore": "", "immagine": "", "miniatura": "", "piede": "",
                "campi": [("", "", False)] * editor.CAMPI_NEL_MODULO}

    def valori(nome: str, dati) -> dict:
        campi = list(dati.fields)[: editor.CAMPI_NEL_MODULO]
        campi += [("", "", False)] * (editor.CAMPI_NEL_MODULO - len(campi))
        return {"nome": nome, "titolo": dati.title or "", "descrizione": dati.description or "", "colore": dati.color or "",
                "immagine": dati.image_url or "", "miniatura": dati.thumbnail_url or "", "piede": dati.footer or "", "campi": campi}

    async def disegna_embed(request, guild, *, form: dict, anteprima=None, errori=(), salvato=None, codice=200):
        elenco = await editor.embed_salvati(guild.id)
        return pagina(request, "editor_embed.html", codice, guild=guild, form=form, anteprima=anteprima, errori=list(errori),
                      salvato=salvato, elenco=[n for n, _ in elenco])

    async def pagina_embed(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        modifica = request.query.get("modifica", "")[:MAX_NOME_EMBED]
        form = vuoto()
        for nome, dati in await editor.embed_salvati(guild.id):
            if nome == modifica:
                form = valori(nome, dati)
        return await disegna_embed(request, guild, form=form)

    async def azione_embed(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        modulo, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        nome = str(modulo.get("nome", "")).strip()[:MAX_NOME_EMBED]
        azione = modulo.get("azione")
        if azione == "elimina":
            cancellato = await editor.elimina_embed(guild.id, nome)
            return await disegna_embed(request, guild, form=vuoto(), salvato="eliminato" if cancellato else None,
                                       errori=[] if cancellato else ["Non trovo questo embed."])
        dati = editor.dati_da_modulo(modulo)
        form = valori(nome, dati)
        if azione == "salva":
            try:
                esito = await editor.salva_embed(guild.id, nome, dati, request[chiave_utente])
            except editor.ErroreEditor as errore:
                return await disegna_embed(request, guild, form=form, errori=errore.messaggi, codice=400)
            return await disegna_embed(request, guild, form=form, anteprima=editor.anteprima(dati), salvato=esito)
        errori = await editor.errori_embed(dati)
        return await disegna_embed(request, guild, form=form, anteprima=None if errori else editor.anteprima(dati), errori=errori,
                                   codice=400 if errori else 200)

    async def pagina_benvenuto(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        stato = await editor.stato_benvenuto(guild)
        return pagina(request, "editor_benvenuto.html", 200, guild=guild, stato=stato, canali=_canali(guild),
                      anteprima=editor.anteprima_benvenuto(guild, stato["messaggio"]), errori=[], salvato=None)

    def _canali(guild) -> list[tuple[int, str]]:
        return [(c.id, c.name) for c in guild.text_channels][:25]

    async def azione_benvenuto(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await server(request)
        if rifiuto is not None:
            return rifiuto
        modulo, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        testo = str(modulo.get("messaggio", ""))[: editor.MAX_MESSAGE_LENGTH + 500]
        try:
            canale = int(modulo.get("canale") or 0) or None
        except ValueError:
            canale = None
        stato = {"attivo": modulo.get("attivo") == "1", "canale": canale, "dm": modulo.get("dm") == "1", "messaggio": testo}
        errori, salvato, codice = [], None, 200
        if modulo.get("azione") == "salva":
            try:
                await editor.salva_benvenuto(guild, stato["attivo"], canale, testo, stato["dm"])
                salvato = "salvato"
            except editor.ErroreEditor as errore:
                errori, codice = errore.messaggi, 400
        else:
            errore = editor.errore_benvenuto(guild, testo)
            if errore:
                errori, codice = [errore], 400
        return pagina(request, "editor_benvenuto.html", codice, guild=guild, stato=stato, canali=_canali(guild),
                      anteprima=editor.anteprima_benvenuto(guild, testo) if not errori else "", errori=errori, salvato=salvato)

    app.router.add_get(r"/server/{guild_id:\d{1,20}}/editor/embed", pagina_embed)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/editor/embed", azione_embed)
    app.router.add_get(r"/server/{guild_id:\d{1,20}}/editor/benvenuto", pagina_benvenuto)
    app.router.add_post(r"/server/{guild_id:\d{1,20}}/editor/benvenuto", azione_benvenuto)

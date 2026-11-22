"""
core/web_panel_backup.py
========================
Pagina dei backup nel pannello web (BKP-041): elenco delle copie, scheda di una copia (solo i conteggi, mai i dati)
ed eliminazione con pagina di conferma. Stessi permessi dei comandi (BKP-018, azione «crea», come `lista` ed
`elimina`): il proprietario del server, oppure un admin se il livello del server lo consente. Nessun caricamento
di un backup dal web: caricare cambia il server e resta al comando, con il consenso di chi lo lancia.
Si registra con una riga da `core/web_panel_server.py`; sessione, CSRF e limiti sono quelli del pannello.
Funzioni coperte: SPEC §24.9 (BKP-041, issue #121)
Dipende da: core/backup_permessi_logic.py, core/repositories/backup_struttura_repo.py, core/panel_bridge.py
"""

from __future__ import annotations

import logging

import discord
from aiohttp import web

from core import backup_struttura_logic as struttura, panel_bridge
from core.backup_permessi_logic import AZIONE_CREA, LIVELLO_PREDEFINITO, SETTING_LIVELLO, puo
from core.database import db
from core.repositories.backup_struttura_repo import backup_struttura_repo

logger = logging.getLogger("iyokai.web_panel_backup")

ID_MASSIMO = 2**31 - 1  # l'id della copia è un intero a 32 bit: oltre, di certo non esiste
RIFIUTO = ("Accesso negato", "Non puoi gestire i backup di questo server (o la copia non esiste).")


async def puo_gestire_backup(guild: discord.Guild, user_id: int) -> bool:
    """Come `_puo` dei comandi: livello del server letto adesso, ruoli letti adesso."""
    membro = await panel_bridge.membro_del_server(guild, user_id)
    if membro is None:
        return False
    livello = await db.get_guild_setting(guild.id, SETTING_LIVELLO, LIVELLO_PREDEFINITO)
    return puo(
        livello, AZIONE_CREA, e_owner=user_id == guild.owner_id,
        e_admin=bool(membro.guild_permissions.administrator),
    )


def tipo_copia(c) -> str:
    return "chat" if c.chat else "automatica" if c.automatica else "struttura"


def registra_rotte(app: web.Application, *, bot, pagina, errore, server, scrittura, chiave_utente) -> None:
    def vai(url: str) -> web.Response:
        return web.Response(status=302, headers={"Location": url})

    async def ammesso(request: web.Request):
        """Server e permessi riletti a ogni richiesta; «non esiste» e «non puoi» hanno la stessa pagina."""
        guild, rifiuto = await server(request, solo_admin=True)
        if rifiuto is not None:
            return None, rifiuto
        if not await puo_gestire_backup(guild, request[chiave_utente]):
            return None, errore(request, 403, *RIFIUTO)
        return guild, None

    def id_copia(request: web.Request) -> int | None:
        valore = int(request.match_info["copia"])
        return valore if 0 < valore <= ID_MASSIMO else None

    def non_trovata(request: web.Request) -> web.Response:
        return errore(request, 404, "Copia non trovata", "Questa copia non esiste (più).")

    async def elenco(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await ammesso(request)
        if rifiuto is not None:
            return rifiuto
        copie = await backup_struttura_repo.lista_strutture(guild.id)
        righe = [(c, tipo_copia(c)) for c in copie]
        return pagina(request, "backup.html", guild=guild, righe=righe)

    async def scheda(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await ammesso(request)
        if rifiuto is not None:
            return rifiuto
        copia = id_copia(request)
        trovata = await backup_struttura_repo.leggi_con_data(guild.id, copia) if copia else None
        if trovata is None:
            return non_trovata(request)
        nome, creato_il, dati = trovata
        return pagina(
            request, "backup_scheda.html", guild=guild, copia=copia, nome=nome, creato_il=creato_il,
            tipo="chat" if dati.get("tipo") == "chat" else "automatica" if dati.get("automatica") else "struttura",
            conteggi=struttura.riassunto(dati),
        )

    async def conferma(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await ammesso(request)
        if rifiuto is not None:
            return rifiuto
        copia = id_copia(request)
        trovata = await backup_struttura_repo.leggi_con_data(guild.id, copia) if copia else None
        if trovata is None:
            return non_trovata(request)
        return pagina(request, "backup_elimina.html", guild=guild, copia=copia, nome=trovata[0], creato_il=trovata[1])

    async def elimina(request: web.Request) -> web.StreamResponse:
        guild, rifiuto = await ammesso(request)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        copia = id_copia(request)
        if not copia or not await backup_struttura_repo.elimina_struttura(guild.id, copia):
            return non_trovata(request)
        try:  # come il comando: se il registro non risponde, l'eliminazione resta fatta
            await backup_struttura_repo.registra(guild.id, request[chiave_utente], "elimina", f"#{copia} (dal web)")
        except Exception:  # noqa: BLE001
            logger.warning("Registro del backup non scritto (%s, elimina)", guild.id, exc_info=True)
        return vai(f"/server/{guild.id}/backup?esito=backup_eliminato")

    base = r"/server/{guild_id:\d{1,20}}/backup"
    app.router.add_get(base, elenco)
    app.router.add_get(base + r"/{copia:\d{1,10}}", scheda)
    app.router.add_get(base + r"/{copia:\d{1,10}}/elimina", conferma)
    app.router.add_post(base + r"/{copia:\d{1,10}}/elimina", elimina)

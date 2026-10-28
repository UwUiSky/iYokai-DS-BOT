"""
core/desktop_api.py
===================
L'interfaccia che iYokai Desktop chiama (SPEC D.1, D.5-D.10): `Authorization: Bearer <token personale>` (il token
si crea con il comando dell'app e si conserva solo come impronta), limite di richieste per token e per indirizzo,
corpo al massimo di 8 KB. Ciò che il programma vede passa dai permessi veri della persona nel server.
Funzioni coperte: SPEC D.1, D.5-D.10 (#108)
Dipende da: core/desktop_logic.py, core/desktop_staff.py, core/repositories/desktop_repo.py, core/panel_bridge.py
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone

import discord
from aiohttp import web

from core import desktop_logic as logica
from core import desktop_staff as staff
from core.ai_testi_logic import LINGUE
from core.repositories.desktop_repo import desktop_repo
from core.repositories.main_radio_repo import main_radio_repo
from core.repositories.user_app_repo import user_app_repo
from core.user_app_ai import chiedi_ai_app
from core.user_app_messaggi import MAX_TESTO_AI, istruzioni_ai
from core.web_panel_attivita import stato_radio
from core.web_panel_logic import LimiteFrequenza

MAX_CORPO = 8192
MAX_ATTESA = 20
MAX_EVENTI = 100
CHIAVE_UTENTE = web.RequestKey("desktop_utente", int)


def _json(dati, stato: int = 200) -> web.Response:
    return web.json_response(dati, status=stato, dumps=lambda d: json.dumps(d, ensure_ascii=False))


def _errore(stato: int, codice: str) -> web.Response:
    return _json({"errore": codice}, stato)


def _intero(testo: str | None, predefinito: int, minimo: int, massimo: int) -> int:
    try:
        return max(minimo, min(massimo, int(testo))) if testo is not None else predefinito
    except ValueError:
        return predefinito


async def _corpo_json(request: web.Request) -> dict | None:
    """Il JSON della richiesta (oggetto), o None se troppo grande o storto."""
    if request.content_length is not None and request.content_length > MAX_CORPO:
        return None
    grezzo = await request.content.read(MAX_CORPO + 1)
    if len(grezzo) > MAX_CORPO:
        return None
    try:
        dati = json.loads(grezzo or b"{}")
    except ValueError:
        return None
    return dati if isinstance(dati, dict) else None


def registra_rotte(app: web.Application, *, bot, ip, url_pannello: str, ponte, attesa_passo: float = 2.0, ora=time.monotonic) -> None:
    """`ip(request)`: l'aiuto di `build_app`. `ponte`: `core/panel_bridge.py`. `attesa_passo`: pausa tra due letture."""
    limite_token = LimiteFrequenza(60, 60)
    limite_errori = LimiteFrequenza(10, 60)  # richieste con token sbagliato, per indirizzo
    limite_ai = LimiteFrequenza(10, 60)
    limite_staff = LimiteFrequenza(20, 60)

    def protetta(gestore):
        async def avvolto(request: web.Request) -> web.StreamResponse:
            indirizzo = ip(request)
            token = logica.token_dall_intestazione(request.headers.get("Authorization"))
            utente = await desktop_repo.utente_del_token(logica.impronta(token)) if token else None
            if utente is None:
                if not limite_errori.consenti(indirizzo):
                    return _errore(429, "troppe_richieste")
                return _errore(401, "token_non_valido")
            if not limite_token.consenti(str(utente)):
                return _errore(429, "troppe_richieste")
            request[CHIAVE_UTENTE] = utente
            return await gestore(request)

        return avvolto

    def _membro_in(guild: discord.Guild, utente: int):
        return guild.get_member(utente)

    def _visibile(utente: int, riga) -> bool:
        """Un evento si mostra solo se la persona è ancora nel server e vede ancora il canale."""
        if riga["guild_id"] is None:
            return True
        guild = bot.get_guild(riga["guild_id"])
        membro = _membro_in(guild, utente) if guild else None
        if membro is None:
            return False
        canale = guild.get_channel(riga["channel_id"]) if riga["channel_id"] else None
        return canale is None or canale.permissions_for(membro).view_channel

    def _evento(riga) -> dict:
        link = logica.link_messaggio(riga["guild_id"], riga["channel_id"], riga["message_id"]) if riga["message_id"] else None
        return {
            "id": riga["id"], "tipo": riga["tipo"], "autore": riga["autore_nome"], "canale": riga["canale_nome"],
            "testo": riga["testo"], "link": link, "quando": riga["created_at"].isoformat(),
        }

    # ------------------------------------------------------------ io, server
    async def io(request: web.Request) -> web.Response:
        utente = request[CHIAVE_UTENTE]
        pref = await desktop_repo.preferenze(utente)
        return _json({"utente": str(utente), "avvisi": pref.menzioni, "parole": list(pref.parole), "api": 1})

    async def server(request: web.Request) -> web.Response:
        utente = request[CHIAVE_UTENTE]
        gestibili = {g.id for g in await ponte.server_gestibili(bot, utente)}
        elenco = []
        for guild in sorted(bot.guilds, key=lambda g: g.name.lower()):
            if _membro_in(guild, utente) is None:
                continue
            elenco.append({
                "id": str(guild.id), "nome": guild.name, "icona": guild.icon.url if guild.icon else None,
                "iyokai": True, "staff": guild.id in gestibili,
                "pannello": f"{url_pannello}/server/{guild.id}" if guild.id in gestibili and url_pannello else None,
            })
        return _json({"server": elenco})

    # ------------------------------------------------------------ eventi
    async def eventi(request: web.Request) -> web.Response:
        utente = request[CHIAVE_UTENTE]
        dopo = _intero(request.query.get("dopo"), 0, 0, 2**62)
        limite = _intero(request.query.get("limite"), 50, 1, MAX_EVENTI)
        tipo = request.query.get("tipo")
        if tipo is not None and tipo not in logica.TIPI_EVENTO:
            return _errore(400, "tipo_non_valido")
        attesa = _intero(request.query.get("attesa"), 0, 0, MAX_ATTESA)
        fine = ora() + attesa
        while True:
            righe = [r for r in await desktop_repo.eventi(utente, dopo, tipo, limite) if _visibile(utente, r)]
            if righe or ora() >= fine:
                return _json({"eventi": [_evento(r) for r in righe]})
            await asyncio.sleep(attesa_passo)

    # ------------------------------------------------------------ storico, risposte, traduzione
    async def storico(request: web.Request) -> web.Response:
        utente = request[CHIAVE_UTENTE]
        comandi = await user_app_repo.storico(utente, 50)
        azioni = await desktop_repo.azioni_utente(utente, 25)
        return _json({
            "comandi": [{"comando": r["comando"], "quando": r["used_at"].isoformat()} for r in comandi],
            "azioni": [_azione(r) for r in azioni],
        })

    def _azione(r) -> dict:
        return {"server": str(r["guild_id"]), "azione": r["azione"], "dettaglio": r["dettaglio"], "esito": r["esito"],
                "quando": r["created_at"].isoformat()}

    async def risposte(request: web.Request) -> web.Response:
        righe = await user_app_repo.risposte(request[CHIAVE_UTENTE])
        return _json({"risposte": [{"nome": r["nome"], "testo": r["testo"]} for r in righe]})

    async def traduci(request: web.Request) -> web.Response:
        utente = request[CHIAVE_UTENTE]
        dati = await _corpo_json(request)
        if dati is None:
            return _errore(413, "corpo_non_valido")
        testo, lingua = str(dati.get("testo", "")).strip(), str(dati.get("lingua", "it"))
        if not testo or len(testo) > MAX_TESTO_AI or lingua not in LINGUE:
            return _errore(400, "dati_non_validi")
        if not limite_ai.consenti(str(utente)):
            return _errore(429, "troppe_richieste")
        risposta, motivo = await chiedi_ai_app(utente, "traduci", "traduzione", testo, istruzioni_ai("traduci", lingua), lingua)
        if risposta is None:
            return _json({"errore": "ai_non_disponibile", "motivo": motivo}, 503)
        return _json({"testo": risposta})

    # ------------------------------------------------------------ staff
    async def staff_azioni(request: web.Request) -> web.Response:
        try:
            guild_id = int(request.query.get("server", ""))
        except ValueError:
            return _errore(400, "dati_non_validi")
        if await ponte.server_gestibile(bot, guild_id, request[CHIAVE_UTENTE]) is None:
            return _errore(403, staff.NESSUN_PERMESSO)
        return _json({"azioni": [_azione(r) for r in await desktop_repo.azioni_server(guild_id, 25)]})

    async def staff_azione(request: web.Request) -> web.Response:
        utente = request[CHIAVE_UTENTE]
        dati = await _corpo_json(request)
        if dati is None:
            return _errore(413, "corpo_non_valido")
        if not limite_staff.consenti(str(utente)):
            return _errore(429, "troppe_richieste")
        esito = await staff.esegui(bot, utente, dati.get("server"), dati.get("azione"), dati)
        return _json({"esito": esito}, 200 if esito == staff.OK else 403 if esito == staff.NESSUN_PERMESSO else 400)

    # ------------------------------------------------------------ radio (pubblica)
    async def radio(request: web.Request) -> web.Response:
        tracce, stato = await main_radio_repo.list_tracks(), await main_radio_repo.get_state()
        return _json(stato_radio(tracce, stato, datetime.now(timezone.utc)))

    app.router.add_get("/api/desktop/io", protetta(io))
    app.router.add_get("/api/desktop/server", protetta(server))
    app.router.add_get("/api/desktop/eventi", protetta(eventi))
    app.router.add_get("/api/desktop/storico", protetta(storico))
    app.router.add_get("/api/desktop/risposte", protetta(risposte))
    app.router.add_post("/api/desktop/traduci", protetta(traduci))
    app.router.add_get("/api/desktop/staff/azioni", protetta(staff_azioni))
    app.router.add_post("/api/desktop/staff/azione", protetta(staff_azione))
    app.router.add_get("/api/desktop/radio", protetta(radio))

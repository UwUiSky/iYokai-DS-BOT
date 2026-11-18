"""
core/diretta_controllo_logic.py
===============================
«Questo canale è in diretta adesso?» a richiesta (ALR-040): una lettura a Twitch, Kick o YouTube con
la memoria di 60 secondi per canale e una pausa per server, così nessuno finisce la quota dei servizi.
Usa i servizi dei watcher (stesse chiavi, stessa sessione). Funzioni coperte: SPEC §10.13 (#129 ALR-040)
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from core.alert_messaggio_logic import pulisci_esterno
from core.kick_api_logic import normalizza_slug, parse_channels_response
from core.twitch_api_logic import parse_get_streams_response
from core.youtube_api_logic import parse_videos_list_response, stato_live_del_canale

SERVIZI = ("twitch", "kick", "youtube")
VALIDITA_SECONDI = 60
PAUSA_PER_SERVER_SECONDI = 10
MAX_MEMORIA = 500
_TWITCH = re.compile(r"^[A-Za-z0-9_]{1,25}$")
_YOUTUBE = re.compile(r"^UC[\w-]{22}$")

_memoria: dict[tuple[str, str], tuple[float, "StatoDiretta"]] = {}
_ultima_richiesta: dict[int, float] = {}


@dataclass(frozen=True)
class StatoDiretta:
    servizio: str
    nome: str
    in_diretta: bool | None  # None = il servizio non risponde o non è configurato
    titolo: str = ""
    gioco: str = ""


def nome_valido(servizio: str, nome: str) -> str | None:
    """Il nome pulito (login, slug o ID del canale) oppure None se non è valido per quel servizio."""
    nome = (nome or "").strip()
    if servizio == "twitch":
        return nome.lower() if _TWITCH.match(nome) else None
    if servizio == "kick":
        return normalizza_slug(nome)
    if servizio == "youtube":
        return nome if _YOUTUBE.match(nome) else None
    return None


def pausa_server(guild_id: int, adesso: float | None = None) -> float:
    """Secondi da aspettare prima della prossima richiesta di questo server (0 = si può); se si può, la segna."""
    adesso = time.monotonic() if adesso is None else adesso
    resto = _ultima_richiesta.get(guild_id, -1e9) + PAUSA_PER_SERVER_SECONDI - adesso
    if resto > 0:
        return resto
    if len(_ultima_richiesta) > MAX_MEMORIA:
        _ultima_richiesta.clear()
    _ultima_richiesta[guild_id] = adesso
    return 0.0


async def controlla(servizio: str, nome: str) -> StatoDiretta:
    """Lo stato attuale. `nome` deve venire da `nome_valido`. Mai un'eccezione: se non si sa, `in_diretta=None`."""
    chiave = (servizio, nome)
    voce = _memoria.get(chiave)
    if voce and time.monotonic() - voce[0] < VALIDITA_SECONDI:
        return voce[1]
    try:
        stato = await _leggi(servizio, nome)
    except Exception:  # un servizio esterno che si rompe non deve rompere il comando
        stato = StatoDiretta(servizio, nome, None)
    if stato.in_diretta is not None:
        if len(_memoria) >= MAX_MEMORIA:
            _memoria.clear()
        _memoria[chiave] = (time.monotonic(), stato)
    return stato


async def _leggi(servizio: str, nome: str) -> StatoDiretta:
    if servizio == "twitch":
        from core.twitch_watcher import twitch_watcher

        payload = await twitch_watcher._fetch_streams([nome])
        if payload is None:
            return StatoDiretta(servizio, nome, None)
        s = parse_get_streams_response(payload, [nome])[0]
        return StatoDiretta(servizio, nome, s.is_live, pulisci_esterno(s.title), pulisci_esterno(s.game_name, 100))
    if servizio == "kick":
        from core.kick_watcher import kick_watcher

        payload = await kick_watcher._fetch_channels([nome])
        if payload is None:
            return StatoDiretta(servizio, nome, None)
        s = parse_channels_response(payload, [nome])[0]
        return StatoDiretta(servizio, nome, s.is_live, pulisci_esterno(s.title), pulisci_esterno(s.category, 100))
    from core.youtube_watcher import youtube_watcher

    ids = await youtube_watcher._video_recenti(nome)  # feed RSS, nessuna quota
    if ids is None:
        return StatoDiretta(servizio, nome, None)
    payload = await youtube_watcher._fetch_videos(ids)  # una sola videos.list
    if payload is None:
        return StatoDiretta(servizio, nome, None)
    s = stato_live_del_canale(nome, ids, parse_videos_list_response(payload))
    return StatoDiretta(servizio, nome, s.is_live, pulisci_esterno(s.title))


def _azzera_per_test() -> None:
    _memoria.clear()
    _ultima_richiesta.clear()

"""
core/counter_social.py
======================
I numeri che vengono da fuori per i contatori (STA-045, 046): iscritti di un canale YouTube, spettatori
live di un canale Twitch, giocatori di un server Minecraft. Una richiesta per gruppo, mai una per contatore:
tutti i contatori di tutti i server con lo stesso canale o indirizzo condividono la risposta.
Funzioni coperte: STA-045, STA-046
Dipende da: core/youtube_watcher.py, core/twitch_watcher.py (chiavi già usate dagli alert), core/safe_http.py
"""

from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import quote

from core.safe_http import safe_get

logger = logging.getLogger("iyokai.counter_social")

URL_STATO_GIOCO = "https://api.mcsrvstat.us/3/"  # servizio pubblico: l'indirizzo dell'utente è solo un pezzo di percorso
MAX_GIOCHI_PER_GIRO = 30  # un tetto alle richieste per giro, a prescindere da quanti server li usano
MAX_BYTE_GIOCO = 256 * 1024
PAUSA_TRA_GIOCHI = 0.5


async def giocatori_minecraft(host: str, leggi=safe_get) -> int | None:
    """STA-046: i giocatori online di un server Minecraft (Java o Bedrock). 0 se spento, None se il servizio non risponde."""
    testo = await leggi(URL_STATO_GIOCO + quote(host, safe=""), max_bytes=MAX_BYTE_GIOCO)
    if testo is None:
        return None
    try:
        dati = json.loads(testo)
    except ValueError:
        return None
    if not isinstance(dati, dict):
        return None
    if not dati.get("online"):
        return 0
    giocatori = dati.get("players")
    numero = giocatori.get("online") if isinstance(giocatori, dict) else None
    return int(numero) if isinstance(numero, int) and numero >= 0 else None


async def leggi_social(richieste: set[tuple[str, str]], youtube=None, twitch=None, gioco=giocatori_minecraft) -> dict[str, int | None]:
    """{"youtube:UC..": n, "twitch:login": n, "game:host": n}: None dove il numero non si è potuto leggere."""
    if youtube is None or twitch is None:
        from core.twitch_watcher import twitch_watcher
        from core.youtube_watcher import youtube_watcher

        youtube = youtube or youtube_watcher.iscritti
        twitch = twitch or twitch_watcher.spettatori
    risultato: dict[str, int | None] = {f"{k}:{p}": None for k, p in richieste}
    ids = sorted(p for k, p in richieste if k == "youtube")
    if ids:
        try:
            trovati = await youtube(ids)
        except Exception:
            logger.exception("Iscritti YouTube non letti")
            trovati = None
        for i, n in (trovati or {}).items():
            risultato[f"youtube:{i}"] = n
    logins = sorted(p for k, p in richieste if k == "twitch")
    if logins:
        try:
            trovati = await twitch(logins)
        except Exception:
            logger.exception("Spettatori Twitch non letti")
            trovati = None
        for login, n in (trovati or {}).items():
            risultato[f"twitch:{login}"] = n
    for host in sorted(p for k, p in richieste if k == "game")[:MAX_GIOCHI_PER_GIRO]:
        try:
            risultato[f"game:{host}"] = await gioco(host)
        except Exception:
            logger.exception("Giocatori non letti per %s", host)
        await asyncio.sleep(PAUSA_TRA_GIOCHI)
    return risultato

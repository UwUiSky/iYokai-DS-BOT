"""
core/ticket_roblox.py
=====================
Il profilo Roblox di chi apre un ticket (TKT-088, D121). Il collegamento tra l'account Discord e quello Roblox lo dà
Bloxlink (chiave `BLOXLINK_API_KEY` nel `.env`, spenta se vuota); il profilo (nome, nome visto, data di creazione,
sospensione) viene dall'API pubblica di Roblox, senza chiave. Le chiamate passano da `core/safe_http.py`, la chiave va
solo a Bloxlink, i valori letti si controllano (cifre, lunghezze) e il risultato resta in memoria un'ora, anche
quando la persona non è collegata. Nessun dato personale va nel database.
Funzioni coperte: TKT-088
Dipende da: core/safe_http.py, core/bounded_cache.py
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass

import discord

from core import safe_http
from core.bounded_cache import BoundedCache
from core.config import config

logger = logging.getLogger("iyokai.ticket_roblox")

URL_BLOXLINK = "https://api.blox.link/v4/public/guilds/{guild}/discord-to-roblox/{utente}"
URL_ROBLOX = "https://users.roblox.com/v1/users/{id}"
URL_PROFILO = "https://www.roblox.com/users/{id}/profile"
SECONDI_DI_CACHE = 3600
MAX_BYTE = 64 * 1024
_NOME = re.compile(r"[A-Za-z0-9_]{3,20}")
_DATA = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
SETTING_ACCESO = "ticket_roblox"

_cache: BoundedCache[tuple[int, int], tuple[float, "Profilo | None"]] = BoundedCache(2000)


@dataclass(frozen=True)
class Profilo:
    id: int
    nome: str
    nome_visto: str
    creato: str
    bannato: bool


def disponibile() -> bool:
    """Vero se l'owner ha messo la chiave di Bloxlink nel .env."""
    return bool(config.BLOXLINK_API_KEY)


async def profilo(guild_id: int, user_id: int) -> Profilo | None:
    """Il profilo Roblox collegato all'utente, o None (spento, non collegato, errore). Mai solleva."""
    if not disponibile():
        return None
    chiave = (guild_id, user_id)
    voce = _cache.get(chiave)
    if voce is not None and time.monotonic() - voce[0] < SECONDI_DI_CACHE:
        return voce[1]
    trovato = await _scarica(guild_id, user_id)
    _cache.set(chiave, (time.monotonic(), trovato))
    return trovato


async def _scarica(guild_id: int, user_id: int) -> Profilo | None:
    try:
        grezzo = await safe_http.safe_richiesta(
            URL_BLOXLINK.format(guild=int(guild_id), utente=int(user_id)),
            headers={"Authorization": config.BLOXLINK_API_KEY}, max_bytes=MAX_BYTE,
        )
        roblox_id = str((json.loads(grezzo) if grezzo else {}).get("robloxID") or "")
        if not roblox_id.isdigit() or len(roblox_id) > 15:
            return None
        grezzo = await safe_http.safe_richiesta(URL_ROBLOX.format(id=int(roblox_id)), max_bytes=MAX_BYTE)
        dati = json.loads(grezzo) if grezzo else {}
        nome, visto, creato = str(dati.get("name", "")), str(dati.get("displayName", "")), str(dati.get("created", ""))
        if not _NOME.fullmatch(nome) or not _DATA.match(creato) or not 1 <= len(visto) <= 40:
            return None
        return Profilo(int(roblox_id), nome, visto, creato[:10], bool(dati.get("isBanned")))
    except (ValueError, TypeError, AttributeError):
        logger.info("Risposta di Bloxlink o Roblox non leggibile.")
        return None
    except Exception:
        logger.warning("Profilo Roblox non letto.", exc_info=True)
        return None


def come_testo(p: Profilo) -> str:
    """Il campo per l'embed del ticket: nome, nome visto (senza menzioni né markdown), data e collegamento."""
    visto = discord.utils.escape_mentions(discord.utils.escape_markdown(p.nome_visto))
    righe = [
        f"**{p.nome}** ({visto})",
        f"Creato il {p.creato}" + (" · **account sospeso**" if p.bannato else ""),
        URL_PROFILO.format(id=p.id),
    ]
    return "\n".join(righe)[:1000]

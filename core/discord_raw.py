"""
core/discord_raw.py
===================
Invio di un vero messaggio vocale di Discord con la chiamata diretta all'API (discord.py 2.7.1 non lo fa):
un solo allegato OGG Opus, flag 8192, durata e forma d'onda. Un vocale non porta testo né bottoni.
Funzioni coperte: SPEC §14.19, §25.102 (AI-R-109)
"""

from __future__ import annotations

import json

import discord
from discord.http import Route

FLAG_VOCALE = 1 << 13
NOME_FILE = "voice-message.ogg"


def corpo_vocale(durata: float, onda: str, risposta_a: int | None = None, canale_id: int | None = None, guild_id: int | None = None) -> dict:
    corpo: dict = {
        "flags": FLAG_VOCALE,
        "attachments": [{"id": "0", "filename": NOME_FILE, "duration_secs": round(durata, 2), "waveform": onda}],
        "allowed_mentions": {"parse": []},
    }
    if risposta_a:
        corpo["message_reference"] = {"message_id": risposta_a, "fail_if_not_exists": False}
        if canale_id:
            corpo["message_reference"]["channel_id"] = canale_id
        if guild_id:
            corpo["message_reference"]["guild_id"] = guild_id
    return corpo


async def invia_vocale(
    http: discord.http.HTTPClient, canale_id: int, ogg: bytes, durata: float, onda: str, *, risposta_a: int | None = None,
) -> int:
    """Manda il vocale nel canale e restituisce l'id del messaggio."""
    form = [
        {"name": "payload_json", "value": json.dumps(corpo_vocale(durata, onda, risposta_a, canale_id))},
        {"name": "files[0]", "value": ogg, "filename": NOME_FILE, "content_type": "audio/ogg"},
    ]
    dati = await http.request(Route("POST", "/channels/{channel_id}/messages", channel_id=canale_id), form=form)
    return int(dati["id"])

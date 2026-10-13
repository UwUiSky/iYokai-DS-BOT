"""
core/embed_builder_logic.py
===========================
Controllo dei limiti e costruzione dell'embed (NF-17, SPEC §22.6). Tutti i
limiti di Discord si controllano QUANDO l'admin salva, non quando Discord
rifiuta il messaggio. Funzioni pure, usate anche dal pannello web (D16).
Funzioni coperte: SPEC §22 (NF-17)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import discord

from core.leveling_logic import colore_valido

MAX_EMBED = 50  # embed salvati per server
MAX_NOME = 32
MAX_TITOLO = 256
MAX_DESCRIZIONE = 4096
MAX_CAMPI = 25
MAX_NOME_CAMPO = 256
MAX_VALORE_CAMPO = 1024
MAX_PIEDE = 2048
MAX_TOTALE = 6000
MAX_URL = 2000

_NOME_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


@dataclass(frozen=True)
class DatiEmbed:
    title: str | None = None
    description: str | None = None
    color: str | None = None
    image_url: str | None = None
    thumbnail_url: str | None = None
    footer: str | None = None
    fields: tuple[tuple[str, str, bool], ...] = ()


def normalizza_nome(grezzo: str) -> str | None:
    nome = grezzo.strip().lower()
    return nome if _NOME_RE.match(nome) else None


def lunghezza_totale(dati: DatiEmbed) -> int:
    """I caratteri che Discord conta per il tetto di 6000: titolo, descrizione, campi, piede."""
    return (
        len(dati.title or "")
        + len(dati.description or "")
        + len(dati.footer or "")
        + sum(len(n) + len(v) for n, v, _ in dati.fields)
    )


def _url_valido(url: str) -> bool:
    if len(url) > MAX_URL or any(c.isspace() or ord(c) < 32 for c in url):
        return False  # spazi e a-capo: Discord li taglia o li rifiuta, e nei log fanno confusione
    analizzato = urlparse(url)
    return analizzato.scheme in ("http", "https") and bool(analizzato.hostname) and not analizzato.username


def valida(dati: DatiEmbed) -> list[str]:
    """Gli errori (in italiano) che impedirebbero a Discord di accettare l'embed; vuoto = va bene."""
    errori: list[str] = []
    if not (dati.title or dati.description or dati.fields or dati.image_url or dati.thumbnail_url):
        errori.append("L'embed è vuoto: metti almeno un titolo, un testo, un campo o un'immagine.")
    if dati.title and len(dati.title) > MAX_TITOLO:
        errori.append(f"Il titolo supera {MAX_TITOLO} caratteri.")
    if dati.description and len(dati.description) > MAX_DESCRIZIONE:
        errori.append(f"La descrizione supera {MAX_DESCRIZIONE} caratteri.")
    if dati.footer and len(dati.footer) > MAX_PIEDE:
        errori.append(f"Il piede supera {MAX_PIEDE} caratteri.")
    if len(dati.fields) > MAX_CAMPI:
        errori.append(f"Un embed ha al massimo {MAX_CAMPI} campi.")
    for numero, (nome, valore, _) in enumerate(dati.fields, start=1):
        if not nome.strip() or not valore.strip():
            errori.append(f"Il campo {numero} ha il nome o il valore vuoto.")
        if len(nome) > MAX_NOME_CAMPO:
            errori.append(f"Il nome del campo {numero} supera {MAX_NOME_CAMPO} caratteri.")
        if len(valore) > MAX_VALORE_CAMPO:
            errori.append(f"Il valore del campo {numero} supera {MAX_VALORE_CAMPO} caratteri.")
    if dati.color is not None and colore_valido(dati.color) is None:
        errori.append("Il colore va scritto come #RRGGBB, per esempio #FF8800.")
    for etichetta, url in (("immagine", dati.image_url), ("miniatura", dati.thumbnail_url)):
        if url and not _url_valido(url):
            errori.append(f"L'indirizzo della {etichetta} deve cominciare con http:// o https:// ed essere più corto di {MAX_URL} caratteri.")
    if lunghezza_totale(dati) > MAX_TOTALE:
        errori.append(f"In tutto l'embed supera {MAX_TOTALE} caratteri (titolo, testo, campi e piede insieme).")
    return errori


def costruisci(dati: DatiEmbed) -> discord.Embed:
    """L'embed vero. Chiamare solo dopo `valida`."""
    colore = colore_valido(dati.color) if dati.color else None
    embed = discord.Embed(
        title=dati.title or None,
        description=dati.description or None,
        colour=int(colore[1:], 16) if colore else discord.Colour.blurple(),
    )
    for nome, valore, inline in dati.fields:
        embed.add_field(name=nome, value=valore, inline=inline)
    if dati.image_url:
        embed.set_image(url=dati.image_url)
    if dati.thumbnail_url:
        embed.set_thumbnail(url=dati.thumbnail_url)
    if dati.footer:
        embed.set_footer(text=dati.footer)
    return embed


def a_json(dati: DatiEmbed) -> str:
    return json.dumps(
        {
            "title": dati.title,
            "description": dati.description,
            "color": dati.color,
            "image_url": dati.image_url,
            "thumbnail_url": dati.thumbnail_url,
            "footer": dati.footer,
            "fields": [[n, v, i] for n, v, i in dati.fields],
        },
        ensure_ascii=False,
    )


def da_json(dati: dict) -> DatiEmbed:
    return DatiEmbed(
        title=dati.get("title"),
        description=dati.get("description"),
        color=dati.get("color"),
        image_url=dati.get("image_url"),
        thumbnail_url=dati.get("thumbnail_url"),
        footer=dati.get("footer"),
        fields=tuple((str(n), str(v), bool(i)) for n, v, i in dati.get("fields", [])),
    )

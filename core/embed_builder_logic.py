"""
core/embed_builder_logic.py
===========================
Controllo dei limiti e costruzione dell'embed (NF-17, SPEC §22.6). Tutti i
limiti di Discord si controllano QUANDO l'admin salva, non quando Discord
rifiuta il messaggio. Funzioni pure, usate anche dal pannello web (D16).
Funzioni coperte: SPEC §22 (NF-17), catalogo #128 UTL-075, 076, 079, 081 (D69, B4)
"""

from __future__ import annotations

import json
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
MAX_JSON_BYTE = 1_048_576  # file JSON importato: 1 MiB
MAX_JSON_FINESTRA = 4000  # JSON incollato in una finestra
MAX_EMBED_MESSAGGIO = 10  # embed in un solo messaggio (1 + fino a 9 «altri»)
MAX_COMPONENTI_V2 = 40
MAX_TESTO_V2 = 4000
MAX_TESTO_BOTTONE = 80


@dataclass(frozen=True)
class DatiEmbed:
    title: str | None = None
    description: str | None = None
    color: str | None = None
    image_url: str | None = None
    thumbnail_url: str | None = None
    footer: str | None = None
    fields: tuple[tuple[str, str, bool], ...] = ()


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


def _colore_testo(valore) -> str | None:
    if isinstance(valore, int) and 0 <= valore <= 0xFFFFFF:
        return f"#{valore:06X}"
    return valore if isinstance(valore, str) else None


def da_json_discord(d: dict) -> DatiEmbed:
    """L'embed nel formato dei messaggi di Discord (title, color intero, fields con name/value, image.url...)."""
    campi = tuple(
        (str(c.get("name", "")), str(c.get("value", "")), bool(c.get("inline", False)))
        for c in d.get("fields", []) if isinstance(c, dict)
    )
    return DatiEmbed(
        title=d.get("title"), description=d.get("description"), color=_colore_testo(d.get("color")),
        image_url=(d.get("image") or {}).get("url") if isinstance(d.get("image"), dict) else None,
        thumbnail_url=(d.get("thumbnail") or {}).get("url") if isinstance(d.get("thumbnail"), dict) else None,
        footer=(d.get("footer") or {}).get("text") if isinstance(d.get("footer"), dict) else None,
        fields=campi,
    )


def da_testo_json(testo: str) -> tuple[DatiEmbed | None, str | None]:
    """(dati, errore). Accetta il formato di iYokai e quello di Discord, anche dentro «embeds»: [...]."""
    if len(testo.encode("utf-8")) > MAX_JSON_BYTE:
        return None, "Il file è troppo grande (massimo 1 MiB)."
    try:
        d = json.loads(testo)
    except ValueError:
        return None, "Il testo non è un JSON valido."
    if isinstance(d, dict) and isinstance(d.get("embeds"), list) and d["embeds"]:
        d = d["embeds"][0]
    if not isinstance(d, dict):
        return None, "Il JSON deve descrivere un embed (un oggetto)."
    try:
        if "fields" in d and d["fields"] and isinstance(d["fields"][0], (list, tuple)):
            return da_json(d), None
        return da_json_discord(d), None
    except (TypeError, ValueError, AttributeError):
        return None, "Non riesco a leggere i campi dell'embed."


def embed_di_discord_a_dati(embed: discord.Embed) -> DatiEmbed:
    return da_json_discord(embed.to_dict())


def valida_gruppo(gruppo: list[DatiEmbed]) -> list[str]:
    """Più embed in un messaggio: al massimo 10, e 6.000 caratteri IN TUTTO (non per embed)."""
    errori: list[str] = []
    if len(gruppo) > MAX_EMBED_MESSAGGIO:
        errori.append(f"Un messaggio ha al massimo {MAX_EMBED_MESSAGGIO} embed.")
    if sum(lunghezza_totale(d) for d in gruppo) > MAX_TOTALE:
        errori.append(f"In tutto gli embed del messaggio superano {MAX_TOTALE} caratteri.")
    return errori


def componenti_v2(dati: DatiEmbed, bottoni: int) -> tuple[int, int]:
    """(componenti, caratteri di testo) del messaggio V2: contenitore, testi, galleria, righe e bottoni."""
    n = 1  # il contenitore
    testo = 0
    if dati.title or dati.description:
        n += 1
        testo += len(dati.title or "") + len(dati.description or "") + 4
        if dati.thumbnail_url:
            n += 2  # sezione con miniatura: il testo conta già, la miniatura è un componente a parte
    for nome, valore, _ in dati.fields:
        n += 1
        testo += len(nome) + len(valore) + 6
    if dati.image_url:
        n += 1
    if dati.footer:
        n += 1
        testo += len(dati.footer) + 4
    if bottoni:
        n += -(-bottoni // 5) + bottoni
    return n, testo


def valida_v2(dati: DatiEmbed, bottoni: int) -> list[str]:
    n, testo = componenti_v2(dati, bottoni)
    errori = []
    if n > MAX_COMPONENTI_V2:
        errori.append(f"Il formato V2 ha al massimo {MAX_COMPONENTI_V2} componenti (qui {n}): togli campi o bottoni.")
    if testo > MAX_TESTO_V2:
        errori.append(f"Il formato V2 ha al massimo {MAX_TESTO_V2} caratteri di testo in tutto (qui {testo}).")
    return errori


def errore_bottone(tipo: str, etichetta: str | None, valore: str | None) -> str | None:
    """Il motivo per cui il bottone non va bene, oppure None."""
    if tipo not in ("link", "tag"):
        return "Il tipo è «link» o «tag»."
    if not etichetta or not etichetta.strip() or len(etichetta) > MAX_TESTO_BOTTONE:
        return f"Serve un'etichetta di al massimo {MAX_TESTO_BOTTONE} caratteri."
    if not valore or not valore.strip():
        return "Serve il valore: l'indirizzo per un link, il nome del tag per «tag»."
    if tipo == "link" and (len(valore) > 512 or not _url_valido(valore)):
        return "Il link deve cominciare con http:// o https:// ed essere lungo al massimo 512 caratteri."
    return None

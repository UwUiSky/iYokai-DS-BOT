"""
core/alert_messaggio_logic.py
=============================
Il testo di un avviso: segnaposto ammessi per tipo, pulizia dei testi presi da fuori
(titoli, giochi, descrizioni) e valori dei segnaposto. Nessuna rete e nessun Discord.
Funzioni coperte: SPEC §10.9, §10.13 (#129 ALR-014, 020, 021, 022, 023, 024, 029)
"""

from __future__ import annotations

import re
from dataclasses import replace

import discord

from core import embed_builder_logic as eb
from core.feed_parsing_logic import FeedEntry, pulisci_descrizione
from core.template_renderer import render_template

MAX_MODELLO = 500
MAX_TITOLO_ESTERNO = 256

# ALR-020: un modello per ogni tipo di avviso. `{ruolo}` (ALR-021) mette il ping dove vuole chi
# scrive; `{gioco}` (ALR-022) è lo stesso valore di `{game}`; miniatura, descrizione e durata (ALR-023).
SEGNAPOSTO: dict[str, tuple[str, ...]] = {
    "RSS": ("label", "title", "link", "thumbnail", "descrizione", "durata", "ruolo"),
    "TW": ("label", "title", "login", "game", "gioco", "ruolo"),
    "YT": ("label", "title", "video_id", "ruolo"),
    "KK": ("label", "title", "login", "game", "gioco", "ruolo"),
}
_SEGNAPOSTO_RE = re.compile(r"\{([a-z_]+)\}")
_MENZIONE = re.compile(r"<(@[!&]?|#)(?=\d)")


def neutralizza_menzioni(testo: str) -> str:
    """`@everyone`, `@here` e le menzioni scritte in un testo preso da fuori non fanno più ping (D12)."""
    testo = testo.replace("@everyone", "@​everyone").replace("@here", "@​here")
    return _MENZIONE.sub(lambda m: "<​" + m.group(1), testo)


def pulisci_esterno(testo: str | None, massimo: int = MAX_TITOLO_ESTERNO) -> str:
    """Titolo, gioco o descrizione presi da un servizio esterno: senza tag, a una riga, senza ping, tagliati."""
    return neutralizza_menzioni(pulisci_descrizione(testo or "", massimo))


def segnaposto_sconosciuti(modello: str, sigla: str) -> list[str]:
    """I `{nome}` del modello che per questo tipo di avviso non vengono sostituiti (refusi)."""
    ammessi = SEGNAPOSTO.get(sigla, ())
    visti: list[str] = []
    for nome in _SEGNAPOSTO_RE.findall(modello):
        if nome not in ammessi and nome not in visti:
            visti.append(nome)
    return visti


def valori_voce(label: str, voce: FeedEntry, durata: str = "") -> dict[str, str]:
    """Valori dei segnaposto per una voce di feed. Titolo e descrizione arrivano da fuori: puliti."""
    return {
        "label": label,
        "title": pulisci_esterno(voce.title),
        "link": voce.link,
        "thumbnail": voce.thumbnail,
        "descrizione": pulisci_esterno(voce.description, 300),
        "durata": durata,
    }


def durata_leggibile(iso: str | None) -> str:
    """«PT1H2M3S» -> «1:02:03»; vuoto se non si capisce o se è una diretta (P0D)."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return ""
    g, o, mi, s = (int(x or 0) for x in m.groups())
    totale = ((g * 24 + o) * 60 + mi) * 60 + s
    if totale <= 0 or totale > 99 * 3600:
        return ""
    o, resto = divmod(totale, 3600)
    mi, s = divmod(resto, 60)
    return f"{o}:{mi:02d}:{s:02d}" if o else f"{mi}:{s:02d}"


COLORE_AVVISO = 0xC24A3A


def embed_predefinito(valori: dict[str, str], url: str | None) -> discord.Embed:
    """Embed semplice dell'avviso (ALR-014): titolo col link, descrizione e miniatura se ci sono."""
    titolo = valori.get("title") or valori.get("label") or ""
    embed = discord.Embed(title=titolo[:eb.MAX_TITOLO] or None, colour=COLORE_AVVISO)
    if url and url.startswith(("https://", "http://")) and len(url) <= 2000:
        embed.url = url
    descrizione = valori.get("descrizione") or ""
    if descrizione:
        embed.description = descrizione[:eb.MAX_DESCRIZIONE]
    miniatura = valori.get("thumbnail") or ""
    if miniatura.startswith(("https://", "http://")):
        embed.set_thumbnail(url=miniatura)
    if not (embed.title or embed.description):
        embed.description = valori.get("label", "")[:eb.MAX_DESCRIZIONE] or "\u200b"
    return embed


def embed_da_modello(dati: eb.DatiEmbed, valori: dict[str, str]) -> discord.Embed | None:
    """L'embed salvato con i segnaposto sostituiti (ALR-024). None se il risultato non è valido (si usa quello semplice)."""

    def r(testo: str | None, massimo: int) -> str | None:
        return render_template(testo, valori)[:massimo] if testo else testo

    dati = replace(
        dati,
        title=r(dati.title, eb.MAX_TITOLO),
        description=r(dati.description, eb.MAX_DESCRIZIONE),
        footer=r(dati.footer, eb.MAX_PIEDE),
        image_url=r(dati.image_url, eb.MAX_URL),
        thumbnail_url=r(dati.thumbnail_url, eb.MAX_URL),
        fields=tuple((r(n, eb.MAX_NOME_CAMPO) or "", r(v, eb.MAX_VALORE_CAMPO) or "", i) for n, v, i in dati.fields),
    )
    if eb.valida(dati):
        return None
    return eb.costruisci(dati)

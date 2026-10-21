"""
core/nsfw_servizio.py
=====================
Il punto unico (D16) per le scelte dell'istanza NSFW (attiva, lista
permessa, pubblicazione automatica) e per scegliere, pubblicare e
segnalare un contenuto. Lo usano i comandi, il lavoro periodico e il
futuro pannello web.
Funzioni coperte: SPEC §16.10 (NF-23)
Dipende da: core/nsfw_filter_logic.py, core/nsfw_fonti.py, core/repositories/nsfw_repo.py
"""

from __future__ import annotations

import io
import logging
import random
from dataclasses import dataclass

import discord

from core.nsfw_filter_logic import (
    FONTI,
    MAX_TAG_PERMESSI,
    ElementoFonte,
    canale_ammesso,
    filtra,
    impronta,
    motivo_vietato,
    valida_tag,
)
from core.nsfw_fonti import fonti_nsfw
from core.repositories.nsfw_repo import NsfwAutopost, NsfwConfig, NsfwInvio, nsfw_repo

logger = logging.getLogger("iyokai.nsfw")

MAX_AUTOPOST_PER_SERVER = 5
MINUTI_AUTOPOST = (30, 24 * 60)
# Quanti candidati si scaricano al massimo per una pubblicazione.
MAX_TENTATIVI = 6
CANALE_NON_AMMESSO = "Questo canale non è segnato come vietato ai minori (NSFW): qui non pubblico nulla."


@dataclass(frozen=True)
class Scelta:
    elemento: ElementoFonte
    impronta: str
    dati: bytes


# ---- scelte del server ----
async def leggi(guild_id: int) -> NsfwConfig:
    return await nsfw_repo.get_config(guild_id) or NsfwConfig(guild_id, False, ())


async def imposta_attivo(guild_id: int, attivo: bool, da: int) -> None:
    """Accende o spegne l'istanza nel server. Spenta: si fermano anche le pubblicazioni automatiche."""
    await nsfw_repo.imposta_attivo(guild_id, attivo, da)
    if not attivo:
        await nsfw_repo.togli_autopost(guild_id)


async def aggiungi_tag(guild_id: int, testo: str) -> tuple[bool, str]:
    tag, errore = valida_tag(testo)
    if tag is None:
        return False, errore
    attuali = list((await leggi(guild_id)).tag_permessi)
    if tag in attuali:
        return False, f"`{tag}` è già nella lista permessa."
    if len(attuali) >= MAX_TAG_PERMESSI:
        return False, f"La lista permessa ha già {MAX_TAG_PERMESSI} tag: togline uno prima."
    await nsfw_repo.imposta_tag(guild_id, [*attuali, tag])
    return True, f"`{tag}` aggiunto alla lista permessa."


async def togli_tag(guild_id: int, testo: str) -> tuple[bool, str]:
    tag = " ".join(testo.lower().split())
    attuali = list((await leggi(guild_id)).tag_permessi)
    if tag not in attuali:
        return False, f"`{tag[:32]}` non è nella lista permessa."
    await nsfw_repo.imposta_tag(guild_id, [t for t in attuali if t != tag])
    return True, f"`{tag}` tolto dalla lista permessa. Le pubblicazioni automatiche con questo tag si fermano da sole."


async def imposta_autopost(guild_id: int, canale: object, tag: str, minuti: int, da: int) -> tuple[bool, str]:
    config = await leggi(guild_id)
    if not config.attivo:
        return False, "L'istanza NSFW non è attiva in questo server."
    if not canale_ammesso(canale):
        return False, CANALE_NON_AMMESSO
    tag = " ".join((tag or "").lower().split())
    if tag and tag not in config.tag_permessi:
        return False, "Il tag deve essere nella lista permessa del server."
    minimo, massimo = MINUTI_AUTOPOST
    if not minimo <= minuti <= massimo:
        return False, f"L'intervallo va da {minimo} a {massimo} minuti."
    esistenti = await nsfw_repo.elenco_autopost(guild_id)
    if len(esistenti) >= MAX_AUTOPOST_PER_SERVER and all(a.channel_id != canale.id for a in esistenti):
        return False, f"Al massimo {MAX_AUTOPOST_PER_SERVER} canali con la pubblicazione automatica."
    await nsfw_repo.salva_autopost(guild_id, canale.id, tag, minuti, da)
    cosa = f"`{tag}`" if tag else "un tag a caso della lista permessa"
    return True, f"Pubblicazione automatica in {canale.mention}: {cosa} ogni {minuti} minuti."


async def ferma_autopost(guild_id: int, channel_id: int | None) -> int:
    return await nsfw_repo.togli_autopost(guild_id, channel_id)


async def elenco_autopost(guild_id: int) -> list[NsfwAutopost]:
    return await nsfw_repo.elenco_autopost(guild_id)


# ---- scelta, pubblicazione, segnalazione ----
async def scegli(guild_id: int, tag: str, rng: random.Random | None = None) -> Scelta | str:
    """
    Un contenuto che passa tutti i filtri e non è mai uscito nel server; altrimenti il motivo.
    `tag` vuoto: un tag a caso della lista permessa.
    """
    rng = rng or random.Random()
    config = await leggi(guild_id)
    if not config.attivo:
        return "L'istanza NSFW non è attiva in questo server: un admin la accende con /nsfw-admin attiva."
    tag = " ".join(tag.lower().split())
    if not tag and config.tag_permessi:
        tag = rng.choice(config.tag_permessi)
    if tag not in config.tag_permessi or motivo_vietato(tag) is not None:
        return "Questo tag non è nella lista permessa del server."
    elementi = await fonti_nsfw.cerca(tag)
    if elementi is None:
        return "La fonte non risponde: riprova tra qualche minuto."
    candidati = filtra(elementi, set(config.tag_permessi))
    rng.shuffle(candidati)
    for elemento in candidati[:MAX_TENTATIVI]:
        if await nsfw_repo.e_bloccato(elemento.fonte, elemento.id_fonte):
            continue
        dati = await fonti_nsfw.scarica_anteprima(elemento)
        if dati is None:
            continue
        hash_ = impronta(dati)
        if await nsfw_repo.e_bloccato(elemento.fonte, elemento.id_fonte, hash_):
            continue
        if await nsfw_repo.gia_inviato(guild_id, hash_):
            continue
        return Scelta(elemento, hash_, dati)
    return "Nessun contenuto nuovo che passi i filtri per questo tag."


def _embed(scelta: Scelta) -> discord.Embed:
    fonte = FONTI[scelta.elemento.fonte]
    embed = discord.Embed(title=f"Apri su {fonte.nome}", url=scelta.elemento.url_pagina, color=discord.Color.dark_red())
    embed.set_image(url="attachment://anteprima.jpg")
    embed.set_footer(text=f"{fonte.dichiarazione[:200]} Qualcosa non va? Usa «Segnala».")
    return embed


async def pubblica(canale: object, scelta: Scelta, vista: discord.ui.View | None) -> discord.Message | str:
    """Invia nel canale. Il canale si ricontrolla QUI, subito prima dell'invio."""
    if not canale_ammesso(canale):
        return CANALE_NON_AMMESSO
    try:
        messaggio = await canale.send(
            embed=_embed(scelta),
            file=discord.File(io.BytesIO(scelta.dati), filename="anteprima.jpg", spoiler=True),
            view=vista,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException as exc:
        logger.warning("Invio NSFW fallito nel canale %s: %s", getattr(canale, "id", "?"), exc.status)
        return "Non riesco a scrivere in questo canale."
    e = scelta.elemento
    await nsfw_repo.registra_invio(canale.guild.id, canale.id, messaggio.id, e.fonte, e.id_fonte, scelta.impronta)
    return messaggio


async def segnala(message_id: int, da: int) -> NsfwInvio | None:
    """Blocca in tutti i server il contenuto di questo messaggio. None se il messaggio non è nel registro."""
    invio = await nsfw_repo.invio_del_messaggio(message_id)
    if invio is None:
        return None
    await nsfw_repo.blocca(invio.impronta, invio.fonte, invio.id_fonte, "segnalato da un utente", invio.guild_id, da)
    logger.warning("Contenuto NSFW segnalato e bloccato: %s/%s.", invio.fonte, invio.id_fonte)
    return invio

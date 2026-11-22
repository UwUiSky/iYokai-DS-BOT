"""
core/automod_avviso.py
======================
Avviso all'utente quando l'AutoMod cancella un messaggio (D110): messaggio privato con le regole non
rispettate; se i DM sono chiusi, un messaggio breve nel canale (solo la sua menzione) che si cancella dopo 8
secondi. Impostazione del server (acceso di base) con testo proprio e segnaposto {server} {canale} {regole}
{utente}. Tetto per persona: un avviso ogni 30 secondi, al massimo 5 in 10 minuti. Un errore qui non ferma mai
la cancellazione né il resto dell'AutoMod.
Funzioni coperte: SPEC §6 (#116, D110)
Dipende da: cogs/moderation/_shared.py (try_dm_message)
"""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from dataclasses import dataclass

import discord

from core.bounded_cache import BoundedCache
from core.database import db as _db
from core.i18n import testo_guild

logger = logging.getLogger("iyokai.automod_avviso")

SETTING_ATTIVO = "automod_avviso_attivo"
SETTING_TESTO = "automod_avviso_testo"
MAX_TESTO = 500
PAUSA_S = 30
MAX_IN_FINESTRA = 5
FINESTRA_S = 600
SECONDI_CANALE = 8
MAX_REGOLE_ELENCO = 5
MAX_NOME_REGOLA = 50
MAX_ELENCO = 300
MAX_TESTO_CANALE = 380

ESITO_DM = "dm"
ESITO_CANALE = "canale"
ESITO_NESSUNO = "nessuno"
ESITO_SPENTO = "spento"
ESITO_TETTO = "tetto"

_SEGNAPOSTO = re.compile(r"\{(server|canale|regole|utente)\}")
_NON_AMMESSI = re.compile(r"[@<>`*_~|]")


@dataclass(frozen=True)
class OpzioniAvviso:
    attivo: bool = True
    testo: str = ""


async def leggi(guild_id: int, archivio=None) -> OpzioniAvviso:
    db = archivio or _db
    attivo = await db.get_guild_setting(guild_id, SETTING_ATTIVO, True)
    testo = await db.get_guild_setting(guild_id, SETTING_TESTO, None)
    return OpzioniAvviso(
        attivo=attivo if isinstance(attivo, bool) else True,
        testo=testo.strip()[:MAX_TESTO] if isinstance(testo, str) else "",
    )


async def imposta(guild_id: int, attivo: bool | None, testo: str | None, autore_id: int, archivio=None) -> None:
    """Un solo punto per comando e pannello. `None` lascia com'e'; testo vuoto torna a quello di base."""
    db = archivio or _db
    if testo is not None and len(testo.strip()) > MAX_TESTO:
        raise ValueError(f"Il testo va fino a {MAX_TESTO} caratteri.")
    if attivo is not None:
        await db.set_guild_setting(guild_id, SETTING_ATTIVO, attivo, changed_by=autore_id)
    if testo is not None:
        await db.set_guild_setting(guild_id, SETTING_TESTO, testo.strip() or None, changed_by=autore_id)


def espandi(testo: str, valori: dict[str, str]) -> str:
    """Sostituisce solo {server} {canale} {regole} {utente}; gli altri restano com'e'."""
    return _SEGNAPOSTO.sub(lambda m: valori.get(m.group(1), ""), testo)


def elenco_regole(nomi: list[str]) -> str:
    """I nomi senza doppioni, ripuliti da menzioni e formattazione, al massimo 5, ognuno fino a 50 caratteri."""
    visti: list[str] = []
    for nome in nomi:
        pulito = _NON_AMMESSI.sub("", nome).strip()[:MAX_NOME_REGOLA]
        if pulito and pulito not in visti:
            visti.append(pulito)
    testo = ", ".join(visti[:MAX_REGOLE_ELENCO])
    if len(visti) > MAX_REGOLE_ELENCO:
        testo += "…"
    return testo[:MAX_ELENCO]


class LimitatoreAvvisi:
    """Un avviso ogni 30 secondi per persona e non piu' di 5 in 10 minuti. In memoria, con tetto."""

    def __init__(self, max_persone: int = 20_000) -> None:
        self._dati: BoundedCache[tuple[int, int], deque] = BoundedCache(max_persone)

    def __len__(self) -> int:
        return len(self._dati)

    def svuota(self) -> None:
        self._dati = BoundedCache(self._dati._max_size)

    def puo_avvisare(self, guild_id: int, user_id: int, ora: float | None = None) -> bool:
        ora = time.monotonic() if ora is None else ora
        chiave = (guild_id, user_id)
        coda = self._dati.get(chiave)
        if coda is None:
            coda = deque(maxlen=MAX_IN_FINESTRA)
        while coda and coda[0] <= ora - FINESTRA_S:
            coda.popleft()
        if coda and ora - coda[-1] < PAUSA_S:
            return False
        if len(coda) >= MAX_IN_FINESTRA:
            return False
        coda.append(ora)
        self._dati.set(chiave, coda)
        return True


limitatore = LimitatoreAvvisi()


async def _nome_regola(guild, violazione: str, personale: str | None) -> str:
    if personale:
        return personale
    chiave = f"automod_avviso_v_{violazione}"
    testo = await testo_guild(guild, chiave)
    return violazione if testo == chiave else testo


async def avvisa(message: discord.Message, motivi: list[tuple[str, str | None]], archivio=None, ora: float | None = None) -> str:
    """Avvisa l'autore del messaggio cancellato. Non solleva mai; restituisce l'esito (ESITO_*)."""
    try:
        return await _avvisa(message, motivi, archivio, ora)
    except Exception:  # noqa: BLE001 - l'avviso non deve mai fermare l'AutoMod
        logger.warning("Avviso AutoMod non inviato (server %s).", getattr(getattr(message, "guild", None), "id", None), exc_info=True)
        return ESITO_NESSUNO


async def _avvisa(message, motivi, archivio, ora) -> str:
    guild, autore = message.guild, message.author
    if guild is None or getattr(autore, "bot", True) or not isinstance(getattr(autore, "id", None), int):
        return ESITO_NESSUNO
    opz = await leggi(guild.id, archivio)
    if not opz.attivo:
        return ESITO_SPENTO
    if not limitatore.puo_avvisare(guild.id, autore.id, ora):
        return ESITO_TETTO
    nomi = [await _nome_regola(guild, v, p) for v, p in motivi]
    regole = elenco_regole(nomi)
    valori = {
        "server": guild.name, "canale": getattr(message.channel, "mention", ""),
        "regole": regole, "utente": autore.display_name,
    }
    descrizione = espandi(opz.testo or await testo_guild(guild, "automod_avviso_testo_base"), valori)[:1000]
    embed = discord.Embed(title=await testo_guild(guild, "automod_avviso_titolo"), description=descrizione, color=discord.Color.orange())
    embed.add_field(name=await testo_guild(guild, "automod_avviso_campo_regole"), value=regole or "-", inline=False)
    from cogs.moderation._shared import try_dm_message

    try:
        if await try_dm_message(autore, embed) is not None:
            return ESITO_DM
    except Exception:  # noqa: BLE001
        logger.warning("DM dell'avviso AutoMod non riuscito (server %s).", guild.id, exc_info=True)
        return ESITO_NESSUNO
    # DM chiusi: breve nel canale, solo la menzione della persona, si cancella da solo.
    testo = f"{autore.mention} {descrizione} ({regole})"[:MAX_TESTO_CANALE]
    try:
        await message.channel.send(
            testo, delete_after=SECONDI_CANALE,
            allowed_mentions=discord.AllowedMentions(users=[autore], roles=False, everyone=False, replied_user=False),
        )
    except (discord.Forbidden, discord.HTTPException):
        return ESITO_NESSUNO
    return ESITO_CANALE

"""
core/risposte_server.py
=======================
Come il server vuole le risposte del bot (#122): sempre private (CFG-013), cancellate dopo N secondi (CFG-014) e
con i colori di successo ed errore scelti (CFG-033, premium). Un solo punto (D16) per `/admin-bot config risposte`
e per il pannello web: legge, controlla, scrive (con lo storico) e applica le regole alle interazioni.
Il controllo gira in `BlacklistAwareCommandTree.interaction_check`, dopo la politica dei comandi.
Funzioni coperte: SPEC §20 (NF-05), catalogo #122 (CFG-013, CFG-014, CFG-033)
Dipende da: core/database.py (impostazioni), core/premium.py (colori)
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

import discord
from discord.interactions import InteractionResponse

logger = logging.getLogger("iyokai.risposte")

CHIAVE_EFFIMERE = "risposte_effimere"
CHIAVE_CANCELLA = "risposte_cancella_secondi"
CHIAVE_COLORE_OK = "colore_successo"
CHIAVE_COLORE_ERR = "colore_errore"
TUTTE_LE_CHIAVI = (CHIAVE_EFFIMERE, CHIAVE_CANCELLA, CHIAVE_COLORE_OK, CHIAVE_COLORE_ERR)

# Il token di un'interazione dura 15 minuti: si cancella entro 10.
MAX_CANCELLA_SECONDI = 600
MAX_CANCELLAZIONI_PENDENTI = 2000
MODULO_COLORI = "aspetto"  # stesso piano premium dell'aspetto del bot (core/bot_aspetto.py)
MANCA = object()

_COLORE_BASE_SUCCESSO = discord.Color.green().value
_COLORE_BASE_ERRORE = discord.Color.red().value
_ESADECIMALE = re.compile(r"#?[0-9a-fA-F]{6}")

_attivi: set[asyncio.Task] = set()


class RispostaNonValida(ValueError):
    """Valore rifiutato. Il messaggio è la chiave del testo per l'utente."""


class RichiedePremium(RispostaNonValida):
    """I colori degli embed sono solo dei server premium."""


@dataclass(frozen=True)
class Risposte:
    effimere: bool = False
    cancella_secondi: int = 0
    colore_successo: int | None = None
    colore_errore: int | None = None

    @property
    def di_base(self) -> bool:
        return not (self.effimere or self.cancella_secondi or self.colore_successo is not None or self.colore_errore is not None)


def colore_da_testo(testo: str) -> int:
    """`#RRGGBB` (il `#` è facoltativo, solo cifre ASCII). Altro: RispostaNonValida."""
    if not isinstance(testo, str) or not _ESADECIMALE.fullmatch(testo.strip()):
        raise RispostaNonValida("risp_colore_non_valido")
    return int(testo.strip().lstrip("#"), 16)


def _intero_in(valore, minimo: int, massimo: int) -> int:
    if not isinstance(valore, int) or isinstance(valore, bool) or not minimo <= valore <= massimo:
        raise RispostaNonValida("risp_cancella_non_valido")
    return valore


def _colore_salvato(valore) -> int | None:
    if isinstance(valore, int) and not isinstance(valore, bool) and 0 <= valore <= 0xFFFFFF:
        return valore
    return None


async def leggi_risposte(guild_id: int | None) -> Risposte:
    if guild_id is None:
        return Risposte()
    from core.database import db

    effimere = await db.get_guild_setting(guild_id, CHIAVE_EFFIMERE, False)
    cancella = await db.get_guild_setting(guild_id, CHIAVE_CANCELLA, 0)
    cancella = cancella if isinstance(cancella, int) and not isinstance(cancella, bool) else 0
    return Risposte(
        effimere=effimere is True,
        cancella_secondi=min(max(cancella, 0), MAX_CANCELLA_SECONDI),
        colore_successo=_colore_salvato(await db.get_guild_setting(guild_id, CHIAVE_COLORE_OK)),
        colore_errore=_colore_salvato(await db.get_guild_setting(guild_id, CHIAVE_COLORE_ERR)),
    )


async def _scrivi(
    guild_id: int, chiave: str, valore, changed_by: int | None, cambiati: list[str], *, quando_toglie=(None,)
) -> None:
    from core.database import db

    # Il valore di base toglie la chiave: lo storico e l'esportazione restano puliti.
    if any(type(valore) is type(v) and valore == v for v in quando_toglie):
        if await db.get_guild_setting(guild_id, chiave) is not None:
            await db.remove_guild_setting(guild_id, chiave, changed_by=changed_by)
            cambiati.append(chiave)
        return
    if await db.get_guild_setting(guild_id, chiave) != valore:
        await db.set_guild_setting(guild_id, chiave, valore, changed_by=changed_by)
        cambiati.append(chiave)


async def imposta_risposte(
    guild_id: int,
    *,
    effimere=MANCA,
    cancella_secondi=MANCA,
    colore_successo=MANCA,
    colore_errore=MANCA,
    changed_by: int | None,
    premium: bool,
) -> list[str]:
    """
    Cambia le impostazioni indicate (MANCA = non si tocca). I colori sono testo `#RRGGBB` o None per toglierli;
    metterli richiede `premium` (deciso da chi chiama con `guild_has_premium_access`, qui si rifiuta senza).
    Prima si controlla tutto, poi si scrive. Restituisce le chiavi cambiate.
    """
    if effimere is not MANCA and not isinstance(effimere, bool):
        raise RispostaNonValida("risp_effimere_non_valido")
    if cancella_secondi is not MANCA:
        _intero_in(cancella_secondi, 0, MAX_CANCELLA_SECONDI)
    colori: dict[str, int | None] = {}
    for chiave, testo in ((CHIAVE_COLORE_OK, colore_successo), (CHIAVE_COLORE_ERR, colore_errore)):
        if testo is MANCA:
            continue
        if testo is None:
            colori[chiave] = None
            continue
        colori[chiave] = colore_da_testo(testo)
        if not premium:
            raise RichiedePremium("risp_colori_premium")
    cambiati: list[str] = []
    if effimere is not MANCA:
        await _scrivi(guild_id, CHIAVE_EFFIMERE, effimere, changed_by, cambiati, quando_toglie=(False,))
    if cancella_secondi is not MANCA:
        await _scrivi(guild_id, CHIAVE_CANCELLA, cancella_secondi, changed_by, cambiati, quando_toglie=(0,))
    for chiave, valore in colori.items():
        await _scrivi(guild_id, chiave, valore, changed_by, cambiati)
    return cambiati


def ricolora(embeds, colore_successo: int | None, colore_errore: int | None) -> None:
    """Cambia il verde e il rosso di base di Discord con i colori del server. Gli altri colori restano."""
    for embed in embeds or ():
        if not isinstance(embed, discord.Embed) or embed.colour is None:
            continue
        if colore_successo is not None and embed.colour.value == _COLORE_BASE_SUCCESSO:
            embed.colour = discord.Colour(colore_successo)
        elif colore_errore is not None and embed.colour.value == _COLORE_BASE_ERRORE:
            embed.colour = discord.Colour(colore_errore)


def _embed_del_messaggio(kw: dict) -> list:
    trovati = list(kw.get("embeds") or [])
    if kw.get("embed") is not None:
        trovati.append(kw["embed"])
    return trovati


async def _attendi(secondi: float) -> None:
    await asyncio.sleep(secondi)


async def _cancella_dopo(interazione, secondi: int) -> None:
    await _attendi(secondi)
    try:
        await interazione.delete_original_response()
    except discord.HTTPException:
        pass  # già cancellata a mano, o l'interazione è scaduta


def _messaggio_permanente(kw: dict) -> bool:
    """Pannelli con bottoni senza scadenza (menu dei ruoli, ticket, giveaway…) e sondaggi: restano pubblici e non si cancellano."""
    vista = kw.get("view")
    return kw.get("poll") is not None or (vista is not None and getattr(vista, "timeout", 0) is None)


class RispostaServer(InteractionResponse):
    """La risposta di un'interazione, con le regole del server (CFG-013, CFG-014, CFG-033)."""

    __slots__ = ("_regole",)

    def __init__(self, interazione, regole: Risposte) -> None:
        super().__init__(interazione)
        self._regole = regole

    def _programma_cancellazione(self, privata: bool) -> None:
        secondi = self._regole.cancella_secondi
        if privata or not secondi or len(_attivi) >= MAX_CANCELLAZIONI_PENDENTI:
            return
        compito = asyncio.get_running_loop().create_task(_cancella_dopo(self._parent, secondi))
        _attivi.add(compito)
        compito.add_done_callback(_attivi.discard)

    async def defer(self, *, ephemeral: bool = False, thinking: bool = False):
        if self._regole.effimere:
            ephemeral = True
        esito = await super().defer(ephemeral=ephemeral, thinking=thinking)
        self._programma_cancellazione(ephemeral)
        return esito

    async def send_message(self, *args, **kw):
        permanente = _messaggio_permanente(kw)
        if self._regole.effimere and not permanente:
            kw["ephemeral"] = True
        ricolora(_embed_del_messaggio(kw), self._regole.colore_successo, self._regole.colore_errore)
        esito = await super().send_message(*args, **kw)
        # Chi chiede già una sua cancellazione (`delete_after`) la tiene; un pannello permanente non si cancella mai.
        self._programma_cancellazione(bool(kw.get("ephemeral")) or kw.get("delete_after") is not None or permanente)
        return esito


class FollowupServer(discord.Webhook):
    """I messaggi dopo il primo: private se il server lo vuole, con i colori del server."""

    __slots__ = ("_regole",)

    async def send(self, *args, **kw):
        regole: Risposte = getattr(self, "_regole", Risposte())
        if regole.effimere and not _messaggio_permanente(kw):
            kw["ephemeral"] = True
        ricolora(_embed_del_messaggio(kw), regole.colore_successo, regole.colore_errore)
        return await super().send(*args, **kw)


def applica_a_interazione(interazione, regole: Risposte) -> bool:
    """Mette le regole del server sulla risposta dell'interazione. False se non c'è niente da cambiare."""
    if regole.di_base:
        return False
    interazione._cs_response = RispostaServer(interazione, regole)
    try:
        payload = {"id": interazione.application_id, "type": 3, "token": interazione.token}
        seguito = FollowupServer.from_state(data=payload, state=interazione._state)
        seguito._regole = regole
        interazione._cs_followup = seguito
    except Exception:  # noqa: BLE001 - se discord.py cambia, la risposta resta quella di base
        logger.warning("Non riesco a regolare i messaggi successivi alla prima risposta.", exc_info=True)
    return True


async def applica_regole(interazione) -> bool:
    """Chiamata dal controllo di ogni comando: legge le regole del server e le mette sull'interazione."""
    guild_id = getattr(interazione, "guild_id", None)
    if guild_id is None:
        return False
    try:
        regole = await leggi_risposte(guild_id)
    except Exception:  # noqa: BLE001 - il database non risponde: il comando va avanti con le risposte normali
        logger.warning("Regole delle risposte non lette per il server %s.", guild_id, exc_info=True)
        return False
    return applica_a_interazione(interazione, regole)

"""
core/avvisi_owner.py
====================
Avvisi in DM all'owner del bot: quando un servizio cade e quando torna. Senza spam: le cadute
che arrivano insieme finiscono in un solo messaggio (finestra di 30 secondi) e tra due messaggi
dello stesso tipo passano almeno 5 minuti. Un «tornato» si manda solo per i servizi di cui si
era già avvisato. Se il DM non parte (DM chiusi, Discord giù) si scrive solo nel log.
Funzioni coperte: consiglio 25/11/2026, blocco C voce 6
Dipende da: core/giro_periodico.py (cadute e riprese dei giri)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import discord

from core.config import config
from core.i18n import lingua_utente, t

logger = logging.getLogger(__name__)

FINESTRA_RAGGRUPPO_SECONDI = 30.0
PAUSA_TRA_AVVISI_SECONDI = 300.0
MAX_ELENCO = 15  # righe dell'elenco in un solo DM (un DM può avere 2.000 caratteri)
MAX_DETTAGLIO = 120


class AvvisiOwner:
    """Raccoglie cadute e riprese e le manda all'owner, raggruppate."""

    def __init__(self) -> None:
        self._caduti_in_attesa: dict[str, str] = {}
        self._tornati_in_attesa: set[str] = set()
        self._avvisati: set[str] = set()  # servizi di cui l'owner sa che sono caduti
        self._ultimo_invio: dict[str, float] = {}
        self._compiti: dict[str, asyncio.Task] = {}

    def caduto(self, bot: Any, servizio: str, dettaglio: str = "") -> None:
        """Un servizio è caduto. Va chiamato dal ciclo principale."""
        self._tornati_in_attesa.discard(servizio)
        if servizio in self._avvisati:
            return  # l'owner lo sa già: niente secondo messaggio finché non torna
        self._caduti_in_attesa[servizio] = dettaglio[:MAX_DETTAGLIO]
        self._programma(bot, "caduti")

    def tornato(self, bot: Any, servizio: str) -> None:
        """Un servizio è tornato. Se non c'era stato un avviso di caduta, non si dice nulla."""
        if servizio in self._caduti_in_attesa:
            del self._caduti_in_attesa[servizio]  # è tornato prima dell'avviso: niente da dire
            return
        if servizio not in self._avvisati:
            return
        self._tornati_in_attesa.add(servizio)
        self._programma(bot, "tornati")

    def _programma(self, bot: Any, tipo: str) -> None:
        compito = self._compiti.get(tipo)
        if compito is not None and not compito.done():
            return
        try:
            self._compiti[tipo] = asyncio.get_running_loop().create_task(self._invia_dopo(bot, tipo))
        except RuntimeError:
            logger.warning("Avviso all'owner non programmabile: nessun ciclo asyncio attivo.")

    async def _invia_dopo(self, bot: Any, tipo: str) -> None:
        ultimo = self._ultimo_invio.get(tipo)
        attesa = FINESTRA_RAGGRUPPO_SECONDI
        if ultimo is not None:
            attesa = max(attesa, PAUSA_TRA_AVVISI_SECONDI - (time.monotonic() - ultimo))
        await asyncio.sleep(attesa)
        if tipo == "caduti":
            voci, self._caduti_in_attesa = dict(self._caduti_in_attesa), {}
            if not voci:
                return
            chiave = "owner_servizi_caduti"
        else:
            voci, self._tornati_in_attesa = {s: "" for s in self._tornati_in_attesa}, set()
            if not voci:
                return
            chiave = "owner_servizi_tornati"
        lingua = await _lingua_owner()
        righe = [f"- {nome}" + (f": {det}" if det else "") for nome, det in list(voci.items())[:MAX_ELENCO]]
        if len(voci) > MAX_ELENCO:
            righe.append(f"... (+{len(voci) - MAX_ELENCO})")
        testo = t(chiave, lingua, n=len(voci), elenco="\n".join(righe))
        self._ultimo_invio[tipo] = time.monotonic()
        if await manda_dm_owner(bot, testo):
            if tipo == "caduti":
                self._avvisati.update(voci)
            else:
                self._avvisati.difference_update(voci)


async def _lingua_owner() -> str:
    try:
        return await lingua_utente(config.OWNER_ID) or "it"
    except Exception:
        return "it"


async def manda_dm_owner(bot: Any, testo: str) -> bool:
    """Un DM all'owner (massimo 2.000 caratteri). True se è partito."""
    try:
        owner = await bot.fetch_user(config.OWNER_ID)
        await owner.send(testo[:2000])
        return True
    except (discord.HTTPException, AttributeError):
        logger.warning("Avviso all'owner non inviato (DM chiusi o Discord non raggiungibile).")
        return False
    except Exception:
        logger.exception("Avviso all'owner non inviato.")
        return False


async def avvisa_owner_chiave(bot: Any, chiave: str, **valori: Any) -> bool:
    """Un DM con un testo dei file delle lingue, nella lingua dell'owner."""
    return await manda_dm_owner(bot, t(chiave, await _lingua_owner(), **valori))


avvisi_owner = AvvisiOwner()


def collega_ai_giri(bot: Any) -> None:
    """Fa partire gli avvisi quando un giro cade (3 errori di fila) e quando torna a funzionare."""
    from core import giro_periodico as gp

    gp.ascoltatori_caduta.append(lambda nome, n, testo: avvisi_owner.caduto(bot, nome, f"{n} errori: {testo}"))
    gp.ascoltatori_ripresa.append(lambda nome: avvisi_owner.tornato(bot, nome))

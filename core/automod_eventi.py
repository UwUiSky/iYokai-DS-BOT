"""
core/automod_eventi.py
======================
Regole AutoMod sugli eventi che non sono messaggi (AMD-009 vocali, 010 thread, 017 nomi, 018 stato, 075 ingresso,
uscita, ruolo dato o tolto, caso): sceglie le regole personali accese di quell'evento, controlla le condizioni e
l'innesco, esegue le azioni con il motore unico (core/automod_azioni.py) e scrive la riga nel registro. Freni
contro i giri a vuoto in core/automod_eventi_logic.py (effetti del bot ignorati, al massimo 3 regole per evento).
Lo stato online e le attività (AMD-018) funzionano solo con l'intent Presenze, spento di base (`stato_attivo`).
Funzioni coperte: SPEC §6 (AMD-009, 010, 017, 018, 075), D63
Dipende da: core/automod_eventi_logic.py, core/automod_azioni.py, core/automod_regole_service.py
"""

from __future__ import annotations

import dataclasses
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import discord

from core import automod_contatori as contatori
from core import automod_liste_service as liste_service
from core import automod_regole_service as regole_service
from core import bot_roles
from core import channel_router as router
from core.automod_azioni import Bersaglio, esegui_azioni
from core.automod_contesto import contesto_da_membro, serve_il_livello
from core.automod_eventi_logic import (
    EFFETTO_DELL_EVENTO,
    DatiEvento,
    conteggi,
    effetti,
    innesco_evento_scatta,
    limite_regole,
)
from core.automod_regole_logic import Contesto, condizioni_ok
from core.database import db
from core.repositories.automod_advanced_repo import automod_advanced_repo

logger = logging.getLogger("iyokai.automod.eventi")

MODULE_AUTOMOD = "automod"
VARIABILE_STATO = "AUTOMOD_STATO_ATTIVO"


def stato_attivo() -> bool:
    """AMD-018: lo stato e le attività si leggono solo con questo interruttore del bot (spento di base) e l'intent Presenze."""
    return os.environ.get(VARIABILE_STATO, "").strip().lower() in ("1", "true", "si", "sì", "yes", "on")


def chiede_intent_presenze() -> bool:
    """Il bot chiede l'intent Presenze a Discord solo se l'interruttore è acceso (main.py: `intents.presences = ...`)."""
    return stato_attivo()


def _effetto_nostro(guild_id: int, user_id: int, evento: str, dati: DatiEvento, ora: float) -> bool:
    tipo = EFFETTO_DELL_EVENTO.get(evento)
    if tipo is None:
        return False
    dettagli = (dati.ruolo_id, None) if tipo == "ruolo" else (None,)
    return any(effetti.e_nostro(guild_id, user_id, tipo, d, ora) for d in dettagli)


def _esente(membro: Any, settings: Any, canale_id: int | None) -> bool:
    if canale_id is not None and canale_id in settings.exempt_channel_ids:
        return True
    return bool({r.id for r in getattr(membro, "roles", ())} & set(settings.exempt_role_ids))


async def elabora(
    bot: discord.Client,
    guild: discord.Guild,
    membro: discord.Member | None,
    evento: str,
    dati: DatiEvento = DatiEvento(),
    canale: Any = None,
    user_id: int | None = None,
) -> tuple[str, ...]:
    """
    Le chiavi delle regole scattate per questo evento. Non solleva: un errore si scrive nel log e basta.
    `user_id` serve quando la persona non è nel server (un caso di ban): le azioni sulla persona non partono.
    """
    try:
        return await _elabora(bot, guild, membro, evento, dati, canale, user_id)
    except Exception:
        logger.exception("AutoMod: errore sull'evento %s nel server %s", evento, guild.id)
        return ()


async def _elabora(bot, guild, membro, evento, dati, canale, user_id) -> tuple[str, ...]:
    uid = membro.id if membro is not None else user_id
    if uid is None or bot_roles.e_un_nostro_bot(uid, bot):
        return ()  # il bot, Mod e i suoi worker non si giudicano mai
    regole = [r for r in await regole_service.regole_del_server(guild.id)
              if r.tipo == "personale" and r.attiva and r.evento == evento and r.innesco]
    if not regole or not await db.is_module_active_for_guild(guild.id, MODULE_AUTOMOD):
        return ()
    ora = time.monotonic()
    if _effetto_nostro(guild.id, uid, evento, dati, ora):
        return ()
    settings = await automod_advanced_repo.get_settings(guild.id)
    canale_id = getattr(canale, "id", None)
    esente = membro is not None and _esente(membro, settings, canale_id)
    livello = await regole_service.livello_di(guild.id, uid) if serve_il_livello(tuple(regole)) else None
    if membro is not None:
        contesto = dataclasses.replace(contesto_da_membro(membro, canale, evento=evento), livello=livello)
    else:
        contesto = Contesto(evento=evento, autore_id=uid, canale_id=getattr(canale, "id", None), livello=livello,
                            ora=datetime.now(timezone.utc))
    liste = await liste_service.voci_per_regole(guild.id) if evento in ("nome", "stato") else None
    scattate: list[str] = []
    for regola in regole:
        if esente and regola.condizioni.esenzioni_globali:
            continue
        if not condizioni_ok(regola.condizioni, contesto):
            continue
        if not innesco_evento_scatta(evento, regola.innesco, dati, liste, conteggi, (guild.id, uid, regola.chiave), ora):
            continue
        if not limite_regole.consente(guild.id, uid, evento, ora):
            logger.info("AutoMod: troppe regole su %s per %s nel server %s, le altre aspettano", evento, uid, guild.id)
            break
        bersaglio = _bersaglio(guild, membro, canale, regola, settings.log_channel_id)
        eseguite = await esegui_azioni(regola.azioni, bersaglio)
        await automod_advanced_repo.log_action(
            guild.id, uid, canale_id or 0, regola.chiave, eseguite, (dati.testo or "")[:200] or None,
            regola_id=regola.id, contatore=regola.contatore.nome if regola.contatore else None,
        )
        if regola.contatore and regola.contatore.soglie:
            soglia = await contatori.soglia_scattata(guild.id, uid, regola.contatore)
            if soglia is not None and await contatori.consuma(guild.id, uid, regola.contatore):
                await esegui_azioni(soglia.azioni, bersaglio)
        scattate.append(regola.chiave)
    return tuple(scattate)


def _bersaglio(guild, membro, canale, regola, canale_log_id) -> Bersaglio:
    async def avvisa_staff(testo: str, ruolo_id: int | None) -> None:
        destinazione = await router.destinazione(guild, router.TIPO_AUTOMOD, None)
        if destinazione is not None:
            menzioni = discord.AllowedMentions(roles=[discord.Object(id=ruolo_id)]) if ruolo_id else discord.AllowedMentions.none()
            await destinazione.send(testo, allowed_mentions=menzioni)

    return Bersaglio(
        guild=guild, membro=membro, canale=canale, motivo=regola.nome, regola_chiave=regola.chiave, regola_nome=regola.nome,
        contatore=regola.contatore.nome if regola.contatore else None, canale_log_id=canale_log_id, avvisa_staff=avvisa_staff,
    )

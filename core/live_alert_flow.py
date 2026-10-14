"""
core/live_alert_flow.py
=======================
Il passo comune dei watcher «in diretta» (Twitch, YouTube, Kick) quando lo
stato cambia: trova il canale, pubblica l'avviso (o la chiusura), poi fa
avanzare lo stato, ricorda il messaggio e dà o toglie il ruolo «in diretta».
Lo stato avanza solo dopo un invio riuscito (se fallisce, si ritenta al giro
dopo). Funzioni coperte: SPEC §10.1, §10.2, §10.4, §10.13
"""

from __future__ import annotations

import logging
import time

import discord

from core.alert_options_logic import AlertOptions, avviso_fine, avviso_live
from core.live_role_logic import aggiorna_ruolo_live
from core.repositories.alert_options_repo import alert_options_repo

logger = logging.getLogger("iyokai.live_alert_flow")

ATTESA_BASE_SECONDI = 120
ATTESA_MASSIMA_SECONDI = 3600
# (kind, id) -> (fallimenti di fila, istante prima del quale non si riprova)
_FALLITI: dict[tuple, tuple[int, float]] = {}


def _in_attesa(chiave: tuple) -> bool:
    voce = _FALLITI.get(chiave)
    return voce is not None and time.monotonic() < voce[1]


def _segna_fallito(chiave: tuple) -> bool:
    """Allunga l'attesa (raddoppia, fino a un'ora). True solo al primo fallimento: si logga una volta."""
    prima = chiave not in _FALLITI
    n = _FALLITI.get(chiave, (0, 0.0))[0] + 1
    attesa = min(ATTESA_BASE_SECONDI * 2 ** (n - 1), ATTESA_MASSIMA_SECONDI)
    _FALLITI[chiave] = (n, time.monotonic() + attesa)
    return prima


async def carica_contesto(kind: str, sottoscrizioni: list) -> tuple[dict[int, AlertOptions], dict[int, int]]:
    """Opzioni e ruoli «in diretta» per tutto il giro: due query, non una per sottoscrizione."""
    opzioni = await alert_options_repo.get_many(kind, [s.id for s in sottoscrizioni])
    ruoli = await alert_options_repo.get_live_roles(list({s.guild_id for s in sottoscrizioni}))
    return opzioni, ruoli


async def pubblica_cambio_live(
    bot,
    sub,
    kind: str,
    *,
    in_diretta: bool,
    testo: str,
    url: str | None,
    opz: AlertOptions,
    ruolo_live_id: int | None,
    repo_stato,
    avvisi,
    nome: str,
) -> None:
    if _in_attesa((kind, sub.id)):
        return
    guild = bot.get_guild(sub.guild_id)
    canale = guild.get_channel(sub.channel_id) if guild else None
    if not isinstance(canale, discord.TextChannel):
        if avvisi.prima_volta((kind, sub.id)):
            logger.warning(
                "Canale %s non raggiungibile per la sottoscrizione %s #%s (server %s).",
                sub.channel_id, nome, sub.id, sub.guild_id,
            )
        return
    avvisi.riarma((kind, sub.id))

    try:
        if in_diretta:
            id_messaggio = await avviso_live(canale, testo, opz, url)
        else:
            await avviso_fine(canale, testo, opz)
            id_messaggio = None
    except discord.HTTPException:
        if _segna_fallito((kind, sub.id)):
            logger.warning(
                "Impossibile pubblicare l'alert %s nel canale %s (server %s): riprovo con attese sempre più lunghe.",
                nome, sub.channel_id, sub.guild_id,
            )
        return
    _FALLITI.pop((kind, sub.id), None)

    # P3: lo stato avanza solo dopo un invio riuscito.
    await repo_stato.update_last_known_live(sub.id, in_diretta)
    if opz.delete_on_end and (in_diretta or opz.last_message_id):
        await alert_options_repo.set_last_message(kind, sub.id, sub.guild_id, id_messaggio)
    if not in_diretta and opz.live_member_id and await alert_options_repo.other_live_for_member(
        sub.guild_id, opz.live_member_id, kind, sub.id
    ):
        return  # è ancora in diretta su un altro avviso: il ruolo resta
    await aggiorna_ruolo_live(guild, opz.live_member_id, ruolo_live_id, in_diretta)

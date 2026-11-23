"""
core/ruoli_collegati_giro.py
============================
Giro periodico dei ruoli collegati Twitch (ALR-049, D127): ogni 12 ore, per chi ha già collegato Twitch, rinnova il token
di Twitch, rilegge il tipo di canale (affiliato, partner) e, se è cambiato, riscrive il collegamento su Discord con il
token di quella persona. Se il token è revocato (Twitch o Discord) il collegamento si cancella e i valori di Twitch
tornano a «no». Tetti: al massimo `MAX_PER_GIRO` persone per giro, una pausa tra una persona e l'altra, e il giro si
ferma al primo «troppe richieste» (429). I guasti passeggeri (rete, 5xx) non scollegano nessuno. Niente rete qui:
si usa `ReteRuoliCollegati` (finta nei test). Kick non c'è: vedi D131.
Funzioni coperte: SPEC §24.9 (ALR-049, issue #129)
Dipende da: core/ruoli_collegati_logic.py, core/ruoli_collegati_rete.py, core/ruoli_collegati_verifica.py, core/repositories/ruoli_collegati_repo.py
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidTag

from core import ruoli_collegati_logic as logica
from core.oauth_crypto import OAuthEncryptionNotConfigured
from core.repositories.ruoli_collegati_repo import ruoli_collegati_repo
from core.ruoli_collegati_verifica import corpo_unico, crea_rete_da_config

logger = logging.getLogger("iyokai.ruoli_collegati_giro")

INTERVALLO_ORE = 12
PRIMO_RITARDO_SECONDI = 300  # dopo l'avvio, per non sommarsi al resto
MAX_PER_GIRO = 500
PAUSA_TRA_PERSONE = 0.5  # secondi: lontani dai limiti di Twitch (800 punti al minuto) e di Discord
MARGINE_SCADENZA = timedelta(minutes=5)
_ILLEGGIBILE = (InvalidTag, OAuthEncryptionNotConfigured, ValueError)


@dataclass
class Riepilogo:
    controllati: int = 0
    cambiati: int = 0
    scollegati: int = 0
    errori: int = 0
    fermato_per_limite: bool = False


def _in_scadenza(scade_il: datetime | None) -> bool:
    return scade_il is not None and scade_il - MARGINE_SCADENZA <= datetime.now(timezone.utc)


async def _token_discord(cfg, rete, riga) -> tuple[str | None, str]:
    """(token chiaro, esito): «ok», «revocato», «limite» o «errore». Rinnova se sta per scadere."""
    uid, k = riga["user_id"], cfg.chiave_cifratura
    if not riga["discord_token"]:
        return None, "revocato"
    try:
        token = logica.decifra(k, uid, "discord_token", riga["discord_token"])
        if not _in_scadenza(riga["discord_scade_il"]):
            return token, "ok"
        if not riga["discord_refresh"]:
            return None, "revocato"
        nuovo, esito = await rete.discord_rinnova_esito(logica.decifra(k, uid, "discord_refresh", riga["discord_refresh"]))
    except _ILLEGGIBILE:
        return None, "errore"
    if nuovo is None:
        return None, esito
    await ruoli_collegati_repo.aggiorna_token_discord(
        uid, logica.cifra(k, uid, "discord_token", nuovo.access_token),
        logica.cifra(k, uid, "discord_refresh", nuovo.refresh_token), nuovo.scade_il,
    )
    return nuovo.access_token, "ok"


async def _rinnova_twitch(cfg, rete, riga) -> tuple[str | None, str]:
    uid, k = riga["user_id"], cfg.chiave_cifratura
    if not riga["twitch_refresh"]:
        return None, "revocato"
    try:
        refresh = logica.decifra(k, uid, "twitch_refresh", riga["twitch_refresh"])
    except _ILLEGGIBILE:
        return None, "errore"
    nuovo, esito = await rete.twitch_rinnova(refresh)
    if nuovo is None:
        return None, esito
    await ruoli_collegati_repo.aggiorna_token_twitch(
        uid, logica.cifra(k, uid, "twitch_token", nuovo.access_token),
        logica.cifra(k, uid, "twitch_refresh", nuovo.refresh_token or refresh), nuovo.scade_il,
    )
    return nuovo.access_token, "ok"


async def _scollega(cfg, rete, riga) -> str:
    """Token revocato: i valori di Twitch tornano a «no» su Discord (se il suo token vale ancora) e la riga si cancella."""
    uid = riga["user_id"]
    try:
        token, esito = await _token_discord(cfg, rete, riga)
        if token is not None:
            await rete.discord_scrivi_stato(token, await corpo_unico(uid, escludi_twitch=True))
        elif esito == "limite":
            return "limite"
    except Exception:  # noqa: BLE001 - la cancellazione non dipende da Discord
        logger.warning("Ruoli collegati: azzeramento su Discord non riuscito (utente %s).", uid, exc_info=True)
    await ruoli_collegati_repo.elimina(uid)
    logger.info("Ruoli collegati: collegamento Twitch revocato, tolto (utente %s).", uid)
    return "scollegato"


async def aggiorna_persona(cfg, rete, riga: dict) -> str:
    """«invariato», «cambiato», «scollegato», «errore» o «limite» per una persona."""
    uid, k = riga["user_id"], cfg.chiave_cifratura
    try:
        access = logica.decifra(k, uid, "twitch_token", riga["twitch_token"])
    except _ILLEGGIBILE:
        return "errore"
    rinnovato = False
    if _in_scadenza(riga["twitch_scade_il"]):
        access, esito = await _rinnova_twitch(cfg, rete, riga)
        rinnovato = True
        if access is None:
            return await _scollega(cfg, rete, riga) if esito == "revocato" else esito
    payload, stato = await rete.twitch_utente_stato(access)
    if stato == 401 and not rinnovato:  # il token è scaduto prima del previsto: un solo rinnovo
        access, esito = await _rinnova_twitch(cfg, rete, riga)
        if access is None:
            return await _scollega(cfg, rete, riga) if esito == "revocato" else esito
        payload, stato = await rete.twitch_utente_stato(access)
    if stato == 401:
        return await _scollega(cfg, rete, riga)
    if stato == 429:
        return "limite"
    profilo = logica.leggi_utente_twitch(payload) if stato == 200 else None
    if profilo is None:
        return "errore"
    twitch_id, login, tipo = profilo
    if twitch_id != riga["twitch_id"]:  # il token è di un altro canale: non ci si fida
        return await _scollega(cfg, rete, riga)
    if (login, tipo) == (riga["twitch_login"], riga["tipo"]):
        return "invariato"
    token, esito = await _token_discord(cfg, rete, riga)
    if token is None:
        return await _scollega(cfg, rete, riga) if esito == "revocato" else esito
    await ruoli_collegati_repo.aggiorna_canale(uid, login, tipo)
    scritto = await rete.discord_scrivi_stato(token, await corpo_unico(uid))
    if scritto == 200:
        return "cambiato"
    await ruoli_collegati_repo.aggiorna_canale(uid, riga["twitch_login"], riga["tipo"])  # Discord non ha accettato: si riprova al prossimo giro
    if scritto == 401:
        return await _scollega(cfg, rete, riga)
    return "limite" if scritto == 429 else "errore"


async def giro(*, cfg, rete, limite: int = MAX_PER_GIRO, pausa: float = PAUSA_TRA_PERSONE, dormi=None) -> Riepilogo:
    """Un giro. Non solleva mai: una persona che dà errore non ferma le altre."""
    dormi = dormi or asyncio.sleep
    riepilogo = Riepilogo()
    for riga in await ruoli_collegati_repo.da_aggiornare(limite):
        try:
            esito = await aggiorna_persona(cfg, rete, riga)
        except Exception:  # noqa: BLE001
            logger.warning("Ruoli collegati: giro non riuscito per l'utente %s.", riga["user_id"], exc_info=True)
            esito = "errore"
        riepilogo.controllati += 1
        if esito == "limite":
            riepilogo.fermato_per_limite = True
            logger.warning("Ruoli collegati: troppe richieste, il giro si ferma e riparte al prossimo.")
            break
        if esito == "scollegato":
            riepilogo.scollegati += 1
        elif esito == "errore":
            riepilogo.errori += 1
            await ruoli_collegati_repo.segna_giro(riga["user_id"], riuscito=False)
        else:
            riepilogo.cambiati += esito == "cambiato"
            await ruoli_collegati_repo.segna_giro(riga["user_id"], riuscito=True)
        await dormi(pausa)
    return riepilogo


async def ciclo(*, primo_ritardo: float = PRIMO_RITARDO_SECONDI, intervallo_ore: float = INTERVALLO_ORE, crea=crea_rete_da_config) -> None:
    """Il compito di fondo del pannello: si ferma con `cancel()`; un errore non lo ferma."""
    await asyncio.sleep(primo_ritardo)
    while True:
        try:
            cfg, rete = crea()
            if rete is not None and cfg.pronta:
                r = await giro(cfg=cfg, rete=rete)
                logger.info("Ruoli collegati: giro finito (%s controllati, %s cambiati, %s scollegati, %s errori).",
                            r.controllati, r.cambiati, r.scollegati, r.errori)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.warning("Ruoli collegati: giro periodico non riuscito.", exc_info=True)
        await asyncio.sleep(intervallo_ore * 3600)

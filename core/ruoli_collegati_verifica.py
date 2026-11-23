"""
core/ruoli_collegati_verifica.py
================================
Verifica con i ruoli collegati di Discord (VER-027, D111): la persona collega la verifica dal sito (`/ruoli-collegati`) e
Discord conosce tre valori: «verifica superata», «età dell'account in giorni» e «avatar presente». I server li usano come
requisito di un ruolo (Impostazioni del server, Ruoli, Collegamenti). Quando la persona supera la verifica di un server, o
quando collega, i valori si scrivono con il suo token (cifrato nel database). Nessun dato in più: l'età si ricava dall'ID.
Il corpo del collegamento unisce Twitch (ALR-049) e verifica, perché Discord ne tiene uno solo per persona.
Funzioni coperte: SPEC §24.11 (VER-027, issue #118)
Dipende da: core/ruoli_collegati_logic.py, core/ruoli_collegati_rete.py, core/repositories/ruoli_collegati_*_repo.py
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidTag

from core import ruoli_collegati_logic as logica
from core.oauth_crypto import OAuthEncryptionNotConfigured
from core.repositories.ruoli_collegati_repo import ruoli_collegati_repo
from core.repositories.ruoli_collegati_verifica_repo import ruoli_collegati_verifica_repo
from core.ruoli_collegati_rete import ReteRuoliCollegati

logger = logging.getLogger("iyokai.ruoli_collegati_verifica")

MARGINE_SCADENZA = timedelta(minutes=5)


async def corpo_unico(user_id: int, *, verifica=None, escludi_twitch: bool = False) -> dict:
    """
    Il corpo da scrivere per questa persona: Twitch (se collegato) e verifica (se collegata) insieme.
    `verifica` può essere passata se già letta; `escludi_twitch` serve a «Scollega» di Twitch (i suoi valori tornano a zero).
    """
    twitch = None if escludi_twitch else await ruoli_collegati_repo.leggi_twitch(user_id)
    if verifica is None:
        verifica = await ruoli_collegati_verifica_repo.leggi(user_id)
    valori = None
    if verifica is not None:
        valori = (verifica.verificato, logica.eta_giorni(user_id), verifica.avatar_presente)
    if twitch is not None:
        return logica.corpo_collegamento(twitch[1], twitch[2], verifica=valori)
    if escludi_twitch:  # Twitch scollegato: i suoi due valori tornano a «no», la verifica resta
        return logica.corpo_collegamento("", "", verifica=valori)
    return logica.corpo_collegamento("", "", verifica=valori, con_twitch=False)


def crea_rete_da_config() -> tuple[logica.Configurazione, ReteRuoliCollegati | None]:
    """La rete con le chiavi del bot (fuori dal sito, per il momento in cui la verifica riesce). None se manca qualcosa."""
    from core.config import config

    cfg = logica.leggi_configurazione()
    if not (cfg.verifica_pronta and config.OAUTH2_CLIENT_ID and config.OAUTH2_CLIENT_SECRET):
        return cfg, None
    rete = ReteRuoliCollegati(
        twitch_id=cfg.twitch_id, twitch_segreto=cfg.twitch_segreto, discord_id=config.OAUTH2_CLIENT_ID,
        discord_segreto=config.OAUTH2_CLIENT_SECRET, token_bot=cfg.token_bot,
    )
    return cfg, rete


async def _token_valido(cfg: logica.Configurazione, rete, user_id: int, riga) -> str | None:
    """Il token chiaro, rinnovato se sta per scadere. None se non si legge o non si rinnova."""
    try:
        token = logica.decifra(cfg.chiave_cifratura, user_id, "verifica_token", riga.token)
        in_scadenza = riga.scade_il is not None and riga.scade_il - MARGINE_SCADENZA <= datetime.now(timezone.utc)
        if not in_scadenza:
            return token
        if not riga.refresh:
            return None
        rinnovato = await rete.discord_rinnova(logica.decifra(cfg.chiave_cifratura, user_id, "verifica_refresh", riga.refresh))
    except (InvalidTag, OAuthEncryptionNotConfigured, ValueError):
        logger.info("Ruoli collegati: token della verifica non leggibile (utente %s).", user_id)
        return None
    if rinnovato is None:
        return None
    k = cfg.chiave_cifratura
    await ruoli_collegati_verifica_repo.aggiorna_token(
        user_id, logica.cifra(k, user_id, "verifica_token", rinnovato.access_token),
        logica.cifra(k, user_id, "verifica_refresh", rinnovato.refresh_token or None), rinnovato.scade_il,
    )
    return rinnovato.access_token


async def aggiorna_dopo_verifica(user_id: int, *, avatar_presente: bool, cfg=None, rete=None) -> bool:
    """
    Chiamata quando la persona supera la verifica di un server. Se ha collegato la verifica, scrive «verifica superata»
    e l'avatar di adesso. Non solleva mai: un errore qui non deve toccare la verifica del server.
    """
    try:
        riga = await ruoli_collegati_verifica_repo.leggi(user_id)
        if riga is None:
            return False
        if rete is None:
            cfg, rete = crea_rete_da_config()
        if rete is None or cfg is None:
            return False
        await ruoli_collegati_verifica_repo.aggiorna_valori(user_id, True, avatar_presente)
        token = await _token_valido(cfg, rete, user_id, riga)
        if token is None:
            return False
        corpo = await corpo_unico(user_id)
        return await rete.discord_scrivi_collegamento(token, corpo)
    except Exception:  # noqa: BLE001 - il collegamento è un di più: la verifica del server è già riuscita
        logger.warning("Ruoli collegati: aggiornamento dopo la verifica non riuscito (utente %s).", user_id, exc_info=True)
        return False


_in_corso: set[asyncio.Task] = set()


def programma_aggiornamento(user_id: int, *, avatar_presente: bool) -> None:
    """Come `aggiorna_dopo_verifica`, ma in un compito a parte: la risposta della verifica non aspetta Discord."""
    try:
        compito = asyncio.get_running_loop().create_task(aggiorna_dopo_verifica(user_id, avatar_presente=avatar_presente))
    except RuntimeError:  # nessun ciclo attivo: niente da fare
        return
    _in_corso.add(compito)
    compito.add_done_callback(_in_corso.discard)

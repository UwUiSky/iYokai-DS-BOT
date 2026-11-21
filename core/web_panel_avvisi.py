"""
core/web_panel_avvisi.py
========================
Avvisi del pannello web (CFG-006): ogni persona sceglie per categoria e per server se riceverli nel sito o in DM
(nessuno di default). Chi produce un avviso chiama `avvisa`: arriva solo a chi ha scelto quella categoria E ha
ancora un livello di accesso al pannello di quel server. Nessuna email: manca un servizio di posta configurato e
la pagina lo dice chiaramente (`email_disponibile`).
Funzioni coperte: SPEC §24.8 (CFG-006, issue #122)
Dipende da: core/repositories/web_panel_avvisi_repo.py, core/panel_bridge.py (livello di accesso)
"""

from __future__ import annotations

import logging

import discord

from core.config_schema import ImpostazioneNonValida
from core.web_panel_logic import LimiteFrequenza

logger = logging.getLogger("iyokai.web_panel_avvisi")

SITO = "sito"
DM = "dm"
SPENTO = "spento"
CATEGORIE = {
    "sicurezza": "Sicurezza (chiavi, accessi, cose rese pubbliche)",
    "modifiche": "Modifiche alla configurazione",
}
MAX_TESTO = 300
# Tre DM all'ora per persona e per server: un produttore impazzito non riempie la posta di nessuno.
_limite_dm = LimiteFrequenza(3, 3600)


def email_disponibile() -> bool:
    """Nessun servizio di posta è configurato in iYokai: le email non esistono (decisione D99)."""
    return False


def canali_disponibili() -> tuple[tuple[str, str], ...]:
    scelte = [(SPENTO, "Nessun avviso"), (SITO, "Nel sito"), (DM, "In DM")]
    if email_disponibile():  # pragma: no cover - finché non c'è un servizio di posta
        scelte.append(("email", "Per email"))
    return tuple(scelte)


async def imposta_preferenza(guild_id: int, user_id: int, categoria: str, canale: str) -> None:
    from core.repositories.web_panel_avvisi_repo import web_panel_avvisi_repo

    if categoria not in CATEGORIE:
        raise ImpostazioneNonValida("Categoria non valida.")
    if canale not in {c for c, _ in canali_disponibili()}:
        raise ImpostazioneNonValida("Questo modo di ricevere gli avvisi non è disponibile.")
    await web_panel_avvisi_repo.imposta_preferenza(guild_id, user_id, categoria, None if canale == SPENTO else canale)


async def avvisa(bot, guild, categoria: str, testo: str, *, escludi_user: int | None = None) -> int:
    """
    Manda l'avviso a chi l'ha chiesto. Ritorna quante persone lo hanno ricevuto (sito o DM). Mai eccezioni:
    un avviso mancato non deve rompere l'azione che l'ha prodotto. Chi non ha più accesso al pannello (o non si
    può verificare dalla memoria del bot) non riceve niente.
    """
    from core import panel_bridge
    from core.repositories.web_panel_avvisi_repo import web_panel_avvisi_repo

    if categoria not in CATEGORIE:
        return 0
    testo = discord.utils.escape_mentions(testo.strip())[:MAX_TESTO]
    if not testo:
        return 0
    consegnati = 0
    try:
        destinatari = await web_panel_avvisi_repo.destinatari(guild.id, categoria)
    except Exception:  # noqa: BLE001
        logger.warning("Destinatari degli avvisi non letti nel server %s.", guild.id, exc_info=True)
        return 0
    for user_id, canale in destinatari:
        if user_id == escludi_user:
            continue
        try:
            if await panel_bridge.livello_accesso(guild, user_id, chiedi_a_discord=False) is None:
                continue
            if canale == SITO:
                await web_panel_avvisi_repo.aggiungi(guild.id, user_id, categoria, testo)
                consegnati += 1
            elif canale == DM and _limite_dm.consenti(f"{guild.id}:{user_id}"):
                utente = bot.get_user(user_id) or await bot.fetch_user(user_id)
                await utente.send(f"[{guild.name}] {testo}"[:2000], allowed_mentions=discord.AllowedMentions.none())
                consegnati += 1
        except (discord.HTTPException, discord.Forbidden):
            logger.info("Avviso del pannello non consegnato a %s (DM chiusi o utente non trovato).", user_id)
        except Exception:  # noqa: BLE001
            logger.warning("Avviso del pannello non consegnato a %s.", user_id, exc_info=True)
    return consegnati

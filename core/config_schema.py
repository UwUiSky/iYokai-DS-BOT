"""
core/config_schema.py
=====================
Il punto unico (D16) per le impostazioni che comandi e pannello web
cambiano allo stesso modo: accendere o spegnere un modulo e la lingua
del server. Valida, scrive (con lo storico) e avvisa il bot.
I ruoli del bot hanno già il loro punto unico: `core.command_access.imposta_ruolo`.
Funzioni coperte: SPEC §24.3 (NF-20, issue #91)
Dipende da: core/database.py, core/premium.py (registro dei moduli), core/i18n.py
"""

from __future__ import annotations

import logging

import discord

from core.database import db
from core.i18n import lingua_valida, lingue_disponibili, testo_guild
from core.premium import registry

logger = logging.getLogger("iyokai.config_schema")

# Moduli che difendono il server: accenderli o spegnerli è una mossa da livello SECURITY, e il proprietario
# del server ne viene avvisato. Un helper con la sola «Gestisci server» non deve poterli spegnere dal pannello.
MODULI_SICUREZZA = frozenset({"anti_nuke", "anti_raid", "verify", "spam_trap", "global_ban", "lockdown"})


class ImpostazioneNonValida(ValueError):
    """Valore rifiutato. Il testo è pronto per l'utente (italiano)."""


def valida_modulo(nome: str) -> str:
    """Il nome di un modulo registrato. Rifiuta i nomi sconosciuti."""
    if not isinstance(nome, str) or registry.get(nome) is None:
        raise ImpostazioneNonValida("Questo modulo non esiste.")
    return nome


def valida_lingua(codice: str) -> str:
    """Una delle lingue del bot con testi tradotti."""
    if not lingua_valida(codice):
        raise ImpostazioneNonValida("Lingua non valida: scegli tra " + ", ".join(lingue_disponibili()) + ".")
    return codice


async def imposta_modulo(client, guild_id: int, nome: str, attivo: bool, changed_by: int | None) -> bool:
    """
    Accende o spegne un modulo. Scrive solo se lo stato cambia davvero
    (lo storico non si riempie di rumore) ed emette `modules_updated`.
    Restituisce True se ha cambiato qualcosa.
    Per i moduli di sicurezza (`MODULI_SICUREZZA`) chi cambia deve avere il livello SECURITY nel server in questo
    momento, altrimenti `ImpostazioneNonValida` e non si scrive niente; se il cambio riesce, il proprietario del
    server riceve un avviso. `changed_by` None = il sistema (nessun controllo).
    """
    valida_modulo(nome)
    attivo = bool(attivo)
    if await db.is_module_active_for_guild(guild_id, nome) == attivo:
        return False
    guild = None
    if nome in MODULI_SICUREZZA and changed_by is not None:
        guild = client.get_guild(guild_id) if client is not None else None
        if guild is None or not await _ha_livello_sicurezza(guild, changed_by):
            raise ImpostazioneNonValida("Per accendere o spegnere i moduli di sicurezza serve il permesso «Amministratore».")
    await db.set_module_active_for_guild(guild_id, nome, attivo, changed_by=changed_by)
    if client is not None:
        client.dispatch("modules_updated", guild_id, nome, attivo, changed_by)
    if guild is not None:
        await _avvisa_proprietario(guild, nome, attivo, changed_by)
    return True


async def _ha_livello_sicurezza(guild: discord.Guild, user_id: int) -> bool:
    from core.command_access import ha_livello_sicurezza
    from core.panel_bridge import membro_del_server

    return await ha_livello_sicurezza(guild, await membro_del_server(guild, user_id))


async def _avvisa_proprietario(guild: discord.Guild, nome: str, attivo: bool, changed_by: int) -> None:
    """Un messaggio al proprietario del server per ogni modulo di sicurezza cambiato da un altro. Mai un errore."""
    if changed_by == guild.owner_id:
        return
    try:
        proprietario = guild.owner or await guild.fetch_member(guild.owner_id)
        stato = await testo_guild(guild, "sicurezza_modulo_acceso" if attivo else "sicurezza_modulo_spento")
        await proprietario.send(
            await testo_guild(guild, "sicurezza_modulo_cambiato", modulo=nome, stato=stato, utente=f"<@{changed_by}>", server=discord.utils.escape_markdown(guild.name)),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except (discord.HTTPException, AttributeError):
        logger.warning("Avviso al proprietario del server %s non consegnato.", guild.id)


async def imposta_lingua_server(guild_id: int, codice: str, changed_by: int | None) -> str:
    """Salva la lingua del server (con lo storico) e la restituisce."""
    valida_lingua(codice)
    await db.set_guild_language(guild_id, codice, changed_by=changed_by)
    return codice

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

from core.database import db
from core.i18n import LINGUE, lingua_valida
from core.premium import registry


class ImpostazioneNonValida(ValueError):
    """Valore rifiutato. Il testo è pronto per l'utente (italiano)."""


def valida_modulo(nome: str) -> str:
    """Il nome di un modulo registrato. Rifiuta i nomi sconosciuti."""
    if not isinstance(nome, str) or registry.get(nome) is None:
        raise ImpostazioneNonValida("Questo modulo non esiste.")
    return nome


def valida_lingua(codice: str) -> str:
    """Una delle lingue del bot (`LINGUE`)."""
    if not lingua_valida(codice):
        raise ImpostazioneNonValida("Lingua non valida: scegli tra " + ", ".join(LINGUE) + ".")
    return codice


async def imposta_modulo(client, guild_id: int, nome: str, attivo: bool, changed_by: int | None) -> bool:
    """
    Accende o spegne un modulo. Scrive solo se lo stato cambia davvero
    (lo storico non si riempie di rumore) ed emette `modules_updated`.
    Restituisce True se ha cambiato qualcosa.
    """
    valida_modulo(nome)
    attivo = bool(attivo)
    if await db.is_module_active_for_guild(guild_id, nome) == attivo:
        return False
    await db.set_module_active_for_guild(guild_id, nome, attivo, changed_by=changed_by)
    if client is not None:
        client.dispatch("modules_updated", guild_id, nome, attivo, changed_by)
    return True


async def imposta_lingua_server(guild_id: int, codice: str, changed_by: int | None) -> str:
    """Salva la lingua del server (con lo storico) e la restituisce."""
    valida_lingua(codice)
    await db.set_guild_language(guild_id, codice, changed_by=changed_by)
    return codice

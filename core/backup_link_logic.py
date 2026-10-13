"""
core/backup_link_logic.py
=========================
Collegamento tra server principale e server di backup (D8): codice monouso
a tempo, esiti del collegamento e permessi dei link d'invito. Nessuna chiamata
a Discord: si prova senza connessione.
Funzioni coperte: SPEC §11.1, M 12.1, M 12.9
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

import discord

from core.repositories.backup_repo import BackupRepository

VALIDITA_CODICE = timedelta(hours=24)

# Senza 0, 1, I, L, O: il codice si legge e si ricopia senza errori.
ALFABETO_CODICE = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

ESITO_OK = "ok"
ESITO_SCONOSCIUTO = "sconosciuto"
ESITO_SCADUTO = "scaduto"
ESITO_GIA_USATO = "gia_usato"
ESITO_STESSO_SERVER = "stesso_server"
ESITO_GIA_COLLEGATO = "gia_collegato"
ESITO_NON_AUTORIZZATO = "non_autorizzato"


@dataclass(frozen=True)
class EsitoCollegamento:
    esito: str
    main_guild_id: int | None = None
    job_id: int | None = None


def genera_codice() -> str:
    """Codice di 12 caratteri a gruppi di 4, es. ``K7TQ-2MXB-9HVD``."""
    caratteri = [secrets.choice(ALFABETO_CODICE) for _ in range(12)]
    return "-".join("".join(caratteri[i : i + 4]) for i in range(0, 12, 4))


def hash_codice(codice: str) -> str:
    normalizzato = "".join(c for c in codice.upper() if c.isalnum())
    return hashlib.sha256(normalizzato.encode("utf-8")).hexdigest()


async def crea_codice_collegamento(
    repo: BackupRepository,
    main_guild_id: int,
    creato_da: int,
    adesso: datetime | None = None,
) -> tuple[str, datetime]:
    """Crea e salva un codice nuovo. Restituisce (codice in chiaro, scadenza)."""
    adesso = adesso or datetime.now(timezone.utc)
    scadenza = adesso + VALIDITA_CODICE
    codice = genera_codice()
    await repo.salva_codice_collegamento(main_guild_id, hash_codice(codice), creato_da, scadenza)
    return codice, scadenza


async def collega_backup(
    repo: BackupRepository,
    codice: str,
    backup_guild_id: int,
    adesso: datetime | None = None,
    utente_id: int | None = None,
    puo_collegare: Callable[[int], Awaitable[bool]] | None = None,
) -> EsitoCollegamento:
    """
    Verifica il codice, registra la coppia principale -> backup e mette in
    coda la copia, tutto in una transazione: il codice si brucia solo se
    coppia e job sono scritti. Il codice è personale (``utente_id`` deve essere
    chi lo ha creato) e ``puo_collegare(main_guild_id)`` conferma che è ancora
    admin del server principale. Rifiuta un server già in un'altra coppia,
    un main che ha già un backup o una copia già in corso.
    """
    adesso = adesso or datetime.now(timezone.utc)
    impronta = hash_codice(codice)
    riga = await repo.trova_codice_collegamento(impronta)
    if riga is None:
        return EsitoCollegamento(ESITO_SCONOSCIUTO)
    if utente_id is not None and riga["created_by"] != utente_id:
        return EsitoCollegamento(ESITO_NON_AUTORIZZATO)
    if puo_collegare is not None and not await puo_collegare(riga["main_guild_id"]):
        return EsitoCollegamento(ESITO_NON_AUTORIZZATO)

    esito, main_guild_id, job_id = await repo.collega_atomico(impronta, backup_guild_id, adesso)
    return EsitoCollegamento(esito, main_guild_id=main_guild_id, job_id=job_id)


def permessi_invito_main() -> discord.Permissions:
    """Permessi chiesti a iYokai nel server di backup (M 12.9)."""
    return discord.Permissions(
        view_channel=True,
        manage_guild=True,
        manage_roles=True,
        manage_channels=True,
        manage_webhooks=True,
        manage_expressions=True,
        create_expressions=True,
        send_messages=True,
        read_message_history=True,
        embed_links=True,
        attach_files=True,
        manage_messages=True,
    )


def permessi_invito_creator() -> discord.Permissions:
    """
    Permessi del Creator: struttura, webhook, emoji, sticker, suoni, messaggi.
    Un bot può dare ai ruoli solo i permessi che ha: la copia riduce gli altri e lo
    dice nel riepilogo. Per una copia fedele l'admin dà al Creator Amministratore.
    """
    return permessi_invito_main()


def link_invito(client_id: int, permessi: discord.Permissions) -> str:
    return discord.utils.oauth_url(client_id, permissions=permessi, scopes=["bot"])

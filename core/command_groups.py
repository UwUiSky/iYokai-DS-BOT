"""
core/command_groups.py
======================
I 16 gruppi di primo livello della mappa F7, definiti una volta sola e
usati da tutti i cog. Nomi e descrizioni italiani, `guild_only`,
permessi predefiniti e livello di accesso (core/command_access.py).
Funzioni coperte: SPEC §20 (NF-05)
Dipende da: core/command_access.py;
revisione/02-piano/MAPPA_COMANDI_F7.md §5

Nessun gruppo entra da solo nell'albero del bot: i gruppi vuoti non si
sincronizzano. `registra_gruppi_usati` aggiunge solo quelli che hanno
almeno un comando. `/owner` va aggiunto a parte, solo nel server
dell'owner (mappa §5).
"""

from __future__ import annotations

import discord
from discord import app_commands

from core.command_access import GruppoYokai, Livello

# nome: (descrizione, permesso predefinito di Discord o None, livello)
_DEFINIZIONI: dict[str, tuple[str, str | None, Livello | None]] = {
    "owner": ("Comandi riservati al proprietario del bot", "administrator", Livello.OWNER),
    "admin": ("Impianto del bot: setup, configurazione, lingua, backup, messaggi", "manage_guild", Livello.ADMIN),
    "gestione": ("Gestione del server: ticket, vocali, economia, ruoli, benvenuto", "manage_guild", Livello.ADMIN),
    "moduli": ("Moduli del server: alert, starboard, contatori, compleanni", "manage_guild", Livello.ADMIN),
    "security": ("Sicurezza: anti-raid, anti-nuke, verifica, ban globale", "administrator", Livello.SECURITY),
    "automod": ("Moderazione automatica: filtri, parole vietate, esenzioni", "manage_guild", Livello.ADMIN),
    "mod": ("Moderazione: avvisi, timeout, silenzio, pulizia, blocco canali", "moderate_members", Livello.MOD),
    "modban": ("Moderazione dura: ban, kick, softban e sban", "ban_members", Livello.MODBAN),
    "log": ("Registro degli eventi: canali, stato, ricerca ed esportazione", "manage_guild", Livello.LOG),
    "ticket": ("Gestione del ticket in cui ti trovi", None, None),
    "voice": ("Gestione del tuo canale vocale temporaneo", None, None),
    "music": ("Musica nei canali vocali", None, None),
    "level": ("Livelli, monete, negozio e classifiche", None, None),
    "clan": ("Clan del server: crea, gestisci e fai crescere il tuo clan", None, None),
    "fun": ("Giochi, immagini e divertimento", None, None),
    "utility": ("Strumenti utili: segnalazioni, suggerimenti, promemoria, ricerca comandi", None, None),
}


def nomi_gruppi() -> tuple[str, ...]:
    """I nomi dei 16 gruppi, nell'ordine della mappa."""
    return tuple(_DEFINIZIONI)


def costruisci_gruppi() -> dict[str, GruppoYokai]:
    """Costruisce un insieme NUOVO di gruppi (per i test; il bot usa GRUPPI)."""
    gruppi: dict[str, GruppoYokai] = {}
    for nome, (descrizione, permesso, livello) in _DEFINIZIONI.items():
        gruppi[nome] = GruppoYokai(
            name=nome,
            description=descrizione,
            guild_only=True,
            default_permissions=discord.Permissions(**{permesso: True}) if permesso else None,
            livello=livello,
        )
    return gruppi


GRUPPI: dict[str, GruppoYokai] = costruisci_gruppi()


def ottieni_gruppo(nome: str) -> GruppoYokai:
    """Il gruppo di primo livello con questo nome (KeyError se non esiste)."""
    return GRUPPI[nome]


def aggiungi_a_gruppo(
    nome: str,
    comando: app_commands.Command | app_commands.Group,
    *,
    sottogruppo: tuple[str, str] | None = None,
    gruppi: dict[str, GruppoYokai] | None = None,
) -> None:
    """
    Aggiunge un comando al gruppo `nome`, o a un suo sotto-gruppo
    (`sottogruppo=("nome", "descrizione")`, creato la prima volta).
    Si può richiamare più volte con lo stesso comando (un cog che si
    ricarica): sostituisce, non duplica.
    """
    tutti = GRUPPI if gruppi is None else gruppi
    destinazione: app_commands.Group = tutti[nome]
    if sottogruppo is not None:
        nome_sotto, descrizione_sotto = sottogruppo
        esistente = destinazione.get_command(nome_sotto)
        if esistente is None:
            esistente = GruppoYokai(name=nome_sotto, description=descrizione_sotto, parent=destinazione)
        destinazione = esistente
    destinazione.add_command(comando, override=True)


def registra_gruppi_usati(
    tree: app_commands.CommandTree,
    *,
    gruppi: dict[str, GruppoYokai] | None = None,
) -> list[str]:
    """Aggiunge all'albero i gruppi che hanno comandi (tranne `owner`). Restituisce i nomi."""
    tutti = GRUPPI if gruppi is None else gruppi
    aggiunti = []
    for nome, gruppo in tutti.items():
        if nome == "owner" or not gruppo.commands:
            continue
        tree.add_command(gruppo, override=True)
        aggiunti.append(nome)
    return aggiunti

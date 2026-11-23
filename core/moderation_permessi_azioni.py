"""
core/moderation_permessi_azioni.py
==================================
Permesso per singola azione di moderazione dato a un ruolo (CFG-024): un ruolo può usare «timeout» senza avere
il permesso di Discord né il ruolo mod, e non può per questo bannare. Il controllo sta in `core/command_access.py`
(punto unico); restano sempre i controlli di gerarchia dei comandi. Mai per `@everyone`, mai per un ruolo pari
o sopra chi lo concede (salvo il proprietario), al massimo 25 ruoli per server. Le azioni di massa non si concedono.
Funzioni coperte: CFG-024, VER-018 (azione «verifica»)
"""

from __future__ import annotations

import discord

from core.database import db

MAX_RUOLI = 25

# Percorso completo del comando -> azione concedibile.
COMANDI = {
    "mod-sanzioni warn": "warn",
    "mod-sanzioni timeout": "timeout",
    "mod-sanzioni untimeout": "timeout",
    "mod-sanzioni mute": "mute",
    "mod-sanzioni unmute": "mute",
    "mod-sanzioni quarantena": "quarantena",
    "mod-sanzioni libera": "quarantena",
    "mod-sanzioni shadowban dai": "shadowban",
    "mod-sanzioni shadowban togli": "shadowban",
    "mod-sanzioni shadowban canali": "shadowban",
    "mod-ban kick": "kick",
    "mod-ban ban": "ban",
    "mod-ban tempban": "tempban",
    "mod-ban softban": "softban",
    "mod-ban unban": "unban",
    # VER-018: lo staff che verifica a mano senza essere amministratore (livello «security» del gruppo).
    "admin-sicurezza verify manuale": "verifica",
    "admin-sicurezza verify invia": "verifica",
}
AZIONI = tuple(dict.fromkeys(COMANDI.values()))
# Dove vale un'azione: le sanzioni ai livelli mod e modban, la verifica a mano al livello security.
LIVELLI_DELL_AZIONE = {"verifica": ("security",)}
LIVELLI_DI_BASE = ("mod", "modban")


def azione_del_comando(interaction: discord.Interaction) -> str | None:
    comando = getattr(interaction, "command", None)
    nome = getattr(comando, "qualified_name", None)
    return COMANDI.get(nome) if isinstance(nome, str) else None


async def azioni_dei_ruoli(guild_id: int, ruoli_ids) -> set[str]:
    ruoli = [int(r) for r in ruoli_ids if int(r) != guild_id]
    if not ruoli:
        return set()
    righe = await db.pool.fetch(
        "SELECT DISTINCT azione FROM moderation_ruoli_azioni WHERE guild_id = $1 AND role_id = ANY($2::bigint[])",
        guild_id, ruoli,
    )
    return {r["azione"] for r in righe}


async def consente(interaction: discord.Interaction, livello_valore: str, azione: str | None = None) -> bool:
    """True se un ruolo di chi comanda ha ricevuto questa azione. `azione` si dà per i tasti (nessun comando)."""
    guild, utente = interaction.guild, interaction.user
    if guild is None or not isinstance(utente, discord.Member):
        return False
    azione = azione or azione_del_comando(interaction)
    if azione is None or azione not in AZIONI:
        return False
    if livello_valore not in LIVELLI_DELL_AZIONE.get(azione, LIVELLI_DI_BASE):
        return False
    try:
        concesse = await azioni_dei_ruoli(guild.id, [r.id for r in utente.roles if guild.get_role(r.id) is not None])
    except Exception:  # un errore del database non deve aprire una porta: vale il rifiuto
        return False
    return azione in concesse


def errore_concessione(guild: discord.Guild, ruolo: discord.Role, autore: discord.Member) -> str | None:
    if ruolo.is_default():
        return "Non puoi usare @everyone."
    if ruolo.managed:
        return "Questo ruolo è gestito da un'integrazione."
    if autore.id != guild.owner_id and ruolo >= autore.top_role:
        return "Questo ruolo è pari o sopra il tuo ruolo più alto."
    return None


async def concedi(guild: discord.Guild, ruolo: discord.Role, azione: str, autore: discord.Member) -> str | None:
    """Restituisce l'errore da mostrare, o None se fatto."""
    if azione not in AZIONI:
        return "Azione non concedibile."
    errore = errore_concessione(guild, ruolo, autore)
    if errore:
        return errore
    gia = await db.pool.fetchval(
        "SELECT COUNT(DISTINCT role_id) FROM moderation_ruoli_azioni WHERE guild_id = $1 AND role_id <> $2", guild.id, ruolo.id
    )
    if gia >= MAX_RUOLI:
        return f"Al massimo {MAX_RUOLI} ruoli."
    await db.ensure_guild_exists(guild.id)
    await db.pool.execute(
        "INSERT INTO moderation_ruoli_azioni (guild_id, role_id, azione, dato_da) VALUES ($1, $2, $3, $4) "
        "ON CONFLICT DO NOTHING", guild.id, ruolo.id, azione, autore.id,
    )
    return None


async def togli(guild_id: int, role_id: int, azione: str | None) -> int:
    """Toglie una azione (o tutte) a un ruolo. Restituisce quante righe."""
    esito = await db.pool.execute(
        "DELETE FROM moderation_ruoli_azioni WHERE guild_id = $1 AND role_id = $2 AND ($3::text IS NULL OR azione = $3)",
        guild_id, role_id, azione,
    )
    return int(esito.split()[-1])


async def elenco(guild_id: int) -> dict[int, list[str]]:
    righe = await db.pool.fetch(
        "SELECT role_id, azione FROM moderation_ruoli_azioni WHERE guild_id = $1 ORDER BY role_id, azione", guild_id
    )
    risultato: dict[int, list[str]] = {}
    for r in righe:
        risultato.setdefault(r["role_id"], []).append(r["azione"])
    return risultato

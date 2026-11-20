"""
core/permessi_vista.py
======================
Chi può fare cosa nel bot (#122): l'elenco dei ruoli scelti per lo staff con i gruppi che aprono (CFG-022, CFG-023)
e il livello di permesso di un membro con il motivo (CFG-026). Non decide niente di nuovo: usa le stesse regole di
`core/command_access.py`, così la risposta coincide con ciò che il bot farà davvero.
Funzioni coperte: SPEC §20 (NF-05), catalogo #122 (CFG-022, CFG-023, CFG-026)
Dipende da: core/command_access.py, core/command_permissions.py (gruppi di ogni ruolo)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import discord

from core.command_access import _REGOLE, Livello, TipoRuolo, decidi_accesso, leggi_ruolo
from core.config import config

MOTIVO_NESSUNO = "nessuno"
MOTIVO_PROPRIETARIO_BOT = "proprietario_bot"
MOTIVO_PROPRIETARIO = "proprietario"
MOTIVO_PERMESSO = "permesso"
MOTIVO_RUOLO = "ruolo"

# Dal più alto al più basso, come li mostra il comando.
ORDINE_LIVELLI = (
    Livello.OWNER,
    Livello.FOUNDER,
    Livello.SECURITY,
    Livello.ADMIN,
    Livello.LOG,
    Livello.MODBAN,
    Livello.MOD,
)


@dataclass(frozen=True)
class VoceLivello:
    livello: Livello
    motivo: str

    @property
    def ha(self) -> bool:
        return self.motivo != MOTIVO_NESSUNO


@dataclass(frozen=True)
class RuoloStaff:
    tipo: TipoRuolo
    ruolo_id: int | None
    esiste: bool
    gruppi: tuple[str, ...]


def motivo_accesso(
    livello: Livello,
    *,
    user_id: int,
    owner_bot_id: int,
    guild_owner_id: int | None,
    permessi: discord.Permissions,
    ruoli_utente_ids: Iterable[int],
    ruolo_configurato_id: int | None,
    ruolo_esiste: bool = True,
) -> str:
    """Perché un utente ha (o non ha) un livello. Coerente con `decidi_accesso`: stesso esito, in più il motivo."""
    ruoli = list(ruoli_utente_ids)
    ha = decidi_accesso(
        livello,
        user_id=user_id,
        owner_bot_id=owner_bot_id,
        guild_owner_id=guild_owner_id,
        permessi=permessi,
        ruoli_utente_ids=ruoli,
        ruolo_configurato_id=ruolo_configurato_id,
        ruolo_esiste=ruolo_esiste,
    )
    if not ha:
        return MOTIVO_NESSUNO
    if livello is Livello.OWNER:
        return MOTIVO_PROPRIETARIO_BOT
    if guild_owner_id is not None and user_id == guild_owner_id:
        return MOTIVO_PROPRIETARIO
    permesso, _ = _REGOLE[livello] if livello in _REGOLE else (None, None)
    if permesso is not None and getattr(permessi, permesso):
        return MOTIVO_PERMESSO
    return MOTIVO_RUOLO


async def livelli_del_membro(guild: discord.Guild, membro: discord.Member) -> list[VoceLivello]:
    """Per ogni livello del bot: ce l'ha il membro, e perché."""
    risultato = []
    for livello in ORDINE_LIVELLI:
        configurato = None
        if livello in _REGOLE:
            configurato = await leggi_ruolo(guild.id, _REGOLE[livello][1])
        motivo = motivo_accesso(
            livello,
            user_id=membro.id,
            owner_bot_id=config.OWNER_ID,
            guild_owner_id=guild.owner_id,
            permessi=membro.guild_permissions,
            ruoli_utente_ids=[r.id for r in membro.roles],
            ruolo_configurato_id=configurato,
            ruolo_esiste=configurato is not None and guild.get_role(configurato) is not None,
        )
        risultato.append(VoceLivello(livello, motivo))
    return risultato


async def ruoli_dello_staff(guild: discord.Guild) -> list[RuoloStaff]:
    """I tre ruoli del bot (admin, mod, ban) con i gruppi di comandi che aprono."""
    from core.command_permissions import GRUPPI_DEL_RUOLO

    voci = []
    for tipo in TipoRuolo:
        ruolo_id = await leggi_ruolo(guild.id, tipo)
        voci.append(
            RuoloStaff(tipo, ruolo_id, ruolo_id is not None and guild.get_role(ruolo_id) is not None, GRUPPI_DEL_RUOLO[tipo])
        )
    return voci

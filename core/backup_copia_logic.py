"""
core/backup_copia_logic.py
==========================
Copia di un canale (per una categoria anche i canali dentro) e di un ruolo
(a scelta con i suoi permessi nei canali) dentro lo stesso server, una
chiamata alla volta e nei tetti di Discord (500 canali, 250 ruoli).
Funzioni coperte: BKP-024, BKP-025
"""

from __future__ import annotations

from dataclasses import dataclass

import discord

from core.backup_clone_logic import _overwrite_consentito, _permessi_consentiti
from core.backup_mirror_logic import NOME_CANALE_OFFUSCATO

MAX_CANALI = 500
MAX_RUOLI = 250
MOTIVO = "Copia con /backup di iYokai"


@dataclass
class EsitoCopia:
    nuovo: object | None = None
    copiati: int = 0
    saltati: int = 0
    falliti: int = 0
    errore: str | None = None


async def copia_canale(guild: discord.Guild, canale, nome: str | None = None) -> EsitoCopia:
    """Il canale con i permessi; per una categoria anche i canali dentro (in ordine)."""
    esito = EsitoCopia()
    if canale.name == NOME_CANALE_OFFUSCATO:
        esito.errore = "Questo canale è nascosto al bot: non si può copiare."
        return esito
    totale = len(guild.channels)
    if totale >= MAX_CANALI:
        esito.errore = f"Il server ha già {MAX_CANALI} canali."
        return esito
    esito.nuovo = await canale.clone(name=(nome or canale.name)[:100], reason=MOTIVO)
    esito.copiati = 1
    totale += 1
    if canale.type != discord.ChannelType.category:
        return esito
    for figlio in sorted(canale.channels, key=lambda c: c.position):
        if figlio.name == NOME_CANALE_OFFUSCATO or totale >= MAX_CANALI:
            esito.saltati += 1
            continue
        try:
            await figlio.clone(category=esito.nuovo, reason=MOTIVO)
            esito.copiati += 1
            totale += 1
        except discord.HTTPException:
            esito.falliti += 1
    return esito


async def copia_ruolo(
    guild: discord.Guild, ruolo: discord.Role, nome: str | None = None, permessi_canali: bool = False
) -> EsitoCopia:
    """Il ruolo con i suoi permessi; a scelta anche i permessi nei canali dove compare."""
    esito = EsitoCopia()
    if ruolo.is_default() or ruolo.managed:
        esito.errore = "@everyone e i ruoli delle integrazioni non si possono copiare."
        return esito
    if len(guild.roles) >= MAX_RUOLI:
        esito.errore = f"Il server ha già {MAX_RUOLI} ruoli."
        return esito
    permessi = _permessi_consentiti(guild, ruolo.permissions)
    esito.nuovo = await guild.create_role(
        name=(nome or ruolo.name)[:100], permissions=permessi, colour=ruolo.colour,
        hoist=ruolo.hoist, mentionable=ruolo.mentionable, reason=MOTIVO,
    )
    esito.copiati = 1
    if permessi != ruolo.permissions:
        esito.saltati += 1  # permessi che il bot non ha: tolti
    if not permessi_canali:
        return esito
    for canale in guild.channels:
        overwrite = canale.overwrites.get(ruolo) if canale.name != NOME_CANALE_OFFUSCATO else None
        if overwrite is None:
            continue
        try:
            await canale.set_permissions(esito.nuovo, overwrite=_overwrite_consentito(guild, overwrite), reason=MOTIVO)
            esito.copiati += 1
        except discord.HTTPException:
            esito.falliti += 1
    return esito

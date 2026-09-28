"""
tests/test_command_policy.py
================================
Controlla sull'albero comandi reale (tutti i cog caricati) chi può
vedere ogni comando: ogni comando top-level deve avere un pubblico
dichiarato in tests/support/command_policy.py, e i comandi staff/owner
devono avere `default_permissions` (REVIEW.md §6, SEC-1, LC-2).

Gli elenchi KNOWN_* in command_policy.py sono un cricchetto: contengono
i problemi ancora aperti. Se un comando viene sistemato ma resta
nell'elenco, il test fallisce e chiede di toglierlo; così l'elenco può
solo accorciarsi.
"""

import pytest

from tests.support.command_policy import (
    AUDIENCE,
    KNOWN_MISSING_DEFAULT_PERMISSIONS,
    KNOWN_NOT_GUILD_ONLY,
    OWNER,
    STAFF,
)
from tests.support.full_tree import build_full_bot, close_full_bot, connect_db_if_needed
from core.database import db


@pytest.fixture
async def full_tree():
    connesso_qui = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert falliti == [], f"Cog non caricati: {falliti}"
        yield {cmd.name: cmd for cmd in bot.tree.get_commands()}
    finally:
        await close_full_bot(bot)
        if connesso_qui:
            await db.close()


async def test_ogni_comando_top_level_ha_un_pubblico_dichiarato(full_tree):
    senza_pubblico = sorted(set(full_tree) - set(AUDIENCE))
    assert senza_pubblico == [], (
        "Comandi nuovi senza pubblico dichiarato: aggiungili ad AUDIENCE in "
        f"tests/support/command_policy.py: {senza_pubblico}"
    )
    spariti = sorted(set(AUDIENCE) - set(full_tree))
    assert spariti == [], f"Comandi in AUDIENCE che non esistono più: {spariti}"


async def test_comandi_staff_e_owner_hanno_default_permissions(full_tree):
    mancanti = {
        nome
        for nome, cmd in full_tree.items()
        if AUDIENCE.get(nome) in (STAFF, OWNER) and cmd.default_permissions is None
    }
    nuovi = sorted(mancanti - KNOWN_MISSING_DEFAULT_PERMISSIONS)
    assert nuovi == [], f"Comandi staff/owner senza default_permissions: {nuovi}"

    sistemati = sorted(KNOWN_MISSING_DEFAULT_PERMISSIONS - mancanti)
    assert sistemati == [], (
        "Questi comandi ora hanno default_permissions: toglili da "
        f"KNOWN_MISSING_DEFAULT_PERMISSIONS: {sistemati}"
    )


async def test_comandi_disponibili_solo_nei_server(full_tree):
    non_guild_only = {nome for nome, cmd in full_tree.items() if not cmd.guild_only}
    nuovi = sorted(non_guild_only - KNOWN_NOT_GUILD_ONLY)
    assert nuovi == [], f"Comandi usabili anche in DM: {nuovi}"

    sistemati = sorted(KNOWN_NOT_GUILD_ONLY - non_guild_only)
    assert sistemati == [], (
        f"Questi comandi ora sono guild_only: toglili da KNOWN_NOT_GUILD_ONLY: {sistemati}"
    )

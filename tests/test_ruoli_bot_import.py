"""
tests/test_ruoli_bot_import.py
==============================
Import e rollback della configurazione: un ruolo mod o ban del bot nuovo nel file lo accetta solo chi ha già
su Discord il permesso corrispondente (blocco A, voce 3), come per il ruolo admin (D28).
"""

from unittest.mock import AsyncMock

import discord

import cogs.utility.config_history as storico
from tests.support.discord_fakes import fake_guild, fake_member


async def test_import_con_ruolo_ban_nuovo_rifiutato_senza_il_permesso(monkeypatch):
    monkeypatch.setattr(storico, "leggi_ruolo", AsyncMock(return_value=None))
    guild = fake_guild(guild_id=77, owner_id=1)
    helper = fake_member(5, guild_permissions=discord.Permissions(manage_guild=True, moderate_members=True))
    assert await storico.errore_cambio_ruolo_admin(guild, helper, {"modban_role_id": 900}) is not None
    assert await storico.errore_cambio_ruolo_admin(guild, helper, {"mod_role_id": 900}) is None
    assert await storico.errore_cambio_ruolo_admin(guild, helper, {"modban_role_id": None}) is None
    proprietario = fake_member(1)
    assert await storico.errore_cambio_ruolo_admin(guild, proprietario, {"modban_role_id": 900}) is None

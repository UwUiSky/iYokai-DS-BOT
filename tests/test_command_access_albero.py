"""
tests/test_command_access_albero.py
===================================
Il controllo di accesso dei gruppi tiene davvero, passando da
`Command._check_can_run` (la strada di discord.py), non chiamando a mano
`interaction_check`. Albero vero con `aggiungi_a_gruppo`.
Funzioni coperte: NF-05 (issue #76)
"""

from __future__ import annotations

import types

import discord
import pytest
from discord import app_commands

from core import command_access as ca
from core import command_groups as cg
from core.command_access import GruppoYokai, Livello
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role
from tests.support.full_tree import build_full_bot, close_full_bot, connect_db_if_needed


class _FakeDb:
    async def get_guild_setting(self, guild_id, key, default=None):
        return default


@pytest.fixture(autouse=True)
def _finti(monkeypatch):
    monkeypatch.setattr(ca, "db", _FakeDb())
    monkeypatch.setattr(ca, "config", types.SimpleNamespace(OWNER_ID=1))


async def _cb(interaction: discord.Interaction):  # pragma: no cover
    pass


def _ix(perm=None):
    membro = fake_member(
        user_id=3,
        guild_permissions=discord.Permissions(**{perm: True}) if perm else discord.Permissions.none(),
    )
    return fake_interaction(guild=fake_guild(guild_id=77, owner_id=2), user=membro)


def _comando(nome="c"):
    return app_commands.Command(name=nome, description="Prova", callback=_cb)


async def test_comando_sotto_un_livello_viene_bloccato_da_check_can_run():
    gruppi = cg.costruisci_gruppi()
    cmd = _comando()
    cg.aggiungi_a_gruppo("mod", cmd, gruppi=gruppi)
    with pytest.raises(ca.AccessoNegato):
        await cmd._check_can_run(_ix())
    assert await cmd._check_can_run(_ix("moderate_members")) is True


async def test_comando_in_un_sottogruppo_viene_bloccato_da_check_can_run():
    gruppi = cg.costruisci_gruppi()
    cmd = _comando()
    cg.aggiungi_a_gruppo("modban", cmd, sottogruppo=("sotto", "Sotto-gruppo"), gruppi=gruppi)
    with pytest.raises(ca.AccessoNegato):
        await cmd._check_can_run(_ix())
    assert await cmd._check_can_run(_ix("ban_members")) is True


async def test_gruppi_senza_livello_restano_aperti():
    gruppi = cg.costruisci_gruppi()
    cmd = _comando()
    cg.aggiungi_a_gruppo("fun", cmd, sottogruppo=("sotto", "Sotto-gruppo"), gruppi=gruppi)
    assert await cmd._check_can_run(_ix()) is True


def test_un_group_semplice_sotto_un_gruppo_protetto_viene_rifiutato():
    gruppi = cg.costruisci_gruppi()
    with pytest.raises(TypeError):
        app_commands.Group(name="aperto", description="Senza controllo", parent=gruppi["admin"])
    with pytest.raises(TypeError):
        gruppi["admin"].add_command(app_commands.Group(name="aperto2", description="Senza controllo"))


def test_un_group_semplice_sotto_un_gruppo_aperto_e_ammesso():
    gruppi = cg.costruisci_gruppi()
    app_commands.Group(name="libero", description="Libero", parent=gruppi["fun"])


async def test_albero_vero_ogni_group_sotto_un_gruppo_protetto_e_un_gruppoyokai():
    creato_qui = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti, falliti
        for radice in bot.tree.get_commands():
            if not isinstance(radice, app_commands.Group) or getattr(radice, "livello", None) is None:
                continue
            for figlio in radice.commands:
                if isinstance(figlio, app_commands.Group):
                    assert isinstance(figlio, GruppoYokai), (
                        f"'{radice.name} {figlio.name}' è un Group semplice sotto un gruppo "
                        f"protetto: passerebbe a chiunque. Usa GruppoYokai."
                    )
    finally:
        await close_full_bot(bot)
        if creato_qui:
            from core.database import db as db_singleton

            await db_singleton.close()


async def test_albero_costruito_con_i_gruppi_veri_registra_e_blocca():
    from discord.ext import commands

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    gruppi = cg.costruisci_gruppi()
    cmd = _comando("ban")
    cg.aggiungi_a_gruppo("modban", cmd, gruppi=gruppi)
    cg.registra_gruppi_usati(bot.tree, gruppi=gruppi)
    trovato = bot.tree.get_command("modban").get_command("ban")
    with pytest.raises(ca.AccessoNegato):
        await trovato._check_can_run(_ix())

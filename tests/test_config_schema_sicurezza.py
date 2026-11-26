"""
tests/test_config_schema_sicurezza.py
=====================================
Blocco A, voce 3: accendere o spegnere un modulo di sicurezza richiede il livello SECURITY (come i comandi
`admin-sicurezza…`) e avvisa il proprietario del server. Vale per ogni via che passa da `imposta_modulo`
(pannello, procedura guidata, assistente). Un test elenca i moduli e fallisce se uno esce dalla regola.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import core.config_schema as schema
import core.database as database_module
from core.config_schema import MODULI_SICUREZZA, ImpostazioneNonValida, imposta_modulo
from core.database import db
from core.premium import PremiumModule, registry
from tests.support.discord_fakes import fake_guild, fake_member

GUILD = 9200
PROPRIETARIO = 1


@pytest.fixture
def mondo(monkeypatch, clean_db, reset_premium_registry):
    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    for nome in MODULI_SICUREZZA:
        # Se un altro test ha già importato il cog vero, il modulo è registrato con la sua dichiarazione:
        # si usa quello (registrarne uno diverso con lo stesso nome è vietato dal registro).
        if registry.get(nome) is None:
            registry.register(PremiumModule(nome, nome, "prova", category="security"))
    guild = fake_guild(guild_id=GUILD, owner_id=PROPRIETARIO)
    guild.owner = MagicMock(send=AsyncMock())
    guild.get_role.return_value = None
    membri = {}
    monkeypatch.setattr("core.panel_bridge.membro_del_server", AsyncMock(side_effect=lambda g, uid: membri.get(uid)))
    monkeypatch.setattr("core.command_access.leggi_ruolo", AsyncMock(return_value=None))
    client = MagicMock()
    client.get_guild.return_value = guild
    return client, guild, membri


def test_i_moduli_di_sicurezza_sono_questi_sei():
    assert MODULI_SICUREZZA == {"anti_nuke", "anti_raid", "verify", "spam_trap", "global_ban", "lockdown"}


@pytest.mark.parametrize("nome", sorted(MODULI_SICUREZZA))
async def test_chi_ha_solo_gestisci_server_non_tocca_la_sicurezza(mondo, nome):
    client, guild, membri = mondo
    membri[5] = fake_member(5, guild_permissions=discord.Permissions(manage_guild=True, ban_members=True))
    with pytest.raises(ImpostazioneNonValida):
        await imposta_modulo(client, GUILD, nome, True, 5)
    assert await db.is_module_active_for_guild(GUILD, nome) is False
    client.dispatch.assert_not_called()
    guild.owner.send.assert_not_awaited()


async def test_chi_ha_amministratore_passa_e_il_proprietario_viene_avvisato(mondo):
    client, guild, membri = mondo
    membri[6] = fake_member(6, guild_permissions=discord.Permissions(administrator=True))
    assert await imposta_modulo(client, GUILD, "anti_nuke", True, 6) is True
    assert await db.is_module_active_for_guild(GUILD, "anti_nuke") is True
    guild.owner.send.assert_awaited_once()
    assert "<@6>" in guild.owner.send.call_args.args[0]
    assert guild.owner.send.call_args.kwargs["allowed_mentions"].users is False


async def test_il_proprietario_non_si_avvisa_da_solo(mondo):
    client, guild, membri = mondo
    membri[PROPRIETARIO] = fake_member(PROPRIETARIO)
    assert await imposta_modulo(client, GUILD, "lockdown", True, PROPRIETARIO) is True
    guild.owner.send.assert_not_awaited()


async def test_senza_server_o_senza_membro_si_rifiuta(mondo):
    client, guild, membri = mondo
    with pytest.raises(ImpostazioneNonValida):
        await imposta_modulo(client, GUILD, "verify", True, 77)  # non è nel server
    with pytest.raises(ImpostazioneNonValida):
        await imposta_modulo(None, GUILD, "verify", True, 77)  # niente bot, niente controllo: si rifiuta


async def test_gli_altri_moduli_non_cambiano(mondo):
    client, guild, membri = mondo
    registry.register(PremiumModule("fun_prova", "Fun", "prova", category="fun"))
    assert await imposta_modulo(client, GUILD, "fun_prova", True, 77) is True
    guild.owner.send.assert_not_awaited()

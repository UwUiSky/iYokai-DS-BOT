"""
tests/test_permission_heatmap_limiti.py
=======================================
/permission-heatmap con molti ruoli critici (LIM-14): la descrizione
di un embed tiene 4096 caratteri. L'elenco si ferma prima e dice
quanti ruoli sono rimasti fuori.
"""

import re
from unittest.mock import create_autospec

import discord
import pytest

import cogs.security.permission_heatmap as modulo
from core.database import Database
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_role


@pytest.fixture
def db_finto(monkeypatch):
    finto = create_autospec(Database, instance=True)
    finto.is_module_active_for_guild.return_value = True
    monkeypatch.setattr(modulo, "db", finto)
    return finto


def _server_con_ruoli_critici(quanti: int, lunghezza_nome: int):
    server = fake_guild()
    server.roles = []
    for numero in range(quanti):
        ruolo = fake_role(
            role_id=1000 + numero,
            name=f"{numero:03d}".ljust(lunghezza_nome, "r"),
            permissions=discord.Permissions.all(),
        )
        ruolo.members = []
        server.roles.append(ruolo)
    return server


async def test_heatmap_con_sessanta_ruoli_critici_resta_un_embed_valido(db_finto):
    server = _server_con_ruoli_critici(60, lunghezza_nome=100)
    interazione = fake_interaction(guild=server)
    cog = modulo.PermissionHeatmapCog(bot=None)

    await cog.permission_heatmap.callback(cog, interazione)

    embed = interazione.response.send_message.call_args.kwargs["embed"]
    assert len(embed.description) <= 4096

    mostrati = sum(1 for ruolo in server.roles if ruolo.name in embed.description)
    esclusi = re.search(r"e altri (\d+) ruoli", embed.description)
    assert esclusi is not None, embed.description[-200:]
    assert 0 < mostrati < 60
    assert mostrati + int(esclusi.group(1)) == 60


async def test_heatmap_con_pochi_ruoli_li_mostra_tutti(db_finto):
    server = _server_con_ruoli_critici(3, lunghezza_nome=10)
    interazione = fake_interaction(guild=server)
    cog = modulo.PermissionHeatmapCog(bot=None)

    await cog.permission_heatmap.callback(cog, interazione)

    embed = interazione.response.send_message.call_args.kwargs["embed"]
    assert all(ruolo.name in embed.description for ruolo in server.roles)
    assert "altri" not in embed.description

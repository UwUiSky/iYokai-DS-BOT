"""
tests/test_schede.py
====================
Catalogo #128 e #123: `/utility scheda` (utente, server, canale, ruolo,
ruoli, membri, anzianità, permessi). Testi puri e comandi del cog.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.schede as modulo
from cogs.utility.schede import SchedeCog
from core.schede_logic import (
    MAX_CAMPO,
    classifica_anzianita,
    data_discord,
    elenco_menzioni,
    righe_permessi,
    righe_ruoli,
)
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role
from tests.support.percorsi import comando_nel_gruppo


def _data(anno):
    return datetime(anno, 1, 1, tzinfo=timezone.utc)


def test_data_nel_formato_di_discord():
    assert data_discord(_data(2026)) == f"<t:{int(_data(2026).timestamp())}:D>"
    assert data_discord(None) == "—"


def test_elenco_menzioni_non_supera_il_campo():
    voci = [f"<@&{i:018d}>" for i in range(200)]
    testo = elenco_menzioni(voci)
    assert len(testo) <= MAX_CAMPO and testo.endswith(tuple(f"+{n}" for n in range(1, 200)))


def test_righe_ruoli_dal_piu_alto_con_avviso_everyone():
    alto = fake_role(2, "Staff", position=5, permissions=discord.Permissions(mention_everyone=True))
    basso = fake_role(1, "Base", position=1)
    for r in (alto, basso):
        r.members = [object()] * r.id
        r.colour = discord.Colour(0x112233)
    righe = righe_ruoli([basso, fake_role(0, "@everyone", position=0), alto])
    assert len(righe) == 2
    assert righe[0].startswith("`2`") and "può menzionare @everyone" in righe[0]
    assert "1 membri" in righe[1]


def test_classifica_anzianita():
    a, b, c = fake_member(1), fake_member(2), fake_member(3)
    a.created_at, b.created_at, c.created_at = _data(2020), _data(2016), _data(2024)
    righe = classifica_anzianita([a, b, c], "account-vecchi")
    assert [r.split()[1] for r in righe] == ["<@2>", "<@1>", "<@3>"]
    assert classifica_anzianita([a, b, c], "account-nuovi")[0].split()[1] == "<@3>"


def test_righe_permessi():
    si, no = righe_permessi(discord.Permissions(send_messages=True, view_channel=True))
    assert "send_messages" in si and "manage_roles" in no


@pytest.mark.asyncio
async def test_utente_mostra_scheda_effimera():
    cog = SchedeCog(MagicMock())
    membro = fake_member(5, "tizio", roles=[fake_role(0, "@everyone", position=0), fake_role(9, "VIP", position=3)])
    membro.created_at, membro.joined_at, membro.premium_since = _data(2020), _data(2024), None
    it = fake_interaction()
    await cog.utente.callback(cog, it, membro)
    embed = it.response.send_message.await_args.kwargs["embed"]
    valori = {f.name: f.value for f in embed.fields}
    assert valori["ID"] == "`5`" and valori["Ruoli (1)"] == "<@&9>"
    assert it.response.send_message.await_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_anzianita_scarica_i_membri_e_va_a_pagine(monkeypatch):
    cog = SchedeCog(MagicMock())
    server = fake_guild()
    server.chunked = False
    server.chunk = AsyncMock()
    m = fake_member(5)
    m.joined_at = _data(2025)
    server.members = [m]
    invia = AsyncMock()
    monkeypatch.setattr(modulo, "invia_a_pagine", invia)
    it = fake_interaction(guild=server)
    await cog.anzianita.callback(cog, it, "primi-entrati")
    server.chunk.assert_awaited_once()
    assert invia.await_args.args[2][0].startswith("1. <@5>")
    assert invia.await_args.kwargs["dopo_defer"] is True


@pytest.mark.asyncio
async def test_permessi_del_bot_per_predefinito():
    cog = SchedeCog(MagicMock())
    server = fake_guild()
    canale = MagicMock(spec=discord.TextChannel)
    canale.name = "generale"
    canale.permissions_for = MagicMock(return_value=discord.Permissions(send_messages=True))
    it = fake_interaction(guild=server, channel=canale)
    await cog.permessi.callback(cog, it, None, None)
    canale.permissions_for.assert_called_once_with(server.me)


@pytest.mark.asyncio
async def test_i_comandi_stanno_sotto_utility_scheda():
    from discord.ext import commands as ext

    bot = ext.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    for nome in ("utente", "server", "canale", "ruolo", "ruoli", "membri", "anzianita", "permessi"):
        assert comando_nel_gruppo("utility", f"scheda {nome}") is not None

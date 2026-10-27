"""
tests/test_bot_inviti.py
========================
Gli altri bot di iYokai in `/admin setup attiva` (#113): chi c'è, chi manca, link e conseguenza.
Client veri non collegati (`commands.Bot`), nessuna chiamata a Discord.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from core import bot_inviti, bot_roles
from core.i18n import t
from tests.support.discord_fakes import fake_guild, fake_interaction


class _Flotta:
    worker_bots = [MagicMock() for _ in range(5)]

    def __init__(self, assenti):
        self.assenti = set(assenti)
        for w in self.worker_bots:
            w.is_ready.return_value = True

    def get_worker_bot(self, i):
        return self.worker_bots[i - 1]

    async def get_missing_worker_indices(self, guild_id):
        return self.assenti

    def build_invite_url(self, i, guild_id):
        return f"https://invito/{i}/{guild_id}"


@pytest.fixture(autouse=True)
def _senza_mod():
    bot_roles.registra_mod(None)
    yield
    bot_roles.registra_mod(None)


async def test_senza_mod_e_senza_flotta_non_c_e_niente_da_dire():
    assert await bot_inviti.altri_bot(MagicMock(spec=[]), 1) == []


async def test_mod_assente_ha_il_link_e_mod_presente_no():
    mod = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    mod._connection.application_id = 888
    bot_roles.registra_mod(mod)
    with patch.object(bot_roles, "server_mod", return_value=None):
        (voce,) = await bot_inviti.altri_bot(MagicMock(spec=[]), 5)
    assert voce.chiave == "mod" and voce.presenti == 0
    assert voce.mancanti[0][0] == "iYokai Mod" and "888" in voce.mancanti[0][1]
    with patch.object(bot_roles, "server_mod", return_value=object()):
        (voce,) = await bot_inviti.altri_bot(MagicMock(spec=[]), 5)
    assert voce.presenti == 1 and voce.mancanti == []
    await mod.close()


async def test_musica_conta_i_presenti_e_da_i_link_dei_mancanti():
    principale = MagicMock()
    principale.music_fleet = _Flotta({2, 4})
    (voce,) = await bot_inviti.altri_bot(principale, 5)
    assert (voce.chiave, voce.presenti, voce.totale) == ("musica", 3, 5)
    assert voce.mancanti == [("#2", "https://invito/2/5"), ("#4", "https://invito/4/5")]


async def test_il_setup_mostra_gli_altri_bot_con_link_e_conseguenza():
    from cogs.utility.setup import SetupCog

    principale = MagicMock()
    principale.music_fleet = _Flotta({2})
    cog = SetupCog(principale)
    interazione = fake_interaction(guild=fake_guild(5))

    async def testo(_interazione, chiave, **valori):
        return t(chiave, "it", **valori)

    with patch("cogs.utility.setup.testo_per", testo):
        riga = await cog._testo_altri_bot(interazione)

    assert "Gli altri bot di iYokai" in riga
    assert "[#2](https://invito/2/5)" in riga and "canale vocale in meno" in riga


async def test_se_l_elenco_non_si_legge_il_setup_funziona_lo_stesso():
    from cogs.utility.setup import SetupCog

    cog = SetupCog(MagicMock())
    with patch("cogs.utility.setup.altri_bot", AsyncMock(side_effect=RuntimeError("x"))):
        assert await cog._testo_altri_bot(fake_interaction(guild=fake_guild(5))) == ""

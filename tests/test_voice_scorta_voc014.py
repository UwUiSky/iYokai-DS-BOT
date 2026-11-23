"""
tests/test_voice_scorta_voc014.py
=================================
VOC-014 (D121): la stanza vocale di scorta. Con l'opzione accesa c'è sempre una stanza vuota pronta; chi ci entra la
prende e il bot ne prepara un'altra; il tetto della categoria vale; spenta di base. Database vero, Discord finto.
"""

from unittest.mock import AsyncMock

import pytest
from discord.ext import commands

from cogs.voice_temp.voice_temp import VoiceTempCog
from core import voice_scorta
from core.database import db
from core.repositories.voice_temp_repo import voice_temp_repo
from tests.test_voice_temp_correzioni import ID_OSPITE, ID_SERVER, Scena, _ambiente  # noqa: F401


@pytest.fixture
async def scena(monkeypatch):
    s = Scena()
    s.guild.me.id = 999
    await db.set_module_active_for_guild(ID_SERVER, "voice_temp", True)
    await voice_temp_repo.set_config(ID_SERVER, 1, s.categoria.id)
    s.canali[s.categoria.id] = s.categoria
    cog = VoiceTempCog(commands.Bot(command_prefix="!", intents=__import__("discord").Intents.none()))
    return s, cog


async def test_spenta_di_base_non_prepara_niente(scena):
    s, cog = scena
    await cog._assicura_scorta(s.guild)
    s.categoria.create_voice_channel.assert_not_awaited()


async def test_accesa_prepara_una_sola_stanza_e_non_ne_aggiunge(scena):
    s, cog = scena
    await voice_scorta.imposta(db, ID_SERVER, True, 1)
    await cog._assicura_scorta(s.guild)
    await cog._assicura_scorta(s.guild)
    assert s.categoria.create_voice_channel.await_count == 1
    canale_id = (await voice_temp_repo.canali_di(ID_SERVER, 999))[0]
    assert await voice_temp_repo.get_owner(canale_id) == 999
    assert s.canali[canale_id].send.await_count == 0  # nessun messaggio finché non la prende qualcuno


async def test_chi_entra_la_prende_e_ne_nasce_un_altra(scena):
    s, cog = scena
    await voice_scorta.imposta(db, ID_SERVER, True, 1)
    await cog._assicura_scorta(s.guild)
    scorta = s.canali[(await voice_temp_repo.canali_di(ID_SERVER, 999))[0]]
    scorta.edit = AsyncMock()
    scorta.set_permissions = AsyncMock()
    ospite = s.membro(ID_OSPITE)
    assert await cog._prendi_scorta(ospite, scorta) is True
    assert await voice_temp_repo.get_owner(scorta.id) == ID_OSPITE
    scorta.edit.assert_awaited()
    assert scorta.send.await_count >= 1  # ora arrivano messaggio e pannello
    s.entra(ospite, scorta)
    await cog._assicura_scorta(s.guild)
    assert s.categoria.create_voice_channel.await_count == 2


async def test_una_stanza_normale_non_si_prende(scena):
    s, cog = scena
    proprietario = s.membro(10)
    canale = await s.crea_canale_di(proprietario)
    assert await cog._prendi_scorta(s.membro(ID_OSPITE), canale) is False
    assert await voice_temp_repo.get_owner(canale.id) == 10


async def test_se_discord_rifiuta_la_stanza_resta_di_scorta(scena):
    import discord
    from unittest.mock import MagicMock

    s, cog = scena
    await voice_scorta.imposta(db, ID_SERVER, True, 1)
    await cog._assicura_scorta(s.guild)
    scorta = s.canali[(await voice_temp_repo.canali_di(ID_SERVER, 999))[0]]
    scorta.set_permissions = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500, reason="x"), "x"))
    assert await cog._prendi_scorta(s.membro(ID_OSPITE), scorta) is False
    assert await voice_temp_repo.get_owner(scorta.id) == 999


async def test_il_tetto_della_categoria_vale_anche_per_la_scorta(scena):
    s, cog = scena
    await voice_scorta.imposta(db, ID_SERVER, True, 1)
    await voice_temp_repo.set_category_cap(ID_SERVER, 1)
    s.categoria.channels = [object()]  # già al tetto
    await cog._assicura_scorta(s.guild)
    s.categoria.create_voice_channel.assert_not_awaited()


def test_serve_nuova():
    assert voice_scorta.serve_nuova(0) is True
    assert voice_scorta.serve_nuova(1) is False

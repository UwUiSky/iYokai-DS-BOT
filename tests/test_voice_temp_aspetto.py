"""
tests/test_voice_temp_aspetto.py
================================
#127: aspetto del pannello (VOC-010) e canali copiati dal generatore (VOC-013).
Database vero e codice di produzione; di Discord solo i finti fedeli.
"""

import discord
import pytest

from cogs.voice_temp.voice_temp import MODULE_VOICE_TEMP, VoiceTempCog
from core.database import db
from core.repositories.voice_temp_repo import voice_temp_repo
from core.voice_temp_logic import colore_da_testo, impostazioni_da_generatore
from tests.support.discord_fakes import fake_role, fake_voice_channel
from tests.test_voice_temp_correzioni import ID_PROPRIETARIO, ID_SERVER, Scena, _ambiente  # noqa: F401


def test_colore_da_testo():
    assert colore_da_testo("#5865F2") == 0x5865F2
    assert colore_da_testo("ff0000") == 0xFF0000
    assert colore_da_testo("rosso") is None
    assert colore_da_testo("12345") is None


def test_impostazioni_da_generatore_entro_i_limiti_del_server():
    assert impostazioni_da_generatore(384000, 5, 96000) == {"bitrate": 96000, "user_limit": 5}
    assert impostazioni_da_generatore(1000, 0, 96000)["bitrate"] == 8000


async def _con_generatore(scena, copia: bool):
    scena.guild.bitrate_limit = 256000
    generatore = fake_voice_channel(800, "Crea")
    ruolo = fake_role(555, "Ospiti")
    generatore.bitrate, generatore.user_limit = 128000, 4
    generatore.overwrites = {ruolo: discord.PermissionOverwrite(stream=False)}
    scena.canali[800] = generatore
    await voice_temp_repo.set_config(ID_SERVER, 800, scena.categoria.id)
    await voice_temp_repo.set_aspetto(ID_SERVER, None, None, None, copia)
    return generatore, ruolo


async def test_canale_copiato_dal_generatore_eredita_limite_qualita_e_permessi():
    scena = Scena()
    generatore, ruolo = await _con_generatore(scena, True)

    await scena.crea_canale_di(scena.membro(ID_PROPRIETARIO))

    kw = scena.categoria.create_voice_channel.call_args.kwargs
    assert (kw["bitrate"], kw["user_limit"]) == (128000, 4)
    assert kw["overwrites"][ruolo].stream is False
    assert kw["overwrites"][scena.membro(ID_PROPRIETARIO)].manage_channels is True


async def test_senza_copia_il_canale_nasce_come_prima():
    scena = Scena()
    await _con_generatore(scena, False)

    await scena.crea_canale_di(scena.membro(ID_PROPRIETARIO))

    kw = scena.categoria.create_voice_channel.call_args.kwargs
    assert "bitrate" not in kw and "user_limit" not in kw and len(kw["overwrites"]) == 2


async def test_opzioni_salvano_aspetto_e_predefiniti_lo_azzera():
    scena = Scena()
    await voice_temp_repo.set_config(ID_SERVER, 800, scena.categoria.id)
    staff = scena.membro(ID_PROPRIETARIO, manage_channels=True)
    cog = VoiceTempCog(bot=None)

    await cog.voicetemp_opzioni.callback(
        cog, scena.interazione(staff), copia_generatore=True,
        pannello_titolo="Stanze", pannello_testo="Premi", pannello_colore="#00ff00",
    )
    config = await voice_temp_repo.get_config(ID_SERVER)
    assert (config.pannello_titolo, config.pannello_testo, config.pannello_colore, config.clona_generatore) == (
        "Stanze", "Premi", 0x00FF00, True,
    )

    interazione = scena.interazione(staff)
    await cog.voicetemp_panel.callback(cog, interazione)
    embed = interazione.response.send_message.call_args.kwargs["embed"]
    assert (embed.title, embed.description, embed.color.value) == ("Stanze", "Premi", 0x00FF00)

    await cog.voicetemp_opzioni.callback(cog, scena.interazione(staff), predefiniti=True)
    config = await voice_temp_repo.get_config(ID_SERVER)
    assert (config.pannello_titolo, config.pannello_colore, config.clona_generatore) == (None, None, False)


async def test_colore_non_valido_e_rifiutato():
    scena = Scena()
    await voice_temp_repo.set_config(ID_SERVER, 800, scena.categoria.id)
    cog = VoiceTempCog(bot=None)
    interazione = scena.interazione(scena.membro(ID_PROPRIETARIO, manage_channels=True))

    await cog.voicetemp_opzioni.callback(cog, interazione, pannello_colore="rosso")

    assert "esadecimale" in interazione.response.send_message.call_args.args[0]
    assert (await voice_temp_repo.get_config(ID_SERVER)).pannello_colore is None


# ---------------------------------------------------------------- VOC-016
from unittest.mock import create_autospec  # noqa: E402

from tests.test_voice_temp_correzioni import _bot_con  # noqa: E402


async def _entra_in(scena, membro, canale_id):
    prima = create_autospec(discord.VoiceState, instance=True)
    prima.channel = None
    dopo = create_autospec(discord.VoiceState, instance=True)
    dopo.channel = scena.canali[canale_id]
    cog = VoiceTempCog(_bot_con(scena))
    await cog.on_voice_state_update(membro, prima, dopo)


async def _generatore_in_piu(scena, nome="Squadra {numero}", limite=3):
    scena.guild.bitrate_limit = 256000
    scena.canali[801] = fake_voice_channel(801, "Crea squadra")
    scena.canali[scena.categoria.id] = scena.categoria
    await voice_temp_repo.set_config(ID_SERVER, 800, scena.categoria.id)
    await db.set_module_active_for_guild(ID_SERVER, MODULE_VOICE_TEMP, True)
    staff = scena.membro(ID_PROPRIETARIO, manage_channels=True)
    cog = VoiceTempCog(bot=None)
    await cog.voicetemp_generatore.callback(
        cog, scena.interazione(staff), "aggiungi", scena.canali[801], scena.categoria, nome, limite
    )


async def test_generatore_in_piu_crea_con_le_sue_regole():
    scena = Scena()
    await _generatore_in_piu(scena)
    assert [g.channel_id for g in await voice_temp_repo.lista_generatori(ID_SERVER)] == [801]

    membro = scena.membro(30)
    await _entra_in(scena, membro, 801)

    kw = scena.categoria.create_voice_channel.call_args.kwargs
    assert kw["name"] == "Squadra 1" and kw["user_limit"] == 3
    membro.move_to.assert_awaited_once()


async def test_generatore_non_registrato_non_crea_nulla():
    scena = Scena()
    await _generatore_in_piu(scena)
    scena.canali[802] = fake_voice_channel(802, "Altro")

    await _entra_in(scena, scena.membro(31), 802)

    scena.categoria.create_voice_channel.assert_not_called()


async def test_tetto_dei_generatori_e_togli():
    from cogs.voice_temp.voice_temp import GENERATORI_EXTRA_MAX

    scena = Scena()
    await voice_temp_repo.set_config(ID_SERVER, 800, scena.categoria.id)
    for n in range(GENERATORI_EXTRA_MAX):
        assert await voice_temp_repo.aggiungi_generatore(ID_SERVER, 900 + n, 1, None, 0, GENERATORI_EXTRA_MAX)
    assert not await voice_temp_repo.aggiungi_generatore(ID_SERVER, 999, 1, None, 0, GENERATORI_EXTRA_MAX)
    assert await voice_temp_repo.aggiungi_generatore(ID_SERVER, 900, 2, "x", 5, GENERATORI_EXTRA_MAX)
    assert await voice_temp_repo.rimuovi_generatore(ID_SERVER, 900)
    assert not await voice_temp_repo.rimuovi_generatore(ID_SERVER, 900)

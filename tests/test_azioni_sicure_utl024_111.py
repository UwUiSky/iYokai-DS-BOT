"""
tests/test_azioni_sicure_utl024_111.py
======================================
UTL-024 e UTL-111 (D121): l'elenco chiuso di azioni sicure (dare o togliere un ruolo, scrivere un messaggio, reagire,
sbloccare un canale), controllate con i permessi di chi le usa. Mai moderazione né amministrazione.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import azioni_sicure as az
from tests.support.discord_fakes import fake_guild, fake_member, fake_message, fake_role, fake_text_channel

G = 1


def _scena(permessi_esecutore=None):
    guild = fake_guild(G)
    guild.me.top_role = fake_role(role_id=900, name="bot", position=50)
    guild.me.guild_permissions = discord.Permissions(manage_roles=True)
    basso = fake_role(role_id=10, name="Giochi", position=5)
    alto = fake_role(role_id=11, name="Staff", position=60)
    pericoloso = fake_role(role_id=12, name="Admin", position=6, permissions=discord.Permissions(administrator=True))
    ruoli = {10: basso, 11: alto, 12: pericoloso}
    guild.get_role.side_effect = ruoli.get
    canale = fake_text_channel(77)
    canale.permissions_for = lambda who: discord.Permissions(view_channel=True, send_messages=True, add_reactions=True, manage_channels=True)
    canale.send = AsyncMock()
    canale.set_permissions = AsyncMock()
    guild.get_channel.side_effect = lambda i: canale if i == 77 else None
    guild.default_role = fake_role(role_id=0, name="@everyone", position=0)
    capo = fake_role(role_id=800, name="Capo", position=40)
    esec = fake_member(5, roles=[capo], guild_permissions=permessi_esecutore or discord.Permissions(manage_roles=True, manage_channels=True))
    esec.top_role = capo
    utente = fake_member(6)
    utente.add_roles, utente.remove_roles = AsyncMock(), AsyncMock()
    utente.top_role = fake_role(role_id=0, name="@everyone", position=0)
    guild.get_member.side_effect = lambda i: {5: esec, 6: utente}.get(i)
    return guild, canale, esec, utente


def test_da_testo_e_validazione_dell_elenco_chiuso():
    assert az.da_dict({"tipo": "dai_ruolo", "ruolo_id": 10}).tipo == "dai_ruolo"
    for cattivo in ({"tipo": "ban"}, {"tipo": "kick", "utente_id": 1}, {"tipo": "eval"}, {"tipo": "dai_ruolo"}, {"tipo": "messaggio", "canale_id": 1}, {"tipo": "reazione"}):
        with pytest.raises(az.AzioneNonValida):
            az.da_dict(cattivo)


def test_il_testo_si_taglia_e_non_pinga():
    a = az.da_dict({"tipo": "messaggio", "canale_id": 77, "testo": "ciao @everyone " + "x" * 500})
    assert len(a.testo) <= az.MAX_TESTO


async def test_tag_dai_ruolo_all_invocatore_con_ruolo_normale():
    guild, canale, esec, utente = _scena()
    errore = await az.esegui(guild, az.da_dict({"tipo": "dai_ruolo", "ruolo_id": 10}), esecutore=utente, bersaglio=utente, autonomo=False)
    assert errore is None
    utente.add_roles.assert_awaited_once()


async def test_ruolo_pericoloso_o_sopra_il_bot_e_rifiutato():
    guild, canale, esec, utente = _scena()
    for rid in (11, 12):
        errore = await az.esegui(guild, az.da_dict({"tipo": "dai_ruolo", "ruolo_id": rid}), esecutore=utente, bersaglio=utente, autonomo=False)
        assert errore is not None
    utente.add_roles.assert_not_awaited()


async def test_messaggio_senza_ping_e_solo_dove_l_esecutore_puo_scrivere():
    guild, canale, esec, utente = _scena()
    a = az.da_dict({"tipo": "messaggio", "canale_id": 77, "testo": "ciao @everyone"})
    assert await az.esegui(guild, a, esecutore=utente, bersaglio=utente, autonomo=False) is None
    kw = canale.send.await_args.kwargs
    assert kw["allowed_mentions"].everyone is False and kw["allowed_mentions"].roles is False and kw["allowed_mentions"].users is False
    canale.permissions_for = lambda who: discord.Permissions(view_channel=True, send_messages=False)
    canale.send.reset_mock()
    assert await az.esegui(guild, a, esecutore=utente, bersaglio=utente, autonomo=False) is not None
    canale.send.assert_not_awaited()


async def test_reazione_sul_messaggio_che_ha_acceso_il_tag():
    guild, canale, esec, utente = _scena()
    msg = fake_message(5, author=utente, channel=canale, guild=guild)
    msg.add_reaction = AsyncMock()
    assert await az.esegui(guild, az.da_dict({"tipo": "reazione", "emoji": "👍"}), esecutore=utente, bersaglio=utente, messaggio=msg, autonomo=False) is None
    msg.add_reaction.assert_awaited_once_with("👍")
    # senza messaggio (comando slash) non fa niente e non è un errore
    assert await az.esegui(guild, az.da_dict({"tipo": "reazione", "emoji": "👍"}), esecutore=utente, bersaglio=utente, autonomo=False) is None


async def test_programmata_riprova_i_permessi_di_chi_l_ha_messa():
    guild, canale, esec, utente = _scena()
    a = az.da_dict({"tipo": "togli_ruolo", "ruolo_id": 10, "utente_id": 6})
    assert await az.esegui(guild, a, esecutore=esec, bersaglio=utente, autonomo=True) is None
    utente.remove_roles.assert_awaited_once()
    # chi l'ha messa ha perso «Gestire i ruoli»: non esegue
    utente.remove_roles.reset_mock()
    esec.guild_permissions = discord.Permissions.none()
    assert await az.esegui(guild, a, esecutore=esec, bersaglio=utente, autonomo=True) is not None
    utente.remove_roles.assert_not_awaited()


async def test_sblocca_canale_serve_gestire_i_canali_e_toglie_il_blocco():
    guild, canale, esec, utente = _scena()
    a = az.da_dict({"tipo": "sblocca_canale", "canale_id": 77})
    assert await az.esegui(guild, a, esecutore=esec, bersaglio=None, autonomo=True) is None
    canale.set_permissions.assert_awaited_once()
    assert canale.set_permissions.await_args.args[0] is guild.default_role
    assert canale.set_permissions.await_args.kwargs["send_messages"] is None
    esec.guild_permissions = discord.Permissions.none()
    assert await az.esegui(guild, a, esecutore=esec, bersaglio=None, autonomo=True) is not None


def test_il_tipo_sblocca_canale_non_e_dei_tag():
    with pytest.raises(az.AzioneNonValida):
        az.da_dict({"tipo": "sblocca_canale", "canale_id": 1}, ammessi=az.TIPI_TAG)

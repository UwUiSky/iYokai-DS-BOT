"""
tests/test_report_limiti.py
===========================
/report rispetta i limiti di Discord (LIM-4): il motivo ha una
lunghezza massima dichiarata e un errore di invio nel canale dello
staff non fa cadere il comando.
"""

from unittest.mock import MagicMock, create_autospec

import discord
import pytest
from discord.ext import commands

import cogs.moderation._shared as modulo_shared
import cogs.moderation.report as modulo_report
from core.database import Database
from tests.support.discord_fakes import fake_interaction, fake_member, fake_text_channel

ID_CANALE_STAFF = 4242


@pytest.fixture
def db_finto(monkeypatch):
    finto = create_autospec(Database, instance=True)
    finto.is_module_active_for_guild.return_value = True
    finto.get_guild_setting.return_value = ID_CANALE_STAFF
    monkeypatch.setattr(modulo_shared, "db", finto)
    monkeypatch.setattr(modulo_report, "db", finto)
    return finto


async def test_report_dichiara_la_lunghezza_massima_del_motivo():
    """Un campo di embed tiene 1024 caratteri: il motivo si ferma a 1000."""
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo_report.setup(bot)

    opzioni = {o["name"]: o for o in bot.tree.get_command("report").to_dict(bot.tree)["options"]}

    assert opzioni["reason"]["min_length"] == 3
    assert opzioni["reason"]["max_length"] == 1000


async def test_report_errore_di_invio_avvisa_chi_segnala(db_finto):
    """
    Se Discord rifiuta il messaggio (errore 400, non solo "permessi
    mancanti") chi segnala riceve una risposta chiara, non
    "L'applicazione non ha risposto".
    """
    canale = fake_text_channel(channel_id=ID_CANALE_STAFF)
    canale.send.side_effect = discord.HTTPException(
        MagicMock(status=400, reason="Bad Request"), "Invalid Form Body"
    )
    interazione = fake_interaction()
    interazione.guild.get_channel.return_value = canale
    cog = modulo_report.ModerationReportCog(bot=None)

    await cog.report.callback(cog, interazione, fake_member(user_id=77), "Insulti in chat")

    canale.send.assert_awaited_once()
    interazione.response.send_message.assert_awaited_once()
    risposta = interazione.response.send_message.call_args
    assert "Non riesco a inviare la segnalazione" in risposta.args[0]
    assert risposta.kwargs["ephemeral"] is True


async def test_report_motivo_di_mille_caratteri_arriva_intero(db_finto):
    """Il motivo più lungo ammesso entra nel campo dell'embed senza tagli."""
    canale = fake_text_channel(channel_id=ID_CANALE_STAFF)
    interazione = fake_interaction()
    interazione.guild.get_channel.return_value = canale
    cog = modulo_report.ModerationReportCog(bot=None)

    await cog.report.callback(cog, interazione, fake_member(user_id=77), "m" * 1000)

    embed = canale.send.call_args.kwargs["embed"]
    campo_motivo = next(campo for campo in embed.fields if campo.name == "Motivo")
    assert campo_motivo.value == "m" * 1000
    assert len(campo_motivo.value) <= 1024

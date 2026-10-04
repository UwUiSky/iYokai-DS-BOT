"""
tests/test_basic_logs_limiti.py
===============================
Log di base con molti ruoli cambiati insieme (LIM-19): un campo di
embed tiene 1024 caratteri. L'elenco dei ruoli viene tagliato e dice
quanti ne restano fuori.
"""

import re
from unittest.mock import create_autospec

import pytest

import cogs.logging.basic_logs as modulo
from core.database import Database
from core.repositories.event_log_repo import EventLogRepository
from tests.support.discord_fakes import fake_guild, fake_member, fake_role, fake_text_channel

ID_CANALE_LOG = 31337


@pytest.fixture
def canale_log(monkeypatch):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    db_finto.get_guild_setting.return_value = ID_CANALE_LOG
    monkeypatch.setattr(modulo, "db", db_finto)
    monkeypatch.setattr(
        modulo, "event_log_repo", create_autospec(EventLogRepository, instance=True)
    )
    return fake_text_channel(channel_id=ID_CANALE_LOG)


def _membro(server, ruoli):
    membro = fake_member(user_id=42, roles=ruoli)
    membro.guild = server
    membro.nick = None
    return membro


def _ruoli(quanti: int):
    # ID lunghi come quelli veri di Discord (19 cifre).
    return [fake_role(role_id=1_000_000_000_000_000_000 + n) for n in range(quanti)]


async def _campi_dopo_il_cambio(canale_log, prima, dopo) -> dict[str, str]:
    server = fake_guild()
    server.get_channel.return_value = canale_log
    cog = modulo.BasicLogsCog(bot=None)

    await cog.on_member_update(_membro(server, prima), _membro(server, dopo))

    embed = canale_log.send.call_args.kwargs["embed"]
    return {campo.name: campo.value for campo in embed.fields}


async def test_sessanta_ruoli_aggiunti_insieme_restano_in_un_campo_valido(canale_log):
    campi = await _campi_dopo_il_cambio(canale_log, prima=[], dopo=_ruoli(60))

    assert len(campi["Aggiunti"]) <= 1024
    mostrati = campi["Aggiunti"].count("<@&")
    esclusi = re.search(r"\+(\d+) altri$", campi["Aggiunti"])
    assert esclusi is not None, campi["Aggiunti"][-80:]
    assert mostrati + int(esclusi.group(1)) == 60


async def test_sessanta_ruoli_tolti_insieme_restano_in_un_campo_valido(canale_log):
    """Il caso reale: la punizione anti-nuke toglie tutti i ruoli in una volta."""
    campi = await _campi_dopo_il_cambio(canale_log, prima=_ruoli(60), dopo=[])

    assert len(campi["Rimossi"]) <= 1024
    assert re.search(r"\+\d+ altri$", campi["Rimossi"]) is not None


async def test_pochi_ruoli_vengono_mostrati_tutti(canale_log):
    campi = await _campi_dopo_il_cambio(canale_log, prima=[], dopo=_ruoli(3))

    assert campi["Aggiunti"].count("<@&") == 3
    assert "altri" not in campi["Aggiunti"]

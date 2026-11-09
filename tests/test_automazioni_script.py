"""B26: /tag prova (nulla si salva), /admin-automazioni script errori, errori registrati dal cog."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

import cogs.utility.automazioni as modulo
from cogs.utility.automazioni import AutomazioniCog
from core import tag_script_logic as ts
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member


@pytest.fixture
def cog(monkeypatch):
    c = AutomazioniCog(MagicMock())
    db_finto = MagicMock()
    db_finto.is_module_active_for_guild = AsyncMock(return_value=True)
    db_finto.get_guild_setting = AsyncMock(return_value=None)
    monkeypatch.setattr(modulo, "db", db_finto)
    repo = MagicMock()
    repo.archivio = MagicMock(return_value=ts.ArchivioMemoria({"x": "1"}))
    repo.ultimi_errori = AsyncMock(return_value=[])
    monkeypatch.setattr(modulo, "tag_script_repo", repo)
    monkeypatch.setattr(modulo, "massimo_chiavi", AsyncMock(return_value=ts.MAX_CHIAVI))
    c.repo = repo
    return c


def _i(staff=True):
    server = fake_guild()
    utente = fake_member(5)
    utente.guild = server
    utente.display_name = "Mario"
    utente.guild_permissions = MagicMock(manage_guild=staff, administrator=False)
    return fake_interaction(guild=server, user=utente)


async def _invia(cog, i, script, argomenti=""):
    await cog.prova.callback(cog, i)
    finestra = i.response.send_modal.await_args.args[0]
    finestra.script._value, finestra.argomenti._value = script, argomenti
    i2 = _i()
    await finestra.on_submit(i2)
    return i2


async def test_prova_apre_la_finestra_con_i_tetti(cog):
    i = _i()
    await cog.prova.callback(cog, i)
    f = i.response.send_modal.await_args.args[0]
    assert f.script.max_length == 4000 and f.argomenti.max_length == 200


async def test_prova_riservata_a_staff_o_creatori(cog):
    i = _i(staff=False)
    await cog.prova.callback(cog, i)
    i.response.send_modal.assert_not_awaited()
    i.response.send_message.assert_awaited()


async def test_prova_risponde_senza_salvare(cog):
    i2 = await _invia(cog, _i(), "{dati:set|x|99}{dati:get|x} {maiuscolo:{args}}", "ciao")
    testo = i2.followup.send.await_args.args[0]
    assert "99 CIAO" in testo and "operazioni" in testo
    assert cog.repo.archivio.return_value.dati == {"x": "1"}  # niente è stato scritto davvero
    assert i2.followup.send.await_args.kwargs["ephemeral"] is True
    assert i2.followup.send.await_args.kwargs["allowed_mentions"].everyone is False


async def test_prova_con_errore_dice_quale(cog):
    i2 = await _invia(cog, _i(), "{ripeti:50|{ripeti:5|{var:a=1}}}")
    assert "200" in i2.followup.send.await_args.args[0]


async def test_prova_non_fa_uscire_everyone(cog):
    i2 = await _invia(cog, _i(), "{args}", "@everyone")
    assert "@everyone" not in i2.followup.send.await_args.args[0].replace("@​everyone", "")


async def test_errori_elenco_e_vuoto(cog):
    i = _i()
    await cog.errori.callback(cog, i, "dado")
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    cog.repo.ultimi_errori.return_value = [{"chiave": "tag_script_tempo", "dettaglio": "boh", "creato_il": datetime(2026, 11, 9, tzinfo=timezone.utc)}]
    i = _i()
    await cog.errori.callback(cog, i, "dado")
    assert "boh" in i.response.send_message.await_args.args[0]

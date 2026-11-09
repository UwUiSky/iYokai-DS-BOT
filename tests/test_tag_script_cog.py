"""Tag con script (B25): il cog esegue lo script del testo e non fa uscire menzioni."""
from unittest.mock import AsyncMock, MagicMock

import pytest

import cogs.utility.custom_commands as modulo
from tests.test_custom_commands import _interazione, _tag, scena  # noqa: F401


@pytest.fixture(autouse=True)
def archivio_finto(monkeypatch):
    repo = MagicMock()
    repo.registra_errore = AsyncMock()
    monkeypatch.setattr(modulo, "tag_script_repo", repo)
    return repo


async def test_il_tag_esegue_lo_script(scena):
    scena.repo.get_tag.return_value = _tag(response="{se:{args}==ciao|saluto|{maiuscolo:{args}}} {var:x=2}{calcola:{x}*21}")
    i, *_ = _interazione()
    await scena.tag.callback(scena, i, "regole", "ciao")
    assert i.followup.send.await_args.args[0] == "saluto 42"


async def test_lo_script_non_fa_uscire_everyone(scena):
    scena.repo.get_tag.return_value = _tag(response="{maiuscolo:{args}} {lista:@everyone|@here}")
    i, *_ = _interazione()
    await scena.tag.callback(scena, i, "regole", "@everyone")
    kw = i.followup.send.await_args.kwargs
    assert kw["allowed_mentions"].everyone is False and kw["allowed_mentions"].roles is False


async def test_script_fermato_dice_solo_il_motivo_breve(scena):
    scena.repo.get_tag.return_value = _tag(response="{ripeti:50|{ripeti:50|x}}")
    i, *_ = _interazione()
    await scena.tag.callback(scena, i, "regole", "")
    assert "regole" in i.followup.send.await_args.args[0]


async def test_tag_senza_script_non_passa_dal_motore(scena, monkeypatch):
    import cogs.utility.custom_commands as modulo
    chiamato = AsyncMock()
    monkeypatch.setattr(modulo.tag_script, "esegui", chiamato)
    i, *_ = _interazione()
    await scena.tag.callback(scena, i, "regole", "x")
    chiamato.assert_not_awaited()


async def test_errore_dello_script_si_registra(scena, archivio_finto):
    scena.repo.get_tag.return_value = _tag(response="{ripeti:50|{ripeti:5|{var:a=1}}}")
    i, *_ = _interazione()
    await scena.tag.callback(scena, i, "regole", "")
    archivio_finto.registra_errore.assert_awaited_once()
    assert archivio_finto.registra_errore.await_args.args[1:3] == ("regole", "tag_script_troppi_passi")


async def test_se_il_registro_degli_errori_si_rompe_il_tag_risponde(scena, archivio_finto):
    archivio_finto.registra_errore.side_effect = RuntimeError("db")
    scena.repo.get_tag.return_value = _tag(response="{ripeti:50|{ripeti:5|{var:a=1}}}")
    i, *_ = _interazione()
    await scena.tag.callback(scena, i, "regole", "")
    assert "regole" in i.followup.send.await_args.args[0]


async def test_il_tag_riceve_l_archivio_del_suo_server(scena, archivio_finto):
    scena.repo.get_tag.return_value = _tag(response="{dati:get|k|vuoto}")
    archivio_finto.archivio.return_value = __import__("core.tag_script_logic", fromlist=["x"]).ArchivioMemoria({"k": "visto"})
    i, *_ = _interazione()
    await scena.tag.callback(scena, i, "regole", "")
    assert i.followup.send.await_args.args[0] == "visto"


async def test_eliminare_il_tag_toglie_i_suoi_errori(scena, archivio_finto):
    scena.repo.delete_tag = AsyncMock(return_value=True)
    archivio_finto.togli_errori = AsyncMock()
    i, server, _ = _interazione()
    await scena.elimina.callback(scena, i, "regole")
    archivio_finto.togli_errori.assert_awaited_once_with(server.id, "regole")

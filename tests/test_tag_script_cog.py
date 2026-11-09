"""Tag con script (B25): il cog esegue lo script del testo e non fa uscire menzioni."""
from unittest.mock import AsyncMock

import pytest

from tests.test_custom_commands import _interazione, _tag, scena  # noqa: F401


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

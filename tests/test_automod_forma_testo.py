"""
tests/test_automod_forma_testo.py
=================================
Catalogo AutoMod (#116): AMD-002 troppi a-capo, AMD-003 messaggio troppo
lungo, AMD-005 troppi spoiler. 0 = filtro spento.
"""

import pytest

from cogs.automod.automod import AutomodCog
from core.automod_advanced_logic import (
    AutomodAdvancedConfig,
    MessageSignals,
    VIOLATION_A_CAPO,
    VIOLATION_LUNGHEZZA,
    VIOLATION_SPOILER,
    conta_spoiler,
    evaluate_message_violations,
)
from core.repositories.automod_advanced_repo import _from_json, _to_json, automod_advanced_repo
from tests.test_automod_advanced_behavior import (  # noqa: F401
    GUILD_ID,
    _FakeGuild,
    _FakeMember,
    _FakeMessage,
    _FakeTextChannel,
    _salva_config,
    contesto,
)


def _v(testo, **config):
    segnali = MessageSignals(
        content=testo, mention_count=0, emoji_count=0, attachment_count=0, sticker_count=0,
        recent_message_count=0, recent_attachment_count=0, recent_sticker_count=0,
    )
    return evaluate_message_violations(segnali, AutomodAdvancedConfig(**config))


def test_tutto_spento_di_partenza():
    assert _v("a\n" * 500 + "||x||" * 50) == ()


def test_a_capo_scatta_solo_oltre_il_massimo():
    assert _v("a\n" * 5, max_a_capo=5) == ()
    assert _v("a\n" * 6, max_a_capo=5) == (VIOLATION_A_CAPO,)


def test_lunghezza_scatta_solo_oltre_il_massimo():
    assert _v("x" * 100, max_lunghezza=100) == ()
    assert _v("x" * 101, max_lunghezza=100) == (VIOLATION_LUNGHEZZA,)


def test_spoiler_si_contano_a_coppie():
    assert conta_spoiler("||a|| e ||b|| e ||c") == 2
    assert _v("||a|| ||b||", max_spoiler=2) == ()
    assert _v("||a|| ||b|| ||c||", max_spoiler=2) == (VIOLATION_SPOILER,)


def test_i_tre_limiti_si_salvano_e_si_rileggono():
    config = AutomodAdvancedConfig(max_a_capo=7, max_lunghezza=900, max_spoiler=3)
    settings = _from_json(1, _to_json(type("S", (), dict(
        guild_id=1, config=config, exempt_channel_ids=(), exempt_role_ids=(), actions={},
        mute_duration_seconds=600, log_channel_id=None))()))
    assert (settings.config.max_a_capo, settings.config.max_lunghezza, settings.config.max_spoiler) == (7, 900, 3)


@pytest.mark.asyncio
async def test_il_muro_di_testo_viene_cancellato(contesto):
    await _salva_config(contesto, config=AutomodAdvancedConfig(max_a_capo=3))
    guild = _FakeGuild(GUILD_ID)
    messaggio = _FakeMessage(guild, _FakeMember(1, guild), _FakeTextChannel(1), content="riga\n" * 10)

    await AutomodCog(bot=None).on_message(messaggio)

    assert messaggio.deleted is True


@pytest.mark.asyncio
async def test_il_messaggio_corto_passa(contesto):
    await _salva_config(contesto, config=AutomodAdvancedConfig(max_a_capo=3, max_lunghezza=50, max_spoiler=1))
    guild = _FakeGuild(GUILD_ID)
    messaggio = _FakeMessage(guild, _FakeMember(1, guild), _FakeTextChannel(1), content="ciao\nmondo")

    await AutomodCog(bot=None).on_message(messaggio)

    assert messaggio.deleted is False

"""
tests/test_automod_messaggi_modificati.py
=========================================
AMD-021: un messaggio modificato viene controllato di nuovo dai filtri
lato bot; una modifica non conta come messaggio in più per l'anti-spam.
"""

import pytest

from cogs.automod.automod import AutomodCog
from core.automod_advanced_logic import AutomodAdvancedConfig
from tests.test_automod_advanced_behavior import (  # noqa: F401
    GUILD_ID,
    _FakeGuild,
    _FakeMember,
    _FakeMessage,
    _FakeTextChannel,
    _salva_config,
    contesto,
)


def _prima_dopo(testo_prima, testo_dopo):
    guild = _FakeGuild(GUILD_ID)
    autore = _FakeMember(1, guild)
    canale = _FakeTextChannel(1)
    return (
        _FakeMessage(guild, autore, canale, content=testo_prima),
        _FakeMessage(guild, autore, canale, content=testo_dopo),
    )


@pytest.mark.asyncio
async def test_modifica_che_diventa_zalgo_viene_cancellata(contesto):
    await _salva_config(contesto, config=AutomodAdvancedConfig(anti_zalgo_enabled=True))
    prima, dopo = _prima_dopo("ciao", "A" + "́" * 10)

    await AutomodCog(bot=None).on_message_edit(prima, dopo)

    assert dopo.deleted is True


@pytest.mark.asyncio
async def test_modifica_senza_cambio_di_testo_non_si_controlla(contesto):
    await _salva_config(contesto, config=AutomodAdvancedConfig(anti_zalgo_enabled=True))
    prima, dopo = _prima_dopo("A" + "́" * 10, "A" + "́" * 10)

    await AutomodCog(bot=None).on_message_edit(prima, dopo)

    assert dopo.deleted is False


@pytest.mark.asyncio
async def test_modifica_non_conta_per_lo_spam(contesto, monkeypatch):
    from cogs.automod import automod as modulo

    registrazioni = []
    monkeypatch.setattr(
        modulo.rate_tracker, "record_and_count", lambda *a, **k: registrazioni.append(a) or 99
    )
    await _salva_config(contesto)
    prima, dopo = _prima_dopo("uno", "due")

    await AutomodCog(bot=None).on_message_edit(prima, dopo)

    assert registrazioni == []
    assert dopo.deleted is False


@pytest.mark.asyncio
async def test_modifiche_ripetute_con_sola_azione_warn_danno_un_warn(contesto):
    from cogs.automod import automod as modulo
    from core.repositories.moderation_repo import moderation_repo

    modulo._avvisati.clear()
    await _salva_config(
        contesto,
        config=AutomodAdvancedConfig(anti_zalgo_enabled=True),
        actions={"anti_zalgo": ("warn",)},
    )
    prima, dopo = _prima_dopo("ciao", "A" + "\u0301" * 10)
    prima.id = dopo.id = 777
    cog = AutomodCog(bot=None)

    await cog.on_message_edit(prima, dopo)
    seconda = _stesso(dopo, "B" + "\u0301" * 12)
    await cog.on_message_edit(dopo, seconda)

    casi = await moderation_repo.list_cases_for_user(GUILD_ID, 1)
    assert [c.action_type for c in casi].count("warn") == 1


def _stesso(messaggio, testo):
    copia = _FakeMessage(messaggio.guild, messaggio.author, messaggio.channel, content=testo)
    copia.id = messaggio.id
    return copia

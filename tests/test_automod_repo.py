"""
tests/test_automod_repo.py
=============================
Test di AutomodRepository contro PostgreSQL reale.
"""

import pytest

from core.repositories.automod_repo import AutomodRepository


@pytest.fixture
def repo(clean_db):
    return AutomodRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_config_di_default_per_server_mai_configurato(repo):
    config = await repo.get_config(guild_id=100)
    assert config.custom_badwords == ()
    assert config.block_invites is False


@pytest.mark.asyncio
async def test_aggiunta_parola(repo):
    config = await repo.add_badword(100, "spam")
    assert "spam" in config.custom_badwords

    riletta = await repo.get_config(100)
    assert riletta.custom_badwords == ("spam",)


@pytest.mark.asyncio
async def test_aggiunta_parola_e_case_insensitive(repo):
    await repo.add_badword(100, "Spam")
    config = await repo.add_badword(100, "SPAM")
    # Non deve comparire due volte: "Spam" e "SPAM" sono la stessa parola.
    assert len(config.custom_badwords) == 1


@pytest.mark.asyncio
async def test_aggiunta_parola_vuota_viene_ignorata(repo):
    config = await repo.add_badword(100, "   ")
    assert config.custom_badwords == ()


@pytest.mark.asyncio
async def test_rimozione_parola(repo):
    await repo.add_badword(100, "spam")
    await repo.add_badword(100, "scam")
    config = await repo.remove_badword(100, "spam")
    assert config.custom_badwords == ("scam",)


@pytest.mark.asyncio
async def test_rimozione_parola_case_insensitive(repo):
    await repo.add_badword(100, "spam")
    config = await repo.remove_badword(100, "SPAM")
    assert "spam" not in config.custom_badwords


@pytest.mark.asyncio
async def test_rimozione_parola_inesistente_non_fallisce(repo):
    config = await repo.remove_badword(100, "non_esiste")
    assert config.custom_badwords == ()


@pytest.mark.asyncio
async def test_set_block_invites(repo):
    assert (await repo.get_config(100)).block_invites is False
    await repo.set_block_invites(100, True)
    assert (await repo.get_config(100)).block_invites is True
    await repo.set_block_invites(100, False)
    assert (await repo.get_config(100)).block_invites is False


@pytest.mark.asyncio
async def test_server_diversi_non_si_influenzano(repo):
    await repo.add_badword(100, "parola_a")
    await repo.add_badword(200, "parola_b")

    config_a = await repo.get_config(100)
    config_b = await repo.get_config(200)
    assert config_a.custom_badwords == ("parola_a",)
    assert config_b.custom_badwords == ("parola_b",)


@pytest.mark.asyncio
async def test_last_synced_di_default_e_vuoto(repo):
    keywords, regex = await repo.get_last_synced(100, "iYokai — Test")
    assert keywords == ()
    assert regex == ()


@pytest.mark.asyncio
async def test_set_e_get_last_synced(repo):
    await repo.set_last_synced(100, "iYokai — Test", ("a", "b"), ("pattern1",))
    keywords, regex = await repo.get_last_synced(100, "iYokai — Test")
    assert keywords == ("a", "b")
    assert regex == ("pattern1",)


@pytest.mark.asyncio
async def test_set_last_synced_sovrascrive_il_precedente(repo):
    await repo.set_last_synced(100, "iYokai — Test", ("a",), ())
    await repo.set_last_synced(100, "iYokai — Test", ("a", "b"), ())
    keywords, _ = await repo.get_last_synced(100, "iYokai — Test")
    assert keywords == ("a", "b")


@pytest.mark.asyncio
async def test_last_synced_indipendente_per_nome_regola(repo):
    await repo.set_last_synced(100, "iYokai — Badwords", ("a",), ())
    await repo.set_last_synced(100, "iYokai — Anti-Invite", (), ("pattern",))

    kw_badwords, _ = await repo.get_last_synced(100, "iYokai — Badwords")
    _, regex_invite = await repo.get_last_synced(100, "iYokai — Anti-Invite")
    assert kw_badwords == ("a",)
    assert regex_invite == ("pattern",)


@pytest.mark.asyncio
async def test_clear_last_synced(repo):
    await repo.set_last_synced(100, "iYokai — Test", ("a",), ())
    await repo.clear_last_synced(100, "iYokai — Test")
    keywords, regex = await repo.get_last_synced(100, "iYokai — Test")
    assert keywords == ()
    assert regex == ()

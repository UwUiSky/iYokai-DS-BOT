"""
tests/test_blacklist_repo.py
===============================
Test di BlacklistRepository contro PostgreSQL reale — incluso un test
dedicato che dimostra la cache davvero usata, stesso pattern già
collaudato per la config moduli e spam_trap.
"""

import pytest

from core.repositories.blacklist_repo import BlacklistRepository


@pytest.fixture
def repo(clean_db):
    return BlacklistRepository(pool_provider=lambda: clean_db)


# ====================================================================
# Utenti
# ====================================================================
@pytest.mark.asyncio
async def test_utente_non_in_blacklist_di_default(repo):
    assert await repo.is_user_blacklisted(1) is False


@pytest.mark.asyncio
async def test_add_e_is_user_blacklisted(repo):
    await repo.add_user(1, reason="spam ripetuto", added_by=99)
    assert await repo.is_user_blacklisted(1) is True


@pytest.mark.asyncio
async def test_remove_user(repo):
    await repo.add_user(1, reason="test", added_by=99)
    rimosso = await repo.remove_user(1)
    assert rimosso is True
    assert await repo.is_user_blacklisted(1) is False


@pytest.mark.asyncio
async def test_remove_user_inesistente_restituisce_false(repo):
    assert await repo.remove_user(999) is False


@pytest.mark.asyncio
async def test_list_users(repo):
    await repo.add_user(1, reason="a", added_by=99)
    await repo.add_user(2, reason="b", added_by=99)
    risultato = await repo.list_users()
    assert len(risultato) == 2


@pytest.mark.asyncio
async def test_is_user_blacklisted_cache_serve_davvero_dalla_memoria(repo, clean_db):
    # Stesso identico schema già usato per is_module_active_for_guild
    # e per spam_trap_repo.get_config: SQL grezzo che bypassa la
    # cache, verifica che il valore stantio resti in memoria finché
    # non si passa esplicitamente da add_user/remove_user.
    await repo.add_user(1, reason="test", added_by=99)
    assert await repo.is_user_blacklisted(1) is True

    await clean_db.execute("DELETE FROM user_blacklist WHERE user_id = 1")

    # La cache non sa nulla di questa modifica: deve restituire
    # ANCORA True.
    assert await repo.is_user_blacklisted(1) is True

    # Solo passando da remove_user (che invalida) il nuovo stato
    # diventa visibile.
    await repo.remove_user(1)
    assert await repo.is_user_blacklisted(1) is False


# ====================================================================
# Server
# ====================================================================
@pytest.mark.asyncio
async def test_server_non_in_blacklist_di_default(repo):
    assert await repo.is_guild_blacklisted(100) is False


@pytest.mark.asyncio
async def test_add_e_is_guild_blacklisted(repo):
    await repo.add_guild(100, reason="raid organizzato", added_by=99)
    assert await repo.is_guild_blacklisted(100) is True


@pytest.mark.asyncio
async def test_remove_guild(repo):
    await repo.add_guild(100, reason="test", added_by=99)
    rimosso = await repo.remove_guild(100)
    assert rimosso is True
    assert await repo.is_guild_blacklisted(100) is False


@pytest.mark.asyncio
async def test_remove_guild_inesistente_restituisce_false(repo):
    assert await repo.remove_guild(999) is False


@pytest.mark.asyncio
async def test_list_guilds(repo):
    await repo.add_guild(100, reason="a", added_by=99)
    await repo.add_guild(200, reason="b", added_by=99)
    risultato = await repo.list_guilds()
    assert len(risultato) == 2


@pytest.mark.asyncio
async def test_is_guild_blacklisted_cache_serve_davvero_dalla_memoria(repo, clean_db):
    await repo.add_guild(100, reason="test", added_by=99)
    assert await repo.is_guild_blacklisted(100) is True

    await clean_db.execute("DELETE FROM guild_blacklist WHERE guild_id = 100")

    assert await repo.is_guild_blacklisted(100) is True

    await repo.remove_guild(100)
    assert await repo.is_guild_blacklisted(100) is False


@pytest.mark.asyncio
async def test_blacklist_utenti_e_server_indipendenti(repo):
    # Un ID che esiste come utente bloccato non deve mai risultare
    # bloccato anche come server - le due tabelle sono indipendenti.
    await repo.add_user(100, reason="utente", added_by=99)
    assert await repo.is_guild_blacklisted(100) is False

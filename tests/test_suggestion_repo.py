"""
tests/test_suggestion_repo.py
================================
Test di SuggestionRepository contro PostgreSQL reale.
"""

from datetime import datetime, timezone

import pytest

from core.repositories.suggestion_repo import SuggestionRepository
from core.suggestion_logic import APPROVED, PENDING, REJECTED


@pytest.fixture
def repo(clean_db):
    return SuggestionRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_create_e_get_suggestion(repo):
    suggestion_id = await repo.create_suggestion(
        guild_id=100, channel_id=500, user_id=1, suggestion_text="Aggiungete un canale meme"
    )
    suggestion = await repo.get_suggestion(suggestion_id)

    assert suggestion is not None
    assert suggestion.guild_id == 100
    assert suggestion.suggestion_text == "Aggiungete un canale meme"
    assert suggestion.status == PENDING
    assert suggestion.message_id is None


@pytest.mark.asyncio
async def test_get_suggestion_inesistente_restituisce_none(repo):
    assert await repo.get_suggestion(999999) is None


@pytest.mark.asyncio
async def test_set_message_id(repo):
    suggestion_id = await repo.create_suggestion(100, 500, 1, "Testo")
    await repo.set_message_id(suggestion_id, message_id=12345)

    suggestion = await repo.get_suggestion(suggestion_id)
    assert suggestion.message_id == 12345


@pytest.mark.asyncio
async def test_set_status_approva(repo):
    suggestion_id = await repo.create_suggestion(100, 500, 1, "Testo")
    ora = datetime.now(timezone.utc)

    await repo.set_status(suggestion_id, APPROVED, decided_by=99, decided_at=ora)

    suggestion = await repo.get_suggestion(suggestion_id)
    assert suggestion.status == APPROVED
    assert suggestion.decided_by == 99
    assert suggestion.decided_at is not None


@pytest.mark.asyncio
async def test_set_status_rifiuta(repo):
    suggestion_id = await repo.create_suggestion(100, 500, 1, "Testo")
    ora = datetime.now(timezone.utc)

    await repo.set_status(suggestion_id, REJECTED, decided_by=99, decided_at=ora)

    suggestion = await repo.get_suggestion(suggestion_id)
    assert suggestion.status == REJECTED


@pytest.mark.asyncio
async def test_list_pending_filtra_per_server(repo):
    id_100 = await repo.create_suggestion(100, 500, 1, "Server 100")
    id_200 = await repo.create_suggestion(200, 600, 1, "Server 200")

    risultato_100 = await repo.list_pending(guild_id=100)
    assert len(risultato_100) == 1
    assert risultato_100[0].id == id_100


@pytest.mark.asyncio
async def test_list_pending_esclude_quelle_gia_decise(repo):
    id_pending = await repo.create_suggestion(100, 500, 1, "In sospeso")
    id_approvata = await repo.create_suggestion(100, 500, 1, "Approvata")
    await repo.set_status(id_approvata, APPROVED, decided_by=99, decided_at=datetime.now(timezone.utc))

    risultato = await repo.list_pending(guild_id=100)
    assert len(risultato) == 1
    assert risultato[0].id == id_pending


@pytest.mark.asyncio
async def test_list_pending_senza_guild_id_prende_tutte_ma_solo_con_message_id(repo):
    # Usata all'avvio del bot per ricostruire le View: una suggestion
    # creata ma senza ancora un messaggio pubblicato (caso limite,
    # non dovrebbe capitare in pratica) non deve comparire, non c'è
    # un messaggio a cui agganciare una View.
    id_con_messaggio = await repo.create_suggestion(100, 500, 1, "Con messaggio")
    await repo.set_message_id(id_con_messaggio, message_id=111)
    await repo.create_suggestion(200, 600, 1, "Senza messaggio")

    risultato = await repo.list_pending()
    assert len(risultato) == 1
    assert risultato[0].id == id_con_messaggio

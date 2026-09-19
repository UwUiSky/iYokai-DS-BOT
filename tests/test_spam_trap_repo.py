"""
tests/test_spam_trap_repo.py
===============================
Test di SpamTrapRepository contro PostgreSQL reale.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.repositories.spam_trap_repo import SpamTrapRepository


@pytest.fixture
def repo(clean_db):
    return SpamTrapRepository(pool_provider=lambda: clean_db)


# ====================================================================
# Configurazione
# ====================================================================
@pytest.mark.asyncio
async def test_config_di_default_e_vuota(repo):
    config = await repo.get_config(100)
    assert config.trap_channel_id is None
    assert config.log_channel_id is None


@pytest.mark.asyncio
async def test_set_e_get_config(repo):
    await repo.set_config(100, trap_channel_id=111, log_channel_id=222)
    config = await repo.get_config(100)
    assert config.trap_channel_id == 111
    assert config.log_channel_id == 222


@pytest.mark.asyncio
async def test_set_config_sovrascrive(repo):
    await repo.set_config(100, 111, 222)
    await repo.set_config(100, 333, 444)
    config = await repo.get_config(100)
    assert config.trap_channel_id == 333
    assert config.log_channel_id == 444


@pytest.mark.asyncio
async def test_get_config_cache_serve_davvero_dalla_memoria(repo, clean_db):
    # Prova diretta che la cache è USATA (non solo che il metodo
    # continua a funzionare, che test_set_config_sovrascrive già
    # copre): modifichiamo la riga con SQL grezzo che bypassa
    # set_config (quindi bypassa anche l'invalidazione), e
    # verifichiamo che get_config continui a restituire il valore
    # VECCHIO finché non passiamo esplicitamente da set_config.
    await repo.set_config(100, 111, 222)

    # Primo giro: legge dal DB, popola la cache.
    config = await repo.get_config(100)
    assert config.trap_channel_id == 111

    # Modifica DIRETTA sul DB, bypassando set_config.
    await clean_db.execute(
        "UPDATE spam_trap_config SET trap_channel_id = 999 WHERE guild_id = $1", 100
    )

    # La cache non sa nulla di questa modifica: deve restituire
    # ANCORA 111 (il valore stantio), prova che legge dalla memoria.
    config_stantio = await repo.get_config(100)
    assert config_stantio.trap_channel_id == 111

    # Solo passando da set_config (che invalida) il nuovo valore
    # diventa visibile.
    await repo.set_config(100, 999, 222)
    config_aggiornato = await repo.get_config(100)
    assert config_aggiornato.trap_channel_id == 999


@pytest.mark.asyncio
async def test_get_config_cache_non_mischia_server(repo):
    await repo.set_config(100, 111, 222)
    await repo.set_config(200, 333, 444)

    config_100 = await repo.get_config(100)
    config_200 = await repo.get_config(200)
    assert config_100.trap_channel_id == 111
    assert config_200.trap_channel_id == 333


# ====================================================================
# Indice messaggi
# ====================================================================
@pytest.mark.asyncio
async def test_index_message_e_lettura(repo):
    ora = datetime.now(timezone.utc)
    await repo.index_message(
        message_id=1001, guild_id=100, channel_id=5000, user_id=1, created_at=ora
    )

    messaggi = await repo.get_all_user_messages(100, 1)
    assert len(messaggi) == 1
    assert messaggi[0].message_id == 1001
    assert messaggi[0].channel_id == 5000


@pytest.mark.asyncio
async def test_index_message_duplicato_non_fallisce(repo):
    ora = datetime.now(timezone.utc)
    await repo.index_message(1001, 100, 5000, 1, ora)
    # Stesso message_id due volte (es. evento duplicato): non deve
    # sollevare eccezioni né creare una riga in più.
    await repo.index_message(1001, 100, 5000, 1, ora)

    messaggi = await repo.get_all_user_messages(100, 1)
    assert len(messaggi) == 1


@pytest.mark.asyncio
async def test_get_user_messages_in_window_filtra_correttamente(repo):
    ora = datetime.now(timezone.utc)
    await repo.index_message(1, 100, 5000, 1, ora - timedelta(days=2))   # dentro
    await repo.index_message(2, 100, 5000, 1, ora - timedelta(days=40))  # fuori (troppo vecchio)
    await repo.index_message(3, 100, 5000, 1, ora + timedelta(days=1))   # fuori (troppo recente)

    risultato = await repo.get_user_messages_in_window(
        100, 1, start=ora - timedelta(days=30), end=ora
    )
    assert {m.message_id for m in risultato} == {1}


@pytest.mark.asyncio
async def test_get_user_messages_non_mischia_altri_utenti(repo):
    ora = datetime.now(timezone.utc)
    await repo.index_message(1, 100, 5000, 1, ora)
    await repo.index_message(2, 100, 5000, 2, ora)  # altro utente

    messaggi = await repo.get_all_user_messages(100, 1)
    assert len(messaggi) == 1
    assert messaggi[0].message_id == 1


@pytest.mark.asyncio
async def test_get_user_messages_non_mischia_altri_server(repo):
    ora = datetime.now(timezone.utc)
    await repo.index_message(1, 100, 5000, 1, ora)
    await repo.index_message(2, 200, 5000, 1, ora)  # altro server

    messaggi = await repo.get_all_user_messages(100, 1)
    assert len(messaggi) == 1


@pytest.mark.asyncio
async def test_delete_indexed_messages(repo):
    ora = datetime.now(timezone.utc)
    await repo.index_message(1, 100, 5000, 1, ora)
    await repo.index_message(2, 100, 5000, 1, ora)

    await repo.delete_indexed_messages([1])

    messaggi = await repo.get_all_user_messages(100, 1)
    assert {m.message_id for m in messaggi} == {2}


@pytest.mark.asyncio
async def test_delete_indexed_messages_lista_vuota_non_fallisce(repo):
    await repo.delete_indexed_messages([])  # non deve sollevare eccezioni


@pytest.mark.asyncio
async def test_prune_old_index(repo):
    ora = datetime.now(timezone.utc)
    await repo.index_message(1, 100, 5000, 1, ora - timedelta(days=40))  # vecchio
    await repo.index_message(2, 100, 5000, 1, ora - timedelta(days=5))   # recente

    eliminati = await repo.prune_old_index(older_than=ora - timedelta(days=30))

    assert eliminati == 1
    messaggi = await repo.get_all_user_messages(100, 1)
    assert {m.message_id for m in messaggi} == {2}


# ====================================================================
# Appeal
# ====================================================================
@pytest.mark.asyncio
async def test_last_appeal_di_default_e_none(repo):
    assert await repo.get_last_appeal(100, 1) is None


@pytest.mark.asyncio
async def test_set_e_get_last_appeal(repo):
    ora = datetime.now(timezone.utc)
    await repo.set_last_appeal(100, 1, ora)
    letto = await repo.get_last_appeal(100, 1)
    assert letto is not None


@pytest.mark.asyncio
async def test_set_last_appeal_sovrascrive(repo):
    ora1 = datetime.now(timezone.utc) - timedelta(days=1)
    ora2 = datetime.now(timezone.utc)
    await repo.set_last_appeal(100, 1, ora1)
    await repo.set_last_appeal(100, 1, ora2)

    letto = await repo.get_last_appeal(100, 1)
    # Verifica che sia stato aggiornato al secondo valore (con
    # tolleranza sui microsecondi di precisione del DB).
    assert abs((letto - ora2).total_seconds()) < 1


# ====================================================================
# Incidenti
# ====================================================================
@pytest.mark.asyncio
async def test_create_e_get_incident(repo):
    incident_id = await repo.create_incident(
        guild_id=100,
        case_number=1,
        trapped_content="ciao a tutti",
        invite_code="abc123",
        invite_creator_id=42,
        deleted_count_by_channel={"general": 5, "memes": 3},
        transcript_html="<html>...</html>",
    )
    assert isinstance(incident_id, int)

    incidente = await repo.get_incident_by_case(100, 1)
    assert incidente is not None
    assert incidente.trapped_content == "ciao a tutti"
    assert incidente.invite_code == "abc123"
    assert incidente.invite_creator_id == 42
    assert incidente.deleted_count_by_channel == {"general": 5, "memes": 3}
    assert incidente.transcript_html == "<html>...</html>"


@pytest.mark.asyncio
async def test_get_incident_inesistente_restituisce_none(repo):
    assert await repo.get_incident_by_case(999, 999) is None


@pytest.mark.asyncio
async def test_create_incident_senza_invito(repo):
    # Caso "nessun invito determinato" (vanity URL o ambiguo).
    await repo.create_incident(
        guild_id=100,
        case_number=1,
        trapped_content="x",
        invite_code=None,
        invite_creator_id=None,
        deleted_count_by_channel={},
    )
    incidente = await repo.get_incident_by_case(100, 1)
    assert incidente.invite_code is None
    assert incidente.invite_creator_id is None


@pytest.mark.asyncio
async def test_create_incident_transcript_html_e_opzionale(repo):
    # transcript_html non passato esplicitamente: deve restare NULL,
    # non far fallire l'inserimento (il ban avviene subito, il
    # transcript può essere generato e collegato in un secondo
    # momento se qualcosa va storto nella generazione).
    await repo.create_incident(
        guild_id=100,
        case_number=1,
        trapped_content="x",
        invite_code=None,
        invite_creator_id=None,
        deleted_count_by_channel={},
    )
    incidente = await repo.get_incident_by_case(100, 1)
    assert incidente.transcript_html is None


# ====================================================================
# Invito al join
# ====================================================================
@pytest.mark.asyncio
async def test_get_latest_join_invite_senza_join_restituisce_none(repo):
    assert await repo.get_latest_join_invite(100, 1) is None


@pytest.mark.asyncio
async def test_record_e_get_latest_join_invite(repo):
    await repo.record_join_invite(100, 1, invite_code="abc123", invite_creator_id=42)
    risultato = await repo.get_latest_join_invite(100, 1)
    assert risultato == ("abc123", 42)


@pytest.mark.asyncio
async def test_record_join_invite_senza_invito_determinato(repo):
    # Corrisponde a diff_invite_uses() che ha restituito None (join
    # da vanity URL o caso ambiguo).
    await repo.record_join_invite(100, 1, invite_code=None, invite_creator_id=None)
    risultato = await repo.get_latest_join_invite(100, 1)
    assert risultato == (None, None)


@pytest.mark.asyncio
async def test_get_latest_join_invite_restituisce_il_piu_recente(repo):
    # L'utente è entrato, uscito, e rientrato con un invito diverso:
    # deve valere l'ULTIMO join, non il primo.
    await repo.record_join_invite(100, 1, invite_code="vecchio", invite_creator_id=1)
    await repo.record_join_invite(100, 1, invite_code="nuovo", invite_creator_id=2)

    risultato = await repo.get_latest_join_invite(100, 1)
    assert risultato == ("nuovo", 2)

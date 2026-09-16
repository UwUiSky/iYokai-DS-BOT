"""
tests/test_moderation_repo.py
================================
Test del case system contro PostgreSQL reale. Usa una istanza
ModerationRepository "locale", costruita passando pool_provider che
punta al pool di test (clean_db) — non serve monkeypatchare il
singleton globale, il repository è già progettato per accettare un
provider diverso, proprio per rendere questo genere di test diretto.
"""

import asyncio

import pytest

from core.repositories.moderation_repo import ModerationRepository, run_migrations


@pytest.fixture
def repo(clean_db):
    return ModerationRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_migrations_sono_idempotenti(clean_db):
    await run_migrations(clean_db)
    await run_migrations(clean_db)  # non deve sollevare errori

    for tabella in (
        "moderation_case_counters",
        "moderation_cases",
        "moderation_notes",
    ):
        exists = await clean_db.fetchval(
            "SELECT to_regclass($1) IS NOT NULL", f"public.{tabella}"
        )
        assert exists is True


@pytest.mark.asyncio
async def test_primo_caso_di_un_server_e_il_numero_1(repo):
    numero = await repo.create_case(
        guild_id=100, user_id=1, moderator_id=999, action_type="warn"
    )
    assert numero == 1


@pytest.mark.asyncio
async def test_numeri_di_caso_progressivi_nello_stesso_server(repo):
    n1 = await repo.create_case(100, 1, 999, "warn")
    n2 = await repo.create_case(100, 2, 999, "kick")
    n3 = await repo.create_case(100, 1, 999, "ban")
    assert (n1, n2, n3) == (1, 2, 3)


@pytest.mark.asyncio
async def test_ogni_server_ha_la_propria_numerazione_indipendente(repo):
    # Il caso #1 del server A non deve avere nulla a che fare con il
    # caso #1 del server B: ognuno riparte da 1.
    n_server_a = await repo.create_case(guild_id=100, user_id=1, moderator_id=9, action_type="warn")
    n_server_b = await repo.create_case(guild_id=200, user_id=1, moderator_id=9, action_type="warn")
    assert n_server_a == 1
    assert n_server_b == 1


@pytest.mark.asyncio
async def test_numerazione_resta_corretta_con_scritture_concorrenti(repo):
    # Il punto critico del case system: se due moderatori bannano
    # due persone diverse nello STESSO istante, i numeri di caso
    # assegnati devono essere comunque univoci e senza buchi. Lo
    # verifichiamo lanciando 20 create_case in parallelo con
    # asyncio.gather, non in sequenza.
    risultati = await asyncio.gather(
        *[
            repo.create_case(guild_id=300, user_id=i, moderator_id=9, action_type="warn")
            for i in range(20)
        ]
    )
    # Devono essere 20 numeri TUTTI DIVERSI (nessuna collisione) e,
    # essendo assegnati da un contatore che parte da 1 e incrementa
    # di 1 alla volta, insieme devono coprire esattamente 1..20.
    assert sorted(risultati) == list(range(1, 21))


@pytest.mark.asyncio
async def test_get_case_restituisce_i_dati_corretti(repo):
    numero = await repo.create_case(
        guild_id=100,
        user_id=42,
        moderator_id=7,
        action_type="ban",
        reason="spam ripetuto",
        duration_seconds=None,
    )
    caso = await repo.get_case(100, numero)
    assert caso is not None
    assert caso.user_id == 42
    assert caso.moderator_id == 7
    assert caso.action_type == "ban"
    assert caso.reason == "spam ripetuto"
    assert caso.active is True
    assert caso.revoked_at is None


@pytest.mark.asyncio
async def test_get_case_inesistente_restituisce_none(repo):
    caso = await repo.get_case(guild_id=999, case_number=999)
    assert caso is None


@pytest.mark.asyncio
async def test_list_cases_for_user_ordina_dal_piu_recente(repo):
    await repo.create_case(100, 1, 9, "warn")
    await repo.create_case(100, 1, 9, "kick")
    await repo.create_case(100, 1, 9, "ban")

    storico = await repo.list_cases_for_user(100, 1)
    assert [c.action_type for c in storico] == ["ban", "kick", "warn"]


@pytest.mark.asyncio
async def test_list_cases_for_user_non_mischia_altri_utenti(repo):
    await repo.create_case(100, 1, 9, "warn")
    await repo.create_case(100, 2, 9, "warn")  # altro utente

    storico_utente_1 = await repo.list_cases_for_user(100, 1)
    assert len(storico_utente_1) == 1
    assert storico_utente_1[0].user_id == 1


@pytest.mark.asyncio
async def test_revoke_case_disattiva_il_caso(repo):
    numero = await repo.create_case(100, 1, 9, "ban")

    revocato = await repo.revoke_case(100, numero, revoked_by=42)
    assert revocato is True

    caso = await repo.get_case(100, numero)
    assert caso.active is False
    assert caso.revoked_by == 42
    assert caso.revoked_at is not None


@pytest.mark.asyncio
async def test_revoke_case_su_caso_gia_revocato_restituisce_false(repo):
    numero = await repo.create_case(100, 1, 9, "ban")
    await repo.revoke_case(100, numero, revoked_by=42)

    # Secondo tentativo sullo stesso caso, già inattivo.
    revocato_di_nuovo = await repo.revoke_case(100, numero, revoked_by=42)
    assert revocato_di_nuovo is False


@pytest.mark.asyncio
async def test_revoke_case_inesistente_restituisce_false(repo):
    revocato = await repo.revoke_case(guild_id=999, case_number=999, revoked_by=1)
    assert revocato is False


@pytest.mark.asyncio
async def test_get_latest_active_case_ignora_i_revocati(repo):
    n1 = await repo.create_case(100, 1, 9, "ban")
    await repo.revoke_case(100, n1, revoked_by=9)
    n2 = await repo.create_case(100, 1, 9, "ban")  # ribannato dopo

    attivo = await repo.get_latest_active_case(100, 1, "ban")
    assert attivo is not None
    assert attivo.case_number == n2


@pytest.mark.asyncio
async def test_get_latest_active_case_restituisce_none_se_nessuno_attivo(repo):
    n1 = await repo.create_case(100, 1, 9, "ban")
    await repo.revoke_case(100, n1, revoked_by=9)

    attivo = await repo.get_latest_active_case(100, 1, "ban")
    assert attivo is None


@pytest.mark.asyncio
async def test_note_vengono_salvate_e_lette_in_ordine(repo):
    await repo.add_note(100, 1, 9, "prima nota")
    await repo.add_note(100, 1, 9, "seconda nota")

    note = await repo.list_notes_for_user(100, 1)
    assert [n.note for n in note] == ["seconda nota", "prima nota"]

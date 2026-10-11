"""
tests/test_retention_worker.py
==============================
NF-04 (#19, #46, D6): 90 giorni dopo l'uscita del bot i dati del server vanno,
tranne ban e kick; le tabelle che crescono scadono; un rientro prima dei 90
giorni non perde niente.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core import retention_worker as lavoro
from core.repositories.guild_presence_repo import GuildPresenceRepository

G = 7000      # il server uscito
ALTRO = 7001  # un server che resta
ADESSO = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def presenza(clean_db, monkeypatch):
    repo = GuildPresenceRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(lavoro, "guild_presence_repo", repo)
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    return repo


async def _dati_del_server(pool, guild_id):
    await pool.execute("INSERT INTO guild_config (guild_id) VALUES ($1)", guild_id)
    await pool.execute("INSERT INTO leveling_totals (guild_id,user_id,xp_total) VALUES ($1,1,5)", guild_id)
    await pool.execute("INSERT INTO moderation_cases (guild_id,case_number,user_id,moderator_id,action_type) VALUES ($1,1,5,9,'warn')", guild_id)
    await pool.execute("INSERT INTO moderation_cases (guild_id,case_number,user_id,moderator_id,action_type) VALUES ($1,2,5,9,'ban')", guild_id)
    await pool.execute("INSERT INTO event_log (guild_id,event_type,target_user_id) VALUES ($1,'warn',5)", guild_id)
    await pool.execute("INSERT INTO event_log (guild_id,event_type,target_user_id) VALUES ($1,'kick',5)", guild_id)
    await pool.execute("INSERT INTO clans (guild_id,tag,name,owner_id,officialize_deadline) VALUES ($1,'T','C',1,now())", guild_id)
    clan = await pool.fetchval("SELECT id FROM clans WHERE guild_id = $1", guild_id)
    await pool.execute("INSERT INTO clan_treasury_ledger (clan_id,user_id,amount,reason) VALUES ($1,1,5,'x')", clan)
    await pool.execute("INSERT INTO clan_members (clan_id,guild_id,user_id,role) VALUES ($1,$2,1,'member')", clan, guild_id)
    await pool.execute(
        "INSERT INTO restore_oauth_tokens (source_guild_id,user_id,encrypted_access_token,encrypted_refresh_token,expires_at)"
        " VALUES ($1,1,'a','b',now())", guild_id,
    )
    await pool.execute("INSERT INTO scheduled_actions (guild_id,user_id,action_type,execute_at) VALUES ($1,1,'unban',now())", guild_id)
    await pool.execute("INSERT INTO global_ban_log (source_guild_id,target_guild_id,user_id) VALUES ($1,99,5)", guild_id)


async def _conta(pool, tabella, colonna, guild_id):
    return await pool.fetchval(f"SELECT count(*) FROM {tabella} WHERE {colonna} = $1", guild_id)


# ------------------------------------------------------------------ presenza
@pytest.mark.asyncio
async def test_uscita_e_rientro(presenza):
    await presenza.segna_entrato(G)
    assert (await presenza.get(G))["left_at"] is None

    await presenza.segna_uscito(G, ADESSO - timedelta(days=10))
    assert (await presenza.get(G))["left_at"] is not None

    await presenza.segna_uscito(G, ADESSO)  # una seconda uscita non sposta il conto
    assert (await presenza.get(G))["left_at"] == ADESSO - timedelta(days=10)

    await presenza.segna_entrato(G)  # rientro prima dei 90 giorni: niente si perde
    assert (await presenza.get(G))["left_at"] is None


@pytest.mark.asyncio
async def test_da_cancellare_solo_dopo_90_giorni(presenza):
    await presenza.segna_uscito(G, ADESSO - timedelta(days=89))
    await presenza.segna_uscito(ALTRO, ADESSO - timedelta(days=91))

    assert await presenza.da_cancellare(ADESSO) == [ALTRO]


@pytest.mark.asyncio
async def test_sincronizza_segna_usciti_i_server_non_piu_visibili(presenza):
    await presenza.segna_entrato(G)
    await presenza.segna_entrato(ALTRO)

    usciti = await presenza.sincronizza({ALTRO, 7002})

    assert usciti == 1
    assert (await presenza.get(G))["left_at"] is not None
    assert (await presenza.get(ALTRO))["left_at"] is None
    assert (await presenza.get(7002)) is not None


@pytest.mark.asyncio
async def test_sincronizza_riporta_dentro_chi_e_tornato(presenza):
    await presenza.segna_uscito(G, ADESSO - timedelta(days=5))

    await presenza.sincronizza({G})

    assert (await presenza.get(G))["left_at"] is None


# ------------------------------------------------------------------ cancellazione del server
@pytest.mark.asyncio
async def test_purga_cancella_il_server_e_tiene_ban_e_kick(clean_db, presenza):
    await _dati_del_server(clean_db, G)
    await _dati_del_server(clean_db, ALTRO)
    await presenza.segna_uscito(G, ADESSO - timedelta(days=100))

    tolte = await lavoro.purga_server(clean_db, G)

    assert tolte["leveling_totals"] == 1
    assert await _conta(clean_db, "guild_config", "guild_id", G) == 0
    assert await _conta(clean_db, "clans", "guild_id", G) == 0
    assert await clean_db.fetchval("SELECT count(*) FROM clan_treasury_ledger") == 1  # solo quello dell'altro
    assert await _conta(clean_db, "restore_oauth_tokens", "source_guild_id", G) == 0
    assert await _conta(clean_db, "scheduled_actions", "guild_id", G) == 0
    # ban e kick restano
    azioni = {r["action_type"] for r in await clean_db.fetch("SELECT action_type FROM moderation_cases WHERE guild_id = $1", G)}
    assert azioni == {"ban"}
    eventi = {r["event_type"] for r in await clean_db.fetch("SELECT event_type FROM event_log WHERE guild_id = $1", G)}
    assert eventi == {"kick"}
    assert await _conta(clean_db, "global_ban_log", "source_guild_id", G) == 1
    # l'altro server è intatto
    assert await _conta(clean_db, "leveling_totals", "guild_id", ALTRO) == 1
    assert await _conta(clean_db, "moderation_cases", "guild_id", ALTRO) == 2
    assert (await presenza.get(G))["purged_at"] is not None


@pytest.mark.asyncio
async def test_giro_cancella_solo_chi_e_uscito_da_piu_di_90_giorni(clean_db, presenza):
    await _dati_del_server(clean_db, G)
    await _dati_del_server(clean_db, ALTRO)
    await presenza.segna_uscito(G, ADESSO - timedelta(days=91))
    await presenza.segna_uscito(ALTRO, ADESSO - timedelta(days=89))

    esito = await lavoro.giro(clean_db, set(), ADESSO)

    assert list(esito["server"]) == [G]
    assert await _conta(clean_db, "leveling_totals", "guild_id", G) == 0
    assert await _conta(clean_db, "leveling_totals", "guild_id", ALTRO) == 1


@pytest.mark.asyncio
async def test_giro_non_tocca_un_server_in_cui_il_bot_e_adesso(clean_db, presenza):
    await _dati_del_server(clean_db, G)
    await presenza.segna_uscito(G, ADESSO - timedelta(days=200))

    esito = await lavoro.giro(clean_db, {G}, ADESSO)

    assert esito["server"] == {}
    assert await _conta(clean_db, "leveling_totals", "guild_id", G) == 1
    assert (await presenza.get(G))["left_at"] is None  # lo riconosce come tornato


@pytest.mark.asyncio
async def test_seconda_esecuzione_non_rompe_niente(clean_db, presenza):
    await _dati_del_server(clean_db, G)
    await presenza.segna_uscito(G, ADESSO - timedelta(days=100))
    await lavoro.giro(clean_db, set(), ADESSO)

    secondo = await lavoro.giro(clean_db, set(), ADESSO)

    assert secondo["server"] == {}


@pytest.mark.asyncio
async def test_la_cancellazione_di_un_server_svuota_le_cache_in_memoria(clean_db, presenza):
    import core.database as database_module

    db = database_module.db
    await _dati_del_server(clean_db, G)
    await db.set_guild_setting(G, "canale", 5)
    assert await db.get_guild_setting(G, "canale") == 5

    await lavoro.purga_server(clean_db, G)

    assert await db.get_guild_setting(G, "canale", default="niente") == "niente"


# ------------------------------------------------------------------ scadenze
@pytest.mark.asyncio
async def test_le_righe_scadute_vanno_le_recenti_restano(clean_db, presenza):
    await clean_db.execute("INSERT INTO verify_attempts (guild_id,user_id,success,reason,attempted_at) VALUES (1,1,true,'x', now() - interval '91 days')")
    await clean_db.execute("INSERT INTO verify_attempts (guild_id,user_id,success,reason) VALUES (1,2,true,'x')")
    await clean_db.execute("INSERT INTO scheduled_actions (guild_id,user_id,action_type,execute_at,executed,executed_at) VALUES (1,1,'a', now(), TRUE, now() - interval '31 days')")
    await clean_db.execute("INSERT INTO scheduled_actions (guild_id,user_id,action_type,execute_at,executed,executed_at) VALUES (1,2,'b', now(), TRUE, now())")
    await clean_db.execute("INSERT INTO scheduled_actions (guild_id,user_id,action_type,execute_at,created_at) VALUES (1,3,'c', now() - interval '60 days', now() - interval '60 days')")
    await clean_db.execute("INSERT INTO command_usage (guild_id,user_id,command_path,used_at) VALUES (1,1,'x', now() - interval '91 days')")

    tolte = await lavoro.pulisci_scaduti(clean_db)

    assert tolte["verify_attempts"] == 1
    assert tolte["scheduled_actions"] == 1  # solo l'eseguita vecchia; quella ancora in coda resta
    assert tolte["command_usage"] == 1
    assert await clean_db.fetchval("SELECT count(*) FROM verify_attempts") == 1
    assert {r["user_id"] for r in await clean_db.fetch("SELECT user_id FROM scheduled_actions")} == {2, 3}


@pytest.mark.asyncio
async def test_le_richieste_di_cancellazione_si_tengono_24_mesi(clean_db, presenza):
    await clean_db.execute("INSERT INTO data_deletion_requests (user_id,stato,richiesta_il) VALUES (1,'eseguita', now() - interval '800 days')")
    await clean_db.execute("INSERT INTO data_deletion_requests (user_id,stato,richiesta_il) VALUES (2,'eseguita', now() - interval '100 days')")
    await clean_db.execute("INSERT INTO data_deletion_requests (user_id,stato,richiesta_il) VALUES (3,'in_attesa', now() - interval '800 days')")

    tolte = await lavoro.pulisci_scaduti(clean_db)

    assert tolte["data_deletion_requests"] == 1
    assert await clean_db.fetchval("SELECT count(*) FROM data_deletion_requests") == 2

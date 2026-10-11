"""
tests/test_forget_user.py
=========================
NF-04 (#75, #37): cancellazione ed esportazione dei dati di un utente, contro il
database vero. Ban e kick restano; le altre righe vanno; gli altri utenti non si
toccano.
"""

import json

import pytest

from core import forget_user_service as servizio

U = 1001  # l'utente che chiede
V = 2002  # un altro utente: non deve cambiare niente
G = 5000


async def _prepara(pool):
    await pool.execute("INSERT INTO guild_config (guild_id) VALUES ($1)", G)
    for uid in (U, V):
        await pool.execute("INSERT INTO leveling_totals (guild_id, user_id, xp_total) VALUES ($1,$2,50)", G, uid)
        await pool.execute("INSERT INTO command_usage (guild_id, user_id, command_path) VALUES ($1,$2,'level rank')", G, uid)
        await pool.execute("INSERT INTO rank_card_prefs (user_id, colore, tema) VALUES ($1,'#FFFFFF','scuro')", uid)
        await pool.execute(
            "INSERT INTO restore_oauth_tokens (source_guild_id,user_id,encrypted_access_token,"
            "encrypted_refresh_token,expires_at) VALUES ($1,$2,'SEGRETO-A','SEGRETO-R', now())",
            G, uid,
        )
        await pool.execute("INSERT INTO suggestions (guild_id,channel_id,user_id,suggestion_text) VALUES ($1,1,$2,'idea')", G, uid)
        await pool.execute("INSERT INTO tickets (guild_id,ticket_number,channel_id,user_id) VALUES ($1,$2,$3,$3)", G, uid, uid)
    # casi: un avviso (si cancella), un ban e un kick (restano)
    for numero, azione in ((1, "warn"), (2, "ban"), (3, "kick")):
        await pool.execute(
            "INSERT INTO moderation_cases (guild_id,case_number,user_id,moderator_id,action_type) VALUES ($1,$2,$3,77,$4)",
            G, numero, U, azione,
        )
    # U come moderatore di un caso su V
    await pool.execute(
        "INSERT INTO moderation_cases (guild_id,case_number,user_id,moderator_id,action_type) VALUES ($1,4,$2,$3,'warn')",
        G, V, U,
    )
    await pool.execute("INSERT INTO event_log (guild_id,event_type,target_user_id,actor_id,details) VALUES ($1,'warn',$2,77,'{\"a\":1}')", G, U)
    await pool.execute("INSERT INTO event_log (guild_id,event_type,target_user_id,actor_id) VALUES ($1,'ban',$2,77)", G, U)
    await pool.execute("INSERT INTO global_ban_log (source_guild_id,target_guild_id,user_id) VALUES ($1,6,$2)", G, U)
    # azione ancora in coda (resta) e azione già eseguita (va)
    await pool.execute("INSERT INTO scheduled_actions (guild_id,user_id,action_type,execute_at) VALUES ($1,$2,'unban', now())", G, U)
    await pool.execute(
        "INSERT INTO scheduled_actions (guild_id,user_id,action_type,execute_at,executed) VALUES ($1,$2,'reminder', now(), TRUE)", G, U
    )
    await pool.execute("INSERT INTO clans (guild_id,tag,name,owner_id,officialize_deadline) VALUES ($1,'T','Clan',$2,now())", G, V)
    clan = await pool.fetchval("SELECT id FROM clans")
    await pool.execute("INSERT INTO clan_treasury_ledger (clan_id,user_id,amount,reason) VALUES ($1,$2,10,'deposito')", clan, U)
    await pool.execute("UPDATE clans SET co_owner_id = $1", U)


async def _conta(pool, tabella, colonna, uid):
    return await pool.fetchval(f"SELECT count(*) FROM {tabella} WHERE {colonna} = $1", uid)


@pytest.mark.asyncio
async def test_cancella_i_dati_dell_utente_e_solo_i_suoi(clean_db):
    await _prepara(clean_db)

    rapporto = await servizio.dimentica_utente(clean_db, U)

    for tabella in ("leveling_totals", "command_usage", "rank_card_prefs", "restore_oauth_tokens"):
        assert await _conta(clean_db, tabella, "user_id", U) == 0, tabella
        assert await _conta(clean_db, tabella, "user_id", V) == 1, tabella
    assert rapporto["restore_oauth_tokens"]["cancellate"] == 1
    assert rapporto["command_usage"]["cancellate"] == 1


@pytest.mark.asyncio
async def test_ban_e_kick_restano_le_altre_azioni_vanno(clean_db):
    await _prepara(clean_db)

    rapporto = await servizio.dimentica_utente(clean_db, U)

    azioni = {r["action_type"] for r in await clean_db.fetch("SELECT action_type FROM moderation_cases WHERE user_id = $1", U)}
    assert azioni == {"ban", "kick"}
    assert rapporto["moderation_cases"]["conservate"] == 2
    assert rapporto["moderation_cases"]["cancellate"] == 1
    assert rapporto["global_ban_log"]["conservate"] == 1
    assert await _conta(clean_db, "global_ban_log", "user_id", U) == 1


@pytest.mark.asyncio
async def test_event_log_diventa_anonimo_tranne_ban(clean_db):
    await _prepara(clean_db)

    await servizio.dimentica_utente(clean_db, U)

    righe = {r["event_type"]: r for r in await clean_db.fetch("SELECT * FROM event_log")}
    assert righe["warn"]["target_user_id"] is None
    assert json.loads(righe["warn"]["details"]) == {}
    assert righe["ban"]["target_user_id"] == U  # sicurezza


@pytest.mark.asyncio
async def test_ticket_e_suggerimenti_si_anonimizzano_e_restano_per_le_statistiche(clean_db):
    await _prepara(clean_db)

    await servizio.dimentica_utente(clean_db, U)

    assert await _conta(clean_db, "tickets", "user_id", 0) == 1
    assert await _conta(clean_db, "tickets", "user_id", U) == 0
    assert await clean_db.fetchval("SELECT suggestion_text FROM suggestions WHERE user_id = 0") == "[cancellato]"
    assert await _conta(clean_db, "suggestions", "user_id", V) == 1


@pytest.mark.asyncio
async def test_lo_staff_che_ha_agito_diventa_anonimo(clean_db):
    await _prepara(clean_db)

    await servizio.dimentica_utente(clean_db, U)

    assert await _conta(clean_db, "moderation_cases", "moderator_id", U) == 0
    assert await clean_db.fetchval("SELECT moderator_id FROM moderation_cases WHERE case_number = 4") == 0
    assert await clean_db.fetchval("SELECT co_owner_id FROM clans") == 0
    assert await clean_db.fetchval("SELECT user_id FROM clan_treasury_ledger") is None


@pytest.mark.asyncio
async def test_azione_in_coda_resta_quella_conclusa_va(clean_db):
    await _prepara(clean_db)

    await servizio.dimentica_utente(clean_db, U)

    tipi = {r["action_type"] for r in await clean_db.fetch("SELECT action_type FROM scheduled_actions WHERE user_id = $1", U)}
    assert tipi == {"unban"}


@pytest.mark.asyncio
async def test_il_titolare_di_un_clan_non_viene_toccato(clean_db):
    await _prepara(clean_db)

    rapporto = await servizio.dimentica_utente(clean_db, V)

    assert await clean_db.fetchval("SELECT owner_id FROM clans") == V
    assert rapporto["clans"]["conservate"] == 1


@pytest.mark.asyncio
async def test_secondo_giro_non_cambia_niente(clean_db):
    await _prepara(clean_db)
    await servizio.dimentica_utente(clean_db, U)

    secondo = await servizio.dimentica_utente(clean_db, U)

    assert servizio.riepilogo(secondo)["cancellate"] == 0
    assert servizio.riepilogo(secondo)["anonimizzate"] == 0


@pytest.mark.asyncio
async def test_utente_senza_dati_rapporto_vuoto(clean_db):
    assert await servizio.dimentica_utente(clean_db, 999) == {}


def test_il_testo_del_rapporto_spiega_cosa_resta():
    testo = servizio.testo_rapporto({"moderation_cases": {"cancellate": 1, "anonimizzate": 0, "conservate": 2}})
    assert "cancellate: 1" in testo and "conservate: 2" in testo and "sicurezza" in testo


# ---------------------------------------------------------------- esportazione
@pytest.mark.asyncio
async def test_esportazione_ha_i_dati_dell_utente_e_non_i_token(clean_db):
    await _prepara(clean_db)

    dati = await servizio.esporta_utente(clean_db, U)
    testo, accorciate = servizio.serializza_esportazione(dati)

    assert dati["utente"] == U
    assert {"leveling_totals", "command_usage", "rank_card_prefs", "moderation_cases", "restore_oauth_tokens"} <= set(dati["tabelle"])
    assert b"SEGRETO" not in testo
    assert accorciate == []
    righe_leveling = dati["tabelle"]["leveling_totals"]["righe"]
    assert [r["user_id"] for r in righe_leveling] == [U]


@pytest.mark.asyncio
async def test_esportazione_non_contiene_altri_utenti(clean_db):
    await _prepara(clean_db)

    dati = await servizio.esporta_utente(clean_db, V)

    for voce in dati["tabelle"].values():
        for riga in voce["righe"]:
            assert U not in {riga.get("user_id")}
    assert dati["tabelle"]["tickets"]["righe"][0]["user_id"] == V


def test_esportazione_troppo_grande_viene_accorciata():
    dati = {
        "utente": 1,
        "tabelle": {
            "grande": {"descrizione": "x", "righe": [{"t": "a" * 1000} for _ in range(400)]},
            "piccola": {"descrizione": "y", "righe": [{"t": "b"}]},
        },
    }
    testo, accorciate = servizio.serializza_esportazione(dati, limite_byte=50_000)

    assert len(testo) <= 60_000
    assert accorciate == ["grande"]
    assert json.loads(testo)["accorciate"] == ["grande"]
    assert json.loads(testo)["tabelle"]["piccola"]["righe"] == [{"t": "b"}]


# ---------------------------------------------------------------- richieste
@pytest.mark.asyncio
async def test_approvare_una_richiesta_cancella_e_la_chiude(clean_db):
    from core.repositories.data_deletion_request_repo import DataDeletionRequestRepository

    repo = DataDeletionRequestRepository(pool_provider=lambda: clean_db)
    await _prepara(clean_db)
    richiesta, nuova = await repo.crea(U, "voglio uscire")
    assert nuova is True

    esito = await servizio.esegui_richiesta(clean_db, richiesta, deciso_da=1)

    assert esito["user_id"] == U
    assert await _conta(clean_db, "leveling_totals", "user_id", U) == 0
    riga = await repo.get(richiesta)
    assert riga["stato"] == "eseguita" and riga["deciso_da"] == 1
    assert riga["esito"]["totali"]["cancellate"] >= 4
    # la richiesta resta come prova e non conta tra le righe "conservate"
    assert "data_deletion_requests" not in esito["rapporto"]
    assert await servizio.esegui_richiesta(clean_db, richiesta, deciso_da=1) is None


@pytest.mark.asyncio
async def test_una_sola_richiesta_in_attesa_per_utente(clean_db):
    from core.repositories.data_deletion_request_repo import DataDeletionRequestRepository

    repo = DataDeletionRequestRepository(pool_provider=lambda: clean_db)
    primo, nuova1 = await repo.crea(U)
    secondo, nuova2 = await repo.crea(U)

    assert (nuova1, nuova2) == (True, False)
    assert primo == secondo
    assert [r["id"] for r in await repo.in_attesa()] == [primo]


@pytest.mark.asyncio
async def test_rifiutare_non_cancella_niente(clean_db):
    from core.repositories.data_deletion_request_repo import STATO_RIFIUTATA, DataDeletionRequestRepository

    repo = DataDeletionRequestRepository(pool_provider=lambda: clean_db)
    await _prepara(clean_db)
    richiesta, _ = await repo.crea(U)

    assert await repo.chiudi(richiesta, STATO_RIFIUTATA, 1, {"motivo": "prova"}) is True
    assert await repo.chiudi(richiesta, STATO_RIFIUTATA, 1) is False
    assert await _conta(clean_db, "leveling_totals", "user_id", U) == 1
    nuova_id, nuova = await repo.crea(U)  # dopo il rifiuto può chiederne un'altra
    assert nuova is True and nuova_id != richiesta

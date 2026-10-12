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
    await pool.execute("INSERT INTO scheduled_actions (guild_id,user_id,action_type,execute_at) VALUES ($1,$2,'moderation_tempban_expire', now())", G, U)
    # un promemoria ancora in coda ha testo libero: va via
    await pool.execute(
        "INSERT INTO scheduled_actions (guild_id,user_id,action_type,execute_at,payload) VALUES ($1,$2,'reminder_fire', now(), '{\"message\": \"cosa privata\"}')", G, U
    )
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
    assert await clean_db.fetchval("SELECT co_owner_id FROM clans") is None
    assert await clean_db.fetchval("SELECT user_id FROM clan_treasury_ledger") is None


@pytest.mark.asyncio
async def test_azione_in_coda_resta_quella_conclusa_va(clean_db):
    await _prepara(clean_db)

    await servizio.dimentica_utente(clean_db, U)

    tipi = {r["action_type"] for r in await clean_db.fetch("SELECT action_type FROM scheduled_actions WHERE user_id = $1", U)}
    assert tipi == {"moderation_tempban_expire"}  # il promemoria in coda e' andato


@pytest.mark.asyncio
async def test_il_titolare_passa_al_co_titolare(clean_db):
    await _prepara(clean_db)  # V titolare, U co-titolare
    clan = await clean_db.fetchval("SELECT id FROM clans")
    await clean_db.execute("INSERT INTO clan_members (clan_id,guild_id,user_id,role) VALUES ($1,$2,$3,'owner')", clan, G, V)
    await clean_db.execute("INSERT INTO clan_members (clan_id,guild_id,user_id,role) VALUES ($1,$2,$3,'co_owner')", clan, G, U)

    rapporto = await servizio.dimentica_utente(clean_db, V)

    riga = await clean_db.fetchrow("SELECT owner_id, co_owner_id FROM clans")
    assert (riga["owner_id"], riga["co_owner_id"]) == (U, None)
    assert await clean_db.fetchval("SELECT role FROM clan_members WHERE user_id = $1", U) == "owner"
    assert await clean_db.fetchval("SELECT count(*) FROM clan_members WHERE user_id = $1", V) == 0
    assert rapporto["clans"]["anonimizzate"] == 1 and rapporto["clans"]["conservate"] == 0


@pytest.mark.asyncio
async def test_il_titolare_senza_co_titolare_passa_al_membro_piu_anziano(clean_db):
    await _prepara(clean_db)
    await clean_db.execute("UPDATE clans SET co_owner_id = NULL")
    clan = await clean_db.fetchval("SELECT id FROM clans")
    await clean_db.execute("INSERT INTO clan_members (clan_id,guild_id,user_id,role) VALUES ($1,$2,$3,'owner')", clan, G, V)
    await clean_db.execute("INSERT INTO clan_members (clan_id,guild_id,user_id,role,joined_at) VALUES ($1,$2,31,'member', now() - interval '1 day')", clan, G)
    await clean_db.execute("INSERT INTO clan_members (clan_id,guild_id,user_id,role,joined_at) VALUES ($1,$2,32,'member', now() - interval '9 days')", clan, G)

    await servizio.dimentica_utente(clean_db, V)

    assert await clean_db.fetchval("SELECT owner_id FROM clans") == 32
    assert await clean_db.fetchval("SELECT role FROM clan_members WHERE user_id = 32") == "owner"


@pytest.mark.asyncio
async def test_il_titolare_da_solo_scioglie_il_clan_senza_righe_orfane(clean_db):
    await _prepara(clean_db)
    clan = await clean_db.fetchval("SELECT id FROM clans")
    await clean_db.execute("INSERT INTO clan_members (clan_id,guild_id,user_id,role) VALUES ($1,$2,$3,'owner')", clan, G, V)
    await clean_db.execute("UPDATE clans SET co_owner_id = NULL")
    await clean_db.execute("DELETE FROM clan_treasury_ledger")

    rapporto = await servizio.dimentica_utente(clean_db, V)

    assert await clean_db.fetchval("SELECT count(*) FROM clans") == 0
    assert await clean_db.fetchval("SELECT count(*) FROM clan_members") == 0
    assert rapporto["clans"]["cancellate"] == 1


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


# ------------------------------------------------------------------ secondo giro (cacciatore-bug 12/10)
@pytest.mark.asyncio
async def test_ticket_aperti_di_due_utenti_si_anonimizzano_insieme(clean_db):
    """Prima dava UniqueViolation sull'indice (guild, user_id) WHERE open."""
    await clean_db.execute("INSERT INTO tickets (guild_id,ticket_number,channel_id,user_id) VALUES ($1,1,11,$2)", G, U)
    await clean_db.execute("INSERT INTO tickets (guild_id,ticket_number,channel_id,user_id) VALUES ($1,2,12,$2)", G, V)
    await servizio.dimentica_utente(clean_db, U)

    await servizio.dimentica_utente(clean_db, V)  # il secondo non deve rompere

    assert await clean_db.fetchval("SELECT count(*) FROM tickets WHERE user_id = 0") == 2


@pytest.mark.asyncio
async def test_il_kick_e_il_mute_dell_automod_restano(clean_db):
    for numero, azione in ((1, "automod_escalation"), (2, "mute_role"), (3, "warn")):
        await clean_db.execute(
            "INSERT INTO moderation_cases (guild_id,case_number,user_id,moderator_id,action_type) VALUES ($1,$2,$3,77,$4)",
            G, numero, U, azione,
        )

    rapporto = await servizio.dimentica_utente(clean_db, U)

    assert {r["action_type"] for r in await clean_db.fetch("SELECT action_type FROM moderation_cases")} == {
        "automod_escalation", "mute_role"
    }
    assert rapporto["moderation_cases"]["conservate"] == 2


def test_ogni_action_type_dei_cog_e_dichiarato():
    """Se un cog scrive un nuovo action_type, qualcuno deve decidere se resta (ban/kick) o va."""
    import ast
    import importlib
    from pathlib import Path

    # trattenuti: lo dice la migrazione 0050; "non trattenuti": scelta consapevole
    trattenuti = {"ban", "tempban", "softban", "kick", "spam_trap_ban", "automod_escalation", "mute_role"}
    non_trattenuti = {"warn", "timeout"}
    trovati = set()
    for percorso in Path("cogs").rglob("*.py"):
        albero = ast.parse(percorso.read_text())
        costanti = {
            n.targets[0].id: n.value.value
            for n in albero.body
            if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
            and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
        }
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Call) and getattr(nodo.func, "attr", "") == "create_case":
                for kw in nodo.keywords:
                    if kw.arg != "action_type":
                        continue
                    if isinstance(kw.value, ast.Constant):
                        trovati.add(kw.value.value)
                    elif isinstance(kw.value, ast.Name) and kw.value.id in costanti:
                        trovati.add(costanti[kw.value.id])
                    elif isinstance(kw.value, ast.Name):  # importata da un altro modulo
                        modulo = importlib.import_module(str(percorso.with_suffix("")).replace("/", "."))
                        trovati.add(getattr(modulo, kw.value.id))
    assert trovati, "nessun create_case trovato: il test non guarda niente"
    assert trovati <= trattenuti | non_trattenuti, f"action_type non dichiarati: {trovati - trattenuti - non_trattenuti}"


@pytest.mark.asyncio
async def test_la_colonna_retain_for_security_segue_l_elenco(clean_db):
    for i, azione in enumerate(("ban", "tempban", "softban", "kick", "spam_trap_ban", "automod_escalation", "mute_role", "warn", "timeout")):
        await clean_db.execute(
            "INSERT INTO moderation_cases (guild_id,case_number,user_id,moderator_id,action_type) VALUES ($1,$2,1,2,$3)", G, i + 1, azione
        )
    righe = {r["action_type"]: r["retain_for_security"] for r in await clean_db.fetch("SELECT action_type, retain_for_security FROM moderation_cases")}
    assert [a for a, v in righe.items() if not v] == ["warn", "timeout"] or set(a for a, v in righe.items() if not v) == {"warn", "timeout"}


@pytest.mark.asyncio
async def test_l_esportazione_non_contiene_cio_che_l_utente_ha_scritto_su_altri(clean_db):
    await _prepara(clean_db)  # U e' anche moderatore del caso 4 su V, e actor di eventi
    await clean_db.execute("INSERT INTO moderation_notes (guild_id,user_id,moderator_id,note) VALUES ($1,$2,$3,'segreto su V')", G, V, U)
    await clean_db.execute(
        "INSERT INTO tickets (guild_id,ticket_number,channel_id,user_id,claimed_by,status) VALUES ($1,90,90,$2,$3,'closed')", G, V, U
    )
    await clean_db.execute("INSERT INTO event_log (guild_id,event_type,target_user_id,actor_id,details) VALUES ($1,'warn',$2,$3,'{\"altro\":\"dato di V\"}')", G, V, U)

    dati = await servizio.esporta_utente(clean_db, U)
    testo = json.dumps(dati, default=str)

    assert "segreto su V" not in testo and "dato di V" not in testo
    assert all(r["user_id"] == U for r in dati["tabelle"]["moderation_cases"]["righe"])
    assert "moderation_notes" not in dati["tabelle"]
    assert all(r["user_id"] == U for r in dati["tabelle"]["tickets"]["righe"])
    for r in dati["tabelle"]["event_log"]["righe"]:
        assert "details" not in r and r["target_user_id"] == U
    # l'id dello staff che ha agito su U non esce
    assert all(r["moderator_id"] is None for r in dati["tabelle"]["moderation_cases"]["righe"])


@pytest.mark.asyncio
async def test_l_esportazione_e_ordinata_e_dichiara_il_taglio(clean_db):
    for i in range(1, 8):
        await clean_db.execute(
            "INSERT INTO moderation_cases (guild_id,case_number,user_id,moderator_id,action_type) VALUES ($1,$2,$3,77,'warn')", G, 8 - i, U
        )

    dati = await servizio.esporta_utente(clean_db, U, righe_max=5)

    numeri = [r["case_number"] for r in dati["tabelle"]["moderation_cases"]["righe"]]
    assert len(numeri) == 5
    ids = [r["id"] for r in dati["tabelle"]["moderation_cases"]["righe"]]
    assert ids == sorted(ids)  # per chiave primaria, non a caso
    assert dati["troncate"] == ["moderation_cases"]
    assert "troncata" in dati["tabelle"]["moderation_cases"]
    intero = await servizio.esporta_utente(clean_db, U, righe_max=50)
    assert "troncate" not in intero


def test_serializza_misura_ogni_riga_una_volta(monkeypatch):
    righe = [{"n": i, "testo": "x" * 200} for i in range(400)]
    dati = {"tabelle": {"a": {"descrizione": "a", "righe": list(righe)}, "b": {"descrizione": "b", "righe": righe[:10]}}}
    chiamate = []
    vero = json.dumps
    monkeypatch.setattr(servizio.json, "dumps", lambda *a, **k: (chiamate.append(1), vero(*a, **k))[1])

    testo, accorciate = servizio.serializza_esportazione(dati, limite_byte=20_000)

    assert len(testo) <= 20_000 and accorciate and accorciate[0] == "a"
    assert len(chiamate) <= 400 + 10 + 4  # ~una per riga + il documento, non una per ogni dimezzamento


@pytest.mark.asyncio
async def test_l_attore_di_un_registro_di_sicurezza_resta(clean_db):
    await clean_db.execute("INSERT INTO security_action_log (guild_id, actor_id, category) VALUES ($1,$2,'x')", G, U)

    rapporto = await servizio.dimentica_utente(clean_db, U)

    assert await clean_db.fetchval("SELECT actor_id FROM security_action_log") == U
    assert "security_action_log" not in rapporto or rapporto["security_action_log"]["anonimizzate"] == 0


@pytest.mark.asyncio
async def test_il_co_titolare_batte_il_membro_piu_anziano(clean_db):
    await _prepara(clean_db)
    clan = await clean_db.fetchval("SELECT id FROM clans")
    await clean_db.execute("UPDATE clans SET co_owner_id = 33")
    await clean_db.execute("INSERT INTO clan_members (clan_id,guild_id,user_id,role) VALUES ($1,$2,$3,'owner')", clan, G, V)
    await clean_db.execute("INSERT INTO clan_members (clan_id,guild_id,user_id,role,joined_at) VALUES ($1,$2,32,'member', now() - interval '30 days')", clan, G)
    await clean_db.execute("INSERT INTO clan_members (clan_id,guild_id,user_id,role,joined_at) VALUES ($1,$2,33,'co_owner', now() - interval '1 day')", clan, G)

    await servizio.dimentica_utente(clean_db, V)

    assert await clean_db.fetchval("SELECT owner_id FROM clans") == 33
    assert await clean_db.fetchval("SELECT co_owner_id FROM clans") is None


@pytest.mark.asyncio
async def test_sciogliere_un_clan_toglie_anche_l_attivita_vocale(clean_db):
    await _prepara(clean_db)
    clan = await clean_db.fetchval("SELECT id FROM clans")
    await clean_db.execute("UPDATE clans SET co_owner_id = NULL")
    await clean_db.execute("INSERT INTO clan_members (clan_id,guild_id,user_id,role) VALUES ($1,$2,$3,'owner')", clan, G, V)
    await clean_db.execute("INSERT INTO clan_voice_activity (clan_id,user_id) VALUES ($1,$2)", clan, V)
    await clean_db.execute("INSERT INTO clan_voice_activity (clan_id,user_id) VALUES ($1,$2)", clan, 4242)

    await servizio.dimentica_utente(clean_db, V)

    assert await clean_db.fetchval("SELECT count(*) FROM clan_voice_activity") == 0


@pytest.mark.asyncio
async def test_titolare_di_un_clan_e_co_titolare_di_un_altro_nel_rapporto(clean_db):
    """Il rapporto 'clans' somma trasferimenti e cancellazioni delle due vie."""
    await _prepara(clean_db)  # clan 1: V titolare, U co-titolare
    primo = await clean_db.fetchval("SELECT id FROM clans")
    await clean_db.execute("INSERT INTO clan_members (clan_id,guild_id,user_id,role) VALUES ($1,$2,$3,'owner')", primo, G, V)
    await clean_db.execute("INSERT INTO clan_members (clan_id,guild_id,user_id,role) VALUES ($1,$2,$3,'co_owner')", primo, G, U)
    await clean_db.execute("INSERT INTO clans (guild_id,tag,name,owner_id,co_owner_id,officialize_deadline) VALUES ($1,'U2','Due',$2,$3,now())", G + 1, 77, V)

    rapporto = await servizio.dimentica_utente(clean_db, V)

    assert rapporto["clans"]["anonimizzate"] == 2  # un passaggio di titolarita' + un posto di co-titolare svuotato


@pytest.mark.asyncio
async def test_l_ordine_dell_esportazione_segue_la_chiave_primaria_non_la_posizione_fisica(clean_db):
    for n in (1, 2, 3):
        await clean_db.execute(
            "INSERT INTO moderation_cases (guild_id,case_number,user_id,moderator_id,action_type) VALUES ($1,$2,$3,77,'warn')", G, n, U
        )
    await clean_db.execute("UPDATE moderation_cases SET reason = 'x' WHERE case_number = 1")  # la riga cambia posto

    dati = await servizio.esporta_utente(clean_db, U)

    ids = [r["id"] for r in dati["tabelle"]["moderation_cases"]["righe"]]
    assert ids == sorted(ids)

"""
tests/test_data_registry.py
===========================
NF-04 (#75): il registro dei dati personali dichiara ogni tabella dello schema
vero, e ogni suo SQL gira davvero. Una tabella nuova senza voce nel registro fa
fallire questo test: nessun dato personale sfugge alla cancellazione.
"""

import re

import pytest

from core import data_registry as reg

# Colonne che di solito contengono l'id di una persona.
COLONNE_PERSONA = re.compile(
    r"(^|_)(user_id|owner_id|co_owner_id|moderator_id|actor_id|executor_id|claimed_by|closed_by|"
    r"created_by|added_by|decided_by|revoked_by|changed_by|granted_by|updated_by|invite_creator_id|"
    r"target_user_id|requester_id)$"
)


async def _schema(conn) -> dict[str, dict[str, str]]:
    righe = await conn.fetch(
        "SELECT table_name, column_name, is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'public'"
    )
    schema: dict[str, dict[str, str]] = {}
    for r in righe:
        schema.setdefault(r["table_name"], {})[r["column_name"]] = r["is_nullable"]
    return schema


def test_gli_identificatori_sono_semplici():
    assert reg.identificatori_validi()


def test_nomi_unici():
    nomi = [t.nome for t in reg.REGISTRO]
    assert len(nomi) == len(set(nomi))


@pytest.mark.asyncio
async def test_ogni_tabella_dello_schema_e_dichiarata(clean_db):
    schema = await _schema(clean_db)
    mancanti = sorted(set(schema) - reg.TABELLE_ESCLUSE - reg.nomi_dichiarati())
    assert mancanti == [], f"Tabelle senza voce in core/data_registry.py: {mancanti}"


@pytest.mark.asyncio
async def test_le_colonne_dichiarate_esistono(clean_db):
    schema = await _schema(clean_db)
    errori = []
    for t in reg.REGISTRO:
        colonne = schema.get(t.nome)
        if colonne is None:
            continue  # tabella dichiarata in anticipo: ammessa
        usate = [*t.colonne_utente, *t.colonne_attore, *(c for c, _ in t.anonimizza)]
        if t.colonna_server:
            usate.append(t.colonna_server)
        usate += list(t.escludi_dall_esportazione)
        errori += [f"{t.nome}.{c}" for c in usate if c not in colonne]
    assert errori == []


@pytest.mark.asyncio
async def test_ogni_colonna_con_una_persona_e_coperta(clean_db):
    """Una colonna `user_id` (o simili) non dichiarata fa fallire il test."""
    schema = await _schema(clean_db)
    scoperte = []
    for t in reg.REGISTRO:
        for colonna in schema.get(t.nome, {}):
            if COLONNE_PERSONA.search(colonna) and colonna not in t.colonne_tutte:
                scoperte.append(f"{t.nome}.{colonna}")
    assert scoperte == [], f"Colonne con una persona non dichiarate: {scoperte}"


@pytest.mark.asyncio
async def test_la_cancellazione_usa_il_valore_giusto_per_colonne_non_nulle(clean_db):
    """`anonimizza` non può mettere NULL in una colonna NOT NULL."""
    schema = await _schema(clean_db)
    errori = []
    for t in reg.REGISTRO:
        colonne = schema.get(t.nome)
        if colonne is None:
            continue
        for colonna, espressione in t.anonimizza:
            if espressione.strip().upper() == "NULL" and colonne[colonna] == "NO":
                errori.append(f"{t.nome}.{colonna}")
    assert errori == []


@pytest.mark.asyncio
async def test_ogni_sql_del_registro_gira(clean_db):
    """Ogni istruzione generata è SQL valido sullo schema vero (transazione annullata)."""
    schema = await _schema(clean_db)
    async with clean_db.acquire() as conn:
        tx = conn.transaction()
        await tx.start()
        try:
            for t in reg.REGISTRO:
                if t.nome not in schema:
                    continue
                if t.colonne_utente:
                    if t.utente == "cancella":
                        await conn.execute(t.sql_cancella_utente(), 424242)
                    elif t.utente == "anonimizza":
                        await conn.execute(t.sql_anonimizza_utente(), 424242)
                    if t.utente == "conserva" or t.conserva_se or t.conserva_utente_se:
                        await conn.fetchval(t.sql_conta_conservate(), 424242)
                for colonna in t.attori_da_azzerare():
                    await conn.execute(t.sql_azzera_attore(colonna), 424242)
                if t.esporta and t.colonne_tutte:
                    await conn.fetch(t.sql_esporta(10), 424242)
                sql_server = t.sql_cancella_server()
                if sql_server:
                    await conn.execute(sql_server, 424242)
                if t.sql_scaduti():
                    await conn.execute(t.sql_scaduti(), 30)
        finally:
            await tx.rollback()


def test_le_tabelle_chieste_dal_proprietario_sono_nel_registro():
    for nome in ("command_usage", "rank_card_prefs", "event_log", "restore_oauth_tokens", "log_ignora"):
        assert nome in reg.nomi_dichiarati()
    assert reg.tabella("command_usage").utente == "cancella"
    assert reg.tabella("rank_card_prefs").utente == "cancella"


def test_ban_e_kick_restano():
    casi = reg.tabella("moderation_cases")
    assert casi.conserva_se == "retain_for_security"
    assert reg.tabella("global_ban_log").utente == "conserva"
    assert reg.tabella("global_ban_log").server == "conserva"


def test_i_token_oauth_non_escono_nell_esportazione():
    t = reg.tabella("restore_oauth_tokens")
    assert {"encrypted_access_token", "encrypted_refresh_token"} <= set(t.escludi_dall_esportazione)


def test_le_tabelle_figlie_vengono_prima_delle_madri():
    ordine = [t.nome for t in reg.REGISTRO]
    for figlia, madre in (
        ("giveaway_entries", "giveaways"),
        ("role_menu_options", "role_menus"),
        ("clan_members", "clans"),
        ("clan_treasury_ledger", "clans"),
        ("clan_voice_activity", "clans"),
    ):
        assert ordine.index(figlia) < ordine.index(madre)


# ------------------------------------------------------------------ secondo giro (cacciatore-bug 12/10)
def test_l_esportazione_guarda_solo_le_colonne_dell_utente():
    for t in reg.tabelle_esportabili():
        sql = t.sql_esporta(10, ("id",))
        for colonna in t.colonne_attore:
            if colonna not in t.colonne_utente:
                assert colonna not in sql.split("WHERE")[1], f"{t.nome} esporta le righe di chi ha solo agito ({colonna})"
        assert "ORDER BY" in sql


def test_event_log_non_esporta_i_dettagli_ne_le_righe_dove_l_utente_ha_agito_su_altri():
    t = reg.tabella("event_log")
    assert "details" in t.escludi_dall_esportazione
    assert "target_user_id IS NULL OR target_user_id = actor_id" in t.sql_esporta(1)


def test_la_purga_del_server_tiene_lo_sban_in_coda_e_ricostruisce_il_contatore():
    assert "NOT COALESCE(" in reg.tabella("scheduled_actions").sql_cancella_server()
    from cogs.moderation.actions import SCHEDULED_TEMPBAN_EXPIRE

    assert SCHEDULED_TEMPBAN_EXPIRE in reg.tabella("scheduled_actions").sql_cancella_server()
    assert reg.tabella("moderation_case_counters").dopo_purga_server


def test_i_dati_di_inviti_e_bacheca_hanno_una_regola_di_pulizia():
    con = {t.nome for t in reg.tabelle_con_scadenza()}
    assert {"invite_joins", "starboard_posts", "autorole_memory"} <= con


@pytest.mark.asyncio
async def test_la_scadenza_toglie_gli_inviti_di_chi_e_uscito_da_tempo(clean_db):
    t = reg.tabella("invite_joins")
    await clean_db.execute(
        "INSERT INTO invite_joins (guild_id, user_id, inviter_id, code, left_at) VALUES "
        "(1, 10, 99, 'a', now() - interval '200 days'), (1, 11, 99, 'a', now() - interval '5 days'), "
        "(1, 12, 99, 'a', NULL)"
    )
    await clean_db.execute(t.sql_scaduti(), t.scadenza.giorni)
    righe = {r["user_id"] for r in await clean_db.fetch("SELECT user_id FROM invite_joins")}
    assert righe == {11, 12}

"""
tests/test_migrazione_percorsi_tag_quote.py
===========================================
Migrazioni 0557 (tag e risposte automatiche passano a `/tag` e `/admin-tag`) e 0558 (`/fun quote` diventa
`/fun citazioni caso`) del blocco Utility (D69): un comando spento nella politica dei server resta spento col nome
nuovo; registro modifiche e ultimo comando usato seguono; rilanciarle non cambia nulla. Database vero.
"""

from __future__ import annotations

import json
from pathlib import Path

DIR = Path(__file__).parent.parent / "core/migrations"
SQL_0557 = (DIR / "0557_tag_opzioni.sql").read_text()
SQL_0558 = (DIR / "0558_fun_quote_citazioni.sql").read_text()

VECCHI_TAG = {
    "utility tag": "tag usa", "admin-messaggi tag crea": "admin-tag tag crea", "admin-messaggi tag modifica": "admin-tag tag modifica",
    "admin-messaggi tag elimina": "admin-tag tag elimina", "admin-messaggi tag elenco": "admin-tag tag elenco",
    "admin-messaggi tag prefisso": "admin-tag tag prefisso", "admin-messaggi risposte crea": "admin-tag risposte crea",
    "admin-messaggi risposte elimina": "admin-tag risposte elimina", "admin-messaggi risposte elenco": "admin-tag risposte elenco",
}


def _json(valore):
    return json.loads(valore) if isinstance(valore, str) else valore


async def _scenario(clean_db, guild, spenti, usato):
    await clean_db.execute("INSERT INTO guild_config (guild_id, settings) VALUES ($1, $2::jsonb)", guild,
                           json.dumps({"policy_comandi_off": spenti, "altro": 1}))
    await clean_db.execute(
        "INSERT INTO guild_config_history (guild_id, change_type, key_name, old_value, new_value) VALUES ($1, 'set', 'policy_comandi_off', $2, $3)",
        guild, json.dumps(spenti[:1]), json.dumps(spenti))
    await clean_db.execute("INSERT INTO command_usage (guild_id, user_id, command_path) VALUES ($1, 1, $2)", guild, usato)


async def test_0557_ogni_comando_spento_resta_spento_col_nome_nuovo(clean_db):
    spenti = [*VECCHI_TAG, "fun dice"]
    await _scenario(clean_db, 779001, spenti, "utility tag")
    for _ in range(2):  # la seconda corsa non deve cambiare niente
        await clean_db.execute(SQL_0557)
        s = _json(await clean_db.fetchval("SELECT settings FROM guild_config WHERE guild_id = 779001"))
        assert sorted(s["policy_comandi_off"]) == sorted([*VECCHI_TAG.values(), "fun dice"]) and s["altro"] == 1
    cron = await clean_db.fetchrow("SELECT old_value, new_value FROM guild_config_history WHERE guild_id = 779001")
    assert json.loads(cron["old_value"]) == ["tag usa"] and sorted(json.loads(cron["new_value"])) == sorted([*VECCHI_TAG.values(), "fun dice"])
    assert await clean_db.fetchval("SELECT command_path FROM command_usage WHERE guild_id = 779001") == "tag usa"


async def test_0558_fun_quote_segue_il_nuovo_nome_senza_doppioni(clean_db):
    await _scenario(clean_db, 779002, ["fun quote", "fun citazioni caso", "fun dice"], "fun quote")
    await clean_db.execute("INSERT INTO guild_config (guild_id, settings) VALUES (779003, '{}'::jsonb)")
    for _ in range(2):
        await clean_db.execute(SQL_0558)
        s = _json(await clean_db.fetchval("SELECT settings FROM guild_config WHERE guild_id = 779002"))
        assert sorted(s["policy_comandi_off"]) == ["fun citazioni caso", "fun dice"]
    assert await clean_db.fetchval("SELECT command_path FROM command_usage WHERE guild_id = 779002") == "fun citazioni caso"
    assert _json(await clean_db.fetchval("SELECT settings FROM guild_config WHERE guild_id = 779003")) == {}


async def test_percorsi_vecchi_spariti_e_nuovi_presenti_nell_albero():
    from core.command_groups import GRUPPI
    from core.command_policy import percorsi_dei_comandi
    from tests.support.full_tree import build_full_bot, close_full_bot, connect_db_if_needed

    creato = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti, falliti
        percorsi = set(percorsi_dei_comandi(list(GRUPPI.values())))
        assert not [v for v in (*VECCHI_TAG, "fun quote") if v in percorsi]
        assert not [n for n in (*VECCHI_TAG.values(), "fun citazioni caso") if n not in percorsi]
    finally:
        await close_full_bot(bot)
        if creato:
            from core.database import db

            await db.close()

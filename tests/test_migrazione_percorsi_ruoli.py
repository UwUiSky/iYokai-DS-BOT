"""
tests/test_migrazione_percorsi_ruoli.py
=======================================
Migrazione 0488 (D60): i percorsi dei comandi dello staff salvati nel database seguono il passaggio sotto il
ruolo (`/admin-…`, `/mod-…`, `/founder`). Un comando spento nella politica dei server resta spento col nome
nuovo; registro modifiche e ultimo comando usato seguono.
Funzioni coperte: D60
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SQL = (Path(__file__).parent.parent / "core/migrations/0488_percorsi_comandi_ruoli.sql").read_text()
COPPIE = re.findall(r"\('([^']+)', '([^']+)'\)", SQL.split("WITH m(vecchio, nuovo)", 2)[1])


def _json(valore):
    return json.loads(valore) if isinstance(valore, str) else valore


def test_la_mappa_ha_377_spostamenti_senza_doppioni_e_senza_catene():
    assert len(COPPIE) == 377
    vecchi = {v for v, _ in COPPIE}
    nuovi = {n for _, n in COPPIE}
    assert len(vecchi) == 377
    assert len(nuovi) == 377
    assert not vecchi & nuovi, "un percorso nuovo non può essere anche vecchio: la migrazione non sarebbe idempotente"


def test_ogni_tabella_con_percorsi_usa_la_stessa_mappa():
    """policy_comandi_off, guild_config_history (vecchio e nuovo valore) e command_usage: quattro blocchi uguali."""
    blocchi = re.findall(r"VALUES\n((?:\s+\('.*\),?\n)+)", SQL)
    assert len(blocchi) == 4
    assert all(len(re.findall(r"\('", b)) == 377 for b in blocchi)
    assert len({b.replace(" ", "") for b in blocchi}) == 1


async def test_percorsi_vecchi_spariti_e_nuovi_presenti_nell_albero_vero():
    from core.command_groups import GRUPPI
    from core.command_policy import percorsi_dei_comandi
    from tests.support.full_tree import build_full_bot, close_full_bot, connect_db_if_needed

    creato = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti, falliti
        percorsi = set(percorsi_dei_comandi(list(GRUPPI.values())))
        mancano = sorted(n for _, n in COPPIE if n not in percorsi)
        assert not mancano, f"Percorsi nuovi che non esistono: {mancano}"
        restano = sorted(v for v, _ in COPPIE if v in percorsi)
        assert not restano, f"Percorsi vecchi ancora nell'albero: {restano}"
    finally:
        await close_full_bot(bot)
        if creato:
            from core.database import db

            await db.close()


async def test_comandi_spenti_restano_spenti_e_cronologia_e_uso_seguono(clean_db):
    guild, altro = 778001, 778002
    spenti = ["admin config export", "mod warn", "modban ban", "ticket-pannelli opzioni limiti", "backup sincronia", "fun dice"]
    await clean_db.execute(
        "INSERT INTO guild_config (guild_id, settings) VALUES ($1, $2::jsonb)",
        guild,
        json.dumps({"policy_comandi_off": spenti, "altro": 1}),
    )
    await clean_db.execute(
        "INSERT INTO guild_config (guild_id, settings) VALUES ($1, $2::jsonb)", altro, json.dumps({"policy_comandi_off": ["fun dice"]})
    )
    await clean_db.execute(
        "INSERT INTO guild_config_history (guild_id, change_type, key_name, old_value, new_value) "
        "VALUES ($1, 'set', 'policy_comandi_off', $2, $3)",
        guild,
        json.dumps(["mod warn"]),
        json.dumps(["mod warn", "economia xp"]),
    )
    await clean_db.execute("INSERT INTO command_usage (guild_id, user_id, command_path) VALUES ($1, 1, 'ai attiva')", guild)
    await clean_db.execute("INSERT INTO command_usage (guild_id, user_id, command_path) VALUES ($1, 2, 'fun dice')", guild)

    await clean_db.execute(SQL)

    settings = _json(await clean_db.fetchval("SELECT settings FROM guild_config WHERE guild_id = $1", guild))
    assert sorted(settings["policy_comandi_off"]) == sorted(
        ["admin-bot config export", "mod-sanzioni warn", "mod-ban ban", "admin-ticket-opzioni limiti", "founder backup sincronia", "fun dice"]
    )
    assert settings["altro"] == 1
    settings_altro = _json(await clean_db.fetchval("SELECT settings FROM guild_config WHERE guild_id = $1", altro))
    assert settings_altro["policy_comandi_off"] == ["fun dice"]
    cron = await clean_db.fetchrow("SELECT old_value, new_value FROM guild_config_history WHERE guild_id = $1", guild)
    assert json.loads(cron["old_value"]) == ["mod-sanzioni warn"]
    assert sorted(json.loads(cron["new_value"])) == ["admin-livelli membro", "mod-sanzioni warn"]
    usi = {r["user_id"]: r["command_path"] for r in await clean_db.fetch("SELECT user_id, command_path FROM command_usage WHERE guild_id = $1", guild)}
    assert usi == {1: "admin-ai attiva", 2: "fun dice"}


async def test_la_migrazione_si_puo_rilanciare_senza_danni(clean_db):
    guild = 778003
    await clean_db.execute(
        "INSERT INTO guild_config (guild_id, settings) VALUES ($1, $2::jsonb)",
        guild,
        json.dumps({"policy_comandi_off": ["filtri invites", "mod timeout"]}),
    )
    await clean_db.execute("INSERT INTO command_usage (guild_id, user_id, command_path) VALUES ($1, 1, 'log canale')", guild)
    await clean_db.execute(SQL)
    await clean_db.execute(SQL)
    settings = _json(await clean_db.fetchval("SELECT settings FROM guild_config WHERE guild_id = $1", guild))
    assert sorted(settings["policy_comandi_off"]) == ["admin-filtri invites", "mod-sanzioni timeout"]
    assert await clean_db.fetchval("SELECT command_path FROM command_usage WHERE guild_id = $1", guild) == "admin-log canale"


async def test_un_server_senza_politica_o_con_elenco_vuoto_non_cambia(clean_db):
    senza, vuoto = 778004, 778005
    await clean_db.execute("INSERT INTO guild_config (guild_id, settings) VALUES ($1, $2::jsonb)", senza, json.dumps({"altro": 2}))
    await clean_db.execute("INSERT INTO guild_config (guild_id, settings) VALUES ($1, $2::jsonb)", vuoto, json.dumps({"policy_comandi_off": []}))
    await clean_db.execute(SQL)
    assert _json(await clean_db.fetchval("SELECT settings FROM guild_config WHERE guild_id = $1", senza)) == {"altro": 2}
    assert _json(await clean_db.fetchval("SELECT settings FROM guild_config WHERE guild_id = $1", vuoto)) == {"policy_comandi_off": []}

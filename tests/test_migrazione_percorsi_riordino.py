"""
tests/test_migrazione_percorsi_riordino.py
==========================================
Migrazione 0485 (D56): i percorsi dei comandi salvati nel database seguono il riordino dei gruppi.
Un comando spento nella politica dei server resta spento col nome nuovo.
Funzioni coperte: D56
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from core import database as database_module

SQL = (Path(__file__).parent.parent / "core/migrations/0485_percorsi_comandi_riordino.sql").read_text()
COPPIE = re.findall(r"\('([^']+)', '([^']+)'\)", SQL.split("WITH m(vecchio, nuovo)", 2)[1])


def test_la_mappa_ha_152_spostamenti_senza_doppioni():
    assert len(COPPIE) == 152
    assert len({v for v, _ in COPPIE}) == 152
    assert len({n for _, n in COPPIE}) == 152


async def test_percorsi_vecchi_spariti_e_nuovi_presenti_nell_albero_vero():
    from core.command_policy import percorsi_dei_comandi
    from core.command_groups import GRUPPI
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
    guild = 777001
    await clean_db.execute(
        "INSERT INTO guild_config (guild_id, settings) VALUES ($1, $2::jsonb)",
        guild,
        json.dumps({"policy_comandi_off": ["fun meme", "fun coinflip", "utility poll", "ai manutenzione"], "altro": 1}),
    )
    altro = 777002
    await clean_db.execute(
        "INSERT INTO guild_config (guild_id, settings) VALUES ($1, $2::jsonb)", altro, json.dumps({"policy_comandi_off": ["fun dice"]})
    )
    await clean_db.execute(
        "INSERT INTO guild_config_history (guild_id, change_type, key_name, old_value, new_value) VALUES ($1, 'set', 'policy_comandi_off', $2, $3)",
        guild,
        json.dumps(["fun meme"]),
        json.dumps(["fun meme", "utility snipe"]),
    )
    await clean_db.execute("INSERT INTO command_usage (guild_id, user_id, command_path) VALUES ($1, 1, 'level balance')", guild)
    await clean_db.execute("INSERT INTO command_usage (guild_id, user_id, command_path) VALUES ($1, 2, 'fun dice')", guild)

    await clean_db.execute(SQL)

    row = await clean_db.fetchval("SELECT settings FROM guild_config WHERE guild_id = $1", guild)
    settings = json.loads(row) if isinstance(row, str) else row
    assert sorted(settings["policy_comandi_off"]) == sorted(["immagini meme", "fun coinflip", "sondaggi crea", "owner ai manutenzione"])
    assert settings["altro"] == 1
    row = await clean_db.fetchval("SELECT settings FROM guild_config WHERE guild_id = $1", altro)
    assert (json.loads(row) if isinstance(row, str) else row)["policy_comandi_off"] == ["fun dice"]
    cron = await clean_db.fetchrow("SELECT old_value, new_value FROM guild_config_history WHERE guild_id = $1", guild)
    assert json.loads(cron["old_value"]) == ["immagini meme"]
    assert sorted(json.loads(cron["new_value"])) == ["immagini meme", "utility snipe messaggio"]
    usi = {r["user_id"]: r["command_path"] for r in await clean_db.fetch("SELECT user_id, command_path FROM command_usage WHERE guild_id = $1", guild)}
    assert usi == {1: "monete balance", 2: "fun dice"}


async def test_la_migrazione_si_puo_rilanciare_senza_danni(clean_db):
    guild = 777003
    await clean_db.execute(
        "INSERT INTO guild_config (guild_id, settings) VALUES ($1, $2::jsonb)", guild, json.dumps({"policy_comandi_off": ["fun meme"]})
    )
    await clean_db.execute(SQL)
    await clean_db.execute(SQL)
    row = await clean_db.fetchval("SELECT settings FROM guild_config WHERE guild_id = $1", guild)
    assert (json.loads(row) if isinstance(row, str) else row)["policy_comandi_off"] == ["immagini meme"]

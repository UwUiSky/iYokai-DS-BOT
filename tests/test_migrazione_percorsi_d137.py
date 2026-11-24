"""
tests/test_migrazione_percorsi_d137.py
======================================
Migrazione 0972 (D137, riordino dei comandi): i percorsi salvati nel database seguono i comandi spostati.
Un comando spento resta spento col nome nuovo; ruoli richiesti, registro modifiche, ultimo comando usato e
conteggio per giorno seguono; `/chiedi` e `/cerca-comando` si sommano in `/help`. Database vero.
Funzioni coperte: D137
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from discord import app_commands

SQL = (Path(__file__).parent.parent / "core/migrations/0972_percorsi_comandi_riordino_d137.sql").read_text()
COPPIE = re.findall(r"^    \('([^']+)', '([^']+)'\)", SQL, re.M)


def _json(v):
    return json.loads(v) if isinstance(v, str) else v


def _percorsi(nodi, prefisso="", foglie=None, tutti=None):
    foglie = set() if foglie is None else foglie
    tutti = set() if tutti is None else tutti
    for n in nodi:
        p = f"{prefisso} {n.name}".strip()
        tutti.add(p)
        if isinstance(n, app_commands.Group):
            _percorsi(n.commands, p, foglie, tutti)
        else:
            foglie.add(p)
    return foglie, tutti


def test_la_mappa_non_ha_doppioni_e_nessun_nuovo_e_anche_vecchio():
    vecchi = [v for v, _ in COPPIE]
    assert len(COPPIE) == 419 and len(set(vecchi)) == 419
    assert not ({n for _, n in COPPIE} & set(vecchi)) - {"admin-livelli premi"}


async def test_percorsi_nuovi_nell_albero_e_vecchi_spariti():
    from core.command_groups import GRUPPI
    from tests.support.full_tree import build_full_bot, close_full_bot, connect_db_if_needed

    creato = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti, falliti
        nodi = list(bot.tree.get_commands()) + [GRUPPI["owner"], GRUPPI["owner-radio"]]
        foglie, tutti = _percorsi(nodi)
        mancano = sorted(n for _, n in COPPIE if n not in tutti)
        assert not mancano, mancano
        restano = sorted(v for v, _ in COPPIE if v in foglie and v != "admin-livelli premi")
        assert not restano, restano
    finally:
        await close_full_bot(bot)
        if creato:
            from core.database import db

            await db.close()


async def test_politica_ruoli_registro_uso_e_conteggio_seguono(clean_db):
    g = 779137
    spenti = ["music playlist salva", "sala roulette", "fun dice", "admin-bot config pulisci"]
    ruoli = {"admin-ruoli premio aggiungi": [1, 2], "music playlist": [3], "fun dice": [4]}
    await clean_db.execute(
        "INSERT INTO guild_config (guild_id, settings) VALUES ($1, $2::jsonb)", g,
        json.dumps({"policy_comandi_off": spenti, "policy_ruoli_richiesti": ruoli, "altro": 1}),
    )
    for chiave, vecchio, nuovo in (("policy_comandi_off", spenti[:1], spenti), ("policy_ruoli_richiesti", {}, ruoli)):
        await clean_db.execute(
            "INSERT INTO guild_config_history (guild_id, change_type, key_name, old_value, new_value) VALUES ($1, 'set', $2, $3, $4)",
            g, chiave, json.dumps(vecchio), json.dumps(nuovo),
        )
    for utente, percorso in ((1, "chiedi"), (2, "tag usa")):
        await clean_db.execute("INSERT INTO command_usage (guild_id, user_id, command_path) VALUES ($1, $2, $3)", g, utente, percorso)
    oggi = date(2026, 11, 24)
    for comando, usi in (("chiedi", 3), ("cerca-comando", 4), ("help", 1), ("fun dice", 2)):
        await clean_db.execute("INSERT INTO comandi_uso_server (guild_id, comando, giorno, usi) VALUES ($1, $2, $3, $4)", g, comando, oggi, usi)

    for _ in range(2):  # la seconda corsa non deve cambiare niente
        await clean_db.execute(SQL)
        s = _json(await clean_db.fetchval("SELECT settings FROM guild_config WHERE guild_id = $1", g))
        assert sorted(s["policy_comandi_off"]) == sorted(
            ["music-playlist salva", "giochi-sala roulette", "fun dice", "admin-bot-config pulisci"])
        assert s["policy_ruoli_richiesti"] == {"admin-livelli premi aggiungi": [1, 2], "music-playlist": [3], "fun dice": [4]}
        assert s["altro"] == 1
    cron = await clean_db.fetch("SELECT key_name, old_value, new_value FROM guild_config_history WHERE guild_id = $1", g)
    per_chiave = {r["key_name"]: r for r in cron}
    assert json.loads(per_chiave["policy_comandi_off"]["old_value"]) == ["music-playlist salva"]
    assert json.loads(per_chiave["policy_ruoli_richiesti"]["new_value"])["music-playlist"] == [3]
    usati = sorted(r["command_path"] for r in await clean_db.fetch("SELECT command_path FROM command_usage WHERE guild_id = $1", g))
    assert usati == ["help", "utility-server tag usa"]
    uso = {r["comando"]: r["usi"] for r in await clean_db.fetch("SELECT comando, usi FROM comandi_uso_server WHERE guild_id = $1", g)}
    assert uso == {"help": 8, "fun dice": 2}

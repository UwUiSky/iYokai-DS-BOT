"""
tests/test_weekly_decay_index.py
====================================
La query oraria del decadimento settimanale deve poter usare l'indice
parziale idx_leveling_totals_weekly_decay_due (migrazione 0001): con
`IS DISTINCT FROM` Postgres non poteva usarlo come condizione di ricerca.
"""

import json

import pytest

from core.repositories.leveling_repo import QUERY_UTENTI_DA_DECADERE, LevelingRepository

PERIODO = "2026-W40"
INDICE = "idx_leveling_totals_weekly_decay_due"


@pytest.fixture
def repo(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


def _nodi(piano: dict):
    yield piano
    for figlio in piano.get("Plans", []):
        yield from _nodi(figlio)


async def test_il_piano_della_query_usa_l_indice_come_condizione_di_ricerca(clean_db):
    """Con tutti gli utenti già coperti, la query non deve leggere tutta la tabella."""
    await clean_db.execute(
        """
        INSERT INTO leveling_totals (guild_id, user_id, coins_total, last_weekly_decay_period)
        SELECT 1, utente, 500, $1 FROM generate_series(1, 20000) AS utente
        """,
        PERIODO,
    )
    await clean_db.execute("ANALYZE leveling_totals")

    letterale = PERIODO.replace("'", "''")
    righe = await clean_db.fetchval(
        "EXPLAIN (FORMAT JSON) " + QUERY_UTENTI_DA_DECADERE.replace("$1", f"'{letterale}'")
    )
    nodi = list(_nodi(json.loads(righe)[0]["Plan"]))

    con_indice = [n for n in nodi if n.get("Index Name") == INDICE and n.get("Index Cond")]
    assert con_indice, [n["Node Type"] for n in nodi]
    assert not any(n["Node Type"] == "Seq Scan" for n in nodi)


async def test_la_query_riscritta_restituisce_gli_stessi_utenti_di_is_distinct_from(repo, clean_db):
    casi = [
        (1, 500, None),  # mai decaduto
        (2, 500, "2026-W39"),  # settimana precedente
        (3, 500, "2026-W41"),  # periodo "futuro" (orologio tornato indietro)
        (4, 500, PERIODO),  # già coperto
        (5, 1, None),  # saldo al minimo
        (6, 0, "2026-W39"),
    ]
    for user_id, coins, periodo in casi:
        await clean_db.execute(
            "INSERT INTO leveling_totals (guild_id, user_id, coins_total, last_weekly_decay_period) "
            "VALUES (1, $1, $2, $3)",
            user_id,
            coins,
            periodo,
        )

    attesi = await clean_db.fetch(
        "SELECT guild_id, user_id FROM leveling_totals "
        "WHERE coins_total > 1 AND last_weekly_decay_period IS DISTINCT FROM $1",
        PERIODO,
    )

    trovati = await repo.list_users_needing_weekly_decay(PERIODO)

    assert sorted(trovati) == sorted((r["guild_id"], r["user_id"]) for r in attesi)
    assert sorted(trovati) == [(1, 1), (1, 2), (1, 3)]

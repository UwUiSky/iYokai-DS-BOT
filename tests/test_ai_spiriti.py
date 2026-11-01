"""
tests/test_ai_spiriti.py
========================
`/utility ai spirito` e `/utility ai frammenti` (§25.71, §25.72): misure vere dal database, Discord finto, AI ferma.
"""

from datetime import date

import pytest

from cogs.ai import spiriti
from core.database import db
from core.repositories.activity_stats_repo import activity_stats_repo
from core.repositories.ai_gioco_repo import ai_gioco_repo
from core.repositories.ai_repo import ai_repo
from core.repositories.leveling_repo import leveling_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G, U = 8401, 8402


@pytest.fixture
def repo(clean_db, monkeypatch):
    for r in (ai_gioco_repo, leveling_repo, activity_stats_repo, ai_repo):
        monkeypatch.setattr(r, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(db, "_pool", clean_db, raising=False)
    return clean_db


def _inter():
    i = fake_interaction(guild=fake_guild(G), user=fake_member(U))
    i.guild_id = G
    return i


async def _attivita(pool, messaggi, secondi, giorni):
    for k in range(giorni):
        await pool.execute(
            "INSERT INTO activity_member_daily (guild_id, day, user_id, messages, voice_seconds) VALUES ($1, current_date - $2::int, $3, $4, $5)",
            G, k, U, messaggi // giorni, secondi // giorni,
        )


async def test_misure_dai_conteggi_veri(repo):
    await _attivita(repo, 100, 1200, 4)
    await leveling_repo.add_coins(G, U, 700)
    m = await spiriti.misure_di(G, U, date.today())
    assert (m.messaggi, m.minuti_voce, m.giorni_attivi, m.monete) == (100, 20, 4, 700)


async def test_spirito_scelto_vince_sul_dominante(repo):
    await _attivita(repo, 300, 0, 3)
    cog = spiriti.AiSpiritiCog(None)
    i = _inter()
    await cog.spirito.callback(cog, i, None)
    emb = i.followup.send.call_args.kwargs["embed"]
    assert "scelto da te" not in emb.description
    i = _inter()
    await cog.spirito.callback(cog, i, "monete")
    assert await ai_gioco_repo.spirito_scelto(G, U) == "monete"
    assert "scelto da te" in i.followup.send.call_args.kwargs["embed"].description
    i = _inter()
    await cog.spirito.callback(cog, i, "auto")
    assert await ai_gioco_repo.spirito_scelto(G, U) is None


async def test_frammenti_sbloccati_e_storia_finale_senza_ai(repo):
    await _attivita(repo, 80, 7200, 6)
    await leveling_repo.add_coins(G, U, 900)
    for codice in ("trofeo_boss", "dungeon"):
        await ai_gioco_repo.frammento_sblocca(G, U, codice)
    cog = spiriti.AiSpiritiCog(None)
    i = _inter()
    await cog.frammenti.callback(cog, i)
    emb = i.followup.send.call_args.kwargs["embed"]
    assert "6 su 6" in emb.title and emb.fields[0].value
    assert "tutti_i_frammenti" in await ai_repo.traguardi(U)

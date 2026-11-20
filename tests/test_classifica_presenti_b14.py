"""
tests/test_classifica_presenti_b14.py
=====================================
Classifica senza chi ha lasciato il server (#125 B14): ECO-013.
Funzioni coperte: catalogo #125
"""

from types import SimpleNamespace

import pytest

from cogs.leveling.leveling import LevelingCog
from core.repositories.leveling_repo import leveling_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.moduli import attiva_livelli

G = 100


@pytest.mark.asyncio
async def test_solo_presenti_toglie_chi_e_uscito(monkeypatch, clean_db):
    await attiva_livelli(monkeypatch, clean_db, G)
    import cogs.leveling.leveling as modulo
    from core.repositories.leveling_repo import LevelingRepository
    repo = LevelingRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "leveling_repo", repo)
    for u, c in ((1, 500), (2, 400), (3, 300)):
        await repo.add_coins(G, u, c)
    cog = LevelingCog(bot=None)
    cog.cog_unload()
    guild = fake_guild(G)
    guild.get_member = lambda uid: fake_member(uid) if uid != 1 else None  # 1 è uscito
    scelta = lambda v: SimpleNamespace(value=v, name=v)
    i = fake_interaction(guild=guild, user=fake_member(9))
    await cog.leaderboard.callback(cog, i, scelta("coins"), scelta("alltime"), 10, True)
    testo = i.response.send_message.await_args.kwargs["embed"].description
    assert "<@2>" in testo and "<@3>" in testo and "<@1>" not in testo
    i2 = fake_interaction(guild=guild, user=fake_member(9))
    await cog.leaderboard.callback(cog, i2, scelta("coins"), scelta("alltime"), 10, False)
    assert "<@1>" in i2.response.send_message.await_args.kwargs["embed"].description

"""
tests/test_fun_controllo_area17_db.py
=====================================
Controllo dell'area 17, parte con database e comandi: FUN-027 (Preferiresti con due bottoni e il conteggio), FUN-031 e FUN-032
(gli scherzi rispettano il blocco personale di FUN-137), FUN-034 (curiosità su gatti e cani).
Funzioni coperte: FUN-027, FUN-031, FUN-032, FUN-034
"""

import random
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.fun.entertainment import MODULE_FUN
from cogs.fun.fun_extra import FunExtraCog, PreferireView
from core.classic_entertainment_logic import FACTS_ANIMALI
from core.database import db
from core.repositories.gif_privacy_repo import gif_privacy_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

ID = 4242


@pytest.fixture(autouse=True)
async def _attivo(monkeypatch, clean_db):
    import core.database as dm

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID, MODULE_FUN, True)
    yield
    dm.db._modules_cache.clear()


def test_fun_034_curiosita_su_gatti_e_cani():
    assert set(FACTS_ANIMALI) == {"gatti", "cani"} or len(FACTS_ANIMALI) >= 2
    assert all(len(frasi) >= 3 for frasi in FACTS_ANIMALI.values())


@pytest.mark.asyncio
async def test_fun_027_preferiresti_conta_un_voto_per_persona_e_i_bot_non_votano():
    v = PreferireView("volare", "essere invisibile")
    assert v.conteggio() == (0, 0)

    async def vota(n, utente):
        i = fake_interaction(guild=fake_guild(ID), user=utente)
        i.response.edit_message = AsyncMock()
        await v.children[n].callback(i)

    await vota(0, fake_member(1))
    await vota(0, fake_member(2))
    await vota(1, fake_member(1))  # cambia voto: non vale due volte
    await vota(1, fake_member(3, bot=True))  # i bot non votano
    assert v.conteggio() == (1, 1) and "1 voti" in v.testo()


@pytest.mark.asyncio
async def test_fun_031_032_gli_scherzi_rispettano_il_blocco_personale():
    cog = FunExtraCog(bot=None)
    cog._rng = random.Random(1)
    scelta = lambda v: SimpleNamespace(value=v, name=v)
    autore, bersaglio = fake_member(10), fake_member(20)
    i = fake_interaction(guild=fake_guild(ID), user=autore)
    await cog.scherzo.callback(cog, i, scelta("lancia"), bersaglio, None)
    assert "ephemeral" not in i.response.send_message.await_args.kwargs  # nessun blocco: lo scherzo parte
    await gif_privacy_repo.blocca(20, 10)  # il bersaglio blocca l'autore
    for tipo in ("lancia", "presa-in-giro", "google", "brindisi"):
        j = fake_interaction(guild=fake_guild(ID), user=autore)
        await cog.scherzo.callback(cog, j, scelta(tipo), bersaglio, "ciao")
        assert j.response.send_message.await_args.kwargs["ephemeral"] is True
        assert bersaglio.mention not in j.response.send_message.await_args.args[0]
    k = fake_interaction(guild=fake_guild(ID), user=fake_member(11))  # un altro autore non è bloccato
    await cog.scherzo.callback(cog, k, scelta("lancia"), bersaglio, None)
    assert "ephemeral" not in k.response.send_message.await_args.kwargs

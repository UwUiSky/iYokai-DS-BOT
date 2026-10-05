"""
tests/test_assegna_lobby_tutto_o_niente.py
==========================================
LC-1 (#18): /assegna-lobby fa defer() per prima cosa e mette l'addebito
della cassa e tutti gli accrediti in una sola transazione. Con 40
persone: o pagano tutti, o non cambia niente. Database vero.
Funzioni coperte: SPEC §15.15
"""

import asyncpg
import pytest

from cogs.leveling.leveling import LevelingCog
from core.repositories.guild_chest_repo import REASON_WEEKLY_PERSONAL_DECAY, guild_chest_repo
from core.repositories.leveling_repo import leveling_repo
from tests.support.moduli import attiva_livelli
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_voice_channel,
)

GUILD_ID = 100
IMPORTO = 50
PERSONE = 40
CASSA = 10_000
SALDO_MASSIMO = 2**63 - 1  # il massimo di una colonna BIGINT


@pytest.fixture
async def cog(monkeypatch, clean_db):
    await attiva_livelli(monkeypatch, clean_db, GUILD_ID)
    await guild_chest_repo.deposit(GUILD_ID, CASSA, REASON_WEEKLY_PERSONAL_DECAY)
    c = LevelingCog(bot=None)
    c.cog_unload()
    return c


def _interazione(id_dei_presenti: list[int]):
    """Server con due canali vocali e i presenti divisi a metà."""
    server = fake_guild(GUILD_ID)
    meta = len(id_dei_presenti) // 2
    primo, secondo = fake_voice_channel(1), fake_voice_channel(2)
    primo.members = [fake_member(i) for i in id_dei_presenti[:meta]]
    secondo.members = [fake_member(i) for i in id_dei_presenti[meta:]]
    server.voice_channels = [primo, secondo]
    interazione = fake_interaction(guild=server)
    # Si tiene l'ordine delle chiamate a Discord: defer() deve essere la prima.
    ordine: list[str] = []
    interazione.response.defer.side_effect = lambda **kw: ordine.append("defer")
    interazione.followup.send.side_effect = lambda *a, **kw: ordine.append("followup")
    interazione.ordine = ordine
    return interazione


@pytest.mark.asyncio
async def test_quaranta_persone_pagate_tutte_con_defer_per_primo(cog):
    presenti = list(range(1, PERSONE + 1))
    interazione = _interazione(presenti)

    await cog.assegna_lobby.callback(cog, interazione, importo=IMPORTO)

    assert interazione.ordine == ["defer", "followup"]
    interazione.response.send_message.assert_not_awaited()
    for user_id in presenti:
        assert (await leveling_repo.get_totals(GUILD_ID, user_id)).coins_total == IMPORTO
    assert await guild_chest_repo.get_balance(GUILD_ID) == CASSA - IMPORTO * PERSONE
    assert f"**{PERSONE}** persone" in interazione.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_errore_a_meta_non_cambia_niente(cog, clean_db):
    # Il ventesimo ha già il saldo più alto che il database può
    # contenere: il suo accredito fallisce, a metà giro.
    presenti = list(range(1, PERSONE + 1))
    await leveling_repo.add_coins(GUILD_ID, 20, SALDO_MASSIMO)
    interazione = _interazione(presenti)

    with pytest.raises(asyncpg.DataError):
        await cog.assegna_lobby.callback(cog, interazione, importo=IMPORTO)

    assert await guild_chest_repo.get_balance(GUILD_ID) == CASSA
    saldi = await clean_db.fetch("SELECT user_id, coins_total FROM leveling_totals")
    assert [(r["user_id"], r["coins_total"]) for r in saldi] == [(20, SALDO_MASSIMO)]
    movimenti = await guild_chest_repo.list_ledger(GUILD_ID)
    assert [m.reason for m in movimenti] == [REASON_WEEKLY_PERSONAL_DECAY]


@pytest.mark.asyncio
async def test_cassa_insufficiente_non_paga_nessuno(cog, clean_db):
    interazione = _interazione(list(range(1, PERSONE + 1)))

    await cog.assegna_lobby.callback(cog, interazione, importo=CASSA)

    assert await guild_chest_repo.get_balance(GUILD_ID) == CASSA
    assert await clean_db.fetchval("SELECT COUNT(*) FROM leveling_totals") == 0
    assert "non basta" in interazione.followup.send.await_args.args[0]

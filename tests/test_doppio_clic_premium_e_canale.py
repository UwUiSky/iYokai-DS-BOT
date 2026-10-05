"""
tests/test_doppio_clic_premium_e_canale.py
==========================================
BUG-14, M 9.3: /cassa sblocca-premium e /clan compra-canale lanciati
due volte insieme devono addebitare una volta sola; se Discord non
crea il canale, la tesoreria torna com'era. Database vero.
Funzioni coperte: SPEC §15.14, §15.15
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from cogs.leveling.leveling import LevelingCog
from core.repositories.guild_chest_repo import REASON_WEEKLY_PERSONAL_DECAY, guild_chest_repo
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction
from tests.test_guild_clan_cog_behavior import (  # noqa: F401  (cog_e_repos è una fixture)
    _crea_clan_con_categoria,
    _FakeGuild,
    _FakeInteraction,
    _FakeMember,
    cog_e_repos,
)

GUILD_ID = 100
COSTO_TIER_1 = 500_000  # 500 membri
COSTO_PRIMO_CANALE = 25_000


# ----------------------------------------------------------------------
# /cassa sblocca-premium
# ----------------------------------------------------------------------
@pytest.fixture
async def cog_con_cassa(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    await apri_connessioni(clean_db)
    await clean_db.execute(
        "INSERT INTO guild_config (guild_id, created_at) VALUES ($1, $2)",
        GUILD_ID,
        datetime.now(timezone.utc) - timedelta(days=400),
    )
    cog = LevelingCog(bot=None)
    cog.cog_unload()
    return cog


def _interazione_admin():
    server = fake_guild(GUILD_ID)
    server.member_count = 500
    return fake_interaction(guild=server)


def _testi(interazione) -> list[str]:
    chiamate = (
        interazione.response.send_message.call_args_list
        + interazione.followup.send.call_args_list
    )
    return [chiamata.args[0] for chiamata in chiamate]


@pytest.mark.asyncio
async def test_sblocca_premium_due_volte_insieme_addebita_una_volta(cog_con_cassa):
    cog = cog_con_cassa
    await guild_chest_repo.deposit(GUILD_ID, 3 * COSTO_TIER_1, REASON_WEEKLY_PERSONAL_DECAY)
    prima, seconda = _interazione_admin(), _interazione_admin()

    await asyncio.gather(
        cog.chest_sblocca_premium.callback(cog, prima, tier=1),
        cog.chest_sblocca_premium.callback(cog, seconda, tier=1),
    )

    assert await guild_chest_repo.get_balance(GUILD_ID) == 2 * COSTO_TIER_1
    risposte = _testi(prima) + _testi(seconda)
    assert sum("sbloccato per" in testo for testo in risposte) == 1
    assert sum("già stato acquistato" in testo for testo in risposte) == 1


# ----------------------------------------------------------------------
# /clan compra-canale
# ----------------------------------------------------------------------
async def _clan_pronto_per_un_canale(clan_repo, guild):
    clan_id, categoria = await _crea_clan_con_categoria(clan_repo, guild)
    await clan_repo.donate(clan_id, user_id=1, amount=15_000 + 4 * COSTO_PRIMO_CANALE)
    await clan_repo.add_voice_ticks(clan_id, count=100 * 60)
    return clan_id


@pytest.mark.asyncio
async def test_compra_canale_due_volte_insieme_addebita_una_volta(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    await apri_connessioni(clan_repo._pool)
    guild = _FakeGuild(GUILD_ID)
    clan_id = await _clan_pronto_per_un_canale(clan_repo, guild)
    prima = _FakeInteraction(guild, user=_FakeMember(1))
    seconda = _FakeInteraction(guild, user=_FakeMember(1))

    await asyncio.gather(
        cog.clan_compra_canale.callback(cog, prima, tipo="testuale", nome=None),
        cog.clan_compra_canale.callback(cog, seconda, tipo="testuale", nome=None),
    )

    clan = await clan_repo.get_clan(clan_id)
    assert clan.channels_unlocked == 1
    assert clan.treasury_balance == 3 * COSTO_PRIMO_CANALE
    assert len(guild.created_channels) == 1
    risposte = prima.response.sent_messages + seconda.response.sent_messages
    assert sum("sbloccato per" in testo for testo in risposte) == 1


@pytest.mark.asyncio
async def test_compra_canale_se_discord_non_lo_crea_la_tesoreria_torna_com_era(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID, channel_creation_forbidden=True)
    clan_id = await _clan_pronto_per_un_canale(clan_repo, guild)
    interazione = _FakeInteraction(guild, user=_FakeMember(1))

    await cog.clan_compra_canale.callback(cog, interazione, tipo="vocale", nome=None)

    clan = await clan_repo.get_clan(clan_id)
    assert clan.channels_unlocked == 0
    assert clan.treasury_balance == 4 * COSTO_PRIMO_CANALE
    assert "permessi" in interazione.response.sent_messages[0]
    # Addebito e rimborso restano scritti nello storico della tesoreria.
    movimenti = await clan_repo._pool.fetch(
        "SELECT amount FROM clan_treasury_ledger WHERE clan_id = $1 AND reason LIKE 'channel_unlock%' ORDER BY id",
        clan_id,
    )
    assert [m["amount"] for m in movimenti] == [-COSTO_PRIMO_CANALE, COSTO_PRIMO_CANALE]

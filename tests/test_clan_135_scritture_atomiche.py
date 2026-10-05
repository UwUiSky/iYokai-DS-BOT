"""
tests/test_clan_135_scritture_atomiche.py
=========================================
#135: /clan boost, /clan tesoreria dona e /clan promuovi non leggono più
"controllo poi scrivo": pagamento e effetto stanno in una transazione
sola, il tetto dei ruoli si controlla sotto blocco. Database vero.
Funzioni coperte: SPEC §15.14
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from core.guild_clan_boost_logic import (
    BOOST_DURATION_HOURS,
    GUILD_BOOST_COST,
    INDIVIDUAL_BOOST_COST,
)
from core.guild_clan_logic import MAX_ADMINS_PER_CLAN
from tests.support.concorrenza import apri_connessioni
from tests.test_guild_clan_cog_behavior import (  # noqa: F401  (cog_e_repos è una fixture)
    _crea_clan_con_categoria,
    _FakeGuild,
    _FakeInteraction,
    _FakeMember,
    cog_e_repos,
)

GUILD_ID = 100
DURATA = timedelta(hours=BOOST_DURATION_HOURS)


def _clic(guild, user_id=1):
    return _FakeInteraction(guild, user=_FakeMember(user_id))


# ----------------------------------------------------------------------
# /clan boost: i due clic insieme pagano due volte E ricevono due volte
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_boost_gilda_due_clic_insieme_estendono_due_volte(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    await apri_connessioni(clan_repo._pool)
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    await clan_repo.donate(clan_id, user_id=1, amount=15_000 + 3 * GUILD_BOOST_COST)
    prima = datetime.now(timezone.utc)

    await asyncio.gather(
        cog.clan_boost_gilda.callback(cog, _clic(guild)),
        cog.clan_boost_gilda.callback(cog, _clic(guild)),
    )

    clan = await clan_repo.get_clan(clan_id)
    assert clan.treasury_balance == GUILD_BOOST_COST
    # Due pagamenti = due durate: la seconda parte da dove finisce la prima.
    assert clan.guild_boost_expires_at >= prima + 2 * DURATA - timedelta(minutes=1)


@pytest.mark.asyncio
async def test_boost_individuale_due_clic_insieme_estendono_due_volte(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    await apri_connessioni(clan_repo._pool)
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    await leveling_repo.add_coins(GUILD_ID, 1, 3 * INDIVIDUAL_BOOST_COST)
    prima = datetime.now(timezone.utc)

    await asyncio.gather(
        cog.clan_boost_individuale.callback(cog, _clic(guild)),
        cog.clan_boost_individuale.callback(cog, _clic(guild)),
    )

    assert (await leveling_repo.get_totals(GUILD_ID, 1)).coins_total == INDIVIDUAL_BOOST_COST
    membro = await clan_repo.get_member(clan_id, 1)
    assert membro.boost_expires_at >= prima + 2 * DURATA - timedelta(minutes=1)


@pytest.mark.asyncio
async def test_boost_gilda_tesoreria_per_uno_solo_ne_passa_uno(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    await apri_connessioni(clan_repo._pool)
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    await clan_repo.donate(clan_id, user_id=1, amount=15_000 + GUILD_BOOST_COST)

    await asyncio.gather(
        cog.clan_boost_gilda.callback(cog, _clic(guild)),
        cog.clan_boost_gilda.callback(cog, _clic(guild)),
    )

    clan = await clan_repo.get_clan(clan_id)
    assert clan.treasury_balance == 0
    assert clan.guild_boost_expires_at is not None
    assert clan.guild_boost_expires_at < datetime.now(timezone.utc) + DURATA + timedelta(minutes=1)


# ----------------------------------------------------------------------
# /clan tesoreria dona: una transazione sola
# ----------------------------------------------------------------------
@pytest.fixture
async def ledger_che_rifiuta_le_donazioni(cog_e_repos):
    _, clan_repo, _ = cog_e_repos
    pool = clan_repo._pool
    await pool.execute(
        """
        CREATE OR REPLACE FUNCTION _rifiuta_donazione() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'prova: ledger giù'; END $$ LANGUAGE plpgsql
        """
    )
    await pool.execute(
        "CREATE TRIGGER _rifiuta_donazione BEFORE INSERT ON clan_treasury_ledger "
        "FOR EACH ROW WHEN (NEW.reason = 'donation') EXECUTE FUNCTION _rifiuta_donazione()"
    )
    yield
    await pool.execute("DROP TRIGGER IF EXISTS _rifiuta_donazione ON clan_treasury_ledger")
    await pool.execute("DROP FUNCTION IF EXISTS _rifiuta_donazione()")


@pytest.mark.asyncio
async def test_dona_se_la_scrittura_fallisce_le_coin_restano_al_donatore(
    cog_e_repos, ledger_che_rifiuta_le_donazioni
):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    await leveling_repo.add_coins(GUILD_ID, 1, 1_000)
    saldo_clan = (await clan_repo.get_clan(clan_id)).treasury_balance

    try:
        await cog.clan_tesoreria_dona.callback(cog, _clic(guild), importo=400)
    except Exception:
        pass

    assert (await leveling_repo.get_totals(GUILD_ID, 1)).coins_total == 1_000
    assert (await clan_repo.get_clan(clan_id)).treasury_balance == saldo_clan


@pytest.mark.asyncio
async def test_dona_due_volte_insieme_con_coin_per_una_sola(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    await apri_connessioni(clan_repo._pool)
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    await leveling_repo.add_coins(GUILD_ID, 1, 500)
    saldo_clan = (await clan_repo.get_clan(clan_id)).treasury_balance

    await asyncio.gather(
        cog.clan_tesoreria_dona.callback(cog, _clic(guild), importo=500),
        cog.clan_tesoreria_dona.callback(cog, _clic(guild), importo=500),
    )

    assert (await leveling_repo.get_totals(GUILD_ID, 1)).coins_total == 0
    assert (await clan_repo.get_clan(clan_id)).treasury_balance == saldo_clan + 500


@pytest.mark.asyncio
async def test_dona_senza_coin_non_tocca_la_tesoreria(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    saldo_clan = (await clan_repo.get_clan(clan_id)).treasury_balance

    interazione = _clic(guild)
    await cog.clan_tesoreria_dona.callback(cog, interazione, importo=400)

    assert "Non hai abbastanza coin" in interazione.response.sent_messages[0]
    assert (await clan_repo.get_clan(clan_id)).treasury_balance == saldo_clan


# ----------------------------------------------------------------------
# /clan promuovi: il tetto si controlla nella scrittura
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_promuovi_due_admin_insieme_non_superano_il_tetto(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    await apri_connessioni(clan_repo._pool)
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    for user_id in (2, 3):
        await clan_repo.add_member(clan_id, user_id, role="admin")
    for user_id in (4, 5):
        await clan_repo.add_member(clan_id, user_id)
    assert MAX_ADMINS_PER_CLAN == 3

    await asyncio.gather(
        cog.clan_promuovi.callback(cog, _clic(guild), membro=_FakeMember(4), ruolo="admin"),
        cog.clan_promuovi.callback(cog, _clic(guild), membro=_FakeMember(5), ruolo="admin"),
    )

    assert await clan_repo.count_members_with_role(clan_id, "admin") == MAX_ADMINS_PER_CLAN


# ----------------------------------------------------------------------
# Deadlock con il tick testuale e verifiche di appartenenza
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_set_member_role_e_apply_text_tick_in_parallelo_senza_deadlock(cog_e_repos):
    _, clan_repo, _ = cog_e_repos
    await apri_connessioni(clan_repo._pool, 4)
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    await clan_repo.add_member(clan_id, 2)

    async def ruoli():
        for i in range(150):
            await clan_repo.set_member_role(clan_id, 2, "mod" if i % 2 else "member")

    async def tick():
        for _ in range(150):
            await clan_repo._pool.execute(
                "UPDATE clan_members SET last_text_xp_at = NULL WHERE clan_id = $1 AND user_id = 2",
                clan_id,
            )
            await clan_repo.apply_text_tick(clan_id, 2)

    await asyncio.gather(ruoli(), tick())


@pytest.mark.asyncio
async def test_non_membro_non_puo_diventare_co_owner(cog_e_repos):
    _, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)

    esito = await clan_repo.set_member_role(clan_id, 99, "co_owner")

    assert esito.value == "non_membro"
    assert (await clan_repo.get_clan(clan_id)).co_owner_id is None


@pytest.mark.asyncio
async def test_boost_con_guild_sbagliato_non_spende(cog_e_repos):
    _, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    await leveling_repo.add_coins(200, 1, 50_000)

    nuova = await clan_repo.buy_member_boost(
        200, clan_id, 1, INDIVIDUAL_BOOST_COST, datetime.now(timezone.utc)
    )

    assert nuova is None
    assert (await leveling_repo.get_totals(200, 1)).coins_total == 50_000


@pytest.mark.asyncio
async def test_dona_da_non_membro_o_con_guild_sbagliato_non_spende(cog_e_repos):
    _, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    await leveling_repo.add_coins(GUILD_ID, 99, 1_000)
    await leveling_repo.add_coins(200, 1, 1_000)

    assert await clan_repo.donate_from_member(GUILD_ID, clan_id, 99, 500) is None
    assert await clan_repo.donate_from_member(200, clan_id, 1, 500) is None

    assert (await leveling_repo.get_totals(GUILD_ID, 99)).coins_total == 1_000
    assert (await leveling_repo.get_totals(200, 1)).coins_total == 1_000

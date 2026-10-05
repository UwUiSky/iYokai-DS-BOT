"""
tests/test_clan_146_boost_per_tipo.py
=====================================
#146 (D23): boost del clan per tipo (exp, coin, super), individuale e di
gilda. Un boost si compra solo se nessuno dei suoi benefici è attivo;
niente somma delle durate; nessun addebito se rifiutato. Database vero.
Funzioni coperte: SPEC §15.14
"""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.guild_clan_boost_logic import (
    GUILD_BOOST_COSTS,
    INDIVIDUAL_BOOST_COSTS,
    Beneficio,
    StatoBoost,
    TipoBoost,
)
from tests.support.concorrenza import apri_connessioni
from tests.test_guild_clan_cog_behavior import (  # noqa: F401  (cog_e_repos è una fixture)
    _crea_clan_con_categoria,
    _FakeGuild,
    cog_e_repos,
)

GUILD_ID = 100
ORA = datetime.now(timezone.utc)
DOMANI = ORA + timedelta(hours=24)
FUTURO = ORA + timedelta(hours=5)
PASSATO = ORA - timedelta(hours=1)
E, C, S = TipoBoost.EXP, TipoBoost.COIN, TipoBoost.SUPER

# (exp attivo, coin attivo, tipo che si prova a comprare, comprabile?)
MATRICE = [
    (False, False, E, True), (False, False, C, True), (False, False, S, True),
    (False, True, E, True), (False, True, C, False), (False, True, S, False),
    (True, False, E, False), (True, False, C, True), (True, False, S, False),
    (True, True, E, False), (True, True, C, False), (True, True, S, False),
]


async def _imposta_membro(repo, clan_id, user_id, exp, coin):
    await repo._pool.execute(
        "UPDATE clan_members SET boost_exp_expires_at = $3, boost_coin_expires_at = $4 "
        "WHERE clan_id = $1 AND user_id = $2",
        clan_id, user_id, FUTURO if exp else None, FUTURO if coin else None,
    )


async def _imposta_gilda(repo, clan_id, exp, coin):
    await repo._pool.execute(
        "UPDATE clans SET guild_boost_exp_expires_at = $2, guild_boost_coin_expires_at = $3 "
        "WHERE id = $1",
        clan_id, FUTURO if exp else None, FUTURO if coin else None,
    )


# ----------------------------------------------------------------------
# Matrice completa, ambito individuale
# ----------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("exp_att, coin_att, tipo, ok", MATRICE)
async def test_matrice_individuale(cog_e_repos, exp_att, coin_att, tipo, ok):
    _, repo, leveling = cog_e_repos
    clan_id, _ = await _crea_clan_con_categoria(repo, _FakeGuild(GUILD_ID))
    await leveling.add_coins(GUILD_ID, 1, 50_000)
    await _imposta_membro(repo, clan_id, 1, exp_att, coin_att)
    prima = await repo.get_member(clan_id, 1)

    esito = await repo.buy_member_boost(GUILD_ID, clan_id, 1, tipo, ORA)

    saldo = (await leveling.get_totals(GUILD_ID, 1)).coins_total
    m = await repo.get_member(clan_id, 1)
    if ok:
        assert esito.stato is StatoBoost.ACQUISTATO
        assert esito.scadenza == DOMANI or abs(esito.scadenza - DOMANI) < timedelta(seconds=1)
        assert saldo == 50_000 - INDIVIDUAL_BOOST_COSTS[tipo]
        for b, scad in (
            (Beneficio.EXP, m.boost_exp_expires_at), (Beneficio.COIN, m.boost_coin_expires_at)
        ):
            if b in tipo.benefici:
                assert scad == esito.scadenza  # now + 24h, mai sommata
    else:
        assert esito.stato is StatoBoost.GIA_ATTIVO
        assert esito.scadenza is None
        assert {b for b, _ in esito.attivi} == (
            ({Beneficio.EXP} if exp_att else set()) | ({Beneficio.COIN} if coin_att else set())
        )
        assert all(scad == FUTURO for _, scad in esito.attivi)
        # nessuna scrittura, nessun addebito
        assert saldo == 50_000
        assert (m.boost_exp_expires_at, m.boost_coin_expires_at) == (
            prima.boost_exp_expires_at, prima.boost_coin_expires_at
        )


# ----------------------------------------------------------------------
# Matrice completa, ambito di gilda
# ----------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("exp_att, coin_att, tipo, ok", MATRICE)
async def test_matrice_gilda(cog_e_repos, exp_att, coin_att, tipo, ok):
    _, repo, _ = cog_e_repos
    clan_id, _ = await _crea_clan_con_categoria(repo, _FakeGuild(GUILD_ID))
    await repo.donate(clan_id, user_id=1, amount=15_000 + 300_000)
    await _imposta_gilda(repo, clan_id, exp_att, coin_att)

    esito = await repo.buy_guild_boost(clan_id, tipo, ORA)

    clan = await repo.get_clan(clan_id)
    if ok:
        assert esito.stato is StatoBoost.ACQUISTATO
        assert clan.treasury_balance == 300_000 - GUILD_BOOST_COSTS[tipo]
        for b, scad in (
            (Beneficio.EXP, clan.guild_boost_exp_expires_at),
            (Beneficio.COIN, clan.guild_boost_coin_expires_at),
        ):
            if b in tipo.benefici:
                assert scad == esito.scadenza
        movimenti = await repo.list_ledger(clan_id, limit=1)
        assert movimenti[0].amount == -GUILD_BOOST_COSTS[tipo]
    else:
        assert esito.stato is StatoBoost.GIA_ATTIVO
        assert clan.treasury_balance == 300_000
        assert clan.guild_boost_exp_expires_at == (FUTURO if exp_att else None)
        assert clan.guild_boost_coin_expires_at == (FUTURO if coin_att else None)


@pytest.mark.asyncio
async def test_boost_scaduto_non_blocca_e_riparte_da_ora(cog_e_repos):
    _, repo, leveling = cog_e_repos
    clan_id, _ = await _crea_clan_con_categoria(repo, _FakeGuild(GUILD_ID))
    await leveling.add_coins(GUILD_ID, 1, 50_000)
    await repo._pool.execute(
        "UPDATE clan_members SET boost_exp_expires_at = $3, boost_coin_expires_at = $3 "
        "WHERE clan_id = $1 AND user_id = $2", clan_id, 1, PASSATO,
    )

    esito = await repo.buy_member_boost(GUILD_ID, clan_id, 1, S, ORA)

    assert esito.stato is StatoBoost.ACQUISTATO
    assert abs(esito.scadenza - DOMANI) < timedelta(seconds=1)


@pytest.mark.asyncio
async def test_fondi_insufficienti_non_scrivono(cog_e_repos):
    _, repo, leveling = cog_e_repos
    clan_id, _ = await _crea_clan_con_categoria(repo, _FakeGuild(GUILD_ID))
    await leveling.add_coins(GUILD_ID, 1, 9_999)

    esito = await repo.buy_member_boost(GUILD_ID, clan_id, 1, S, ORA)

    assert esito.stato is StatoBoost.NON_ABBASTANZA_FONDI
    assert (await leveling.get_totals(GUILD_ID, 1)).coins_total == 9_999
    m = await repo.get_member(clan_id, 1)
    assert m.boost_exp_expires_at is None and m.boost_coin_expires_at is None

    esito = await repo.buy_guild_boost(clan_id, E, ORA)  # tesoreria a 0
    assert esito.stato is StatoBoost.NON_ABBASTANZA_FONDI
    clan = await repo.get_clan(clan_id)
    assert clan.guild_boost_exp_expires_at is None


@pytest.mark.asyncio
async def test_non_membro_e_gilda_assente(cog_e_repos):
    _, repo, leveling = cog_e_repos
    clan_id, _ = await _crea_clan_con_categoria(repo, _FakeGuild(GUILD_ID))
    await leveling.add_coins(GUILD_ID, 99, 50_000)
    await leveling.add_coins(200, 1, 50_000)

    assert (await repo.buy_member_boost(GUILD_ID, clan_id, 99, E, ORA)).stato is StatoBoost.NON_MEMBRO
    assert (await repo.buy_member_boost(200, clan_id, 1, E, ORA)).stato is StatoBoost.NON_MEMBRO
    assert (await repo.buy_guild_boost(987_654, E, ORA)).stato is StatoBoost.ASSENTE
    assert (await leveling.get_totals(GUILD_ID, 99)).coins_total == 50_000
    assert (await leveling.get_totals(200, 1)).coins_total == 50_000


# ----------------------------------------------------------------------
# Ambiti indipendenti
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_individuale_e_di_gilda_sono_indipendenti(cog_e_repos):
    _, repo, leveling = cog_e_repos
    clan_id, _ = await _crea_clan_con_categoria(repo, _FakeGuild(GUILD_ID))
    await leveling.add_coins(GUILD_ID, 1, 50_000)
    await repo.donate(clan_id, user_id=1, amount=15_000 + 300_000)
    await _imposta_gilda(repo, clan_id, True, True)  # super di gilda attivo

    esito = await repo.buy_member_boost(GUILD_ID, clan_id, 1, S, ORA)
    assert esito.stato is StatoBoost.ACQUISTATO

    await _imposta_gilda(repo, clan_id, False, False)
    esito = await repo.buy_guild_boost(clan_id, S, ORA)  # individuale super attivo
    assert esito.stato is StatoBoost.ACQUISTATO


@pytest.mark.asyncio
async def test_boost_di_un_membro_non_tocca_gli_altri(cog_e_repos):
    _, repo, leveling = cog_e_repos
    clan_id, _ = await _crea_clan_con_categoria(repo, _FakeGuild(GUILD_ID))
    await repo.add_member(clan_id, user_id=5, role="member")
    await leveling.add_coins(GUILD_ID, 5, 50_000)
    await _imposta_membro(repo, clan_id, 1, True, True)

    esito = await repo.buy_member_boost(GUILD_ID, clan_id, 5, S, ORA)

    assert esito.stato is StatoBoost.ACQUISTATO


# ----------------------------------------------------------------------
# Acquisti insieme dello stesso beneficio: ne passa uno solo
# ----------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("t1, t2", [(E, E), (C, C), (S, S), (E, S), (S, C)])
async def test_due_acquisti_insieme_individuali_ne_passa_uno(cog_e_repos, t1, t2):
    _, repo, leveling = cog_e_repos
    await apri_connessioni(repo._pool)
    clan_id, _ = await _crea_clan_con_categoria(repo, _FakeGuild(GUILD_ID))
    await leveling.add_coins(GUILD_ID, 1, 100_000)

    esiti = await asyncio.gather(
        repo.buy_member_boost(GUILD_ID, clan_id, 1, t1, ORA),
        repo.buy_member_boost(GUILD_ID, clan_id, 1, t2, ORA),
    )

    stati = sorted(e.stato.value for e in esiti)
    assert stati == [StatoBoost.ACQUISTATO.value, StatoBoost.GIA_ATTIVO.value]
    pagato = next(
        INDIVIDUAL_BOOST_COSTS[t] for t, e in zip((t1, t2), esiti)
        if e.stato is StatoBoost.ACQUISTATO
    )
    assert (await leveling.get_totals(GUILD_ID, 1)).coins_total == 100_000 - pagato


@pytest.mark.asyncio
async def test_due_acquisti_insieme_di_gilda_ne_passa_uno(cog_e_repos):
    _, repo, _ = cog_e_repos
    await apri_connessioni(repo._pool)
    clan_id, _ = await _crea_clan_con_categoria(repo, _FakeGuild(GUILD_ID))
    await repo.donate(clan_id, user_id=1, amount=15_000 + 300_000)

    esiti = await asyncio.gather(
        repo.buy_guild_boost(clan_id, S, ORA), repo.buy_guild_boost(clan_id, S, ORA)
    )

    assert sorted(e.stato.value for e in esiti) == ["acquistato", "gia_attivo"]
    clan = await repo.get_clan(clan_id)
    assert clan.treasury_balance == 300_000 - GUILD_BOOST_COSTS[S]
    assert len(await repo.list_ledger(clan_id, limit=50)) == 3  # deficit, dona, boost


@pytest.mark.asyncio
async def test_exp_e_coin_insieme_passano_tutti_e_due(cog_e_repos):
    _, repo, leveling = cog_e_repos
    await apri_connessioni(repo._pool)
    clan_id, _ = await _crea_clan_con_categoria(repo, _FakeGuild(GUILD_ID))
    await leveling.add_coins(GUILD_ID, 1, 100_000)

    esiti = await asyncio.gather(
        repo.buy_member_boost(GUILD_ID, clan_id, 1, E, ORA),
        repo.buy_member_boost(GUILD_ID, clan_id, 1, C, ORA),
    )

    assert [e.stato for e in esiti] == [StatoBoost.ACQUISTATO] * 2
    assert (await leveling.get_totals(GUILD_ID, 1)).coins_total == 100_000 - 12_000


# ----------------------------------------------------------------------
# Migrazione 0020: il boost di oggi diventa un super
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_migrazione_0020_copia_le_scadenze_in_entrambe(cog_e_repos):
    _, repo, _ = cog_e_repos
    clan_id, _ = await _crea_clan_con_categoria(repo, _FakeGuild(GUILD_ID))
    await repo.add_member(clan_id, user_id=7, role="member")
    scad_m = datetime(2031, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    scad_g = datetime(2031, 5, 6, 7, 8, 9, tzinfo=timezone.utc)
    await repo._pool.execute(
        "UPDATE clan_members SET boost_expires_at = $3, boost_exp_expires_at = NULL, "
        "boost_coin_expires_at = NULL WHERE clan_id = $1 AND user_id = $2", clan_id, 1, scad_m,
    )
    await repo._pool.execute(
        "UPDATE clans SET guild_boost_expires_at = $2, guild_boost_exp_expires_at = NULL, "
        "guild_boost_coin_expires_at = NULL WHERE id = $1", clan_id, scad_g,
    )

    sql = (Path(__file__).parent.parent / "core/migrations/0020_clan_boost_per_tipo.sql").read_text()
    await repo._pool.execute(sql)

    m = await repo.get_member(clan_id, 1)
    assert m.boost_exp_expires_at == m.boost_coin_expires_at == scad_m
    clan = await repo.get_clan(clan_id)
    assert clan.guild_boost_exp_expires_at == clan.guild_boost_coin_expires_at == scad_g
    altro = await repo.get_member(clan_id, 7)
    assert altro.boost_exp_expires_at is None and altro.boost_coin_expires_at is None


# ----------------------------------------------------------------------
# Scheda del clan: boost attivi per tipo
# ----------------------------------------------------------------------
async def _campo_boost(cog, guild):
    from tests.test_guild_clan_cog_behavior import _FakeInteraction, _FakeMember

    interazione = _FakeInteraction(guild, user=_FakeMember(1))
    await cog.clan_info.callback(cog, interazione, tag=None)
    embed = interazione.response.sent_embeds[0]
    return next((c for c in embed.fields if c.name == "Boost di gilda"), None)


@pytest.mark.asyncio
async def test_scheda_senza_boost_non_mostra_il_campo(cog_e_repos):
    cog, repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    await _crea_clan_con_categoria(repo, guild)

    assert await _campo_boost(cog, guild) is None


@pytest.mark.asyncio
async def test_scheda_mostra_boost_per_beneficio_e_super(cog_e_repos):
    cog, repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _crea_clan_con_categoria(repo, guild)

    await _imposta_gilda(repo, clan_id, True, False)
    assert "Exp" in (await _campo_boost(cog, guild)).value
    assert "Coin" not in (await _campo_boost(cog, guild)).value

    await _imposta_gilda(repo, clan_id, False, True)
    assert "Coin" in (await _campo_boost(cog, guild)).value

    await repo._pool.execute(
        "UPDATE clans SET guild_boost_exp_expires_at = $2, guild_boost_coin_expires_at = $2 "
        "WHERE id = $1", clan_id, FUTURO,
    )
    campo = await _campo_boost(cog, guild)
    assert "Super" in campo.value and len(campo.value.split("\n")) == 1

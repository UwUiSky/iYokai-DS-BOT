"""
tests/test_premium_posti.py
===========================
CFG-034, CFG-035 (#122): posti premium legati a una persona (`core/premium_posti_service.py`), come li legge
`guild_has_premium_access` e come li mostrano `/admin-bot premium stato|assegna|togli-posto`.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core import premium_posti_service as pp
from core.premium import guild_has_premium_access


@pytest.fixture
async def db_pronto(clean_db, monkeypatch):
    import core.database as database_module

    from core import premium as premium_module

    class _Config:
        PREMIUM_ALPHA_UNLOCK_ALL = False

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(premium_module, "config", _Config())
    for g in (1001, 1002, 1003):
        await database_module.db.ensure_guild_exists(g)
    return clean_db


async def _ripristina_attesa(pool, user_id):
    await pool.execute("UPDATE premium_posti_utente SET ultimo_cambio = now() - interval '2 hours' WHERE user_id = $1", user_id)


async def test_senza_posti_non_si_assegna_niente(db_pronto):
    assert await pp.assegna(7, 1001) is pp.Esito.NESSUN_ABBONAMENTO
    assert not await pp.posto_attivo(1001)


async def test_assegna_rispetta_tetto_attesa_e_un_solo_posto_per_server(db_pronto):
    await pp.concedi_posti(7, 2, 30, concesso_da=1)
    assert await pp.assegna(7, 1001) is pp.Esito.FATTO
    assert await pp.assegna(7, 1001) is pp.Esito.GIA_SUO
    assert await pp.assegna(7, 1002) is pp.Esito.DA_ATTENDERE  # un cambio all'ora
    await _ripristina_attesa(db_pronto, 7)
    assert await pp.assegna(8, 1002) is pp.Esito.NESSUN_ABBONAMENTO
    await pp.concedi_posti(8, 1, None, concesso_da=1)
    assert await pp.assegna(8, 1001) is pp.Esito.OCCUPATO  # il posto di un altro non si ruba
    assert await pp.assegna(7, 1002) is pp.Esito.FATTO
    await _ripristina_attesa(db_pronto, 7)
    assert await pp.assegna(7, 1003) is pp.Esito.NESSUN_POSTO_LIBERO  # 2 posti, 2 usati
    stato = await pp.stato_utente(7)
    assert (stato.posti, stato.usati, stato.liberi, set(stato.server)) == (2, 2, 0, {1001, 1002})


async def test_il_premium_del_server_viene_dal_posto_e_scade_con_l_abbonamento(db_pronto):
    assert not await guild_has_premium_access(1001, "aspetto")
    await pp.concedi_posti(7, 1, 30, concesso_da=1)
    await pp.assegna(7, 1001)
    assert await guild_has_premium_access(1001, "aspetto")
    assert not await guild_has_premium_access(1002, "aspetto")  # un altro server no
    assert await pp.posto_del_server(1001) == 7
    await db_pronto.execute("UPDATE premium_posti_utente SET scade_il = now() - interval '1 minute' WHERE user_id = 7")
    assert not await guild_has_premium_access(1001, "aspetto")  # scaduto: non vale, senza bisogno di un job
    assert await pp.posto_del_server(1001) is None
    assert await pp.stato_utente(7) is None
    assert await pp.assegna(7, 1002) is pp.Esito.NESSUN_ABBONAMENTO


async def test_togli_solo_il_proprio_posto_e_libera_il_server(db_pronto):
    await pp.concedi_posti(7, 1, None, concesso_da=1)
    await pp.concedi_posti(8, 1, None, concesso_da=1)
    await pp.assegna(7, 1001)
    assert await pp.togli(8, 1001) is pp.Esito.NON_SUO  # il posto di un altro non si toglie
    assert await pp.posto_attivo(1001)
    assert await pp.togli(7, 1001) is pp.Esito.FATTO
    assert not await pp.posto_attivo(1001)
    assert await pp.togli(7, 1001) is pp.Esito.NON_SUO
    assert await pp.assegna(7, 1002) is pp.Esito.DA_ATTENDERE  # togliere conta come cambio


async def test_ridurre_i_posti_toglie_i_server_assegnati_per_ultimi(db_pronto):
    await pp.concedi_posti(7, 3, None, concesso_da=1)
    for g in (1001, 1002, 1003):
        await _ripristina_attesa(db_pronto, 7)
        assert await pp.assegna(7, g) is pp.Esito.FATTO
        await db_pronto.execute(
            "UPDATE premium_posti_server SET assegnato_il = now() + make_interval(secs => $2) WHERE guild_id = $1", g, g - 1000
        )
    await pp.concedi_posti(7, 1, None, concesso_da=1)
    assert [await pp.posto_attivo(g) for g in (1001, 1002, 1003)] == [True, False, False]
    await pp.concedi_posti(7, 0, None, concesso_da=1)  # 0 = tutti tolti
    assert not await pp.posto_attivo(1001) and await pp.stato_utente(7) is None


async def test_valori_non_validi_sono_rifiutati_prima_di_scrivere(db_pronto):
    for brutti in ((7, 11, 30), (7, -1, 30), (7, True, 30), (7, 1, 31), (0, 1, 30), (True, 1, 30), ("7", 1, 30)):
        with pytest.raises(pp.PostoNonValido):
            await pp.concedi_posti(*brutti, concesso_da=1)
    assert await db_pronto.fetchval("SELECT count(*) FROM premium_posti_utente") == 0


async def test_due_assegnazioni_insieme_non_superano_i_posti(db_pronto):
    import asyncio

    await pp.concedi_posti(7, 1, None, concesso_da=1)
    esiti = await asyncio.gather(pp.assegna(7, 1001), pp.assegna(7, 1002), pp.assegna(7, 1003))
    assert sorted(e.value for e in esiti).count("fatto") == 1
    assert (await pp.stato_utente(7)).usati == 1


async def test_la_scadenza_concessa_e_nel_futuro(db_pronto):
    scade = await pp.concedi_posti(7, 1, 365, concesso_da=1)
    assert timedelta(days=364) < scade - datetime.now(timezone.utc) <= timedelta(days=365)
    assert await pp.concedi_posti(8, 1, None, concesso_da=1) is None


async def test_i_comandi_mostrano_stato_assegnano_e_tolgono(db_pronto):
    from unittest.mock import AsyncMock, MagicMock

    from cogs.utility.premium_server import PremiumServerCog
    from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

    bot = MagicMock()
    bot.application_id = None
    cog = PremiumServerCog(bot)
    guild = fake_guild(1001)
    i = fake_interaction(guild=guild, user=fake_member(7))
    i.locale = __import__("discord").Locale.italian
    await PremiumServerCog.assegna_posto.callback(cog, i)
    assert "Non hai posti" in i.response.send_message.await_args.args[0]
    await pp.concedi_posti(7, 1, None, concesso_da=1)
    await PremiumServerCog.assegna_posto.callback(cog, i)
    assert "uno dei tuoi posti" in i.response.send_message.await_args.args[0]
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    estraneo = fake_interaction(guild=guild, user=fake_member(9))
    estraneo.locale = i.locale
    await PremiumServerCog.togli_posto.callback(cog, estraneo)
    assert "non ha un tuo posto" in estraneo.response.send_message.await_args.args[0]
    assert await pp.posto_attivo(1001)  # l'estraneo non ha tolto niente
    await PremiumServerCog.togli_posto.callback(cog, i)
    assert not await pp.posto_attivo(1001)

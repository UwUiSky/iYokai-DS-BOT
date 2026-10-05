"""
tests/test_shop_acquisto_atomico.py
===================================
BUG-14 (#23): /shop buy non deve togliere coin senza dare il ruolo, e
due acquisti insieme dello stesso oggetto a ruolo devono pagare una
volta sola. Saldo e acquisti sono letti dal database vero.
Funzioni coperte: SPEC §15.4
"""

import asyncio
from pathlib import Path

import discord
import pytest

import cogs.leveling.leveling as leveling_module
from cogs.leveling.leveling import LevelingCog
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.shop_repo import ShopRepository
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role
from tests.support.moduli import attiva_livelli

GUILD_ID = 100
USER_ID = 1
ROLE_ID = 999
PREZZO = 30


class _RispostaHTTPFinta:
    status = 403
    reason = "Forbidden"


@pytest.fixture
async def ambiente(clean_db, monkeypatch):
    await apri_connessioni(clean_db)
    await attiva_livelli(monkeypatch, clean_db, GUILD_ID)
    shop = ShopRepository(pool_provider=lambda: clean_db)
    livelli = LevelingRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(leveling_module, "shop_repo", shop)
    monkeypatch.setattr(leveling_module, "leveling_repo", livelli)
    cog = LevelingCog(bot=None)
    cog.cog_unload()
    return cog, shop, livelli, clean_db


def _interazione(ruolo_presente: bool = True):
    """Server con un ruolo innocuo sotto quello del bot, e un compratore."""
    bot = fake_member(1000, "Yokai Bot", bot=True)
    bot.top_role = fake_role(1001, "Yokai Bot", position=50)
    server = fake_guild(GUILD_ID, me=bot)
    ruolo = fake_role(ROLE_ID, "VIP", position=1)
    server.get_role.side_effect = lambda role_id: (
        ruolo if ruolo_presente and role_id == ROLE_ID else None
    )
    return fake_interaction(guild=server, user=fake_member(USER_ID))


def _testi(interazione) -> list[str]:
    chiamate = (
        interazione.response.send_message.call_args_list
        + interazione.followup.send.call_args_list
    )
    return [chiamata.args[0] for chiamata in chiamate]


async def _acquisti(pool) -> int:
    return await pool.fetchval("SELECT COUNT(*) FROM shop_purchases")


@pytest.mark.asyncio
async def test_ruolo_non_assegnabile_i_coin_tornano_indietro(ambiente):
    cog, shop, livelli, pool = ambiente
    item_id = await shop.add_item(GUILD_ID, name="VIP", price=PREZZO, role_id=ROLE_ID)
    await livelli.add_coins(GUILD_ID, USER_ID, 100)
    interazione = _interazione()
    interazione.user.add_roles.side_effect = discord.Forbidden(
        _RispostaHTTPFinta(), "niente permessi"
    )

    await cog.shop_buy.callback(cog, interazione, item_id=item_id)

    assert (await livelli.get_totals(GUILD_ID, USER_ID)).coins_total == 100
    assert await _acquisti(pool) == 0
    assert "restituiti" in _testi(interazione)[-1]


@pytest.mark.asyncio
async def test_due_acquisti_insieme_dello_stesso_ruolo_pagano_una_volta(ambiente):
    cog, shop, livelli, pool = ambiente
    item_id = await shop.add_item(GUILD_ID, name="VIP", price=PREZZO, role_id=ROLE_ID)
    await livelli.add_coins(GUILD_ID, USER_ID, 100)
    prima, seconda = _interazione(), _interazione()

    await asyncio.gather(
        cog.shop_buy.callback(cog, prima, item_id=item_id),
        cog.shop_buy.callback(cog, seconda, item_id=item_id),
    )

    assert (await livelli.get_totals(GUILD_ID, USER_ID)).coins_total == 100 - PREZZO
    assert await _acquisti(pool) == 1
    assert prima.user.add_roles.await_count + seconda.user.add_roles.await_count == 1
    risposte = _testi(prima) + _testi(seconda)
    assert sum("Hai acquistato" in testo for testo in risposte) == 1
    assert sum("già acquistato" in testo for testo in risposte) == 1


@pytest.mark.asyncio
async def test_ruolo_cancellato_da_discord_non_si_paga(ambiente):
    cog, shop, livelli, pool = ambiente
    item_id = await shop.add_item(GUILD_ID, name="VIP", price=PREZZO, role_id=ROLE_ID)
    await livelli.add_coins(GUILD_ID, USER_ID, 100)
    interazione = _interazione(ruolo_presente=False)

    await cog.shop_buy.callback(cog, interazione, item_id=item_id)

    assert (await livelli.get_totals(GUILD_ID, USER_ID)).coins_total == 100
    assert await _acquisti(pool) == 0
    assert "non esiste più" in _testi(interazione)[0]


@pytest.mark.asyncio
async def test_saldo_insufficiente_non_lascia_un_acquisto_a_meta(ambiente):
    cog, shop, livelli, pool = ambiente
    item_id = await shop.add_item(GUILD_ID, name="VIP", price=PREZZO, role_id=ROLE_ID)
    await livelli.add_coins(GUILD_ID, USER_ID, PREZZO - 1)
    interazione = _interazione()

    await cog.shop_buy.callback(cog, interazione, item_id=item_id)

    assert await _acquisti(pool) == 0
    assert (await livelli.get_totals(GUILD_ID, USER_ID)).coins_total == PREZZO - 1
    interazione.user.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_oggetto_senza_ruolo_si_puo_comprare_due_volte(ambiente):
    cog, shop, livelli, pool = ambiente
    item_id = await shop.add_item(GUILD_ID, name="Biscotto", price=PREZZO)
    await livelli.add_coins(GUILD_ID, USER_ID, 100)

    await cog.shop_buy.callback(cog, _interazione(), item_id=item_id)
    await cog.shop_buy.callback(cog, _interazione(), item_id=item_id)

    assert (await livelli.get_totals(GUILD_ID, USER_ID)).coins_total == 100 - 2 * PREZZO
    assert await _acquisti(pool) == 2


@pytest.mark.asyncio
async def test_motivo_del_ruolo_tagliato_a_512(ambiente):
    cog, shop, livelli, pool = ambiente
    # Un nome lungo salvato prima che esistesse il limite sul comando.
    item_id = await shop.add_item(GUILD_ID, name="V" * 900, price=PREZZO, role_id=ROLE_ID)
    await livelli.add_coins(GUILD_ID, USER_ID, 100)
    interazione = _interazione()

    await cog.shop_buy.callback(cog, interazione, item_id=item_id)

    motivo = interazione.user.add_roles.await_args.kwargs["reason"]
    assert len(motivo) <= 512
    assert all(len(testo) <= 2000 for testo in _testi(interazione))


@pytest.mark.asyncio
async def test_migrazione_0015_toglie_i_doppioni_e_mette_il_vincolo(clean_db):
    """La migrazione deve funzionare su un database che ha già doppioni."""
    sql = (
        Path(leveling_module.__file__).parents[2]
        / "core" / "migrations" / "0015_shop_purchases_ruolo_unico.sql"
    ).read_text(encoding="utf-8")
    shop = ShopRepository(pool_provider=lambda: clean_db)
    con_ruolo = await shop.add_item(GUILD_ID, name="VIP", price=PREZZO, role_id=ROLE_ID)
    senza_ruolo = await shop.add_item(GUILD_ID, name="Biscotto", price=PREZZO)

    async with clean_db.acquire() as conn:
        transazione = conn.transaction()
        await transazione.start()
        try:
            # Stato di prima della migrazione, con i dati sporchi.
            await conn.execute("DROP INDEX IF EXISTS uq_shop_purchases_ruolo")
            await conn.execute("ALTER TABLE shop_purchases DROP COLUMN IF EXISTS role_id")
            for item_id in (con_ruolo, con_ruolo, senza_ruolo, senza_ruolo):
                await conn.execute(
                    "INSERT INTO shop_purchases (guild_id, user_id, item_id) VALUES ($1, $2, $3)",
                    GUILD_ID, USER_ID, item_id,
                )

            await conn.execute(sql)

            righe = await conn.fetch(
                "SELECT item_id, role_id FROM shop_purchases ORDER BY id"
            )
            assert [(r["item_id"], r["role_id"]) for r in righe] == [
                (con_ruolo, ROLE_ID), (senza_ruolo, None), (senza_ruolo, None),
            ]
            with pytest.raises(Exception, match="uq_shop_purchases_ruolo"):
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO shop_purchases (guild_id, user_id, item_id, role_id) "
                        "VALUES ($1, $2, $3, $4)",
                        GUILD_ID, USER_ID, con_ruolo, ROLE_ID,
                    )
        finally:
            # Lo schema del database di test torna com'era.
            await transazione.rollback()

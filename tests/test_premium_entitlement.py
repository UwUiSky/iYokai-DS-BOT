"""
tests/test_premium_entitlement.py
=================================
NF-22 (#93): abbonamenti Discord (app premium) che sbloccano il premium di un server.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
from discord.ext import commands

import core.premium as premium_module
from core import premium_entitlement_service as servizio
from core.premium_status_logic import format_guild_status_line, righe_stato_server
from core.repositories.entitlement_repo import Entitlement, entitlement_repo
from tests.support.discord_fakes import fake_guild, fake_interaction

pytestmark = pytest.mark.asyncio

ORA = datetime.now(timezone.utc)


def _diritto(ent_id=1, guild_id=500, sku_id=77, ends_at=None, deleted=False, user_id=9):
    return SimpleNamespace(
        id=ent_id, guild_id=guild_id, sku_id=sku_id, user_id=user_id,
        starts_at=ORA - timedelta(days=1), ends_at=ends_at, deleted=deleted,
    )


@pytest.fixture
async def db_pronto(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    return clean_db


def test_da_discord_ignora_utenti_e_sku_diversi():
    assert servizio.da_discord(_diritto(guild_id=None)) is None  # abbonamento di utente
    assert servizio.da_discord(_diritto(sku_id=1), sku_ammesso=77) is None
    voce = servizio.da_discord(_diritto(), sku_ammesso=77)
    assert voce is not None and voce.guild_id == 500 and voce.entitlement_id == 1
    assert servizio.da_discord(_diritto(), sku_ammesso=0) is not None


async def test_evento_registra_aggiorna_e_chiude(db_pronto):
    assert await servizio.registra_evento(_diritto()) is True
    assert await servizio.server_ha_abbonamento(500)
    assert await servizio.registra_evento(_diritto(guild_id=None)) is False
    await servizio.registra_evento(_diritto(ends_at=ORA - timedelta(hours=1)))  # update: scaduto
    assert not await servizio.server_ha_abbonamento(500)
    await servizio.registra_evento(_diritto(ends_at=None))
    assert await servizio.server_ha_abbonamento(500)
    await servizio.registra_evento(_diritto(), eliminato=True)  # delete
    assert not await servizio.server_ha_abbonamento(500)
    assert [v.deleted for v in await servizio.abbonamenti_del_server(500)] == [True]


class _BotFinto:
    def __init__(self, diritti):
        self._diritti = diritti

    def entitlements(self, **kw):
        assert kw.get("exclude_ended") is True

        async def genera():
            for d in self._diritti:
                yield d

        return genera()


async def test_allineamento_all_avvio_aggiunge_e_chiude_i_persi(db_pronto):
    await servizio.registra_evento(_diritto(ent_id=1, guild_id=500))  # lo perderemo mentre il bot è spento
    bot = _BotFinto([_diritto(ent_id=2, guild_id=501)])
    assert await servizio.allinea_con_discord(bot) == 1
    assert not await servizio.server_ha_abbonamento(500)
    assert await servizio.server_ha_abbonamento(501)


async def test_allineamento_interrotto_non_chiude_niente(db_pronto):
    await servizio.registra_evento(_diritto(ent_id=1, guild_id=500))

    class _Rotto:
        def entitlements(self, **kw):
            async def genera():
                yield _diritto(ent_id=3, guild_id=502)
                raise RuntimeError("rete")

            return genera()

    with pytest.raises(RuntimeError):
        await servizio.allinea_con_discord(_Rotto())
    assert await servizio.server_ha_abbonamento(500)


async def test_l_abbonamento_discord_sblocca_tutti_i_moduli(db_pronto, monkeypatch):
    class _Config:
        PREMIUM_ALPHA_UNLOCK_ALL = False
        MAIN_GUILD_ID = 999

    monkeypatch.setattr(premium_module, "config", _Config())
    assert not await premium_module.guild_has_premium_access(500, "spam_trap")
    await servizio.registra_evento(_diritto())
    assert await premium_module.guild_has_premium_access(500, "spam_trap")
    assert await premium_module.guild_has_premium_access(500, "anti_raid")
    assert not await premium_module.guild_has_premium_access(501, "spam_trap")
    assert (await premium_module.get_guild_premium_breakdown(500))["discord_attivo"] is True


def test_righe_di_stato():
    righe = righe_stato_server({"discord_attivo": True, "whitelisted": False}, ["`spam_trap` fino al 2027-01-01"])
    assert any("Discord" in r for r in righe) and any("spam_trap" in r for r in righe)
    assert righe_stato_server({}, []) == []
    assert "abbonamento Discord" in format_guild_status_line(1, "x", False, False, False, 0, discord_attivo=True)


async def test_il_cog_registra_gli_eventi_e_risponde_a_stato(db_pronto, monkeypatch):
    from cogs.utility.premium_server import PremiumServerCog, url_negozio

    assert url_negozio(None) is None and url_negozio(5).endswith("/5/store")
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = PremiumServerCog(bot)
    await cog.on_entitlement_create(_diritto())
    assert await servizio.server_ha_abbonamento(500)
    await cog.on_entitlement_delete(_diritto())
    assert not await servizio.server_ha_abbonamento(500)
    await cog.on_entitlement_create(SimpleNamespace())  # evento strano: nessuna eccezione

    class _Config:
        PREMIUM_ALPHA_UNLOCK_ALL = False
        MAIN_GUILD_ID = 999

    monkeypatch.setattr(premium_module, "config", _Config())
    import cogs.utility.premium_server as modulo

    monkeypatch.setattr(modulo, "config", _Config())
    await cog.on_entitlement_create(_diritto())
    i = fake_interaction(guild=fake_guild(500))
    i.locale = discord.Locale.italian
    await cog.stato.callback(cog, i)
    testo = i.followup.send.call_args.kwargs["embed"].description
    assert "Abbonamento Discord attivo" in testo

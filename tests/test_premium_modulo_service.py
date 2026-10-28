"""
tests/test_premium_modulo_service.py
====================================
Sblocco di un modulo premium con 1.000.000 di coin dalla cassa (SPEC §3.1, #93): contro PostgreSQL vero.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.premium import PremiumModule, registry
from core.premium_modulo_service import EsitoSblocco, sblocca_modulo_con_cassa
from core.premium_pricing_logic import COSTO_MODULO_IN_COIN, GIORNI_MODULO_IN_COIN
from core.repositories.guild_chest_repo import REASON_WEEKLY_PERSONAL_DECAY, guild_chest_repo
from core.repositories.module_subscription_repo import module_subscription_repo

ADESSO = datetime(2026, 10, 1, tzinfo=timezone.utc)
GUILD = 4100


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch, clean_db, reset_premium_registry):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    registry.register(PremiumModule(category="security", name="mod_premium", display_name="P", description="p"))
    registry.register(PremiumModule(category="utility", name="mod_libero", display_name="L", description="l"))
    registry.set_module_premium("mod_premium", True)
    yield
    registry.set_module_premium("mod_premium", False)


async def test_con_la_cassa_piena_sblocca_solo_quel_modulo_e_addebita(clean_db):
    await guild_chest_repo.deposit(GUILD, 1_500_000, REASON_WEEKLY_PERSONAL_DECAY)

    r = await sblocca_modulo_con_cassa(GUILD, "mod_premium", 7, ADESSO)

    assert r.esito is EsitoSblocco.SBLOCCATO
    assert r.scade_il == ADESSO + timedelta(days=GIORNI_MODULO_IN_COIN)
    assert await guild_chest_repo.get_balance(GUILD) == 1_500_000 - COSTO_MODULO_IN_COIN
    assert await module_subscription_repo.is_active(GUILD, "mod_premium", ADESSO)
    assert not await module_subscription_repo.is_active(GUILD, "altro", ADESSO)


async def test_cassa_insufficiente_non_scrive_niente(clean_db):
    await guild_chest_repo.deposit(GUILD, COSTO_MODULO_IN_COIN - 1, REASON_WEEKLY_PERSONAL_DECAY)

    r = await sblocca_modulo_con_cassa(GUILD, "mod_premium", 7, ADESSO)

    assert r.esito is EsitoSblocco.CASSA_INSUFFICIENTE
    assert await guild_chest_repo.get_balance(GUILD) == COSTO_MODULO_IN_COIN - 1
    assert not await module_subscription_repo.is_active(GUILD, "mod_premium", ADESSO)


async def test_modulo_non_premium_o_sconosciuto_non_tocca_la_cassa(clean_db):
    await guild_chest_repo.deposit(GUILD, COSTO_MODULO_IN_COIN, REASON_WEEKLY_PERSONAL_DECAY)

    assert (await sblocca_modulo_con_cassa(GUILD, "mod_libero", 7, ADESSO)).esito is EsitoSblocco.NON_PREMIUM
    assert (await sblocca_modulo_con_cassa(GUILD, "non_esiste", 7, ADESSO)).esito is EsitoSblocco.MODULO_SCONOSCIUTO
    assert await guild_chest_repo.get_balance(GUILD) == COSTO_MODULO_IN_COIN


async def test_un_secondo_sblocco_allunga_la_scadenza(clean_db):
    await guild_chest_repo.deposit(GUILD, 2 * COSTO_MODULO_IN_COIN, REASON_WEEKLY_PERSONAL_DECAY)

    await sblocca_modulo_con_cassa(GUILD, "mod_premium", 7, ADESSO)
    r = await sblocca_modulo_con_cassa(GUILD, "mod_premium", 7, ADESSO)

    assert r.scade_il == ADESSO + timedelta(days=2 * GIORNI_MODULO_IN_COIN)
    assert await guild_chest_repo.get_balance(GUILD) == 0


async def test_se_lo_sblocco_fallisce_l_addebito_si_annulla(clean_db, monkeypatch):
    await guild_chest_repo.deposit(GUILD, COSTO_MODULO_IN_COIN, REASON_WEEKLY_PERSONAL_DECAY)

    async def rotto(*a, **k):
        raise RuntimeError("scrittura fallita")

    monkeypatch.setattr(module_subscription_repo, "_grant", rotto)
    with pytest.raises(RuntimeError):
        await sblocca_modulo_con_cassa(GUILD, "mod_premium", 7, ADESSO)

    assert await guild_chest_repo.get_balance(GUILD) == COSTO_MODULO_IN_COIN


async def test_il_comando_chiede_conferma_e_il_bottone_spende(clean_db):
    from unittest.mock import AsyncMock, MagicMock

    from cogs.utility.premium_server import ConfermaSblocco, PremiumServerCog
    from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

    await clean_db.execute("INSERT INTO guild_config (guild_id) VALUES ($1) ON CONFLICT DO NOTHING", GUILD)
    await guild_chest_repo.deposit(GUILD, COSTO_MODULO_IN_COIN, REASON_WEEKLY_PERSONAL_DECAY)
    interazione = fake_interaction(guild=fake_guild(GUILD), user=fake_member(user_id=7))
    cog = PremiumServerCog(MagicMock())

    await cog.sblocca.callback(cog, interazione, "mod_premium")

    invio = interazione.response.send_message.await_args
    assert "1.000.000" in invio.args[0] and isinstance(invio.kwargs["view"], ConfermaSblocco)
    assert await guild_chest_repo.get_balance(GUILD) == COSTO_MODULO_IN_COIN  # ancora niente speso

    clic = fake_interaction(guild=fake_guild(GUILD), user=fake_member(user_id=7))
    await invio.kwargs["view"].conferma.callback(clic)

    assert "sbloccato fino al" in clic.response.edit_message.await_args.kwargs["content"]
    assert await guild_chest_repo.get_balance(GUILD) == 0


async def test_due_clic_sulla_stessa_conferma_spendono_una_volta(clean_db):
    """La vista controlla la lista nera (un await) prima del clic: due clic arrivano entrambi al bottone."""
    import asyncio

    from cogs.utility.premium_server import ConfermaSblocco
    from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

    await guild_chest_repo.deposit(GUILD, 2 * COSTO_MODULO_IN_COIN, REASON_WEEKLY_PERSONAL_DECAY)
    vista = ConfermaSblocco(GUILD, 7, "mod_premium")
    clic = [fake_interaction(guild=fake_guild(GUILD), user=fake_member(user_id=7)) for _ in range(2)]

    await asyncio.gather(*(vista.conferma.callback(c) for c in clic))

    assert await guild_chest_repo.get_balance(GUILD) == COSTO_MODULO_IN_COIN
    risposti = [c for c in clic if c.response.edit_message.await_count or c.response.defer.await_count]
    assert len(risposti) == 2  # anche il secondo clic riceve una risposta


async def test_annulla_dopo_la_conferma_non_dice_annullato(clean_db):
    import asyncio

    from cogs.utility.premium_server import ConfermaSblocco
    from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

    await guild_chest_repo.deposit(GUILD, COSTO_MODULO_IN_COIN, REASON_WEEKLY_PERSONAL_DECAY)
    vista = ConfermaSblocco(GUILD, 7, "mod_premium")
    si, no = (fake_interaction(guild=fake_guild(GUILD), user=fake_member(user_id=7)) for _ in range(2))

    await asyncio.gather(vista.conferma.callback(si), vista.annulla.callback(no))

    assert await guild_chest_repo.get_balance(GUILD) == 0
    no.response.edit_message.assert_not_awaited()
    no.response.defer.assert_awaited_once()


async def test_l_autocomplete_elenca_solo_i_moduli_premium(clean_db):
    from unittest.mock import AsyncMock, MagicMock, patch

    from cogs.utility.premium_server import PremiumServerCog
    from tests.support.discord_fakes import fake_interaction

    cog = PremiumServerCog(MagicMock())
    with patch("core.command_access.puo_usare", AsyncMock(return_value=True)):
        scelte = await cog._moduli_premium(fake_interaction(), "")
    assert [c.value for c in scelte] == ["mod_premium"]

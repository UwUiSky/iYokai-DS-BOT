"""
tests/test_premium_codici.py
============================
CFG-038 (#122): codici premium da riscattare, a tempo o permanenti.
"""

from datetime import datetime, timezone

import pytest

import core.premium as premium_module
from core import premium_code_service as servizio
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def db_pronto(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    servizio._sbagliati.clear()

    class _Config:
        PREMIUM_ALPHA_UNLOCK_ALL = False
        MAIN_GUILD_ID = 999

    monkeypatch.setattr(premium_module, "config", _Config())
    return clean_db


def test_il_codice_ha_la_forma_giusta_e_si_normalizza():
    codice = servizio.nuovo_codice()
    assert codice.startswith("YOKAI-") and len(codice) == len("YOKAI-AAAA-BBBB-CCCC")
    assert servizio.impronta(codice) == servizio.impronta(" " + codice.lower() + " ")
    assert servizio.impronta("YOKAI-AAAA-BBBB-CCCC") != servizio.impronta("YOKAI-AAAA-BBBB-CCCD")
    assert len({servizio.nuovo_codice() for _ in range(200)}) == 200


async def test_il_chiaro_non_finisce_nel_database(db_pronto):
    codice = await servizio.crea_codice(None, 30, created_by=1)
    righe = await db_pronto.fetch("SELECT * FROM premium_codes")
    assert len(righe) == 1 and codice not in str(dict(righe[0])) and righe[0]["code_hint"] == codice[-4:]
    with pytest.raises(ValueError):
        await servizio.crea_codice(None, 0, created_by=1)


async def test_codice_per_modulo_si_riscatta_una_volta_sola(db_pronto):
    codice = await servizio.crea_codice("spam_trap", 30, created_by=1)
    modulo, scadenza = await servizio.riscatta_codice(codice.lower(), user_id=7, guild_id=500)
    assert modulo == "spam_trap" and scadenza > datetime.now(timezone.utc)
    assert await premium_module.guild_has_premium_access(500, "spam_trap")
    assert not await premium_module.guild_has_premium_access(500, "anti_raid")  # solo quel modulo
    assert await servizio.riscatta_codice(codice, user_id=8, guild_id=501) is None  # già usato
    assert not await premium_module.guild_has_premium_access(501, "spam_trap")


async def test_codice_per_tutti_i_moduli_e_permanente(db_pronto):
    codice = await servizio.crea_codice(None, servizio.GIORNI_PERMANENTE, created_by=1)
    modulo, scadenza = await servizio.riscatta_codice(codice, user_id=7, guild_id=500)
    assert modulo is None and scadenza.year >= datetime.now(timezone.utc).year + 99
    assert await premium_module.guild_has_premium_access(500, "spam_trap")
    assert await premium_module.guild_has_premium_access(500, "anti_raid")


async def test_sblocco_fallito_rimette_il_codice_a_disposizione(db_pronto, monkeypatch):
    codice = await servizio.crea_codice("spam_trap", 30, created_by=1)

    async def rotto(*a, **k):
        raise RuntimeError("database giù")

    originale = servizio.applica_sblocco
    monkeypatch.setattr(servizio, "applica_sblocco", rotto)
    with pytest.raises(RuntimeError):
        await servizio.riscatta_codice(codice, 7, 500)
    monkeypatch.setattr(servizio, "applica_sblocco", originale)
    assert await servizio.riscatta_codice(codice, 7, 500) is not None


async def test_troppi_tentativi_sbagliati_bloccano_poi_passa_il_tempo(db_pronto):
    for n in range(servizio.MAX_TENTATIVI_SBAGLIATI):
        assert await servizio.riscatta_codice("YOKAI-XXXX-XXXX-XXXX", 7, 500, adesso=100.0 + n) is None
    with pytest.raises(servizio.TroppiTentativi):
        await servizio.riscatta_codice("YOKAI-XXXX-XXXX-XXXX", 7, 500, adesso=110.0)
    codice = await servizio.crea_codice(None, 30, created_by=1)
    assert await servizio.riscatta_codice(codice, 7, 500, adesso=100.0 + servizio.FINESTRA_SECONDI + 5) is not None
    # un altro utente non è toccato
    assert await servizio.riscatta_codice("YOKAI-XXXX-XXXX-XXXX", 8, 500, adesso=110.0) is None


async def test_comandi_owner_e_admin(db_pronto):
    from types import SimpleNamespace

    from discord import app_commands
    from discord.ext import commands
    import discord

    from cogs.utility.owner_premium import OwnerPremiumCog
    from cogs.utility.premium_server import PremiumServerCog

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    owner = OwnerPremiumCog(bot)
    i = fake_interaction(guild=fake_guild(1), user=fake_member(123))
    permanente = app_commands.Choice(name="Permanente", value="permanent")
    await owner.premium_grant.callback(owner, i, module_name="tutti", duration=permanente)  # niente server: codice
    testo = i.response.send_message.call_args.args[0]
    codice = testo.split("`")[1]
    assert codice.startswith("YOKAI-")

    admin = PremiumServerCog(bot)
    i = fake_interaction(guild=fake_guild(500), user=fake_member(7))
    i.locale = discord.Locale.italian
    await admin.riscatta.callback(admin, i, "YOKAI-NOPE-NOPE-NOPE")
    assert "non esiste" in i.response.send_message.call_args.args[0]
    i = fake_interaction(guild=fake_guild(500), user=fake_member(7))
    i.locale = discord.Locale.italian
    await admin.riscatta.callback(admin, i, codice)
    assert "tutti i moduli" in i.response.send_message.call_args.args[0]
    assert await premium_module.guild_has_premium_access(500, "spam_trap")

    # concessione diretta a un server, con «tutti»
    i = fake_interaction(guild=fake_guild(1), user=fake_member(123))
    await owner.premium_grant.callback(owner, i, module_name="tutti", duration=permanente, guild_id="600")
    assert await premium_module.guild_has_premium_access(600, "anti_raid")

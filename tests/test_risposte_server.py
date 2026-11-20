"""
tests/test_risposte_server.py
=============================
CFG-013, CFG-014, CFG-033 (#122): risposte sempre effimere, cancellazione automatica e colori degli embed
scelti dal server (`core/risposte_server.py`).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.interactions import InteractionResponse

from core import risposte_server as rs


def test_colore_da_testo_accetta_solo_esadecimale_di_sei_cifre():
    assert rs.colore_da_testo("#C24A3A") == 0xC24A3A
    assert rs.colore_da_testo("c24a3a") == 0xC24A3A
    for brutto in ("", "#12", "#GGGGGG", "#1234567", "rosso", "0x112233", "#11 223", "#１２３４５６"):
        with pytest.raises(rs.RispostaNonValida):
            rs.colore_da_testo(brutto)


def test_ricolora_solo_i_verdi_e_i_rossi_di_base():
    ok, err = discord.Color.green().value, discord.Color.red().value
    verde, rosso, blu = discord.Embed(color=ok), discord.Embed(color=err), discord.Embed(color=0x3366FF)
    rs.ricolora([verde, rosso, blu, discord.Embed()], 0x112233, 0x445566)
    assert verde.colour.value == 0x112233
    assert rosso.colour.value == 0x445566
    assert blu.colour.value == 0x3366FF


async def test_impostazioni_seguono_lo_schema_del_server():
    from cogs.utility.config_history import SETTINGS_SCHEMA

    for chiave in rs.TUTTE_LE_CHIAVI:
        assert chiave in SETTINGS_SCHEMA


@pytest.fixture
async def db_pronto(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._settings_cache.clear()
    await database_module.db.ensure_guild_exists(910)
    return database_module.db


async def test_leggi_di_base_e_dopo_il_cambio(db_pronto):
    base = await rs.leggi_risposte(910)
    assert (base.effimere, base.cancella_secondi, base.colore_successo, base.colore_errore) == (False, 0, None, None)
    esito = await rs.imposta_risposte(910, effimere=True, cancella_secondi=30, changed_by=5, premium=False)
    assert esito == ["risposte_effimere", "risposte_cancella_secondi"]
    letto = await rs.leggi_risposte(910)
    assert letto.effimere is True and letto.cancella_secondi == 30


async def test_cancella_oltre_il_tetto_e_rifiutato_e_non_scrive(db_pronto):
    for brutto in (-1, 601, True, "10"):
        with pytest.raises(rs.RispostaNonValida):
            await rs.imposta_risposte(910, cancella_secondi=brutto, changed_by=5, premium=False)
    assert (await rs.leggi_risposte(910)).cancella_secondi == 0


async def test_i_colori_sono_premium_e_la_verifica_sta_nel_punto_unico(db_pronto):
    with pytest.raises(rs.RichiedePremium):
        await rs.imposta_risposte(910, colore_successo="#112233", changed_by=5, premium=False)
    assert (await rs.leggi_risposte(910)).colore_successo is None
    await rs.imposta_risposte(910, colore_successo="#112233", colore_errore="#445566", changed_by=5, premium=True)
    letto = await rs.leggi_risposte(910)
    assert (letto.colore_successo, letto.colore_errore) == (0x112233, 0x445566)
    # il colore si toglie anche senza premium (scaduto): None = torna di base
    await rs.imposta_risposte(910, colore_successo=None, changed_by=5, premium=False)
    assert (await rs.leggi_risposte(910)).colore_successo is None


async def test_ogni_cambio_va_nello_storico(db_pronto):
    await rs.imposta_risposte(910, effimere=True, changed_by=77, premium=False)
    righe = await db_pronto.pool.fetch("SELECT changed_by FROM guild_config_history WHERE guild_id = 910")
    assert [r["changed_by"] for r in righe] == [77]


async def test_risposta_effimera_forza_defer_e_invio(monkeypatch):
    defer = AsyncMock()
    invio = AsyncMock()
    monkeypatch.setattr(InteractionResponse, "defer", defer)
    monkeypatch.setattr(InteractionResponse, "send_message", invio)
    interazione = MagicMock()
    risposta = rs.RispostaServer(interazione, rs.Risposte(effimere=True))
    await risposta.defer()
    await risposta.send_message("ciao", ephemeral=False)
    assert defer.await_args.kwargs["ephemeral"] is True
    assert invio.await_args.kwargs["ephemeral"] is True


async def test_cancella_dopo_n_secondi_solo_se_pubblica(monkeypatch):
    invio = AsyncMock()
    monkeypatch.setattr(InteractionResponse, "send_message", invio)
    monkeypatch.setattr(rs, "_attendi", AsyncMock())
    interazione = MagicMock()
    interazione.delete_original_response = AsyncMock()
    risposta = rs.RispostaServer(interazione, rs.Risposte(cancella_secondi=5))
    await risposta.send_message("ciao")
    await asyncio.gather(*list(rs._attivi))
    interazione.delete_original_response.assert_awaited_once()

    interazione2 = MagicMock()
    interazione2.delete_original_response = AsyncMock()
    privata = rs.RispostaServer(interazione2, rs.Risposte(cancella_secondi=5))
    await privata.send_message("ciao", ephemeral=True)
    await asyncio.gather(*list(rs._attivi))
    interazione2.delete_original_response.assert_not_awaited()


async def test_cancella_non_si_accumula_oltre_il_tetto(monkeypatch):
    monkeypatch.setattr(InteractionResponse, "send_message", AsyncMock())
    monkeypatch.setattr(rs, "MAX_CANCELLAZIONI_PENDENTI", 0)
    interazione = MagicMock()
    interazione.delete_original_response = AsyncMock()
    await rs.RispostaServer(interazione, rs.Risposte(cancella_secondi=5)).send_message("x")
    assert not rs._attivi


async def test_il_colore_si_applica_agli_embed_inviati(monkeypatch):
    invio = AsyncMock()
    monkeypatch.setattr(InteractionResponse, "send_message", invio)
    risposta = rs.RispostaServer(MagicMock(), rs.Risposte(colore_successo=0xABCDEF))
    embed = discord.Embed(color=discord.Color.green())
    await risposta.send_message(embed=embed)
    assert embed.colour.value == 0xABCDEF


async def test_senza_impostazioni_non_cambia_l_interazione():
    interazione = MagicMock()
    interazione._cs_response = "originale"
    assert rs.applica_a_interazione(interazione, rs.Risposte()) is False
    assert interazione._cs_response == "originale"


async def test_il_controllo_dell_albero_applica_le_regole_alla_risposta(db_pronto, monkeypatch):
    from discord.ext import commands

    from core.blacklist_tree import BlacklistAwareCommandTree
    from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

    monkeypatch.setattr("core.blacklist_tree.blacklist_repo.is_user_blacklisted", AsyncMock(return_value=False))
    monkeypatch.setattr("core.blacklist_tree.blacklist_repo.is_guild_blacklisted", AsyncMock(return_value=False))
    await rs.imposta_risposte(910, effimere=True, changed_by=1, premium=False)
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), tree_cls=BlacklistAwareCommandTree)
    interazione = fake_interaction(guild=fake_guild(910), user=fake_member(40))
    interazione.guild_id = 910
    interazione.type = discord.InteractionType.application_command
    interazione.command = type("C", (), {"qualified_name": "fun dado"})()
    interazione.locale = discord.Locale.italian
    interazione.is_guild_integration = lambda: True
    interazione.channel_id = 10
    assert await bot.tree.interaction_check(interazione) is True
    assert isinstance(interazione._cs_response, rs.RispostaServer)


async def test_il_comando_risposte_cambia_e_mostra(db_pronto, monkeypatch):
    from cogs.utility.config_risposte import ConfigRisposteCog
    from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

    cog = ConfigRisposteCog(MagicMock())
    guild = fake_guild(910)
    i = fake_interaction(guild=guild, user=fake_member(5))
    i.locale = discord.Locale.italian
    i.guild_id = 910
    monkeypatch.setattr("cogs.utility.config_risposte.guild_has_premium_access", AsyncMock(return_value=False))
    callback = ConfigRisposteCog.risposte.callback
    await callback(cog, i, solo_private=True, cancella_dopo=20)
    assert (await rs.leggi_risposte(910)).effimere is True
    await callback(cog, i, colore_successo="#112233")
    assert "premium" in i.response.send_message.await_args.args[0]
    assert (await rs.leggi_risposte(910)).colore_successo is None
    await callback(cog, i, colore_successo="rosso")
    monkeypatch.setattr("cogs.utility.config_risposte.guild_has_premium_access", AsyncMock(return_value=True))
    await callback(cog, i, colore_successo="rosso")
    assert "#RRGGBB" in i.response.send_message.await_args.args[0]
    await callback(cog, i)
    assert "20" in i.response.send_message.await_args.args[0]


async def test_i_messaggi_successivi_seguono_le_regole_del_server(monkeypatch):
    invio = AsyncMock()
    monkeypatch.setattr(discord.Webhook, "send", invio)
    interazione = MagicMock()
    interazione.application_id, interazione.token = 123, "token-finto"
    assert rs.applica_a_interazione(interazione, rs.Risposte(effimere=True, colore_errore=0x010203)) is True
    seguito = interazione._cs_followup
    assert isinstance(seguito, rs.FollowupServer)
    embed = discord.Embed(color=discord.Color.red())
    await seguito.send("ciao", ephemeral=False, embed=embed)
    assert invio.await_args.kwargs["ephemeral"] is True
    assert embed.colour.value == 0x010203

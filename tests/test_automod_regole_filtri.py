"""
tests/test_automod_regole_filtri.py
===================================
I filtri di oggi passano dalle regole del server: condizioni (canali, ruoli, età, thread, autori), regola spenta,
esenzioni globali, il bot che non giudica mai sé stesso.
Funzioni coperte: SPEC §6 (AMD-029, 032-040), D63
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import create_autospec

import discord
import pytest

import cogs.automod.automod as modulo_automod
import cogs.moderation._shared as modulo_shared
from core import automod_regole_service as servizio
from core.automod_rate_tracker import AutomodRateTracker
from core.automod_regole_logic import Condizioni, Regola, azioni_dai_nomi_vecchi
from core.database import Database
from core.repositories.automod_advanced_repo import automod_advanced_repo
from core.repositories.automod_regole_repo import automod_regole_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_message, fake_role, fake_text_channel
from tests.support.router_fakes import router_senza_scelte

GUILD_ID = 666
URLATO = "COMPRATE SUBITO QUESTO PRODOTTO"


@pytest.fixture
def cog(clean_db, monkeypatch):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    db_finto.get_guild_setting.return_value = None
    monkeypatch.setattr(modulo_shared, "db", db_finto)
    monkeypatch.setattr(modulo_automod, "db", db_finto)
    monkeypatch.setattr(automod_advanced_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(automod_regole_repo, "_pool_provider", lambda: clean_db)
    servizio.svuota_cache()
    router_senza_scelte(monkeypatch)
    monkeypatch.setattr(modulo_automod, "rate_tracker", AutomodRateTracker())
    return modulo_automod.AutomodCog(bot=None)


async def _caps_attivo(cog):
    await cog.anti_caps.callback(cog, fake_interaction(guild=fake_guild(guild_id=GUILD_ID)), True, 70, 10)


def _msg(testo=URLATO, *, canale=111, ruoli=None, autore=4242, bot=False, creato=None, entrato=None):
    server = fake_guild(guild_id=GUILD_ID)
    membro = fake_member(user_id=autore, roles=ruoli, bot=bot)
    membro.guild = server
    if creato is not None:
        membro.created_at = creato
    if entrato is not None:
        membro.joined_at = entrato
    m = fake_message(author=membro, guild=server, content=testo)
    m.channel = fake_text_channel(channel_id=canale)
    m.mentions, m.role_mentions, m.mention_everyone, m.attachments, m.stickers = [], [], False, [], []
    return m


async def _regola(condizioni=None, attiva=True, azioni=("delete",)):
    await servizio.salva(
        GUILD_ID,
        Regola(chiave="anti_caps", tipo="filtro", nome="anti_caps", attiva=attiva,
               condizioni=condizioni or Condizioni(), azioni=azioni_dai_nomi_vecchi(azioni, 600)),
        1,
    )


async def test_senza_riga_il_filtro_funziona_come_prima(cog):
    await _caps_attivo(cog)
    m = _msg()
    await cog.on_message(m)
    m.delete.assert_awaited_once()


async def test_regola_spenta_non_scatta(cog):
    await _caps_attivo(cog)
    await _regola(attiva=False)
    m = _msg()
    await cog.on_message(m)
    m.delete.assert_not_awaited()


async def test_canale_escluso_e_canale_incluso(cog):
    await _caps_attivo(cog)
    await _regola(Condizioni(canali_esclusi=(111,)))
    escluso, altro = _msg(canale=111), _msg(canale=222)
    await cog.on_message(escluso)
    await cog.on_message(altro)
    escluso.delete.assert_not_awaited()
    altro.delete.assert_awaited_once()
    await _regola(Condizioni(canali_inclusi=(111,)))
    dentro, fuori = _msg(canale=111), _msg(canale=222)
    await cog.on_message(dentro)
    await cog.on_message(fuori)
    dentro.delete.assert_awaited_once()
    fuori.delete.assert_not_awaited()


async def test_solo_chi_non_ha_ruoli(cog):
    await _caps_attivo(cog)
    await _regola(Condizioni(senza_ruoli=True))
    con_ruolo = _msg(ruoli=[fake_role(role_id=5)])
    senza = _msg()
    await cog.on_message(con_ruolo)
    await cog.on_message(senza)
    con_ruolo.delete.assert_not_awaited()
    senza.delete.assert_awaited_once()


async def test_account_giovani_e_nel_server_da_poco(cog):
    await _caps_attivo(cog)
    adesso = datetime.now(timezone.utc)
    await _regola(Condizioni(eta_account_giorni=(None, 7)))
    nuovo, vecchio = _msg(creato=adesso - timedelta(days=2)), _msg(creato=adesso - timedelta(days=400))
    await cog.on_message(nuovo)
    await cog.on_message(vecchio)
    nuovo.delete.assert_awaited_once()
    vecchio.delete.assert_not_awaited()
    await _regola(Condizioni(nel_server_giorni=(None, 3)))
    appena, da_tempo, ignoto = (_msg(entrato=adesso - timedelta(days=1)), _msg(entrato=adesso - timedelta(days=90)), _msg())
    for m in (appena, da_tempo, ignoto):
        await cog.on_message(m)
    appena.delete.assert_awaited_once()
    da_tempo.delete.assert_not_awaited()
    ignoto.delete.assert_not_awaited()  # data d'ingresso ignota: nel dubbio non si punisce


async def test_esenzioni_globali_si_possono_togliere_per_regola(cog):
    await _caps_attivo(cog)
    s = await automod_advanced_repo.get_settings(GUILD_ID)
    await automod_advanced_repo.save_settings(modulo_automod._replace_settings(s, exempt_channel_ids=(111,)))
    esente = _msg(canale=111)
    await cog.on_message(esente)
    esente.delete.assert_not_awaited()  # esenzione globale: vale
    await _regola(Condizioni(esenzioni_globali=False))
    await cog.on_message(esente := _msg(canale=111))
    esente.delete.assert_awaited_once()  # questa regola le ignora


async def test_i_bot_si_giudicano_solo_se_la_regola_lo_dice_mai_il_proprio(cog):
    await _caps_attivo(cog)
    bot = _msg(bot=True, autore=31)
    await cog.on_message(bot)
    bot.delete.assert_not_awaited()  # di base solo persone
    await _regola(Condizioni(autori=("persone", "bot")))
    bot2 = _msg(bot=True, autore=31)
    await cog.on_message(bot2)
    bot2.delete.assert_awaited_once()
    # il bot stesso: mai, anche se la regola accetta i bot
    cog.bot = type("B", (), {"user": type("U", (), {"id": 999})(), "application_id": 1})()
    proprio = _msg(bot=True, autore=999)
    await cog.on_message(proprio)
    proprio.delete.assert_not_awaited()

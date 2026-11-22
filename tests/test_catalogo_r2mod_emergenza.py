"""
tests/test_catalogo_r2mod_emergenza.py
======================================
Difese di emergenza dell'AutoMod (#116, r2mod): blocco per troppe menzioni (AMD-057) e modalità panico (AMD-071).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import automod_emergenza as em
from core.database import db
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role

G = 100


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    em.emergenza.__init__()
    yield
    database_module.db._modules_cache.clear()


def _msg(menzioni=3, everyone=False, bot=False, admin=False, user_id=7):
    m = MagicMock()
    m.guild = fake_guild(G, owner_id=1)
    m.author = fake_member(user_id, bot=bot, guild_permissions=discord.Permissions(administrator=admin))
    m.author.guild = m.guild
    m.mentions = [object()] * menzioni
    m.role_mentions = []
    m.mention_everyone = everyone
    return m


# AMD-057
def test_la_scelta_del_server_resta_nei_limiti():
    assert em.config_pulita(None) == em.BASE
    c = em.config_pulita({"menzioni_soglia": 3, "menzioni_secondi": 9999, "panico_utenti": "x", "panico": "si"})
    assert c["menzioni_soglia"] == 0 and c["menzioni_secondi"] == 30 and c["panico_utenti"] == 5 and c["panico"] is False
    assert em.config_pulita({"menzioni_soglia": 50, "menzioni_secondi": 60, "panico": True})["menzioni_soglia"] == 50


# AMD-057
def test_le_menzioni_si_sommano_nella_finestra_e_everyone_ha_un_tetto():
    e = em.Emergenza()
    assert e.conta_menzioni(G, 10, 30, adesso=0) == 10
    assert e.conta_menzioni(G, 10, 30, adesso=20) == 20
    assert e.conta_menzioni(G, 10, 30, adesso=45) == 20  # la prima è uscita dalla finestra
    assert e.conta_menzioni(G, 999, 30, adesso=46) == 10 + 10 + em.MAX_MENZIONI_PER_MESSAGGIO
    assert e.blocco_permesso(G, adesso=0) is True and e.blocco_permesso(G, adesso=100) is False
    assert e.blocco_permesso(G, adesso=em.PAUSA_TRA_BLOCCHI_SECONDI + 1) is True


# AMD-057
async def test_alla_soglia_il_server_si_blocca_a_tempo_una_sola_volta(monkeypatch):
    from core import lockdown_service as servizio

    attiva = AsyncMock(return_value=MagicMock(ok=True))
    monkeypatch.setattr(servizio, "attiva", attiva)
    config = em.config_pulita({"menzioni_soglia": 10, "menzioni_secondi": 30, "menzioni_minuti": 20})
    assert await em.dopo_messaggio(_msg(6), config) is False
    assert await em.dopo_messaggio(_msg(6), config) is True
    assert attiva.await_args.kwargs["durata_minuti"] == 20 and len(attiva.await_args.kwargs["motivo"]) <= 512
    assert await em.dopo_messaggio(_msg(6), config) is False  # c'è già stato un blocco da poco
    attiva.assert_awaited_once()


# AMD-057
async def test_spento_o_da_bot_o_da_amministratori_non_conta(monkeypatch):
    from core import lockdown_service as servizio

    attiva = AsyncMock(return_value=MagicMock(ok=True))
    monkeypatch.setattr(servizio, "attiva", attiva)
    acceso = em.config_pulita({"menzioni_soglia": 5})
    assert await em.dopo_messaggio(_msg(30), em.BASE) is False
    assert await em.dopo_messaggio(_msg(30, bot=True), acceso) is False
    assert await em.dopo_messaggio(_msg(30, admin=True), acceso) is False
    attiva.assert_not_awaited()


# AMD-071
def test_il_panico_si_accende_con_persone_diverse_e_dura_dieci_minuti():
    e = em.Emergenza()
    assert [e.registra_violazione(G, u, adesso=i) for i, u in enumerate((1, 1, 2, 3))] == [1, 1, 2, 3]
    assert e.registra_violazione(G, 4, adesso=100) == 1  # le vecchie sono uscite dal minuto
    e.accendi_panico(G, adesso=0)
    assert e.panico_attivo(G, adesso=599) and not e.panico_attivo(G, adesso=601)


def _membro(*, giorni, avatar=True, **kw):
    m = _msg(user_id=kw.get("user_id", 9))
    m.author.created_at = datetime.now(timezone.utc) - timedelta(days=giorni)
    m.author.avatar = object() if avatar else None
    m.author.top_role = fake_role(2, position=1)
    m.guild.me.top_role = fake_role(3, position=50)
    return m


# AMD-071
async def test_in_panico_un_account_sospetto_che_viola_va_in_timeout_subito(monkeypatch):
    isola = AsyncMock()
    monkeypatch.setattr(em.bot_roles, "isola", isola)
    config = em.config_pulita({"panico": True, "panico_utenti": 3})
    for u in (31, 32):  # due persone: il panico non è ancora acceso
        assert await em.dopo_violazione(_membro(giorni=1, user_id=u), config, False) is False
    assert await em.dopo_violazione(_membro(giorni=2, user_id=33), config, False) is True  # la terza lo accende e lui è sospetto
    isola.assert_awaited_once()
    assert len(isola.await_args.kwargs["reason"]) <= 512 and isola.await_args.args[1] == em.TIMEOUT_PANICO


# AMD-071
async def test_in_panico_non_toccano_i_vecchi_account_gli_esenti_i_protetti_e_chi_sta_sopra_il_bot(monkeypatch):
    isola = AsyncMock()
    monkeypatch.setattr(em.bot_roles, "isola", isola)
    config = em.config_pulita({"panico": True, "panico_utenti": 3})
    em.emergenza.accendi_panico(G)
    vecchio = _membro(giorni=400, user_id=11)
    esente = _membro(giorni=1, user_id=12)
    protetto = _membro(giorni=1, user_id=13)
    protetto.author.guild_permissions = discord.Permissions(administrator=True)
    sopra = _membro(giorni=1, user_id=14)
    sopra.author.top_role = fake_role(4, position=60)
    assert await em.dopo_violazione(vecchio, config, False) is False
    assert await em.dopo_violazione(esente, config, True) is False
    assert await em.dopo_violazione(protetto, config, False) is False
    assert await em.dopo_violazione(sopra, config, False) is False
    isola.assert_not_awaited()
    assert await em.dopo_violazione(_membro(giorni=1, user_id=15), em.BASE, False) is False  # panico spento nel server


# AMD-057, AMD-071
async def test_il_comando_salva_le_scelte_e_il_blocco_serve_il_permesso_di_gestire():
    from cogs.automod.automod import AutomodCog
    from cogs.automod.automod import MODULE_AUTOMOD

    await db.set_module_active_for_guild(G, MODULE_AUTOMOD, True)
    server = fake_guild(G, owner_id=1)
    cog = AutomodCog.__new__(AutomodCog)
    senza = fake_member(20, guild_permissions=discord.Permissions(administrator=False))
    i = fake_interaction(guild=server, user=senza)
    await cog.emergenza.callback(cog, i, 20)
    assert (await em.leggi_config(G))["menzioni_soglia"] == 0
    i = fake_interaction(guild=server, user=senza)
    await cog.emergenza.callback(cog, i, None, None, None, True, 4)  # il panico non chiude nulla: basta il gruppo
    assert (await em.leggi_config(G))["panico"] is True and (await em.leggi_config(G))["panico_utenti"] == 4
    gestore = fake_member(21, guild_permissions=discord.Permissions(manage_guild=True))
    i = fake_interaction(guild=server, user=gestore)
    await cog.emergenza.callback(cog, i, 20, 15, 45)
    c = await em.leggi_config(G)
    assert (c["menzioni_soglia"], c["menzioni_secondi"], c["menzioni_minuti"]) == (20, 15, 45)

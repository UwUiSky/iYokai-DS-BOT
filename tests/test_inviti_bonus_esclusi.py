"""
tests/test_inviti_bonus_esclusi.py
==================================
D69 B11 (UTL-169, 170, 171, 172, 173): ingressi finti (account giovani, rientri), bonus dello staff,
esclusi dalla classifica, spostamento delle opzioni in /admin-inviti.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

import cogs.utility.invites as modulo
from core import invite_links_logic as logica
from core.repositories.invite_stats_repo import InviteStatsRepository
from core.repositories.inviti_extra_repo import InvitiExtraRepository, TroppiEsclusi
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.percorsi import comando_nel_gruppo

G = 900000000000000002
ORA = datetime(2026, 11, 9, tzinfo=timezone.utc)


# ------------------------------------------------------------------ logica
def test_ingresso_finto_per_eta_e_rientro():
    giovane = ORA - timedelta(days=2)
    vecchio = ORA - timedelta(days=100)
    assert logica.ingresso_finto(giovane, ORA, 7, rientro=False, rientri_finti=False) is True
    assert logica.ingresso_finto(vecchio, ORA, 7, rientro=False, rientri_finti=False) is False
    assert logica.ingresso_finto(giovane, ORA, 0, rientro=False, rientri_finti=False) is False  # 0 = spento
    assert logica.ingresso_finto(vecchio, ORA, 0, rientro=True, rientri_finti=True) is True
    assert logica.ingresso_finto(vecchio, ORA, 0, rientro=True, rientri_finti=False) is False
    assert logica.ingresso_finto(None, ORA, 7, rientro=False, rientri_finti=False) is False


# ------------------------------------------------------------------ archivio
@pytest.fixture
def stats(clean_db):
    return InviteStatsRepository(pool_provider=lambda: clean_db)


@pytest.fixture
def extra(clean_db):
    return InvitiExtraRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_finti_non_contano_ma_si_vedono(stats):
    await stats.record_join(G, 1, 5, "a")
    await stats.record_join(G, 2, 5, "a", finto=True)
    s = await stats.stats_for(G, 5)
    assert (s.totale, s.presenti, s.finti) == (1, 1, 1)
    assert await stats.e_rientro(G, 2) is True and await stats.e_rientro(G, 3) is False


@pytest.mark.asyncio
async def test_bonus_somma_taglia_e_conta_in_classifica(stats, extra):
    await stats.record_join(G, 1, 5, "a")
    await stats.record_join(G, 2, 6, "b")
    await stats.record_join(G, 3, 6, "b")
    assert await extra.aggiungi_bonus(G, 5, 5, 99) == 5
    assert await extra.aggiungi_bonus(G, 5, -2, 99) == 3
    assert await extra.aggiungi_bonus(G, 7, 10, 99) == 10  # chi non ha invitato nessuno compare lo stesso
    top = await stats.top(G)
    assert [u for u, _ in top] == [7, 5, 6]
    assert top[1][1].punti == 4 and top[1][1].bonus == 3
    assert (await stats.stats_for(G, 5)).bonus == 3
    with pytest.raises(ValueError):
        await extra.aggiungi_bonus(G, 5, 10_001, 1)
    for _ in range(12):
        totale = await extra.aggiungi_bonus(G, 8, 10_000, 1)
    assert totale == 100_000


@pytest.mark.asyncio
async def test_esclusi_utenti_e_ruoli_con_tetto(extra):
    assert await extra.aggiungi_escluso(G, "utente", 1) is True
    assert await extra.aggiungi_escluso(G, "utente", 1) is False
    await extra.aggiungi_escluso(G, "ruolo", 9)
    assert await extra.esclusi(G) == ({1}, {9})
    assert await extra.togli_escluso(G, "utente", 1) is True
    assert await extra.togli_escluso(G, "utente", 1) is False
    for i in range(logica.MAX_ESCLUSI - 1):
        await extra.aggiungi_escluso(G, "utente", 1000 + i)
    with pytest.raises(TroppiEsclusi):
        await extra.aggiungi_escluso(G, "utente", 5000)
    assert await extra.aggiungi_escluso(G, "ruolo", 9) is False  # già presente: non è un errore al tetto


# ------------------------------------------------------------------ comandi
@pytest.mark.asyncio
async def test_albero_admin_inviti():
    bot = MagicMock()
    bot.tree = MagicMock()
    from discord.ext import commands

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    for nome in ("impostazioni", "bonus", "escludi"):
        assert comando_nel_gruppo("admin-inviti", nome)


class _Scena:
    def __init__(self):
        self.cog = modulo.InvitesCog(MagicMock())
        self.guild = fake_guild()


@pytest.mark.asyncio
async def test_bonus_rifiuta_zero_e_bot():
    s = _Scena()
    with patch.object(modulo.db, "is_module_active_for_guild", AsyncMock(return_value=True)), \
         patch.object(modulo.inviti_extra_repo, "aggiungi_bonus", AsyncMock(return_value=3)) as add:
        i = fake_interaction(guild=s.guild)
        await s.cog.bonus.callback(s.cog, i, fake_member(user_id=5), 0)
        add.assert_not_awaited()
        m = fake_member(user_id=6)
        i = fake_interaction(guild=s.guild)
        await s.cog.bonus.callback(s.cog, i, m, 4)
        add.assert_awaited_once_with(s.guild.id, 6, 4, i.user.id)
        assert i.response.send_message.await_args.kwargs["allowed_mentions"].users is False


@pytest.mark.asyncio
async def test_classifica_nasconde_esclusi_per_utente_e_ruolo():
    s = _Scena()
    from core.repositories.invite_stats_repo import InviteStats

    righe = [(1, InviteStats(5, 5)), (2, InviteStats(4, 4)), (3, InviteStats(3, 3))]
    due = fake_member(user_id=2)
    due.roles = [MagicMock(id=77)]
    tre = fake_member(user_id=3)
    tre.roles = []
    s.guild.get_member = lambda uid: {2: due, 3: tre}.get(uid)
    with patch.object(modulo.inviti_extra_repo, "esclusi", AsyncMock(return_value=({1}, {77}))):
        assert [u for u, _ in await modulo._senza_esclusi(s.guild, righe, 10)] == [3]
    with patch.object(modulo.inviti_extra_repo, "esclusi", AsyncMock(return_value=(set(), set()))):
        assert len(await modulo._senza_esclusi(s.guild, righe, 2)) == 2


@pytest.mark.asyncio
async def test_impostazioni_passa_eta_e_rientri():
    s = _Scena()
    o = modulo.invite_service.Opzioni(True, None, None, "tutti", 7, True)
    with patch.object(modulo.invite_service, "imposta_opzioni", AsyncMock(return_value=True)) as imposta, \
         patch.object(modulo.invite_service, "leggi_opzioni", AsyncMock(return_value=o)):
        await s.cog.opzioni.callback(s.cog, fake_interaction(guild=s.guild), None, None, None, None, 7, True)
    kw = imposta.await_args.kwargs
    assert kw["eta_minima"] == 7 and kw["rientri_finti"] is True


@pytest.mark.asyncio
async def test_servizio_segna_il_finto(clean_db, monkeypatch):
    from core import invite_service as svc
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(svc, "invite_stats_repo", InviteStatsRepository(pool_provider=lambda: clean_db))
    monkeypatch.setattr(svc.db, "get_guild_setting", AsyncMock(side_effect=lambda g, k: {
        logica.SETTING_ETA_MINIMA: 30, logica.SETTING_RIENTRI_FINTI: True}.get(k)))
    monkeypatch.setattr(svc.db, "is_module_active_for_guild", AsyncMock(return_value=True))
    monkeypatch.setattr(svc.invite_links_repo, "da_codice", AsyncMock(return_value=None))
    guild = fake_guild(G)
    guild.vanity_url_code = None
    ora = datetime.now(timezone.utc)
    assert (await svc.registra_ingresso(guild, 1, ("c", 7), ora - timedelta(days=3))).finto is True
    assert (await svc.registra_ingresso(guild, 2, ("c", 7), ora - timedelta(days=300))).finto is False
    assert (await svc.registra_ingresso(guild, 2, ("c", 7), ora - timedelta(days=300))).finto is True  # rientro

"""
tests/test_invites.py
=====================
NF-27 (#98): chi ha invitato chi. Una riga per membro, classifica di 10 righe, avviso
sull'attribuzione (LC-6), dato cancellabile dall'utente (registro NF-04).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

import cogs.utility.invites as modulo
from core import invite_service
from cogs.utility.invites import AVVISO_ATTRIBUZIONE, InvitesCog
from core.repositories.invite_stats_repo import InviteStatsRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.percorsi import comando_nel_gruppo

G = 900000000000000001


@pytest.fixture
def repo(clean_db):
    return InviteStatsRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_conteggio_presenti_e_usciti(repo):
    for uid in (11, 12, 13):
        await repo.record_join(G, uid, 5, "abc")
    await repo.mark_left(G, 12)
    s = await repo.stats_for(G, 5)
    assert (s.totale, s.presenti) == (3, 2)


@pytest.mark.asyncio
async def test_rientro_con_altro_invito_non_conta_due_volte(repo):
    await repo.record_join(G, 11, 5, "abc")
    await repo.mark_left(G, 11)
    await repo.record_join(G, 11, 6, "xyz")
    assert (await repo.stats_for(G, 5)).totale == 0
    s = await repo.stats_for(G, 6)
    assert (s.totale, s.presenti) == (1, 1)


@pytest.mark.asyncio
async def test_classifica_di_dieci_righe_ordinata(repo):
    for inv in range(100, 115):
        await repo.record_join(G, inv * 10, inv, "c")
    for k in range(3):
        await repo.record_join(G, 5000 + k, 100, "c")
    top = await repo.top(G, limite=50)
    assert len(top) == 10 and top[0][0] == 100 and top[0][1].presenti == 4


@pytest.mark.asyncio
async def test_i_server_sono_separati(repo):
    await repo.record_join(G, 11, 5, "abc")
    assert (await repo.stats_for(G + 1, 5)).totale == 0


# ---------------------------------------------------------------- cog
def _m(uid, guild, bot=False):
    m = fake_member(user_id=uid, bot=bot)
    m.guild = guild
    return m


def _cog():
    return InvitesCog(AsyncMock())


@pytest.mark.asyncio
async def test_ingresso_registrato_e_bot_ignorato():
    cog = _cog()
    guild = fake_guild()
    umano, bot = _m(21, guild), _m(22, guild, True)
    with patch.object(modulo.db, "is_module_active_for_guild", AsyncMock(return_value=True)), \
         patch.object(modulo.invite_tracker, "resolve_join_invite", AsyncMock(return_value=("abc", 5))), \
         patch.object(invite_service.invite_links_repo, "da_codice", AsyncMock(return_value=None)), \
         patch.object(modulo.db, "get_guild_setting", AsyncMock(return_value=None)), \
         patch.object(modulo.invite_stats_repo, "record_join", AsyncMock()) as rec:
        await cog.on_member_join(bot)
        rec.assert_not_awaited()
        await cog.on_member_join(umano)
        rec.assert_awaited_once_with(guild.id, 21, 5, "abc", "normale")


@pytest.mark.asyncio
async def test_invito_sconosciuto_o_auto_invito_registrati_senza_invitante():
    """Lo storico tiene anche chi entra senza invitante noto (tipo «sconosciuto»); nessuno invita se stesso."""
    cog = _cog()
    guild = fake_guild()
    m = _m(21, guild)
    with patch.object(modulo.db, "is_module_active_for_guild", AsyncMock(return_value=True)), \
         patch.object(modulo.db, "get_guild_setting", AsyncMock(return_value=None)), \
         patch.object(invite_service.invite_links_repo, "da_codice", AsyncMock(return_value=None)), \
         patch.object(modulo.invite_stats_repo, "record_join", AsyncMock()) as rec:
        for risposta in (None, ("abc", None), ("abc", 21)):
            with patch.object(modulo.invite_tracker, "resolve_join_invite", AsyncMock(return_value=risposta)):
                await cog.on_member_join(m)
    assert [c.args[2:] for c in rec.await_args_list] == [
        (None, None, "sconosciuto"), (None, "abc", "normale"), (None, "abc", "normale"),
    ]


@pytest.mark.asyncio
async def test_modulo_spento_non_registra():
    cog = _cog()
    m = _m(21, fake_guild())
    with patch.object(modulo.db, "is_module_active_for_guild", AsyncMock(return_value=False)), \
         patch.object(modulo.invite_tracker, "resolve_join_invite", AsyncMock()) as ris:
        await cog.on_member_join(m)
        ris.assert_not_awaited()


@pytest.mark.asyncio
async def test_uscita_segnata():
    cog = _cog()
    guild = fake_guild()
    with patch.object(modulo.invite_stats_repo, "mark_left", AsyncMock()) as left, \
         patch.object(modulo.invite_service, "elimina_link_membro", AsyncMock()) as toglie:
        await cog.on_member_remove(_m(21, guild))
        left.assert_awaited_once_with(guild.id, 21)
        toglie.assert_awaited_once_with(cog.bot, guild.id, 21)


@pytest.mark.asyncio
async def test_i_comandi_avvisano_sull_attribuzione():
    cog = _cog()
    inter = fake_interaction(guild=fake_guild())
    with patch.object(modulo.db, "is_module_active_for_guild", AsyncMock(return_value=True)):
        with patch.object(modulo.invite_stats_repo, "top", AsyncMock(return_value=[])):
            await cog.classifica.callback(cog, inter)
        assert AVVISO_ATTRIBUZIONE in inter.response.send_message.call_args.args[0]


@pytest.mark.asyncio
async def test_albero_dei_comandi():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    for nome in ("utente", "classifica", "storico", "link", "opzioni"):
        assert comando_nel_gruppo("level", f"inviti {nome}") is not None


@pytest.mark.asyncio
async def test_chi_esce_e_rientra_con_un_altro_invito_viene_ricalcolato():
    """Il risultato dell'ingresso restava in memoria: il rientro riceveva l'invito vecchio."""
    from core.invite_tracker import InviteTracker
    t = InviteTracker()
    t._join_results.set((1, 7), ("vecchio", 5))
    assert await t.resolve_join_invite(MagicMock(id=1), 7) == ("vecchio", 5)
    cog = _cog()
    guild = fake_guild(guild_id=1)
    with patch.object(modulo, "invite_tracker", t), patch.object(modulo.invite_stats_repo, "mark_left", AsyncMock()):
        await cog.on_member_remove(_m(7, guild))
    assert (1, 7) not in t._join_results

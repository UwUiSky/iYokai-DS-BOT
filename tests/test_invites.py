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


# ------------------------------------------------- link personali (r10)
from datetime import datetime, timezone
from types import SimpleNamespace

from core import invite_links_logic as logica
from core.repositories.invite_links_repo import LinkPersonale
from core.repositories.invite_stats_repo import IngressoDi, IngressoInvitato, InviteStats

ADESSO = datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_comando_link_da_l_indirizzo_o_il_motivo():
    cog = _cog()
    inter = fake_interaction(guild=fake_guild())
    link = LinkPersonale("srv-anna", 1, 2, None, ADESSO)
    with patch.object(modulo.db, "is_module_active_for_guild", AsyncMock(return_value=True)):
        with patch.object(modulo.invite_service, "ottieni_link", AsyncMock(return_value=(logica.OK, link))), \
             patch.object(modulo.invite_service, "url_pubblico", return_value="https://s.test"):
            await cog.link.callback(cog, inter)
        assert "https://s.test/invito/srv-anna" in inter.response.send_message.call_args.args[0]
        with patch.object(modulo.invite_service, "ottieni_link", AsyncMock(return_value=(logica.OK, link))), \
             patch.object(modulo.invite_service, "url_pubblico", return_value=""):
            await cog.link.callback(cog, inter)
        assert "non è attivo" in inter.response.send_message.call_args.args[0]
        with patch.object(modulo.invite_service, "ottieni_link", AsyncMock(return_value=(logica.SENZA_PERMESSO, None))):
            await cog.link.callback(cog, inter)
        assert "Crea invito" in inter.response.send_message.call_args.args[0]


@pytest.mark.asyncio
async def test_comando_storico_e_utente_dicono_da_chi_e_stato_invitato():
    cog = _cog()
    guild = fake_guild()
    inter = fake_interaction(guild=guild)
    ingresso = IngressoDi(77, "abc", "personale", ADESSO, None)
    ultimi = [IngressoInvitato(5, ADESSO, None, "normale"), IngressoInvitato(6, ADESSO, ADESSO, "vanity")]
    with patch.object(modulo.db, "is_module_active_for_guild", AsyncMock(return_value=True)), \
         patch.object(modulo.invite_stats_repo, "stats_for", AsyncMock(return_value=InviteStats(2, 1))), \
         patch.object(modulo.invite_stats_repo, "ingresso_di", AsyncMock(return_value=ingresso)), \
         patch.object(modulo.invite_stats_repo, "invitati_da", AsyncMock(return_value=ultimi)):
        await cog.storico.callback(cog, inter)
        testo = inter.response.send_message.call_args.args[0]
        assert "Invitato da <@77>" in testo and "link personale dal sito" in testo
        assert "<@5>" in testo and "è ancora qui" in testo and "<@6>" in testo and "uscito il" in testo
        assert AVVISO_ATTRIBUZIONE in testo
        await cog.utente.callback(cog, inter)
        assert "Invitato da <@77>" in inter.response.send_message.call_args.args[0]


@pytest.mark.asyncio
async def test_comando_opzioni_passa_dal_punto_unico():
    cog = _cog()
    guild = fake_guild()
    inter = fake_interaction(guild=guild)
    canale = MagicMock(id=42)
    ruolo = MagicMock(id=55)
    tolto = SimpleNamespace(value="ruolo")
    o = invite_service.Opzioni(True, 42, None)
    with patch.object(modulo.invite_service, "imposta_opzioni", AsyncMock(return_value=True)) as imposta, \
         patch.object(modulo.invite_service, "leggi_opzioni", AsyncMock(return_value=o)):
        await cog.opzioni.callback(cog, inter, canale, None, tolto)
        kw = imposta.await_args.kwargs
        assert kw["canale_log"] == 42 and kw["ruolo_link"] is None
        await cog.opzioni.callback(cog, inter, None, ruolo, None)
        kw = imposta.await_args.kwargs
        assert kw["ruolo_link"] == 55 and kw["canale_log"] is invite_service.NON_CAMBIARE
        assert "<#42>" in inter.response.send_message.call_args.args[0]
    from core.config_schema import ImpostazioneNonValida
    with patch.object(modulo.invite_service, "imposta_opzioni", AsyncMock(side_effect=ImpostazioneNonValida("No."))):
        await cog.opzioni.callback(cog, inter, canale, None, None)
        assert inter.response.send_message.call_args.args[0] == "No."


@pytest.mark.asyncio
async def test_registro_scrive_nel_canale_scelto_senza_menzioni():
    cog = _cog()
    guild = fake_guild()
    m = _m(21, guild)
    canale = MagicMock(spec=discord.TextChannel)
    canale.send = AsyncMock()
    guild.get_channel = MagicMock(return_value=canale)
    ing = invite_service.Ingresso(logica.TIPO_PERSONALE, 77, "abc")
    with patch.object(modulo.db, "get_guild_setting", AsyncMock(return_value=42)):
        await cog._scrivi_nel_registro(m, ing)
    testo = canale.send.call_args.args[0]
    assert "<@77>" in testo and "link personale dal sito" in testo
    assert canale.send.call_args.kwargs["allowed_mentions"].users is False
    with patch.object(modulo.db, "get_guild_setting", AsyncMock(return_value=None)):
        canale.send.reset_mock()
        await cog._scrivi_nel_registro(m, ing)
        canale.send.assert_not_awaited()

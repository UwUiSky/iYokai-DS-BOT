"""
tests/test_ticket_catalogo.py
=============================
#120 (catalogo ticket): motivo di chiusura, rilascia, passa, transcript senza chiudere,
add/remove di un ruolo, chiusura di massa. Database vero; Discord finto.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.tickets.tickets as modulo
from cogs.tickets.tickets import TICKET_DELETE_ACTION_TYPE
from core.repositories.ticket_repo import ticket_repo
from core.scheduler import Scheduler
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_role,
    fake_text_channel,
)

GUILD_ID = 100
CANALE = 200
UTENTE = 20
STAFF = 30
MANAGER = 31


@pytest.fixture(autouse=True)
def _pool(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()


@pytest.fixture
async def cog(monkeypatch):
    monkeypatch.setattr(modulo, "scheduler", Scheduler())
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    c = bot.get_cog("TicketsCog")
    c._transcript_senza_bloccare = AsyncMock()
    c._richiedi_voto = AsyncMock()
    yield c
    await bot.close()


def _manager(uid=MANAGER):
    return fake_member(uid, guild_permissions=discord.Permissions(manage_guild=True))


def _inter(user, canale_id=CANALE):
    canale = fake_text_channel(canale_id)
    guild = fake_guild(GUILD_ID)
    return fake_interaction(guild=guild, user=user, channel=canale)


async def _ticket(canale=CANALE, numero=1, utente=UTENTE):
    await ticket_repo.create_ticket(GUILD_ID, utente, canale, ticket_number=numero)


def _testo(inter) -> str:
    return str(inter.response.send_message.call_args)


async def test_close_salva_il_motivo(cog):
    await _ticket()
    inter = _inter(fake_member(UTENTE))
    await cog.close.callback(cog, inter, "Risolto via DM")
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    assert t.status == "closed" and t.close_reason == "Risolto via DM"
    assert "Risolto via DM" in _testo(inter)


async def test_forceclose_salva_il_motivo(cog, monkeypatch):
    await _ticket()
    cog._elimina_canale = AsyncMock()
    inter = _inter(_manager())
    await cog.forceclose.callback(cog, inter, "Spam")
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    assert t.close_reason == "Spam"


async def test_il_transcript_riporta_il_motivo(cog):
    await _ticket()
    await ticket_repo.close_ticket(CANALE, 1, reason="Duplicato")
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    canale = fake_text_channel(CANALE)

    async def vuota(**_):
        return
        yield

    canale.history = MagicMock(side_effect=lambda **kw: vuota())
    testo = await cog._build_transcript_text(canale, t)
    assert "Motivo di chiusura: Duplicato" in testo


async def test_rilascia_solo_chi_lo_ha_preso_o_manage_guild(cog):
    await _ticket()
    await ticket_repo.claim_ticket(CANALE, STAFF)
    estraneo = fake_member(
        40, roles=[fake_role(role_id=7)], guild_permissions=discord.Permissions.none()
    )
    # 40 non e' staff: rifiutato prima ancora del controllo del reclamante
    inter = _inter(estraneo)
    await cog.rilascia.callback(cog, inter)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).claimed_by == STAFF

    # un altro membro dello staff (manage_guild) puo'
    inter = _inter(_manager())
    await cog.rilascia.callback(cog, inter)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).claimed_by is None


async def test_rilascia_rifiuta_un_collega_con_solo_ruolo_di_supporto(cog, monkeypatch):
    await _ticket()
    await ticket_repo.claim_ticket(CANALE, STAFF)
    monkeypatch.setattr(modulo, "_support_role_ids", AsyncMock(return_value=[7]))
    collega = fake_member(41, roles=[fake_role(role_id=7)])
    inter = _inter(collega)
    await cog.rilascia.callback(cog, inter)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).claimed_by == STAFF
    assert "Solo chi" in _testo(inter)


async def test_rilascia_su_ticket_non_preso(cog):
    await _ticket()
    inter = _inter(_manager())
    await cog.rilascia.callback(cog, inter)
    assert "Nessuno" in _testo(inter)


async def test_passa_solo_a_un_membro_dello_staff(cog, monkeypatch):
    await _ticket()
    monkeypatch.setattr(modulo, "_support_role_ids", AsyncMock(return_value=[7]))
    inter = _inter(_manager())
    semplice = fake_member(50)
    await cog.passa.callback(cog, inter, semplice)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).claimed_by is None

    bot_staff = fake_member(51, bot=True, guild_permissions=discord.Permissions(manage_guild=True))
    await cog.passa.callback(cog, _inter(_manager()), bot_staff)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).claimed_by is None

    collega = fake_member(52, roles=[fake_role(role_id=7)])
    await cog.passa.callback(cog, _inter(_manager()), collega)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).claimed_by == 52


async def test_transcript_solo_staff_e_il_ticket_resta_aperto(cog):
    await _ticket()
    cog._build_transcript_text = AsyncMock(return_value="ciao")
    inter = _inter(fake_member(UTENTE))
    await cog.transcript.callback(cog, inter)
    assert "Solo lo staff" in _testo(inter)
    cog._build_transcript_text.assert_not_called()

    inter = _inter(_manager())
    await cog.transcript.callback(cog, inter)
    inter.followup.send.assert_called()
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).status == "open"


async def test_add_e_remove_ruolo_ma_mai_everyone(cog):
    await _ticket()
    ruolo = fake_role(role_id=7)
    inter = _inter(_manager())
    inter.channel.set_permissions = AsyncMock()
    await cog.add.callback(cog, inter, None, ruolo)
    inter.channel.set_permissions.assert_awaited_once()
    assert inter.channel.set_permissions.await_args.args[0] is ruolo

    inter = _inter(_manager())
    inter.channel.set_permissions = AsyncMock()
    await cog.remove.callback(cog, inter, None, ruolo)
    inter.channel.set_permissions.assert_awaited_once_with(ruolo, overwrite=None)

    everyone = fake_role(role_id=GUILD_ID)
    inter = _inter(_manager())
    inter.channel.set_permissions = AsyncMock()
    await cog.add.callback(cog, inter, None, everyone)
    inter.channel.set_permissions.assert_not_called()


async def test_add_vuole_esattamente_uno_tra_utente_e_ruolo(cog):
    await _ticket()
    inter = _inter(_manager())
    inter.channel.set_permissions = AsyncMock()
    await cog.add.callback(cog, inter, None, None)
    await cog.add.callback(cog, inter, fake_member(60), fake_role(role_id=7))
    inter.channel.set_permissions.assert_not_called()


async def test_chiudi_tutti_ne_chiude_al_massimo_25_e_dice_quanti_restano(cog, monkeypatch):
    totale = modulo.MAX_CHIUSURA_DI_MASSA + 3
    guild = fake_guild(GUILD_ID)
    guild.me = fake_member(999, bot=True)
    canali = {}
    for i in range(totale):
        await _ticket(canale=1000 + i, numero=i + 1, utente=500 + i)
        canali[1000 + i] = fake_text_channel(1000 + i)
    guild.get_channel = MagicMock(side_effect=lambda cid: canali.get(cid))
    inter = fake_interaction(guild=guild, user=_manager(), channel=fake_text_channel(1))
    await cog.chiudi_tutti.callback(cog, inter, "Fine evento")

    chiusi = await ticket_repo._pool.fetch("SELECT close_reason FROM tickets WHERE status = 'closed'")
    assert len(chiusi) == modulo.MAX_CHIUSURA_DI_MASSA
    assert {r["close_reason"] for r in chiusi} == {"Fine evento"}
    azioni = await ticket_repo._pool.fetch(
        "SELECT 1 FROM scheduled_actions WHERE action_type = $1", TICKET_DELETE_ACTION_TYPE
    )
    assert len(azioni) == modulo.MAX_CHIUSURA_DI_MASSA
    assert "ne restano 3" in str(inter.followup.send.call_args).lower()

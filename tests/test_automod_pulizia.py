"""
tests/test_automod_pulizia.py
=============================
Il giro di pulizia di un canale (AMD-073, 074): sceglie i messaggi, cancella in blocco i recenti e uno per uno i
vecchi, lascia i fissati, si ferma dopo tre 403 e non esce mai dai limiti di Discord.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import automod_pulizia as motore
from core.repositories.automod_pulizie_repo import Pulizia
from tests.support.discord_fakes import fake_guild, fake_text_channel

ADESSO = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
_seq = iter(range(1, 10_000_000))


def msg(giorni=1.0, *, bot=False, testo="ciao", fissato=False, allegati=0):
    """Messaggio con la forma di discord.Message (spec) ma leggero: i test ne creano centinaia."""
    m = MagicMock(spec=discord.Message)
    m.id = discord.utils.time_snowflake(ADESSO - timedelta(days=giorni)) + next(_seq) % 1000
    m.author, m.content = MagicMock(spec=discord.Member, bot=bot), testo
    m.pinned, m.attachments, m.type = fissato, [object()] * allegati, discord.MessageType.default
    m.is_system = MagicMock(return_value=False)
    m.delete = AsyncMock()
    return m


def canale(messaggi, *, permessi=None):
    c = fake_text_channel(111)
    c.guild = fake_guild(666)
    c.permissions_for = MagicMock(return_value=permessi or discord.Permissions(view_channel=True, read_message_history=True, manage_messages=True))

    async def storia(limit=None, **k):
        for m in messaggi[:limit]:
            yield m
    c.history = storia
    c.delete_messages = AsyncMock()
    return c


def riga(**k):
    base = dict(guild_id=666, canale_id=111, ogni_secondi=3600, tipo="tutti", fissati=False, attiva=True)
    return Pulizia(**{**base, **k})


@pytest.fixture(autouse=True)
def senza_pause(monkeypatch):
    monkeypatch.setattr(motore, "PAUSA_S", 0)


async def test_recenti_in_blocco_e_vecchi_uno_per_uno():
    recenti, vecchi = [msg(1) for _ in range(3)], [msg(20) for _ in range(2)]
    c = canale(recenti + vecchi)
    e = await motore.pulisci(c, riga(), ADESSO)
    c.delete_messages.assert_awaited_once()
    assert list(c.delete_messages.await_args.args[0]) == recenti
    assert all(m.delete.await_count == 1 for m in vecchi)
    assert e.cancellati == 5


async def test_i_fissati_restano_salvo_scelta():
    f, n = msg(1, fissato=True), [msg(1), msg(1)]
    c = canale([f, *n])
    await motore.pulisci(c, riga(), ADESSO)
    assert list(c.delete_messages.await_args.args[0]) == n
    c2 = canale([f, *n])
    await motore.pulisci(c2, riga(fissati=True), ADESSO)
    assert len(c2.delete_messages.await_args.args[0]) == 3


async def test_il_tipo_sceglie_i_messaggi():
    p1, p2, b = msg(1), msg(1), msg(1, bot=True)
    c = canale([p1, b, p2])
    await motore.pulisci(c, riga(tipo="persone"), ADESSO)
    assert list(c.delete_messages.await_args.args[0]) == [p1, p2]


async def test_i_vecchi_sono_al_massimo_100_per_giro():
    vecchi = [msg(30) for _ in range(150)]
    c = canale(vecchi)
    e = await motore.pulisci(c, riga(), ADESSO)
    assert sum(m.delete.await_count for m in vecchi) == 100 and e.cancellati == 100
    c.delete_messages.assert_not_awaited()


async def test_dopo_tre_403_si_ferma_e_lo_dice():
    vecchi = [msg(30) for _ in range(10)]
    risposta = MagicMock(status=403, reason="x")
    for m in vecchi:
        m.delete.side_effect = discord.Forbidden(risposta, "no")
    c = canale(vecchi)
    e = await motore.pulisci(c, riga(), ADESSO)
    assert e.fermo and sum(m.delete.await_count for m in vecchi) == 3


async def test_un_blocco_rifiutato_conta_come_403():
    recenti = [msg(1) for _ in range(250)]
    c = canale(recenti)
    c.delete_messages.side_effect = discord.Forbidden(MagicMock(status=403, reason="x"), "no")
    e = await motore.pulisci(c, riga(), ADESSO)
    assert e.fermo and c.delete_messages.await_count == 3


async def test_senza_permessi_non_chiama_discord():
    c = canale([msg(1), msg(1)], permessi=discord.Permissions(view_channel=True))
    e = await motore.pulisci(c, riga(), ADESSO)
    assert e.senza_permessi and e.cancellati == 0
    c.delete_messages.assert_not_awaited()


async def test_messaggi_di_sistema_restano():
    s = msg(1)
    s.is_system.return_value = True
    n = [msg(1), msg(1)]
    c = canale([s, *n])
    await motore.pulisci(c, riga(), ADESSO)
    assert list(c.delete_messages.await_args.args[0]) == n


async def test_legge_al_massimo_500_messaggi():
    c = canale([msg(1) for _ in range(700)])
    e = await motore.pulisci(c, riga(), ADESSO)
    assert e.cancellati == 500

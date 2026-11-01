"""
tests/test_desktop_staff.py
===========================
SPEC D.9 (#108): azioni dello staff dal programma. Il bot agisce solo se la persona ha il permesso vero.
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import desktop_staff as ds
from core.repositories.desktop_repo import DesktopRepository

G, ME, ALTRO, CANALE = 500, 10, 20, 77


def _permessi(**kw):
    return SimpleNamespace(**{"manage_channels": False, "send_messages": False, "manage_messages": False, **kw})


def _membro(uid, ruolo=1, moderate=False, admin=False):
    return SimpleNamespace(
        id=uid, top_role=ruolo, timeout=AsyncMock(),
        guild_permissions=SimpleNamespace(moderate_members=moderate, administrator=admin),
    )


def _mondo(permessi_canale=None, **membro_kw):
    canale = MagicMock()
    canale.permissions_for = MagicMock(return_value=permessi_canale or _permessi(manage_channels=True, send_messages=True, manage_messages=True))
    canale.overwrites_for = MagicMock(return_value=discord.PermissionOverwrite())
    canale.set_permissions = AsyncMock()
    canale.send = AsyncMock()
    io, altro = _membro(ME, **membro_kw), _membro(ALTRO)
    guild = MagicMock()
    guild.id, guild.owner_id, guild.default_role = G, 999, "tutti"
    guild.get_channel = MagicMock(side_effect=lambda c: canale if c == CANALE else None)
    guild.get_member = MagicMock(side_effect=lambda u: {ME: io, ALTRO: altro}.get(u))
    guild.fetch_member = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "no"))
    bot = MagicMock()
    bot.get_guild = MagicMock(side_effect=lambda g: guild if g == G else None)
    return SimpleNamespace(bot=bot, guild=guild, canale=canale, io=io, altro=altro)


@pytest.fixture
def repo(monkeypatch, clean_db):
    r = DesktopRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(ds, "desktop_repo", r)
    return r


async def test_blocca_e_sblocca_con_il_permesso(repo):
    m = _mondo()
    assert await ds.esegui(m.bot, ME, G, "blocca_canale", {"channel_id": CANALE}) == ds.OK
    chiamata = m.canale.set_permissions.await_args
    assert chiamata.args[0] == "tutti" and chiamata.kwargs["overwrite"].send_messages is False
    assert await ds.esegui(m.bot, ME, G, "sblocca_canale", {"channel_id": CANALE}) == ds.OK
    assert m.canale.set_permissions.await_args.kwargs["overwrite"].send_messages is None
    assert [a["esito"] for a in await repo.azioni_server(G)] == ["ok", "ok"]


async def test_senza_permesso_non_si_fa_nulla_ma_si_registra(repo):
    m = _mondo(permessi_canale=_permessi())
    assert await ds.esegui(m.bot, ME, G, "blocca_canale", {"channel_id": CANALE}) == ds.NESSUN_PERMESSO
    assert await ds.esegui(m.bot, ME, G, "annuncio", {"channel_id": CANALE, "testo": "ciao"}) == ds.NESSUN_PERMESSO
    assert await ds.esegui(m.bot, ME, G, "timeout", {"target_id": ALTRO, "minuti": 5}) == ds.NESSUN_PERMESSO
    m.canale.set_permissions.assert_not_awaited()
    m.canale.send.assert_not_awaited()
    m.altro.timeout.assert_not_awaited()
    assert [a["esito"] for a in await repo.azioni_utente(ME)] == ["nessun_permesso"] * 3


async def test_chi_non_e_nel_server_non_puo(repo):
    m = _mondo()
    assert await ds.esegui(m.bot, 12345, G, "blocca_canale", {"channel_id": CANALE}) == ds.NESSUN_PERMESSO


async def test_server_azione_e_dati_sconosciuti(repo):
    m = _mondo()
    assert await ds.esegui(m.bot, ME, 1, "blocca_canale", {}) == ds.SERVER_SCONOSCIUTO
    assert await ds.esegui(m.bot, ME, "x", "blocca_canale", {}) == ds.SERVER_SCONOSCIUTO
    assert await ds.esegui(m.bot, ME, G, "banna_tutti", {}) == ds.AZIONE_SCONOSCIUTA
    assert await ds.esegui(m.bot, ME, G, "blocca_canale", {"channel_id": 1}) == ds.CANALE_SCONOSCIUTO
    assert await ds.esegui(m.bot, ME, G, "annuncio", {"channel_id": CANALE, "testo": " "}) == ds.DATI_NON_VALIDI
    assert await ds.esegui(m.bot, ME, G, "annuncio", {"channel_id": CANALE, "testo": "x" * 2001}) == ds.DATI_NON_VALIDI
    assert await ds.esegui(m.bot, ME, G, "timeout", {"target_id": ALTRO, "minuti": ds.MAX_MINUTI_TIMEOUT + 1}) == ds.DATI_NON_VALIDI
    assert await ds.esegui(m.bot, ME, G, "timeout", {"target_id": True, "minuti": 5}) == ds.DATI_NON_VALIDI


async def test_annuncio_senza_menzioni_e_senza_testo_nel_registro(repo):
    m = _mondo()
    assert await ds.esegui(m.bot, ME, G, "annuncio", {"channel_id": CANALE, "testo": "Segreto @everyone"}) == ds.OK
    kw = m.canale.send.await_args
    assert kw.args[0] == "Segreto @everyone" and kw.kwargs["allowed_mentions"].everyone is False
    assert "Segreto" not in (await repo.azioni_server(G))[0]["dettaglio"]


async def test_timeout_con_gerarchia(repo):
    m = _mondo(moderate=True, ruolo=5)
    m.altro.top_role = 3
    assert await ds.esegui(m.bot, ME, G, "timeout", {"target_id": ALTRO, "minuti": 10, "motivo": "spam"}) == ds.OK
    assert m.altro.timeout.await_args.args[0] == timedelta(minutes=10)
    assert "spam" in m.altro.timeout.await_args.kwargs["reason"]
    m.altro.top_role = 5  # pari grado: no
    assert await ds.esegui(m.bot, ME, G, "timeout", {"target_id": ALTRO, "minuti": 10}) == ds.GERARCHIA
    m.altro.top_role, m.altro.guild_permissions.administrator = 1, True  # admin: mai
    assert await ds.esegui(m.bot, ME, G, "timeout", {"target_id": ALTRO, "minuti": 10}) == ds.GERARCHIA
    assert await ds.esegui(m.bot, ME, G, "timeout", {"target_id": 4040, "minuti": 10}) == ds.MEMBRO_SCONOSCIUTO


async def test_il_bot_senza_permessi_lo_dice(repo):
    m = _mondo(moderate=True, ruolo=5)
    m.altro.top_role = 1
    m.altro.timeout.side_effect = discord.Forbidden(MagicMock(status=403), "no")
    m.canale.set_permissions.side_effect = discord.Forbidden(MagicMock(status=403), "no")
    m.canale.send.side_effect = discord.Forbidden(MagicMock(status=403), "no")
    assert await ds.esegui(m.bot, ME, G, "timeout", {"target_id": ALTRO, "minuti": 5}) == ds.BOT_SENZA_PERMESSI
    assert await ds.esegui(m.bot, ME, G, "blocca_canale", {"channel_id": CANALE}) == ds.BOT_SENZA_PERMESSI
    assert await ds.esegui(m.bot, ME, G, "annuncio", {"channel_id": CANALE, "testo": "x"}) == ds.BOT_SENZA_PERMESSI

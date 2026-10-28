"""
tests/test_invite_tracker_vanity.py
===================================
Tracker degli inviti: indirizzo personalizzato (vanity) seguito a parte, codici noti, invito
appena creato dal bot registrato subito.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core.invite_tracker import InviteTracker
from tests.support.discord_fakes import fake_guild


def _guild(inviti, usi_vanity, codice="mio"):
    g = fake_guild(5)
    g.invites = AsyncMock(return_value=inviti)
    g.vanity_url_code = codice
    g.vanity_invite = AsyncMock(return_value=SimpleNamespace(uses=usi_vanity) if usi_vanity is not None else None)
    return g


@pytest.mark.asyncio
async def test_ingresso_dal_vanity_e_riconosciuto():
    t = InviteTracker()
    g = _guild([], 3)
    await t.refresh_guild(g)
    assert t.codici(5) == {"mio"}
    g.vanity_invite.return_value = SimpleNamespace(uses=4)
    assert await t.resolve_join_invite(g, 100) == ("mio", None)


@pytest.mark.asyncio
async def test_senza_permesso_il_vanity_si_salta():
    t = InviteTracker()
    g = _guild([], 3)
    g.vanity_invite.side_effect = discord.Forbidden(MagicMock(status=403), "no")
    await t.refresh_guild(g)
    assert t.codici(5) == set()
    g.vanity_url_code = None
    await t.refresh_guild(g)  # nessun vanity: nessuna chiamata
    assert g.vanity_invite.await_count == 1


@pytest.mark.asyncio
async def test_invito_registrato_dal_bot_si_riconosce_al_primo_uso():
    t = InviteTracker()
    g = _guild([], None, codice=None)
    assert t.codici(5) is None
    await t.refresh_guild(g)
    t.registra_invito(5, "Nuovo", 999)
    assert t.codici(5) == {"Nuovo"}
    g.invites.return_value = [SimpleNamespace(code="Nuovo", uses=1, inviter=SimpleNamespace(id=999))]
    assert await t.resolve_join_invite(g, 100) == ("Nuovo", 999)

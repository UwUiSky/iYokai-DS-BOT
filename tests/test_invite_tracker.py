"""
tests/test_invite_tracker.py
===============================
Test di core/invite_tracker.py con oggetti Guild/Invite finti
minimali (espongono solo gli attributi realmente usati: .id per
Guild, .code/.uses/.inviter per Invite) — non serve una connessione
Discord vera per verificare la logica di cache e refresh.
"""

import pytest

from core.invite_tracker import InviteTracker


class _FakeInviter:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeInvite:
    def __init__(self, code: str, uses: int, inviter_id: int | None) -> None:
        self.code = code
        self.uses = uses
        self.inviter = _FakeInviter(inviter_id) if inviter_id is not None else None


class _FakeGuild:
    def __init__(self, guild_id: int, invites: list[_FakeInvite]) -> None:
        self.id = guild_id
        self._invites = invites

    async def invites(self) -> list[_FakeInvite]:
        return self._invites


@pytest.mark.asyncio
async def test_refresh_guild_popola_la_cache():
    tracker = InviteTracker()
    guild = _FakeGuild(100, [_FakeInvite("abc123", uses=5, inviter_id=42)])

    await tracker.refresh_guild(guild)

    assert tracker._cache.get(100) == {"abc123": 5}
    assert tracker._inviters.get(100) == {"abc123": 42}


@pytest.mark.asyncio
async def test_refresh_guild_con_invito_senza_inviter():
    # Un invito può non avere un inviter noto (es. widget invite).
    tracker = InviteTracker()
    guild = _FakeGuild(100, [_FakeInvite("xyz", uses=1, inviter_id=None)])

    await tracker.refresh_guild(guild)

    assert tracker._inviters.get(100)["xyz"] is None


@pytest.mark.asyncio
async def test_find_used_invite_identifica_il_codice_usato():
    tracker = InviteTracker()
    guild_v1 = _FakeGuild(100, [_FakeInvite("abc123", uses=5, inviter_id=42)])
    await tracker.refresh_guild(guild_v1)

    # Simula: l'invito "abc123" è stato usato, uses sale a 6.
    guild_v2 = _FakeGuild(100, [_FakeInvite("abc123", uses=6, inviter_id=42)])
    risultato = await tracker.find_used_invite(guild_v2)

    assert risultato == ("abc123", 42)


@pytest.mark.asyncio
async def test_find_used_invite_nessun_cambiamento_restituisce_none():
    tracker = InviteTracker()
    guild = _FakeGuild(100, [_FakeInvite("abc123", uses=5, inviter_id=42)])
    await tracker.refresh_guild(guild)

    # Rilettura identica: nessun invito usato (es. join da vanity URL).
    risultato = await tracker.find_used_invite(guild)

    assert risultato is None


@pytest.mark.asyncio
async def test_find_used_invite_aggiorna_la_cache_per_il_prossimo_join():
    tracker = InviteTracker()
    guild_v1 = _FakeGuild(100, [_FakeInvite("abc123", uses=5, inviter_id=42)])
    await tracker.refresh_guild(guild_v1)

    guild_v2 = _FakeGuild(100, [_FakeInvite("abc123", uses=6, inviter_id=42)])
    await tracker.find_used_invite(guild_v2)

    # Un secondo join con lo stesso stato (uses invariato rispetto
    # all'ultimo find) non deve rilevare nessun uso, perché la cache
    # è stata aggiornata dopo il primo find.
    risultato = await tracker.find_used_invite(guild_v2)
    assert risultato is None


@pytest.mark.asyncio
async def test_server_diversi_non_si_influenzano():
    tracker = InviteTracker()
    await tracker.refresh_guild(_FakeGuild(100, [_FakeInvite("a", 1, 1)]))
    await tracker.refresh_guild(_FakeGuild(200, [_FakeInvite("b", 1, 2)]))

    assert tracker._cache.get(100) == {"a": 1}
    assert tracker._cache.get(200) == {"b": 1}

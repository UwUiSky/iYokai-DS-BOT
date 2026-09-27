"""
tests/test_advanced_logs_webhook_resolution.py
====================================================
Test di _resolve_webhook_change() (cogs/logging/advanced_logs.py) —
`on_webhooks_update` non distingue create/update/delete né dice chi
è stato: questa funzione lo risolve via audit log, stesso principio
di _resolve_actor in cogs/security/anti_nuke.py (già testato lì con
lo stesso schema di guild finta).
"""

from datetime import datetime, timedelta, timezone

import discord
import pytest

from cogs.logging.advanced_logs import _resolve_webhook_change


class _FakeAuditEntry:
    def __init__(self, user_id: int, created_at) -> None:
        self.user_id = user_id
        self.created_at = created_at


class _FakeGuild:
    def __init__(self) -> None:
        self._entries: dict = {}

    def set_entries(self, action, entries) -> None:
        self._entries[action] = entries

    async def audit_logs(self, action=None, limit=10):
        for entry in self._entries.get(action, [])[:limit]:
            yield entry


class _FakeChannel:
    def __init__(self, channel_id: int, guild: _FakeGuild) -> None:
        self.id = channel_id
        self.guild = guild


@pytest.mark.asyncio
async def test_nessuna_voce_di_audit_log_restituisce_none():
    guild = _FakeGuild()
    channel = _FakeChannel(1, guild)

    risultato = await _resolve_webhook_change(channel)
    assert risultato is None


@pytest.mark.asyncio
async def test_riconosce_una_creazione_recente():
    guild = _FakeGuild()
    ora = datetime.now(timezone.utc)
    guild.set_entries(discord.AuditLogAction.webhook_create, [_FakeAuditEntry(500, ora)])
    channel = _FakeChannel(1, guild)

    risultato = await _resolve_webhook_change(channel)
    assert risultato == ("webhook_create", 500)


@pytest.mark.asyncio
async def test_voce_troppo_vecchia_viene_ignorata():
    guild = _FakeGuild()
    troppo_vecchia = datetime.now(timezone.utc) - timedelta(minutes=5)
    guild.set_entries(discord.AuditLogAction.webhook_delete, [_FakeAuditEntry(500, troppo_vecchia)])
    channel = _FakeChannel(1, guild)

    risultato = await _resolve_webhook_change(channel)
    assert risultato is None


@pytest.mark.asyncio
async def test_tra_piu_azioni_recenti_vince_la_piu_recente():
    guild = _FakeGuild()
    ora = datetime.now(timezone.utc)
    prima = ora - timedelta(seconds=5)
    guild.set_entries(discord.AuditLogAction.webhook_create, [_FakeAuditEntry(111, prima)])
    guild.set_entries(discord.AuditLogAction.webhook_update, [_FakeAuditEntry(222, ora)])
    channel = _FakeChannel(1, guild)

    risultato = await _resolve_webhook_change(channel)
    assert risultato == ("webhook_update", 222)


@pytest.mark.asyncio
async def test_permessi_insufficienti_su_unazione_non_blocca_le_altre():
    class _GuildParzialmenteBloccata(_FakeGuild):
        async def audit_logs(self, action=None, limit=10):
            if action == discord.AuditLogAction.webhook_create:
                raise discord.Forbidden(response=_FakeHTTPResponse(), message="no")
            for entry in self._entries.get(action, [])[:limit]:
                yield entry

    class _FakeHTTPResponse:
        status = 403
        reason = "Forbidden"

    guild = _GuildParzialmenteBloccata()
    ora = datetime.now(timezone.utc)
    guild.set_entries(discord.AuditLogAction.webhook_delete, [_FakeAuditEntry(999, ora)])
    channel = _FakeChannel(1, guild)

    risultato = await _resolve_webhook_change(channel)
    assert risultato == ("webhook_delete", 999)

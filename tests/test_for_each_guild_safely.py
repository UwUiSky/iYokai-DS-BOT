"""
tests/test_for_each_guild_safely.py
======================================
LC-8: nei worker periodici un server (o clan) problematico non deve
bloccare il giro per tutti gli altri. Test dell'helper comune e, per
ogni worker interessato, del comportamento "il secondo elemento viene
comunque elaborato quando il primo fallisce".
"""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.guild_iteration import for_each_guild_safely


class TestHelper:
    @pytest.mark.asyncio
    async def test_un_errore_non_ferma_gli_altri_elementi(self, caplog):
        visti = []

        async def operazione(x):
            if x == 2:
                raise RuntimeError("server rotto")
            visti.append(x)

        falliti = await for_each_guild_safely([1, 2, 3], operazione, nome_worker="test")

        assert visti == [1, 3]
        assert falliti == 1
        assert "server rotto" in caplog.text

    @pytest.mark.asyncio
    async def test_nessun_errore_zero_falliti(self):
        assert await for_each_guild_safely([1, 2], AsyncMock(), nome_worker="test") == 0

    @pytest.mark.asyncio
    async def test_la_cancellazione_non_viene_inghiottita(self):
        async def operazione(_):
            raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await for_each_guild_safely([1], operazione, nome_worker="test")


def _guild(guild_id):
    return SimpleNamespace(id=guild_id)


@pytest.mark.asyncio
async def test_retention_un_server_che_fallisce_non_blocca_gli_altri(monkeypatch):
    import core.event_log_retention as modulo

    pulite = []

    async def premium(guild_id, *_a, **_k):
        if guild_id == 1:
            raise RuntimeError("boom")
        return False

    async def prune(guild_id, soglia):
        pulite.append(guild_id)
        return 0

    monkeypatch.setattr(modulo, "guild_has_premium_access", premium)
    monkeypatch.setattr(modulo.event_log_repo, "prune_old_events_for_guild", prune)

    await modulo.EventLogRetentionService().tick(SimpleNamespace(guilds=[_guild(1), _guild(2)]))

    assert pulite == [2]


@pytest.mark.asyncio
async def test_decay_tesoreria_un_clan_che_fallisce_non_blocca_gli_altri(monkeypatch):
    import core.guild_clan_treasury_decay_worker as modulo

    # Gilde vecchie di anni: hanno già vissuto un mese intero.
    clan = lambda i: SimpleNamespace(
        id=i, guild_id=9, last_decay_period=None,
        created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    applicati = []

    async def lista():
        return [clan(1), clan(2)]

    async def decay(clan_id, periodo):
        if clan_id == 1:
            raise RuntimeError("boom")
        applicati.append(clan_id)
        return 100, 90

    monkeypatch.setattr(modulo.guild_clan_repo, "list_officialized_clans", lista)
    monkeypatch.setattr(modulo.guild_clan_repo, "apply_monthly_decay", decay)
    monkeypatch.setattr(modulo.guild_chest_repo, "deposit", AsyncMock())

    await modulo.GuildClanTreasuryDecayWorker().tick(datetime(2026, 10, 1, tzinfo=timezone.utc))

    assert applicati == [2]


@pytest.mark.asyncio
async def test_decay_settimanale_un_utente_che_fallisce_non_blocca_gli_altri(monkeypatch):
    import core.weekly_personal_decay_worker as modulo

    applicati = []

    async def lista(settimana, created_before):
        return [(1, 10), (1, 20)]

    async def decay(guild_id, user_id, settimana):
        if user_id == 10:
            raise RuntimeError("boom")
        applicati.append(user_id)
        return 50, 45

    monkeypatch.setattr(modulo.leveling_repo, "list_users_needing_weekly_decay", lista)
    monkeypatch.setattr(modulo.leveling_repo, "apply_weekly_decay", decay)
    monkeypatch.setattr(modulo.guild_chest_repo, "deposit", AsyncMock())

    await modulo.WeeklyPersonalDecayWorker().tick(datetime(2026, 10, 1, tzinfo=timezone.utc))

    assert applicati == [20]


@pytest.mark.asyncio
async def test_expiry_un_clan_che_fallisce_non_blocca_gli_altri(monkeypatch):
    import core.guild_clan_expiry_worker as modulo

    # Gilde scadute con il debito di creazione ancora aperto.
    clan = lambda i: SimpleNamespace(
        id=i, guild_id=9, category_id=None, tag=f"T{i}", treasury_balance=-15_000
    )
    eliminati = []

    async def scaduti(adesso):
        return [clan(1), clan(2)]

    async def elimina(clan_id):
        if clan_id == 1:
            raise RuntimeError("boom")
        eliminati.append(clan_id)

    monkeypatch.setattr(modulo.guild_clan_repo, "get_unofficialized_expired", scaduti)
    monkeypatch.setattr(modulo.guild_clan_repo, "delete_clan", elimina)

    bot = SimpleNamespace(get_guild=lambda _id: None)
    await modulo.GuildClanExpiryWorker().tick(bot, datetime(2026, 10, 1, tzinfo=timezone.utc))

    assert eliminati == [2]

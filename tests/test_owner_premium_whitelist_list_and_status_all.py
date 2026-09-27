"""
tests/test_owner_premium_whitelist_list_and_status_all.py
==============================================================
Test del comportamento REALE di /owner whitelist-list e
/owner premium-status-all (SPEC.md §3.2).

premium-status-all passa da core.premium.get_guild_premium_breakdown,
che legge dal SINGOLETTO globale core.database.db (import locale
dentro la funzione) — non dal riferimento nel modulo del cog. Per
questo qui si connette davvero il singoletto (stesso schema già
usato da tests/test_role_menus_cog_smoke.py), a differenza di altri
test del cog che si limitano a sostituire cogs.utility.owner_premium.db.
"""

import pytest

from cogs.utility.owner_premium import OwnerPremiumCog
from core.config import config

_OWNER_ID = config.OWNER_ID


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.deferred = False

    async def send_message(self, content: str = None, ephemeral: bool = False) -> None:
        if content is not None:
            self.sent_messages.append(content)

    async def defer(self, ephemeral: bool = False) -> None:
        self.deferred = True


class _FakeFollowup:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    async def send(self, content: str = None, ephemeral: bool = False) -> None:
        if content is not None:
            self.sent_messages.append(content)


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeGuild:
    def __init__(self, guild_id: int, name: str) -> None:
        self.id = guild_id
        self.name = name
        self.owner_id = None


class _FakeClient:
    def __init__(self, guilds: list) -> None:
        self.guilds = guilds

    def get_guild(self, guild_id: int):
        for g in self.guilds:
            if g.id == guild_id:
                return g
        return None


class _FakeInteraction:
    def __init__(self, user_id: int, guilds: list | None = None) -> None:
        self.user = _FakeUser(user_id)
        self.response = _FakeResponse()
        self.followup = _FakeFollowup()
        self.client = _FakeClient(guilds or [])


class _FakeBot:
    def get_guild(self, guild_id: int):
        return None


@pytest.mark.asyncio
async def test_whitelist_list_rifiuta_non_owner(clean_db):
    cog = OwnerPremiumCog(_FakeBot())
    interaction = _FakeInteraction(user_id=_OWNER_ID + 1)

    await cog.whitelist_list.callback(cog, interaction)

    assert "riservato al proprietario" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_whitelist_list_vuoto_avvisa(clean_db):
    from core.database import db

    await db.connect()
    try:
        cog = OwnerPremiumCog(_FakeBot())
        interaction = _FakeInteraction(user_id=_OWNER_ID)

        await cog.whitelist_list.callback(cog, interaction)

        assert "vuota" in interaction.response.sent_messages[0]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_whitelist_list_elenca_le_voci_reali(clean_db):
    from core.database import db

    await db.connect()
    try:
        await db.add_guild_to_whitelist(701, added_by=_OWNER_ID, reason="partner")
        await db.add_guild_to_whitelist(702, added_by=_OWNER_ID, reason=None)

        cog = OwnerPremiumCog(_FakeBot())
        interaction = _FakeInteraction(user_id=_OWNER_ID)

        await cog.whitelist_list.callback(cog, interaction)

        testo = interaction.response.sent_messages[0]
        assert "701" in testo
        assert "partner" in testo
        assert "702" in testo
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_premium_status_all_rifiuta_non_owner(clean_db):
    cog = OwnerPremiumCog(_FakeBot())
    interaction = _FakeInteraction(user_id=_OWNER_ID + 1)

    await cog.premium_status_all.callback(cog, interaction)

    assert "riservato al proprietario" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_premium_status_all_mostra_ogni_server_e_meccanismo(clean_db):
    from core.database import db

    await db.connect()
    try:
        await db.add_guild_to_whitelist(801, added_by=_OWNER_ID, reason=None)

        guilds = [_FakeGuild(801, "Server Whitelistato"), _FakeGuild(802, "Server Normale")]
        cog = OwnerPremiumCog(_FakeBot())
        interaction = _FakeInteraction(user_id=_OWNER_ID, guilds=guilds)

        await cog.premium_status_all.callback(cog, interaction)

        assert interaction.response.deferred is True
        testo = interaction.followup.sent_messages[0]
        assert "2 server totali" in testo
        assert "801" in testo and "whitelist" in testo
        assert "802" in testo and "nessuno sblocco proprio" in testo
    finally:
        await db.close()

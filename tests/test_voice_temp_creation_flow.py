"""
tests/test_voice_temp_creation_flow.py
=========================================
Test comportamentali di _create_temp_channel/PlatformRoleView
(SPEC.md §12.4, §12.5, §12.8) con oggetti discord.py finti minimali
— espongono solo gli attributi realmente usati, stesso principio già
seguito in tests/test_invite_tracker.py e affini.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from cogs.voice_temp.voice_temp import PlatformRoleView, _create_temp_channel
from core.repositories.voice_temp_repo import VoiceTempConfig


@dataclass
class _FakeConfig:
    category_cap: int | None = None
    role_pc_id: int | None = None
    role_console_id: int | None = None
    role_mobile_id: int | None = None


class _FakeSendable:
    def __init__(self, channel_id: int, name: str) -> None:
        self.id = channel_id
        self.name = name
        self.members = []
        self.sent = []

    async def send(self, *args, **kwargs) -> None:
        self.sent.append(kwargs)


class _FakeCategory:
    def __init__(self, channels: list) -> None:
        self.id = 1
        self.channels = channels
        self._next = _FakeSendable(999, "Canale di Test")

    async def create_voice_channel(self, **kwargs):
        return self._next


class _FakeRole:
    def __init__(self, role_id: int) -> None:
        self.id = role_id


class _FakeMember:
    def __init__(self, member_id: int, display_name: str = "Test") -> None:
        self.id = member_id
        self.display_name = display_name
        self.mention = f"<@{member_id}>"


class _FakeGuild:
    def __init__(self, guild_id: int = 100) -> None:
        self.id = guild_id
        self.default_role = _FakeRole(0)


@pytest.fixture(autouse=True)
def _fake_repo_register(monkeypatch):
    from core.repositories import voice_temp_repo as repo_module

    async def _noop(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(repo_module.voice_temp_repo, "register_channel", _noop)


class TestCreateTempChannelRispettaIlCap:
    @pytest.mark.asyncio
    async def test_categoria_piena_non_crea_il_canale(self):
        guild = _FakeGuild()
        owner = _FakeMember(1)
        categoria = _FakeCategory(channels=[object()] * 5)
        config = _FakeConfig(category_cap=5)

        channel = await _create_temp_channel(guild, owner, categoria, config)

        assert channel is None

    @pytest.mark.asyncio
    async def test_categoria_sotto_il_cap_crea_il_canale(self):
        guild = _FakeGuild()
        owner = _FakeMember(1)
        categoria = _FakeCategory(channels=[object()] * 3)
        config = _FakeConfig(category_cap=5)

        channel = await _create_temp_channel(guild, owner, categoria, config)

        assert channel is not None
        assert channel.id == 999


class TestCreateTempChannelInviaLaNotifica:
    @pytest.mark.asyncio
    async def test_notifica_inviata_senza_ruoli_piattaforma_configurati(self):
        guild = _FakeGuild()
        owner = _FakeMember(1)
        categoria = _FakeCategory(channels=[])
        config = _FakeConfig()

        channel = await _create_temp_channel(guild, owner, categoria, config)

        assert len(channel.sent) == 1
        assert "embed" in channel.sent[0]
        assert "view" not in channel.sent[0]

    @pytest.mark.asyncio
    async def test_notifica_inviata_con_view_se_almeno_un_ruolo_configurato(self):
        guild = _FakeGuild()
        owner = _FakeMember(1)
        categoria = _FakeCategory(channels=[])
        config = _FakeConfig(role_pc_id=42)

        channel = await _create_temp_channel(guild, owner, categoria, config)

        assert len(channel.sent) == 1
        assert "view" in channel.sent[0]


class TestPlatformRoleView:
    def test_nessun_ruolo_configurato_nessun_bottone(self):
        view = PlatformRoleView(_FakeConfig())
        assert view.children == []

    def test_un_ruolo_configurato_un_bottone(self):
        view = PlatformRoleView(_FakeConfig(role_pc_id=42))
        assert len(view.children) == 1
        assert view.children[0].custom_id == "iyokai_voice_temp_platform_pc"

    def test_tre_ruoli_configurati_tre_bottoni(self):
        view = PlatformRoleView(
            _FakeConfig(role_pc_id=1, role_console_id=2, role_mobile_id=3)
        )
        assert len(view.children) == 3
        custom_ids = {c.custom_id for c in view.children}
        assert custom_ids == {
            "iyokai_voice_temp_platform_pc",
            "iyokai_voice_temp_platform_console",
            "iyokai_voice_temp_platform_mobile",
        }

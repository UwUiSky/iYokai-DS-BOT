"""
tests/test_leveling_voice_notification.py
==============================================
Test della notifica di level-up per XP vocale (SPEC.md §15.12) — il
comportamento REALE di _process_guild_voice_xp(), non solo che il
cog carica. Mandata nel canale VOCALE stesso (discord.VoiceChannel
eredita da Messageable, verificato prima di scrivere il codice), non
in un canale testuale a parte.
"""

import pytest

from cogs.leveling.leveling import LevelingCog
from core.repositories.leveling_repo import VoiceMinuteGrant


class _FakeVoiceState:
    def __init__(self, self_deaf: bool = False, self_mute: bool = False) -> None:
        self.self_deaf = self_deaf
        self.self_mute = self_mute


class _FakeMember:
    def __init__(self, member_id: int, bot: bool = False, voice=None) -> None:
        self.id = member_id
        self.bot = bot
        self.voice = voice or _FakeVoiceState()
        self.mention = f"<@{member_id}>"


class _FakeVoiceChannel:
    def __init__(self, channel_id: int, members: list[_FakeMember]) -> None:
        self.id = channel_id
        self.members = members
        self.sent_messages: list[str] = []

    async def send(self, content: str) -> None:
        self.sent_messages.append(content)


class _FakeGuild:
    def __init__(self, guild_id: int, voice_channels: list[_FakeVoiceChannel]) -> None:
        self.id = guild_id
        self.voice_channels = voice_channels
        self.afk_channel = None


@pytest.fixture
async def cog_e_repo(monkeypatch):
    import cogs.leveling.leveling as leveling_module

    cog = LevelingCog(bot=None)
    cog.cog_unload()  # ferma subito il task periodico avviato nel costruttore

    chiamate_add_voice_minute: list = []

    class _RepoFinto:
        async def add_voice_minute(self, guild_id, user_id, current_channel_id, is_eligible):
            return chiamate_add_voice_minute.pop(0)

    monkeypatch.setattr(leveling_module, "leveling_repo", _RepoFinto())
    return cog, chiamate_add_voice_minute


@pytest.mark.asyncio
async def test_level_up_vocale_manda_la_notifica_nel_canale_vocale(cog_e_repo):
    cog, risultati_preimpostati = cog_e_repo

    membro = _FakeMember(member_id=1)
    canale = _FakeVoiceChannel(channel_id=100, members=[membro])
    guild = _FakeGuild(guild_id=1, voice_channels=[canale])

    risultati_preimpostati.append(
        VoiceMinuteGrant(xp_granted=10, coins_granted=1, leveled_up=True, new_level=5)
    )

    await cog._process_guild_voice_xp(guild)

    assert len(canale.sent_messages) == 1
    assert "livello **5**" in canale.sent_messages[0]
    assert membro.mention in canale.sent_messages[0]


@pytest.mark.asyncio
async def test_nessun_level_up_non_manda_nulla(cog_e_repo):
    cog, risultati_preimpostati = cog_e_repo

    membro = _FakeMember(member_id=1)
    canale = _FakeVoiceChannel(channel_id=100, members=[membro])
    guild = _FakeGuild(guild_id=1, voice_channels=[canale])

    risultati_preimpostati.append(
        VoiceMinuteGrant(xp_granted=10, coins_granted=1, leveled_up=False, new_level=4)
    )

    await cog._process_guild_voice_xp(guild)

    assert canale.sent_messages == []


@pytest.mark.asyncio
async def test_grant_none_non_manda_nulla_ne_solleva(cog_e_repo):
    cog, risultati_preimpostati = cog_e_repo

    membro = _FakeMember(member_id=1)
    canale = _FakeVoiceChannel(channel_id=100, members=[membro])
    guild = _FakeGuild(guild_id=1, voice_channels=[canale])

    risultati_preimpostati.append(None)  # non idoneo (anti-farm)

    await cog._process_guild_voice_xp(guild)  # non deve sollevare

    assert canale.sent_messages == []

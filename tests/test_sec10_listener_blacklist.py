"""
tests/test_sec10_listener_blacklist.py
==========================================
SEC-10: la blacklist globale deve fermare anche i listener che danno
qualcosa all'utente al di fuori di un'interazione (bottone/modale, già
coperti da core.ui_base.BaseView/BaseModal) — XP testuale, XP vocale,
ruoli da reazione (role menu in modalità reaction), verifica da
reazione.
"""

from unittest.mock import AsyncMock

import pytest

from cogs.leveling.leveling import LevelingCog
from cogs.security.verify import VerifyCog
from cogs.utility.role_menus import RoleMenuCog


class _FakeMember:
    def __init__(self, member_id: int, bot: bool = False) -> None:
        self.id = member_id
        self.bot = bot


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _NonDeveEssereChiamato:
    async def send(self, *args, **kwargs):
        raise AssertionError("Non deve inviare nulla per un utente in blacklist")


class _FakeMessage:
    def __init__(self, author, guild, channel) -> None:
        self.author = author
        self.guild = guild
        self.channel = channel


class TestLevelingOnMessageIgnoraBlacklist:
    @pytest.mark.asyncio
    async def test_utente_in_blacklist_non_guadagna_xp_ne_coin(self, monkeypatch):
        import cogs.leveling.leveling as leveling_module

        async def sempre_bloccato(user_id):
            return True

        monkeypatch.setattr(leveling_module.blacklist_repo, "is_user_blacklisted", sempre_bloccato)

        db_finto = AsyncMock()
        monkeypatch.setattr(leveling_module, "db", db_finto)
        leveling_repo_finto = AsyncMock()
        monkeypatch.setattr(leveling_module, "leveling_repo", leveling_repo_finto)

        cog = LevelingCog(bot=None)
        cog.cog_unload()

        messaggio = _FakeMessage(_FakeMember(1), _FakeGuild(100), _NonDeveEssereChiamato())
        await cog.on_message(messaggio)

        # Non deve nemmeno arrivare a controllare se il modulo è
        # attivo: la blacklist va controllata per prima.
        db_finto.is_module_active_for_guild.assert_not_awaited()
        leveling_repo_finto.add_text_xp.assert_not_awaited()


class TestLevelingVoceIgnoraBlacklist:
    @pytest.mark.asyncio
    async def test_membro_in_blacklist_non_guadagna_xp_vocale(self, monkeypatch):
        import cogs.leveling.leveling as leveling_module

        class _FakeVoiceState:
            self_deaf = False
            self_mute = False

        class _FakeVoiceMember:
            def __init__(self, member_id: int) -> None:
                self.id = member_id
                self.bot = False
                self.voice = _FakeVoiceState()
                self.mention = f"<@{member_id}>"

        class _FakeVoiceChannel:
            def __init__(self, channel_id: int, members: list) -> None:
                self.id = channel_id
                self.members = members
                self.sent_messages: list[str] = []

            async def send(self, content: str) -> None:
                self.sent_messages.append(content)

        class _FakeVoceGuild:
            def __init__(self, guild_id: int, voice_channels: list) -> None:
                self.id = guild_id
                self.voice_channels = voice_channels
                self.afk_channel = None

        async def bloccato_solo_utente_1(user_id):
            return user_id == 1

        monkeypatch.setattr(
            leveling_module.blacklist_repo, "is_user_blacklisted", bloccato_solo_utente_1
        )

        repo_finto = AsyncMock()
        monkeypatch.setattr(leveling_module, "leveling_repo", repo_finto)

        cog = LevelingCog(bot=None)
        cog.cog_unload()

        membro_bloccato = _FakeVoiceMember(1)
        canale = _FakeVoiceChannel(channel_id=100, members=[membro_bloccato])
        guild = _FakeVoceGuild(guild_id=1, voice_channels=[canale])

        await cog._process_guild_voice_xp(guild)

        repo_finto.add_voice_minute.assert_not_awaited()


class TestRoleMenusReactionIgnoraBlacklist:
    @pytest.mark.asyncio
    async def test_utente_in_blacklist_non_ottiene_il_ruolo(self, monkeypatch):
        import cogs.utility.role_menus as role_menus_module

        async def sempre_bloccato(user_id):
            return True

        monkeypatch.setattr(
            role_menus_module.blacklist_repo, "is_user_blacklisted", sempre_bloccato
        )
        db_finto = AsyncMock()
        monkeypatch.setattr(role_menus_module, "db", db_finto)
        repo_finto = AsyncMock()
        monkeypatch.setattr(role_menus_module, "role_menu_repo", repo_finto)

        cog = RoleMenuCog(bot=None)

        payload = type(
            "PayloadFinto",
            (),
            {
                "guild_id": 100,
                "member": _FakeMember(1),
                "message_id": 1,
                "emoji": "🎮",
            },
        )()

        await cog.on_raw_reaction_add(payload)

        db_finto.is_module_active_for_guild.assert_not_awaited()
        repo_finto.get_menu_by_message.assert_not_awaited()


class TestVerifyReactionIgnoraBlacklist:
    @pytest.mark.asyncio
    async def test_utente_in_blacklist_non_si_verifica(self, monkeypatch):
        import cogs.security.verify as verify_module

        async def sempre_bloccato(user_id):
            return True

        monkeypatch.setattr(verify_module.blacklist_repo, "is_user_blacklisted", sempre_bloccato)
        db_finto = AsyncMock()
        monkeypatch.setattr(verify_module, "db", db_finto)

        cog = VerifyCog(bot=None)
        cog.run_checks_and_finalize = AsyncMock(
            side_effect=AssertionError("non deve arrivare a verificare l'utente")
        )

        payload = type(
            "PayloadFinto",
            (),
            {
                "guild_id": 100,
                "member": _FakeMember(1),
                "message_id": 1,
                "emoji": verify_module.VERIFY_REACTION_EMOJI,
            },
        )()

        await cog.on_raw_reaction_add(payload)

        db_finto.is_module_active_for_guild.assert_not_awaited()

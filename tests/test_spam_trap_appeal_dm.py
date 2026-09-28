"""
tests/test_spam_trap_appeal_dm.py
=====================================
SEC-12: i DM ricevuti dal bot non devono più fare una query per ogni
server (moderation_repo.get_active_cases_for_user_across_guilds
sostituisce il giro su self.bot.guilds) e non più di un DM viene
elaborato ogni 30 secondi per utente.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from cogs.security.spam_trap import BAN_ACTION_TYPE, SpamTrapCog


class _FakeGuild:
    def __init__(self, guild_id: int, name: str = "Server") -> None:
        self.id = guild_id
        self.name = name


class _FakeBot:
    def __init__(self, guilds: list[_FakeGuild]) -> None:
        self._guilds = {g.id: g for g in guilds}

    def get_guild(self, guild_id: int):
        return self._guilds.get(guild_id)


class _FakeChannel:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, content: str = None, **kwargs) -> None:
        self.sent.append(content)


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.mention = f"<@{user_id}>"

    def __str__(self) -> str:
        return f"utente#{self.id}"


class _FakeMessage:
    def __init__(self, author: _FakeUser, content: str = "") -> None:
        self.author = author
        self.content = content
        self.channel = _FakeChannel()


class _CasoFinto:
    def __init__(self, guild_id: int, case_number: int) -> None:
        self.guild_id = guild_id
        self.case_number = case_number


@pytest.fixture
def cog_con_repo_finto(monkeypatch):
    import cogs.security.spam_trap as spam_trap_module

    moderation_repo_finto = AsyncMock()
    moderation_repo_finto.get_active_cases_for_user_across_guilds.return_value = []
    monkeypatch.setattr(spam_trap_module, "moderation_repo", moderation_repo_finto)

    spam_trap_repo_finto = AsyncMock()
    monkeypatch.setattr(spam_trap_module, "spam_trap_repo", spam_trap_repo_finto)

    guild = _FakeGuild(100)
    bot = _FakeBot([guild])
    cog = SpamTrapCog(bot=bot)
    return cog, moderation_repo_finto, spam_trap_repo_finto, guild


class TestUnaSolaQuery:
    @pytest.mark.asyncio
    async def test_nessun_caso_attivo_usa_una_sola_query(self, cog_con_repo_finto):
        cog, moderation_repo_finto, _, _ = cog_con_repo_finto
        messaggio = _FakeMessage(_FakeUser(1000001))

        await cog._handle_possible_appeal(messaggio)

        moderation_repo_finto.get_active_cases_for_user_across_guilds.assert_awaited_once_with(
            1000001, BAN_ACTION_TYPE
        )
        # Il vecchio metodo (una query per server) non deve più essere
        # chiamato.
        moderation_repo_finto.get_latest_active_case.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_nessun_caso_attivo_non_manda_nessun_messaggio(self, cog_con_repo_finto):
        cog, _, _, _ = cog_con_repo_finto
        messaggio = _FakeMessage(_FakeUser(1000002))

        await cog._handle_possible_appeal(messaggio)

        assert messaggio.channel.sent == []


class TestFlussoConCasoAttivo:
    @pytest.mark.asyncio
    async def test_caso_attivo_ma_appello_recente_rifiutato(self, cog_con_repo_finto):
        cog, moderation_repo_finto, spam_trap_repo_finto, guild = cog_con_repo_finto
        moderation_repo_finto.get_active_cases_for_user_across_guilds.return_value = [
            _CasoFinto(guild_id=guild.id, case_number=1)
        ]
        spam_trap_repo_finto.get_last_appeal.return_value = datetime.now(timezone.utc)

        messaggio = _FakeMessage(_FakeUser(1000003))
        await cog._handle_possible_appeal(messaggio)

        assert any("24 hours" in (testo or "") for testo in messaggio.channel.sent)

    @pytest.mark.asyncio
    async def test_caso_in_un_server_che_il_bot_ha_lasciato_viene_ignorato(
        self, cog_con_repo_finto
    ):
        # self.bot.get_guild(...) restituisce None per un server che
        # il bot non frequenta più — quel caso non deve contare come
        # candidato.
        cog, moderation_repo_finto, _, _ = cog_con_repo_finto
        moderation_repo_finto.get_active_cases_for_user_across_guilds.return_value = [
            _CasoFinto(guild_id=999999, case_number=1)
        ]

        messaggio = _FakeMessage(_FakeUser(1000004))
        await cog._handle_possible_appeal(messaggio)

        assert messaggio.channel.sent == []


class TestRateLimitDM:
    @pytest.mark.asyncio
    async def test_secondo_dm_entro_30_secondi_viene_ignorato(self, cog_con_repo_finto):
        cog, moderation_repo_finto, _, _ = cog_con_repo_finto
        utente = _FakeUser(1000005)

        await cog._handle_possible_appeal(_FakeMessage(utente))
        await cog._handle_possible_appeal(_FakeMessage(utente))

        assert moderation_repo_finto.get_active_cases_for_user_across_guilds.await_count == 1

    @pytest.mark.asyncio
    async def test_utenti_diversi_non_si_bloccano_a_vicenda(self, cog_con_repo_finto):
        cog, moderation_repo_finto, _, _ = cog_con_repo_finto

        await cog._handle_possible_appeal(_FakeMessage(_FakeUser(1000006)))
        await cog._handle_possible_appeal(_FakeMessage(_FakeUser(1000007)))

        assert moderation_repo_finto.get_active_cases_for_user_across_guilds.await_count == 2

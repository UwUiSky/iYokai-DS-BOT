"""
tests/test_spam_trap_staff_exempt.py
========================================
Test SEC-8b: la trappola non deve bannare lo staff, e i bottoni di
appello (Unban/Reject/Reply) devono richiedere "Bannare i membri" a
chi li preme.
"""

from unittest.mock import AsyncMock

import discord
import pytest

from cogs.security.spam_trap import AppealActionsView, _is_staff_exempt
from tests.support.discord_fakes import fake_guild, fake_member, fake_role


class TestIsStaffExempt:
    def test_manage_messages_e_esente(self):
        ruolo_bot = fake_role(role_id=1, position=10)
        guild = fake_guild(me=fake_member(user_id=999, bot=True, roles=[ruolo_bot]))
        membro = fake_member(
            user_id=1, guild_permissions=discord.Permissions(manage_messages=True)
        )
        assert _is_staff_exempt(membro, guild, staff_role_ids=set()) is True

    def test_administrator_e_esente(self):
        ruolo_bot = fake_role(role_id=1, position=10)
        guild = fake_guild(me=fake_member(user_id=999, bot=True, roles=[ruolo_bot]))
        membro = fake_member(
            user_id=1, guild_permissions=discord.Permissions(administrator=True)
        )
        assert _is_staff_exempt(membro, guild, staff_role_ids=set()) is True

    def test_ruolo_staff_configurato_e_esente(self):
        ruolo_bot = fake_role(role_id=1, position=10)
        guild = fake_guild(me=fake_member(user_id=999, bot=True, roles=[ruolo_bot]))
        ruolo_staff = fake_role(role_id=200, position=2)
        membro = fake_member(user_id=1, roles=[ruolo_staff])
        assert _is_staff_exempt(membro, guild, staff_role_ids={200}) is True

    def test_ruolo_sopra_il_bot_e_esente(self):
        ruolo_bot = fake_role(role_id=1, position=5)
        guild = fake_guild(me=fake_member(user_id=999, bot=True, roles=[ruolo_bot]))
        ruolo_alto = fake_role(role_id=300, position=10)
        membro = fake_member(user_id=1, roles=[ruolo_alto])
        assert _is_staff_exempt(membro, guild, staff_role_ids=set()) is True

    def test_membro_qualsiasi_non_e_esente(self):
        ruolo_bot = fake_role(role_id=1, position=10)
        guild = fake_guild(me=fake_member(user_id=999, bot=True, roles=[ruolo_bot]))
        ruolo_basso = fake_role(role_id=300, position=2)
        membro = fake_member(user_id=1, roles=[ruolo_basso])
        assert _is_staff_exempt(membro, guild, staff_role_ids=set()) is False


class TestHandleTriggerRispettaLEsenzione:
    @pytest.mark.asyncio
    async def test_membro_esente_non_viene_bannato(self, monkeypatch):
        import cogs.security.spam_trap as spam_trap_module

        ruolo_bot = fake_role(role_id=1, position=10)
        guild = fake_guild(guild_id=100, me=fake_member(user_id=999, bot=True, roles=[ruolo_bot]))
        guild.ban = AsyncMock()

        membro = fake_member(
            user_id=1, guild_permissions=discord.Permissions(manage_messages=True)
        )

        async def _nessun_ruolo_staff(guild_id):
            return []

        cog = spam_trap_module.SpamTrapCog(bot=None)
        monkeypatch.setattr(cog, "_staff_role_ids", _nessun_ruolo_staff)

        canale = AsyncMock()
        messaggio = type(
            "MessaggioFinto", (), {"guild": guild, "author": membro, "channel": canale, "id": 1}
        )()

        await cog._handle_trigger(messaggio)

        guild.ban.assert_not_called()
        canale.fetch_message.assert_not_called()


class TestAppealActionsViewInteractionCheck:
    @pytest.mark.asyncio
    async def test_senza_ban_members_viene_rifiutato(self):
        view = AppealActionsView(guild_id=100, case_number=1, user_id=42)
        membro = fake_member(user_id=1, guild_permissions=discord.Permissions.none())
        interaction = AsyncMock()
        interaction.user = membro

        risultato = await view.interaction_check(interaction)

        assert risultato is False
        interaction.response.send_message.assert_awaited_once()
        messaggio = interaction.response.send_message.call_args.args[0]
        assert "bannare" in messaggio.lower()

    @pytest.mark.asyncio
    async def test_con_ban_members_viene_accettato(self):
        view = AppealActionsView(guild_id=100, case_number=1, user_id=42)
        membro = fake_member(
            user_id=1, guild_permissions=discord.Permissions(ban_members=True)
        )
        interaction = AsyncMock()
        interaction.user = membro

        risultato = await view.interaction_check(interaction)

        assert risultato is True
        interaction.response.send_message.assert_not_awaited()

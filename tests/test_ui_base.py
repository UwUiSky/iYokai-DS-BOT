"""
tests/test_ui_base.py
=========================
Test di core/ui_base.py (SEC-10): BaseView/BaseModal rifiutano
utenti/server in blacklist e registrano gli errori invece di farli
sparire in silenzio (LC-4).
"""

from unittest.mock import AsyncMock

import discord
import pytest

from core.ui_base import BaseModal, BaseView


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


def _fake_interaction(user_id: int = 1, guild_id: int | None = 100) -> AsyncMock:
    interaction = AsyncMock()
    interaction.user = AsyncMock()
    interaction.user.id = user_id
    interaction.guild = _FakeGuild(guild_id) if guild_id is not None else None
    interaction.response = AsyncMock()
    interaction.response.is_done = lambda: False
    return interaction


class TestBaseViewInteractionCheck:
    @pytest.mark.asyncio
    async def test_utente_in_blacklist_viene_rifiutato(self, monkeypatch):
        import core.ui_base as ui_base_module

        async def utente_bloccato(user_id):
            return user_id == 1

        async def guild_mai_bloccata(guild_id):
            return False

        monkeypatch.setattr(
            ui_base_module.blacklist_repo, "is_user_blacklisted", utente_bloccato
        )
        monkeypatch.setattr(
            ui_base_module.blacklist_repo, "is_guild_blacklisted", guild_mai_bloccata
        )

        view = BaseView()
        interaction = _fake_interaction(user_id=1)

        risultato = await view.interaction_check(interaction)

        assert risultato is False
        interaction.response.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_server_in_blacklist_viene_rifiutato_senza_risposta(self, monkeypatch):
        import core.ui_base as ui_base_module

        async def utente_mai_bloccato(user_id):
            return False

        async def guild_bloccata(guild_id):
            return guild_id == 100

        monkeypatch.setattr(
            ui_base_module.blacklist_repo, "is_user_blacklisted", utente_mai_bloccato
        )
        monkeypatch.setattr(
            ui_base_module.blacklist_repo, "is_guild_blacklisted", guild_bloccata
        )

        view = BaseView()
        interaction = _fake_interaction(user_id=5, guild_id=100)

        risultato = await view.interaction_check(interaction)

        assert risultato is False
        interaction.response.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_utente_non_in_blacklist_viene_accettato(self, monkeypatch):
        import core.ui_base as ui_base_module

        async def mai_bloccato(*_args):
            return False

        monkeypatch.setattr(ui_base_module.blacklist_repo, "is_user_blacklisted", mai_bloccato)
        monkeypatch.setattr(ui_base_module.blacklist_repo, "is_guild_blacklisted", mai_bloccato)

        view = BaseView()
        interaction = _fake_interaction(user_id=5, guild_id=100)

        risultato = await view.interaction_check(interaction)

        assert risultato is True
        interaction.response.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dm_senza_guild_controlla_solo_l_utente(self, monkeypatch):
        import core.ui_base as ui_base_module

        chiamate_guild = []

        async def mai_bloccato_utente(user_id):
            return False

        async def registra_e_rifiuta_guild(guild_id):
            chiamate_guild.append(guild_id)
            return False

        monkeypatch.setattr(
            ui_base_module.blacklist_repo, "is_user_blacklisted", mai_bloccato_utente
        )
        monkeypatch.setattr(
            ui_base_module.blacklist_repo, "is_guild_blacklisted", registra_e_rifiuta_guild
        )

        view = BaseView()
        interaction = _fake_interaction(user_id=5, guild_id=None)

        risultato = await view.interaction_check(interaction)

        assert risultato is True
        assert chiamate_guild == []


class TestBaseViewOnError:
    @pytest.mark.asyncio
    async def test_on_error_risponde_in_modo_effimero_e_non_solleva(self):
        view = BaseView()
        interaction = _fake_interaction()

        await view.on_error(interaction, RuntimeError("errore di prova"), item=None)

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_on_error_usa_followup_se_gia_risposto(self):
        view = BaseView()
        interaction = _fake_interaction()
        interaction.response.is_done = lambda: True

        await view.on_error(interaction, RuntimeError("errore di prova"), item=None)

        interaction.response.send_message.assert_not_awaited()
        interaction.followup.send.assert_awaited_once()


class TestBaseModal:
    @pytest.mark.asyncio
    async def test_interaction_check_rifiuta_utente_in_blacklist(self, monkeypatch):
        import core.ui_base as ui_base_module

        async def utente_bloccato(user_id):
            return True

        async def guild_mai_bloccata(guild_id):
            return False

        monkeypatch.setattr(
            ui_base_module.blacklist_repo, "is_user_blacklisted", utente_bloccato
        )
        monkeypatch.setattr(
            ui_base_module.blacklist_repo, "is_guild_blacklisted", guild_mai_bloccata
        )

        class ModaleDiProva(BaseModal, title="Prova"):
            pass

        modal = ModaleDiProva()
        interaction = _fake_interaction()

        risultato = await modal.interaction_check(interaction)

        assert risultato is False
        interaction.response.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_on_error_risponde_in_modo_effimero(self):
        class ModaleDiProva(BaseModal, title="Prova"):
            pass

        modal = ModaleDiProva()
        interaction = _fake_interaction()

        await modal.on_error(interaction, RuntimeError("errore di prova"))

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True

"""
tests/test_spam_trap_appello_bottoni.py
=======================================
I bottoni dell'appello dello spam-trap (Unban, Reject, Reply):
- LC-5 / LIM-26 / #16: devono rispondere anche dopo un riavvio del bot;
- LIM-25: Unban e Reject rispondono subito (`defer`) e lavorano dopo.

Il "riavvio" è un secondo `commands.Bot` vero (non collegato) che non
ha mai visto il messaggio: riceve il clic come lo manda Discord, con il
solo `custom_id` del bottone. Database vero per i casi.
"""

import asyncio
from unittest.mock import MagicMock, create_autospec

import discord
import pytest
from discord.components import _component_factory
from discord.ext import commands

import cogs.security.spam_trap as modulo
import core.ui_base as modulo_ui_base
from cogs.security.spam_trap import BAN_ACTION_TYPE, AppealActionsView
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_message

GUILD_ID = 100
UTENTE_ID = 42
BOT_ID = 999


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch, clean_db):
    monkeypatch.setattr(moderation_repo, "_pool_provider", lambda: clean_db)

    async def mai_bloccato(*_args):
        return False

    monkeypatch.setattr(modulo_ui_base.blacklist_repo, "is_user_blacklisted", mai_bloccato)
    monkeypatch.setattr(modulo_ui_base.blacklist_repo, "is_guild_blacklisted", mai_bloccato)


async def _caso_spam_trap() -> int:
    return await moderation_repo.create_case(
        guild_id=GUILD_ID,
        user_id=UTENTE_ID,
        moderator_id=BOT_ID,
        action_type=BAN_ACTION_TYPE,
        reason="Triggered the spam trap channel",
    )


async def _casi_attivi() -> list[int]:
    casi = await moderation_repo.get_active_cases_for_user_across_guilds(
        UTENTE_ID, BAN_ACTION_TYPE
    )
    return [caso.case_number for caso in casi]


def _bot_vero() -> commands.Bot:
    return commands.Bot(command_prefix="!", intents=discord.Intents.none())


def _clic(vista: AppealActionsView, etichetta: str, server: MagicMock) -> MagicMock:
    """
    Il clic come arriva da Discord: l'interazione porta il messaggio
    con i suoi componenti (nella forma "letta dal messaggio", non gli
    oggetti della View) e il custom_id del bottone premuto.
    """
    messaggio = fake_message(guild=server)
    messaggio.components = [_component_factory(riga) for riga in vista.to_components()]
    messaggio.flags = discord.MessageFlags()

    staff = fake_member(user_id=7, guild_permissions=discord.Permissions(ban_members=True))
    interazione = fake_interaction(guild=server, user=staff)
    interazione.message = messaggio
    bottone = next(
        componente
        for riga in messaggio.components
        for componente in riga.children
        if componente.label == etichetta
    )
    interazione.data = {"custom_id": bottone.custom_id, "component_type": 2}
    return interazione


async def _consegna(bot: commands.Bot, interazione: MagicMock) -> None:
    """Passa il clic al bot come fa discord.py e aspetta che venga gestito."""
    interazione.client = bot
    prima = asyncio.all_tasks()
    bot._connection._view_store.dispatch_view(2, interazione.data["custom_id"], interazione)
    nuovi = asyncio.all_tasks() - prima
    if nuovi:
        await asyncio.gather(*nuovi)


def _server_con_bot(bot: commands.Bot, monkeypatch) -> MagicMock:
    server = fake_guild(GUILD_ID, "Alpha")
    monkeypatch.setattr(bot, "get_guild", lambda guild_id: server if guild_id == GUILD_ID else None)
    utente = create_autospec(discord.User, instance=True)

    async def _fetch_user(_user_id):
        return utente

    monkeypatch.setattr(bot, "fetch_user", _fetch_user)
    server.utente_bannato = utente
    return server


# ====================================================================
# M 3.9 — i bottoni sopravvivono al riavvio
# ====================================================================
def test_custom_id_porta_server_caso_e_utente():
    vista = AppealActionsView(GUILD_ID, 15, UTENTE_ID)

    assert vista.is_persistent()
    assert vista.timeout is None
    identificativi = {figlio.custom_id for figlio in vista.children}
    assert identificativi == {
        f"spamtrap_appeal:unban:{GUILD_ID}:15:{UTENTE_ID}",
        f"spamtrap_appeal:reject:{GUILD_ID}:15:{UTENTE_ID}",
        f"spamtrap_appeal:reply:{GUILD_ID}:15:{UTENTE_ID}",
    }
    assert all(len(identificativo) <= 100 for identificativo in identificativi)


async def test_dopo_un_riavvio_il_bottone_unban_risponde(monkeypatch):
    caso = await _caso_spam_trap()
    vista_prima_del_riavvio = AppealActionsView(GUILD_ID, caso, UTENTE_ID)

    # Riavvio: un bot nuovo, che carica il cog e non sa nulla del messaggio.
    bot = _bot_vero()
    await modulo.setup(bot)
    server = _server_con_bot(bot, monkeypatch)
    interazione = _clic(vista_prima_del_riavvio, "Unban", server)

    await _consegna(bot, interazione)

    server.unban.assert_awaited_once()
    assert server.unban.call_args.args[0].id == UTENTE_ID
    assert await _casi_attivi() == []
    await bot.close()


async def test_dopo_un_riavvio_il_bottone_reply_apre_il_modulo(monkeypatch):
    caso = await _caso_spam_trap()
    vista = AppealActionsView(GUILD_ID, caso, UTENTE_ID)
    bot = _bot_vero()
    await modulo.setup(bot)
    server = _server_con_bot(bot, monkeypatch)
    interazione = _clic(vista, "Reply", server)

    await _consegna(bot, interazione)

    interazione.response.send_modal.assert_awaited_once()
    modulo_risposta = interazione.response.send_modal.call_args.args[0]
    assert modulo_risposta.user_id == UTENTE_ID
    await bot.close()


async def test_dopo_un_riavvio_chi_non_puo_bannare_viene_rifiutato(monkeypatch):
    caso = await _caso_spam_trap()
    vista = AppealActionsView(GUILD_ID, caso, UTENTE_ID)
    bot = _bot_vero()
    await modulo.setup(bot)
    server = _server_con_bot(bot, monkeypatch)
    interazione = _clic(vista, "Unban", server)
    interazione.user = fake_member(user_id=8, guild_permissions=discord.Permissions.none())

    await _consegna(bot, interazione)

    server.unban.assert_not_awaited()
    assert await _casi_attivi() == [caso]
    assert "bannare" in interazione.response.send_message.call_args.args[0].lower()
    await bot.close()


# ====================================================================
# M 3.11 — Unban e Reject rispondono subito, poi lavorano (LIM-25)
# ====================================================================
def _interazione_staff(server: MagicMock, ordine: list[str]) -> MagicMock:
    """Interazione che annota in `ordine` le chiamate, per vedere quale viene prima."""
    staff = fake_member(user_id=7, guild_permissions=discord.Permissions(ban_members=True))
    interazione = fake_interaction(guild=server, user=staff)
    interazione.client = create_autospec(commands.Bot, instance=True)
    interazione.client.get_guild.return_value = server
    utente = create_autospec(discord.User, instance=True)
    interazione.client.fetch_user.return_value = utente

    def _annota(nome):
        async def _chiamata(*_args, **_kwargs):
            ordine.append(nome)

        return _chiamata

    interazione.response.defer.side_effect = _annota("defer")
    interazione.response.edit_message.side_effect = _annota("edit_message")
    interazione.edit_original_response.side_effect = _annota("edit_original_response")

    async def _fetch_user(_user_id):
        ordine.append("fetch_user")
        return utente

    interazione.client.fetch_user.side_effect = _fetch_user
    server.unban.side_effect = _annota("unban")
    utente.send.side_effect = _annota("dm")
    return interazione


async def test_unban_chiama_defer_per_primo_e_poi_aggiorna_il_messaggio():
    caso = await _caso_spam_trap()
    ordine: list[str] = []
    server = fake_guild(GUILD_ID, "Alpha")
    interazione = _interazione_staff(server, ordine)

    await AppealActionsView(GUILD_ID, caso, UTENTE_ID).unban(interazione)

    assert ordine == ["defer", "unban", "fetch_user", "dm", "edit_original_response"]
    aggiornamento = interazione.edit_original_response.call_args.kwargs
    assert "Unbanned" in aggiornamento["content"]
    assert all(figlio.item.disabled for figlio in aggiornamento["view"].children)
    assert await _casi_attivi() == []


async def test_reject_chiama_defer_per_primo():
    caso = await _caso_spam_trap()
    ordine: list[str] = []
    server = fake_guild(GUILD_ID, "Alpha")
    interazione = _interazione_staff(server, ordine)

    await AppealActionsView(GUILD_ID, caso, UTENTE_ID).reject(interazione)

    assert ordine == ["defer", "fetch_user", "dm", "edit_original_response"]
    assert "rejected" in interazione.edit_original_response.call_args.kwargs["content"]
    # Il rifiuto non toglie il ban: il caso resta attivo.
    assert await _casi_attivi() == [caso]


async def test_unban_senza_permessi_avvisa_dopo_il_defer_e_non_chiude_il_caso():
    caso = await _caso_spam_trap()
    ordine: list[str] = []
    server = fake_guild(GUILD_ID, "Alpha")
    interazione = _interazione_staff(server, ordine)
    risposta = MagicMock()
    risposta.status = 403
    risposta.reason = "Forbidden"
    server.unban.side_effect = discord.Forbidden(risposta, "Missing Permissions")

    await AppealActionsView(GUILD_ID, caso, UTENTE_ID).unban(interazione)

    assert ordine == ["defer"]
    interazione.followup.send.assert_awaited_once()
    assert interazione.followup.send.call_args.kwargs["ephemeral"] is True
    interazione.response.send_message.assert_not_awaited()
    assert await _casi_attivi() == [caso]


async def test_reply_apre_il_modulo_come_prima_risposta():
    server = fake_guild(GUILD_ID, "Alpha")
    interazione = _interazione_staff(server, [])

    await AppealActionsView(GUILD_ID, 1, UTENTE_ID).reply(interazione)

    interazione.response.send_modal.assert_awaited_once()
    interazione.response.defer.assert_not_awaited()


async def test_modulo_di_risposta_chiama_defer_prima_di_mandare_il_dm():
    ordine: list[str] = []
    server = fake_guild(GUILD_ID, "Alpha")
    interazione = _interazione_staff(server, ordine)
    modulo_risposta = modulo.StaffReplyModal(UTENTE_ID)
    modulo_risposta.message_label.component._value = "We are looking into it."

    await modulo_risposta.on_submit(interazione)

    assert ordine == ["defer", "fetch_user", "dm"]
    assert interazione.response.defer.call_args.kwargs == {"ephemeral": True}
    interazione.followup.send.assert_awaited_once()
    assert interazione.followup.send.call_args.kwargs["ephemeral"] is True

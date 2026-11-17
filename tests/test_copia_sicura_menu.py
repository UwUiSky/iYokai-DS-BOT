"""
tests/test_copia_sicura_menu.py
===============================
Menu «Richiedi copia sicura» (D74, #160): solo «Gestisci messaggi», risposta nascosta, copie rifatte e righe di
scheda, video solo in ticket e ModMail, pausa di 10 secondi per utente, nome del menu entro 32 caratteri.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

import cogs.utility.copia_sicura as modulo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel


@pytest.fixture
def cog(monkeypatch):
    modulo._ultima.clear()
    monkeypatch.setattr(modulo, "_e_canale_conversazione", AsyncMock(return_value=False))
    return modulo.CopiaSicuraCog(SimpleNamespace(tree=SimpleNamespace()))


def _inter(permesso=True, utente=5):
    i = fake_interaction(guild=fake_guild(10), user=fake_member(user_id=utente), channel=fake_text_channel(30))
    i.permissions = discord.Permissions(manage_messages=permesso)
    return i


def _messaggio(n=1):
    return SimpleNamespace(attachments=[SimpleNamespace(filename=f"{k}.png") for k in range(n)])


def test_nome_del_menu_entro_32_caratteri():
    assert len(modulo.NOME_MENU) <= 32


async def test_senza_gestisci_messaggi_si_rifiuta_e_non_si_converte(cog, monkeypatch):
    prepara = AsyncMock()
    monkeypatch.setattr(modulo.allegati_mostra, "prepara", prepara)
    i = _inter(permesso=False)
    await cog.menu(i, _messaggio())
    prepara.assert_not_awaited()
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True


async def test_risposta_nascosta_con_copie_e_righe_e_senza_video_nei_canali_normali(cog, monkeypatch):
    prepara = AsyncMock(return_value=([("a.png", b"\x89PNG")], ["`b.pdf` (pdf): file non conservato"]))
    monkeypatch.setattr(modulo.allegati_mostra, "prepara", prepara)
    i = _inter()
    await cog.menu(i, _messaggio(2))
    i.response.defer.assert_awaited_once_with(ephemeral=True)
    kw = i.followup.send.await_args.kwargs
    assert kw["ephemeral"] is True and len(kw["files"]) == 1 and "b.pdf" in i.followup.send.await_args.args[0]
    assert prepara.await_args.kwargs["con_video"] is False and prepara.await_args.kwargs["massimo"] == 5


async def test_video_solo_in_ticket_o_modmail(cog, monkeypatch):
    prepara = AsyncMock(return_value=([], []))
    monkeypatch.setattr(modulo.allegati_mostra, "prepara", prepara)
    monkeypatch.setattr(modulo, "_e_canale_conversazione", AsyncMock(return_value=True))
    await cog.menu(_inter(), _messaggio())
    assert prepara.await_args.kwargs["con_video"] is True


async def test_pausa_di_10_secondi_per_utente(cog, monkeypatch):
    prepara = AsyncMock(return_value=([], []))
    monkeypatch.setattr(modulo.allegati_mostra, "prepara", prepara)
    await cog.menu(_inter(utente=7), _messaggio())
    i = _inter(utente=7)
    await cog.menu(i, _messaggio())
    assert prepara.await_count == 1 and "Aspetta" in i.response.send_message.await_args.args[0]
    await cog.menu(_inter(utente=8), _messaggio())
    assert prepara.await_count == 2


async def test_messaggio_senza_allegati(cog, monkeypatch):
    prepara = AsyncMock()
    monkeypatch.setattr(modulo.allegati_mostra, "prepara", prepara)
    i = _inter()
    await cog.menu(i, _messaggio(0))
    prepara.assert_not_awaited()
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True


async def test_il_bot_principale_accetta_il_sesto_menu_su_messaggio():
    from discord.ext import commands

    from core.blacklist_tree import BlacklistAwareCommandTree

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none(), tree_cls=BlacklistAwareCommandTree)

    async def cb(i, m):
        pass

    for n in range(6):
        bot.tree.add_command(discord.app_commands.ContextMenu(name=f"Menu {n}", callback=cb))
    assert len(bot.tree.get_commands(type=discord.AppCommandType.message)) == 6
    await bot.close()

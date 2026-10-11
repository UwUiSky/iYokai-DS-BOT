"""
tests/test_role_menus_limiti.py
==================================
M 10.7 (LIM-17 e REVIEW §4): limiti dei testi, emoji controllata,
pubblicare PRIMA di salvare l'opzione, verità se la modifica fallisce,
menu senza opzioni cancellato, `toggle=False` rispettato.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

import cogs.utility.role_menus as rm
from cogs.utility.role_menus import RoleMenuCog, _build_embed
from core.repositories.role_menu_repo import RoleMenu, RoleMenuOption, RoleMenuRepository
from core.role_menu_logic import valida_emoji
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_message,
    fake_role,
    fake_text_channel,
)
from tests.support.percorsi import comando_nel_gruppo


# ---------------------------------------------------------------- logica pura
@pytest.mark.parametrize(
    "testo", ["🎮", "👍🏽", "❤️", "1️⃣", "🇮🇹", "<:logo:123456789012345678>", "<a:ballo:123456789012345678>"]
)
def test_emoji_valide(testo):
    assert valida_emoji(testo)


@pytest.mark.parametrize("testo", ["", "ciao", "a", ":smile:", "🎮🎮🎮🎮🎮🎮🎮🎮🎮🎮🎮🎮🎮🎮🎮🎮🎮🎮🎮🎮🎮", "<:x:abc>", " "])
def test_emoji_non_valide(testo):
    assert not valida_emoji(testo)


# ------------------------------------------------------------------- embed
def _menu(mode="button", toggle=True, message_id=None, menu_id=1):
    return RoleMenu(
        id=menu_id, guild_id=1, channel_id=700, message_id=message_id, mode=mode,
        toggle=toggle, max_selectable=None, title="Menu", description="",
    )


def _opzioni(n, label="E" * 80):
    return [
        RoleMenuOption(id=i, menu_id=1, role_id=1000 + i, emoji="🎮", label=label, position=i)
        for i in range(n)
    ]


@pytest.mark.parametrize("modo", ["button", "select", "reaction"])
def test_embed_con_25_opzioni_lunghe_rispetta_i_limiti(modo):
    embed = _build_embed(_menu(mode=modo), _opzioni(25))
    assert all(len(c.value) <= 1024 for c in embed.fields)
    assert len(embed.fields) <= 25
    assert len(embed) <= 6000


# ------------------------------------------------------------------ comandi
@pytest.mark.asyncio
async def test_limiti_delle_opzioni_dei_comandi(clean_db):
    from core.database import db

    await db.connect()  # setup() legge i menu esistenti dal database
    try:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        await rm.setup(bot)
    finally:
        await db.close()
    crea = {o["name"]: o for o in comando_nel_gruppo("gestione", "ruoli menu-crea").to_dict(bot.tree)["options"]}
    assert crea["title"]["max_length"] == 256
    assert crea["description"]["max_length"] == 2000
    aggiungi = {o["name"]: o for o in comando_nel_gruppo("gestione", "ruoli menu-aggiungi").to_dict(bot.tree)["options"]}
    assert aggiungi["label"]["max_length"] == 80


class _Scena:
    def __init__(self, clean_db, monkeypatch, mode="button", toggle=True):
        self.repo = RoleMenuRepository(pool_provider=lambda: clean_db)
        monkeypatch.setattr(rm, "role_menu_repo", self.repo)
        monkeypatch.setattr(rm.db, "is_module_active_for_guild", AsyncMock(return_value=True))
        bot_member = fake_member(user_id=999, name="Yokai Bot", bot=True)
        bot_member.top_role = fake_role(role_id=100, name="Bot", position=50)
        self.guild = fake_guild(guild_id=1, owner_id=1, me=bot_member)
        ruolo_admin = fake_role(role_id=200, name="Admin", position=30)
        self.admin = fake_member(user_id=2, roles=[ruolo_admin])
        self.admin.top_role = ruolo_admin
        self.ruoli = {rid: fake_role(role_id=rid, name=f"R{rid}", position=1) for rid in range(1000, 1030)}
        self.guild.get_role.side_effect = self.ruoli.get
        self.canale = fake_text_channel(channel_id=700)
        self.messaggio = fake_message(message_id=555)
        self.messaggio.reactions = []
        self.canale.send.return_value = self.messaggio
        self.canale.fetch_message = AsyncMock(return_value=self.messaggio)
        self.guild.get_channel.return_value = self.canale
        self.bot = MagicMock()
        self.bot.get_emoji.return_value = None
        self.cog = RoleMenuCog(self.bot)
        self.mode, self.toggle = mode, toggle

    async def menu(self):
        self.menu_id = await self.repo.create_menu(
            guild_id=1, channel_id=700, mode=self.mode, toggle=self.toggle,
            max_selectable=None, title="Menu", description="",
        )
        return self.menu_id

    def admin_interaction(self):
        return fake_interaction(guild=self.guild, user=self.admin, channel=self.canale)

    async def aggiungi(self, rid, emoji="🎮", label="Gioca"):
        interazione = self.admin_interaction()
        await self.cog.add_option_cmd.callback(
            self.cog, interazione, menu_id=self.menu_id, role=self.ruoli[rid], emoji=emoji, label=label
        )
        return interazione


def _testo_risposta(interazione) -> str:
    if interazione.followup.send.await_args is not None:
        return interazione.followup.send.await_args.args[0]
    return interazione.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_emoji_non_valida_rifiutata_e_opzione_non_salvata(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    interazione = await s.aggiungi(1000, emoji="ciao")
    assert "emoji" in _testo_risposta(interazione).lower()
    assert await s.repo.count_options(s.menu_id) == 0
    s.canale.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_emoji_personalizzata_sconosciuta_rifiutata(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    interazione = await s.aggiungi(1000, emoji="<:x:123456789012345678>")
    assert "emoji" in _testo_risposta(interazione).lower()
    assert await s.repo.count_options(s.menu_id) == 0


@pytest.mark.asyncio
async def test_pubblicazione_fallita_non_salva_l_opzione_e_lo_dice(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    s.canale.send.side_effect = discord.HTTPException(MagicMock(status=400, reason="x"), "troppo lungo")

    interazione = await s.aggiungi(1000)

    assert await s.repo.count_options(s.menu_id) == 0
    testo = _testo_risposta(interazione)
    assert "non" in testo.lower() and "aggiunta" not in testo.lower().replace("non è stata aggiunta", "")


@pytest.mark.asyncio
async def test_aggiunta_riuscita_salva_dopo_aver_pubblicato(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    interazione = await s.aggiungi(1000)
    assert await s.repo.count_options(s.menu_id) == 1
    s.canale.send.assert_awaited_once()
    assert "aggiunta" in _testo_risposta(interazione).lower()


@pytest.mark.asyncio
async def test_messaggio_cancellato_a_mano_viene_ripubblicato(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    await s.aggiungi(1000)
    s.canale.fetch_message.side_effect = discord.NotFound(MagicMock(status=404, reason="x"), "no")
    s.canale.send.reset_mock()

    await s.aggiungi(1001)

    s.canale.send.assert_awaited_once()
    assert await s.repo.count_options(s.menu_id) == 2


@pytest.mark.asyncio
async def test_togliere_l_ultima_opzione_cancella_il_menu(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, mode="select")
    await s.menu()
    await s.aggiungi(1000, emoji=None)
    interazione = s.admin_interaction()

    await s.cog.remove_option_cmd.callback(s.cog, interazione, menu_id=s.menu_id, role=s.ruoli[1000])

    assert await s.repo.get_menu(s.menu_id) is None
    s.messaggio.delete.assert_awaited()
    assert "eliminat" in _testo_risposta(interazione).lower()


@pytest.mark.asyncio
async def test_togliere_un_opzione_con_modifica_fallita_non_dice_rimossa(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    await s.aggiungi(1000)
    await s.aggiungi(1001)
    s.messaggio.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500, reason="x"), "boom"))
    interazione = s.admin_interaction()

    await s.cog.remove_option_cmd.callback(s.cog, interazione, menu_id=s.menu_id, role=s.ruoli[1000])

    assert "rimossa" not in _testo_risposta(interazione).lower().replace("non è stata rimossa", "")
    assert await s.repo.count_options(s.menu_id) == 2


@pytest.mark.asyncio
async def test_bottone_con_toggle_spento_non_toglie_il_ruolo(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, toggle=False)
    await s.menu()
    await s.aggiungi(1000)
    ruolo = s.ruoli[1000]
    membro = fake_member(user_id=3, roles=[ruolo])
    interazione = fake_interaction(guild=s.guild, user=membro)

    await s.cog._handle_button_click(interazione, s.menu_id, 1000)

    membro.remove_roles.assert_not_awaited()
    assert "già" in _testo_risposta(interazione).lower()


@pytest.mark.asyncio
async def test_bottone_con_toggle_acceso_toglie_il_ruolo(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, toggle=True)
    await s.menu()
    await s.aggiungi(1000)
    membro = fake_member(user_id=3, roles=[s.ruoli[1000]])

    await s.cog._handle_button_click(fake_interaction(guild=s.guild, user=membro), s.menu_id, 1000)

    membro.remove_roles.assert_awaited_once()


@pytest.mark.asyncio
async def test_errore_http_generico_nel_bottone_e_spiegato(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    await s.aggiungi(1000)
    membro = fake_member(user_id=3)
    membro.add_roles.side_effect = discord.HTTPException(MagicMock(status=500, reason="x"), "boom")
    interazione = fake_interaction(guild=s.guild, user=membro)

    await s.cog._handle_button_click(interazione, s.menu_id, 1000)

    assert "riprova" in _testo_risposta(interazione).lower()

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
from discord.ext import commands

import cogs.utility.role_menus as rm
from cogs.utility.role_menus import RoleMenuCog, _build_embed
from core.repositories.role_menu_repo import RoleMenu, RoleMenuOption, RoleMenuRepository
from core.role_menu_logic import valida_emoji
from tests.support.concorrenza import apri_connessioni
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
    interazione = await s.aggiungi(1000, emoji="<:xx:123456789012345678>")
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
    s.guild.fetch_member = AsyncMock(return_value=membro)
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
    s.guild.fetch_member = AsyncMock(return_value=membro)

    await s.cog._handle_button_click(fake_interaction(guild=s.guild, user=membro), s.menu_id, 1000)

    membro.remove_roles.assert_awaited_once()


@pytest.mark.asyncio
async def test_errore_http_generico_nel_bottone_e_spiegato(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    await s.aggiungi(1000)
    membro = fake_member(user_id=3)
    s.guild.fetch_member = AsyncMock(return_value=membro)
    membro.add_roles.side_effect = discord.HTTPException(MagicMock(status=500, reason="x"), "boom")
    interazione = fake_interaction(guild=s.guild, user=membro)

    await s.cog._handle_button_click(interazione, s.menu_id, 1000)

    assert "riprova" in _testo_risposta(interazione).lower()


def _http(status=400):
    return discord.HTTPException(MagicMock(status=status, reason="x"), "errore")


@pytest.mark.asyncio
async def test_due_aggiunte_insieme_non_perdono_opzioni_ne_duplicano_il_messaggio(clean_db, monkeypatch):
    import asyncio

    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    await apri_connessioni(clean_db)

    async def invio_lento(**kwargs):
        await asyncio.sleep(0.05)
        return s.messaggio

    s.canale.send = AsyncMock(side_effect=invio_lento)

    await asyncio.gather(s.aggiungi(1000), s.aggiungi(1001))

    assert await s.repo.count_options(s.menu_id) == 2
    assert s.canale.send.await_count == 1  # un solo messaggio, il secondo lo modifica
    ultimo = s.messaggio.edit.await_args.kwargs["embed"]
    assert "<@&1000>" in ultimo.fields[0].value and "<@&1001>" in ultimo.fields[0].value


@pytest.mark.asyncio
async def test_reazione_rifiutata_su_messaggio_esistente_non_cambia_l_embed(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, mode="reaction")
    await s.menu()
    await s.aggiungi(1000, emoji="🎮")
    s.messaggio.edit.reset_mock()
    s.messaggio.add_reaction = AsyncMock(side_effect=_http())

    interazione = await s.aggiungi(1001, emoji="🎲")

    s.messaggio.edit.assert_not_awaited()
    assert await s.repo.count_options(s.menu_id) == 1
    assert "non è stata aggiunta" in _testo_risposta(interazione)


@pytest.mark.asyncio
async def test_reazione_rifiutata_su_messaggio_nuovo_lo_cancella(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, mode="reaction")
    await s.menu()
    s.messaggio.add_reaction = AsyncMock(side_effect=_http())

    await s.aggiungi(1000, emoji="🎮")

    s.messaggio.delete.assert_awaited_once()
    assert (await s.repo.get_menu(s.menu_id)).message_id is None
    assert await s.repo.count_options(s.menu_id) == 0


@pytest.mark.asyncio
async def test_cancellazione_del_messaggio_fallita_non_dice_eliminato(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    await s.aggiungi(1000)
    s.messaggio.delete = AsyncMock(side_effect=_http(403))
    interazione = s.admin_interaction()

    await s.cog.delete_cmd.callback(s.cog, interazione, menu_id=s.menu_id)

    testo = interazione.response.send_message.await_args.args[0]
    assert "a mano" in testo and testo != "Role menu eliminato."


@pytest.mark.asyncio
async def test_ultima_opzione_con_cancellazione_fallita_lo_dice(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, mode="select")
    await s.menu()
    await s.aggiungi(1000, emoji=None)
    s.messaggio.delete = AsyncMock(side_effect=_http(403))
    interazione = s.admin_interaction()

    await s.cog.remove_option_cmd.callback(s.cog, interazione, menu_id=s.menu_id, role=s.ruoli[1000])

    assert "a mano" in _testo_risposta(interazione)


@pytest.mark.asyncio
async def test_menu_oltre_6000_caratteri_non_viene_pubblicato_ne_salvato(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch)
    await s.menu()
    gigante = discord.Embed(title="t", description="d" * 4000)
    gigante.add_field(name="n", value="v" * 1000)
    gigante.add_field(name="n", value="v" * 1000)
    gigante.add_field(name="n", value="v" * 1000)
    monkeypatch.setattr(rm, "_build_embed", lambda *_a, **_k: gigante)

    interazione = await s.aggiungi(1000)

    s.canale.send.assert_not_awaited()
    assert await s.repo.count_options(s.menu_id) == 0
    assert "6000" in _testo_risposta(interazione)


def test_nomi_oltre_il_limite_vengono_troncati_nei_componenti():
    cog = RoleMenuCog(MagicMock())
    lunga = "L" * 300
    opzioni = [RoleMenuOption(id=1, menu_id=1, role_id=5, emoji=None, label=lunga, position=0)]
    (bottone,) = cog._build_button_view(1, opzioni).children
    assert len(bottone.label) <= 80
    (select,) = cog._build_select_view(1, opzioni, None).children
    assert len(select.options[0].label) <= 100
    embed = _build_embed(
        RoleMenu(id=1, guild_id=1, channel_id=1, message_id=None, mode="button", toggle=True,
                 max_selectable=None, title="T" * 300, description="D" * 3000),
        opzioni,
    )
    assert len(embed.title) <= 256 and len(embed.description) <= 2000 and len(embed) <= 6000


@pytest.mark.asyncio
async def test_errori_http_nella_tendina_e_nelle_reazioni(clean_db, monkeypatch):
    s = _Scena(clean_db, monkeypatch, mode="select")
    await s.menu()
    await s.aggiungi(1000, emoji=None)
    membro = fake_member(user_id=3)
    s.guild.fetch_member = AsyncMock(return_value=membro)
    membro.add_roles.side_effect = _http(500)
    interazione = fake_interaction(guild=s.guild, user=membro)
    select = MagicMock()
    select.values = ["1000"]

    await s.cog._handle_select(interazione, s.menu_id, select)

    assert "riprova" in _testo_risposta(interazione).lower()

    # Reazioni: add e remove non devono sollevare con un errore Discord.
    monkeypatch.setattr(rm.blacklist_repo, "is_user_blacklisted", AsyncMock(return_value=False))
    menu_r = _Scena(clean_db, monkeypatch, mode="reaction")
    await menu_r.menu()
    await menu_r.aggiungi(1000, emoji="🎮")
    menu_r.guild.id = 1
    membro_r = fake_member(user_id=4)
    membro_r.add_roles.side_effect = _http(500)
    membro_r.remove_roles.side_effect = _http(500)
    menu_r.guild.get_member.return_value = membro_r
    menu_r.cog.bot.get_guild.return_value = menu_r.guild
    evento = MagicMock()
    evento.guild_id = 1
    evento.member = membro_r
    evento.user_id = 4
    evento.message_id = 555
    evento.emoji = "🎮"
    await menu_r.repo.set_menu_message(menu_r.menu_id, 555)

    await menu_r.cog.on_raw_reaction_add(evento)
    await menu_r.cog.on_raw_reaction_remove(evento)


@pytest.mark.asyncio
async def test_all_avvio_un_menu_senza_opzioni_non_registra_view(clean_db, monkeypatch):
    repo = RoleMenuRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(rm, "role_menu_repo", repo)
    menu_id = await repo.create_menu(
        guild_id=1, channel_id=700, mode="select", toggle=True, max_selectable=None,
        title="Vuoto", description="",
    )
    await repo.set_menu_message(menu_id, 555)
    bot = MagicMock()
    bot.add_cog = AsyncMock()

    await rm.setup(bot)

    bot.add_view.assert_not_called()

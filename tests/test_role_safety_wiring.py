"""
tests/test_role_safety_wiring.py
====================================
Verifica che core/role_safety.check_role_assignable() sia davvero
usato in due momenti:

1. CONFIGURAZIONE — i 5 comandi elencati da PIANO_FIX.md per
   SEC-4/SEC-17 (/shop add-item, /level-roles add, /rolemenu
   add-option, /verify setup, /voicetemp-platform-setup) rifiutano un
   ruolo con `administrator` PRIMA di scriverlo nel database.
2. ASSEGNAZIONE (RT-5) — un ruolo configurato quando era innocuo e
   diventato pericoloso DOPO viene rifiutato nel momento in cui un
   utente lo otterrebbe: acquisto nello shop, premio di livello, role
   menu (bottone, select, reazione), verify, bottone piattaforma dei
   vocali temporanei. Per ogni percorso c'è anche il caso di
   controllo: con il ruolo ancora innocuo l'assegnazione avviene.

In entrambi i casi si esegue DAVVERO il comando o il click (con i
finti fedeli di tests/support/discord_fakes.py); nei test di
assegnazione la configurazione la scrive il comando di produzione.
Funzioni coperte: REVIEW.md SEC-4/SEC-17 (issue #10, #14, #29, #32).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from unittest.mock import create_autospec

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from cogs.leveling.leveling import LevelingCog
from cogs.security.verify import MODULE_VERIFY, VerifyCog, VerifyPanelView
from cogs.utility.role_menus import MODULE_ROLE_MENUS, RoleMenuCog
from cogs.voice_temp.voice_temp import PlatformRoleView, VoiceTempCog
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_message,
    fake_role,
    fake_text_channel,
    fake_voice_channel,
)


def _interazione_admin_con_ruolo_pericoloso():
    """
    Server dove il bot e l'admin hanno un ruolo alto in gerarchia, e
    un ruolo bersaglio con `administrator=True` ma posizione bassa:
    la gerarchia va bene, deve rifiutare solo per il permesso
    pericoloso (self_service=True) — esattamente il caso che
    SEC-4/SEC-17 vuole coprire nei comandi di configurazione.
    """
    bot_member = fake_member(user_id=999, name="Yokai Bot", bot=True)
    ruolo_bot = fake_role(role_id=100, name="Yokai Bot", position=50)
    bot_member.top_role = ruolo_bot

    ruolo_admin = fake_role(role_id=200, name="Admin", position=30)
    admin = fake_member(user_id=2, name="admin", roles=[ruolo_admin])
    admin.top_role = ruolo_admin

    server = fake_guild(guild_id=1, owner_id=1, me=bot_member)

    ruolo_pericoloso = fake_role(
        role_id=300, name="Pericoloso", position=1, permissions=discord.Permissions(administrator=True)
    )

    interazione = fake_interaction(guild=server, user=admin)
    return interazione, server, admin, ruolo_pericoloso


async def _attiva_i_livelli(guild_id: int) -> None:
    """I comandi dell'economia controllano per prima cosa che il modulo sia attivo."""
    from core.database import db

    await db.set_module_active_for_guild(guild_id, "leveling", True)


@pytest.mark.asyncio
async def test_level_roles_add_rifiuta_ruolo_administrator(database_collegato):
    interazione, server, admin, ruolo = _interazione_admin_con_ruolo_pericoloso()
    await _attiva_i_livelli(server.id)
    cog = LevelingCog(bot=None)
    cog.cog_unload()

    await cog.level_roles_add.callback(cog, interazione, level=5, role=ruolo)

    interazione.response.send_message.assert_awaited_once()
    _args, kwargs = interazione.response.send_message.call_args
    messaggio = interazione.response.send_message.call_args.args[0]
    assert "administrator" in messaggio


@pytest.mark.asyncio
async def test_shop_add_item_rifiuta_ruolo_administrator(database_collegato):
    interazione, server, admin, ruolo = _interazione_admin_con_ruolo_pericoloso()
    await _attiva_i_livelli(server.id)
    cog = LevelingCog(bot=None)
    cog.cog_unload()

    await cog.shop_add_item.callback(
        cog, interazione, name="VIP", price=100, role=ruolo, description=None
    )

    interazione.response.send_message.assert_awaited_once()
    messaggio = interazione.response.send_message.call_args.args[0]
    assert "administrator" in messaggio


@pytest.mark.asyncio
async def test_rolemenu_add_option_rifiuta_ruolo_administrator(clean_db, monkeypatch):
    import cogs.utility.role_menus as role_menus_module
    from core.repositories.role_menu_repo import RoleMenuRepository

    repo_isolato = RoleMenuRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(role_menus_module, "role_menu_repo", repo_isolato)

    interazione, server, admin, ruolo = _interazione_admin_con_ruolo_pericoloso()
    menu_id = await repo_isolato.create_menu(
        guild_id=server.id, channel_id=1, mode="select",
        toggle=True, max_selectable=None, title="Menu", description="",
    )

    cog = RoleMenuCog(bot=None)
    await cog.add_option_cmd.callback(
        cog, interazione, menu_id=menu_id, role=ruolo, emoji=None, label="VIP"
    )

    interazione.response.send_message.assert_awaited_once()
    messaggio = interazione.response.send_message.call_args.args[0]
    assert "administrator" in messaggio

    assert await repo_isolato.count_options(menu_id) == 0


@pytest.mark.asyncio
async def test_verify_setup_rifiuta_ruolo_administrator():
    interazione, server, admin, ruolo = _interazione_admin_con_ruolo_pericoloso()
    cog = VerifyCog(bot=None)

    class _FakeChoice:
        def __init__(self, value: str) -> None:
            self.value = value
            self.name = value

    await cog.setup_cmd.callback(
        cog,
        interazione,
        method=_FakeChoice("button"),
        verified_role=ruolo,
        min_account_age_days=0,
        min_mutual_servers=0,
        captcha_enabled=False,
        log_channel=None,
    )

    interazione.response.send_message.assert_awaited_once()
    messaggio = interazione.response.send_message.call_args.args[0]
    assert "administrator" in messaggio


@pytest.mark.asyncio
async def test_voicetemp_platform_setup_rifiuta_ruolo_administrator(clean_db, monkeypatch):
    import cogs.voice_temp.voice_temp as voice_temp_module
    from core.repositories.voice_temp_repo import VoiceTempRepository

    repo_isolato = VoiceTempRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(voice_temp_module, "voice_temp_repo", repo_isolato)

    interazione, server, admin, ruolo = _interazione_admin_con_ruolo_pericoloso()
    server.id = 42424242
    interazione.guild = server

    # Generatore e categoria già configurati, altrimenti il comando
    # si fermerebbe prima di arrivare al controllo di sicurezza.
    await repo_isolato.set_config(server.id, generator_channel_id=1, category_id=2)

    cog = VoiceTempCog(bot=None)
    await cog.voicetemp_platform_setup.callback(
        cog, interazione, pc=ruolo, console=None, mobile=None
    )

    interazione.response.send_message.assert_awaited_once()
    messaggio = interazione.response.send_message.call_args.args[0]
    assert "administrator" in messaggio

    config = await repo_isolato.get_config(server.id)
    assert config.role_pc_id is None


# ============================================================================
# RT-5 — rifiuto AL MOMENTO DELL'ASSEGNAZIONE.
# ============================================================================

ID_SERVER = 1
ID_RUOLO = 300
ID_MESSAGGIO_MENU = 555
EMOJI = "🎮"


class _Scena:
    """
    Un server finto con: il bot e un admin in alto in gerarchia, un
    ruolo "VIP" in basso e senza permessi (quindi configurabile), e un
    canale di testo per i role menu.
    """

    def __init__(self) -> None:
        bot_member = fake_member(user_id=999, name="Yokai Bot", bot=True)
        bot_member.top_role = fake_role(role_id=100, name="Yokai Bot", position=50)
        self.server = fake_guild(guild_id=ID_SERVER, owner_id=1, me=bot_member)

        ruolo_admin = fake_role(role_id=200, name="Admin", position=30)
        self.admin = fake_member(user_id=2, name="admin", roles=[ruolo_admin])
        self.admin.top_role = ruolo_admin

        self.ruolo = fake_role(role_id=ID_RUOLO, name="VIP", position=1)
        self.server.get_role.side_effect = lambda rid: self.ruolo if rid == ID_RUOLO else None

        self.canale = fake_text_channel(channel_id=700)
        messaggio_menu = fake_message(message_id=ID_MESSAGGIO_MENU)
        messaggio_menu.reactions = []
        self.canale.send.return_value = messaggio_menu
        self.server.get_channel.return_value = self.canale

        self.bot = create_autospec(commands.Bot, instance=True)
        self.bot.guilds = [self.server]
        self.bot.get_guild.return_value = self.server

    def il_ruolo_diventa_pericoloso(self) -> None:
        self.ruolo.permissions = discord.Permissions(administrator=True)

    def interazione_admin(self):
        return fake_interaction(guild=self.server, user=self.admin, channel=self.canale)

    def utente(self):
        membro = fake_member(user_id=3, name="utente")
        membro.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        return membro

    def interazione_di(self, membro):
        interazione = fake_interaction(guild=self.server, user=membro, channel=self.canale)
        interazione.client = self.bot
        return interazione

    @property
    def vista_pubblicata(self) -> discord.ui.View:
        """La View che il bot ha davvero pubblicato col messaggio del menu."""
        return self.canale.send.await_args.kwargs["view"]


class _Acquisto:
    nome = "shop buy"

    async def configura(self, scena: _Scena) -> None:
        await _attiva_i_livelli(ID_SERVER)
        self.cog = LevelingCog(bot=None)
        self.cog.cog_unload()
        await self.cog.shop_add_item.callback(
            self.cog, scena.interazione_admin(), name="VIP", price=100,
            role=scena.ruolo, description=None,
        )

    async def concedi(self, scena: _Scena, membro) -> None:
        from core.repositories.leveling_repo import leveling_repo
        from core.repositories.shop_repo import shop_repo

        await leveling_repo.add_coins(ID_SERVER, membro.id, 500)
        (oggetto,) = await shop_repo.list_items(ID_SERVER)
        await self.cog.shop_buy.callback(
            self.cog, scena.interazione_di(membro), item_id=oggetto.id
        )


class _PremioDiLivello:
    nome = "premio di livello"

    async def configura(self, scena: _Scena) -> None:
        await _attiva_i_livelli(ID_SERVER)
        self.cog = LevelingCog(bot=None)
        self.cog.cog_unload()
        await self.cog.level_roles_add.callback(
            self.cog, scena.interazione_admin(), level=1, role=scena.ruolo
        )

    async def concedi(self, scena: _Scena, membro) -> None:
        await self.cog._grant_level_rewards(membro, scena.server, new_level=1)


class _RoleMenu:
    """Base dei tre role menu: crea il menu e aggiunge l'opzione coi comandi veri."""

    modalita: str

    async def configura(self, scena: _Scena) -> None:
        from core.database import db
        from core.repositories.role_menu_repo import role_menu_repo

        await db.set_module_active_for_guild(ID_SERVER, MODULE_ROLE_MENUS, True)
        self.cog = RoleMenuCog(scena.bot)
        creazione = scena.interazione_admin()
        await self.cog.create_cmd.callback(
            self.cog, creazione, title="Menu",
            mode=app_commands.Choice(name=self.modalita, value=self.modalita),
            description="", channel=scena.canale, toggle=True, max_selectable=None,
        )
        # L'ID del menu è quello che il comando comunica all'admin.
        risposta = creazione.response.send_message.await_args.args[0]
        menu_id = int(re.search(r"ID `(\d+)`", risposta).group(1))
        await self.cog.add_option_cmd.callback(
            self.cog, scena.interazione_admin(), menu_id=menu_id,
            role=scena.ruolo, emoji=EMOJI, label="VIP",
        )
        assert await role_menu_repo.count_options(menu_id) == 1


class _RoleMenuBottone(_RoleMenu):
    nome = "role menu (bottone)"
    modalita = "button"

    async def concedi(self, scena: _Scena, membro) -> None:
        (bottone,) = scena.vista_pubblicata.children
        await bottone.callback(scena.interazione_di(membro))


class _RoleMenuSelect(_RoleMenu):
    nome = "role menu (select)"
    modalita = "select"

    async def concedi(self, scena: _Scena, membro) -> None:
        (select,) = scena.vista_pubblicata.children
        select._values = [str(ID_RUOLO)]  # ciò che l'utente ha scelto nel menu
        await select.callback(scena.interazione_di(membro))


class _RoleMenuReazione(_RoleMenu):
    nome = "role menu (reazione)"
    modalita = "reaction"

    async def concedi(self, scena: _Scena, membro) -> None:
        evento = create_autospec(discord.RawReactionActionEvent, instance=True)
        evento.guild_id = ID_SERVER
        evento.member = membro
        evento.message_id = ID_MESSAGGIO_MENU
        evento.emoji = EMOJI
        await self.cog.on_raw_reaction_add(evento)


class _Verify:
    nome = "verify"

    async def configura(self, scena: _Scena) -> None:
        from core.database import db

        await db.set_module_active_for_guild(ID_SERVER, MODULE_VERIFY, True)
        self.cog = VerifyCog(scena.bot)
        scena.bot.get_cog.return_value = self.cog
        await self.cog.setup_cmd.callback(
            self.cog, scena.interazione_admin(),
            method=app_commands.Choice(name="Button", value="button"),
            verified_role=scena.ruolo, min_account_age_days=0,
            min_mutual_servers=0, captcha_enabled=False, log_channel=None,
        )

    async def concedi(self, scena: _Scena, membro) -> None:
        (bottone,) = VerifyPanelView().children
        await bottone.callback(scena.interazione_di(membro))


class _PiattaformaVocale:
    nome = "vocali temporanei (bottone piattaforma)"

    async def configura(self, scena: _Scena) -> None:
        self.cog = VoiceTempCog(scena.bot)
        categoria = create_autospec(discord.CategoryChannel, instance=True)
        categoria.id = 800
        categoria.name = "Vocali"
        await self.cog.voicetemp_setup.callback(
            self.cog, scena.interazione_admin(),
            generator=fake_voice_channel(801), category=categoria,
        )
        await self.cog.voicetemp_platform_setup.callback(
            self.cog, scena.interazione_admin(), pc=scena.ruolo, console=None, mobile=None
        )

    async def concedi(self, scena: _Scena, membro) -> None:
        from core.repositories.voice_temp_repo import voice_temp_repo

        # La stessa View che accompagna la notifica del canale creato.
        vista = PlatformRoleView(await voice_temp_repo.get_config(ID_SERVER))
        (bottone,) = vista.children
        await bottone.callback(scena.interazione_di(membro))


PERCORSI = [
    _Acquisto,
    _PremioDiLivello,
    _RoleMenuBottone,
    _RoleMenuSelect,
    _RoleMenuReazione,
    _Verify,
    _PiattaformaVocale,
]


@pytest.fixture
def database_collegato(monkeypatch, clean_db):
    import core.database as database_module
    from core.repositories.blacklist_repo import blacklist_repo

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    blacklist_repo._user_cache.clear()
    yield
    database_module.db._modules_cache.clear()
    blacklist_repo._user_cache.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("percorso", PERCORSI, ids=lambda p: p.nome)
async def test_ruolo_ancora_innocuo_viene_assegnato(database_collegato, percorso):
    # Caso di controllo: senza questo, il test qui sotto passerebbe
    # anche se il percorso non assegnasse mai nulla.
    scena = _Scena()
    passo = percorso()
    await passo.configura(scena)
    membro = scena.utente()

    await passo.concedi(scena, membro)

    membro.add_roles.assert_awaited_once()
    assert membro.add_roles.await_args.args == (scena.ruolo,)


@pytest.mark.asyncio
@pytest.mark.parametrize("percorso", PERCORSI, ids=lambda p: p.nome)
async def test_ruolo_diventato_pericoloso_viene_rifiutato_all_assegnazione(
    database_collegato, percorso
):
    scena = _Scena()
    passo = percorso()
    await passo.configura(scena)
    membro = scena.utente()

    scena.il_ruolo_diventa_pericoloso()
    await passo.concedi(scena, membro)

    membro.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_acquisto_rifiutato_non_fa_spendere_i_coin(database_collegato):
    from core.repositories.leveling_repo import leveling_repo

    scena = _Scena()
    passo = _Acquisto()
    await passo.configura(scena)
    membro = scena.utente()

    scena.il_ruolo_diventa_pericoloso()
    await passo.concedi(scena, membro)

    assert (await leveling_repo.get_totals(ID_SERVER, membro.id)).coins_total == 500

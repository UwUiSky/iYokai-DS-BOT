"""
tests/test_role_safety_wiring.py
====================================
Verifica che core/role_safety.check_role_assignable() sia davvero
usato nei 5 punti elencati da PIANO_FIX.md per SEC-4/SEC-17: /shop
add-item, /level-roles add, /rolemenu add-option, /verify setup,
/voicetemp-platform-setup. Per ognuno, esegue DAVVERO il callback del
comando (con i finti fedeli di tests/support/discord_fakes.py) e
controlla che un ruolo con `administrator` venga rifiutato PRIMA di
essere scritto nel database.
Funzioni coperte: REVIEW.md SEC-4/SEC-17 (issue #10, #14, #29, #32).
"""

from __future__ import annotations

import discord
import pytest

from cogs.leveling.leveling import LevelingCog
from cogs.security.verify import VerifyCog
from cogs.utility.role_menus import RoleMenuCog
from cogs.voice_temp.voice_temp import VoiceTempCog
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role


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


@pytest.mark.asyncio
async def test_level_roles_add_rifiuta_ruolo_administrator():
    interazione, server, admin, ruolo = _interazione_admin_con_ruolo_pericoloso()
    cog = LevelingCog(bot=None)
    cog.cog_unload()

    await cog.level_roles_add.callback(cog, interazione, level=5, role=ruolo)

    interazione.response.send_message.assert_awaited_once()
    _args, kwargs = interazione.response.send_message.call_args
    messaggio = interazione.response.send_message.call_args.args[0]
    assert "administrator" in messaggio


@pytest.mark.asyncio
async def test_shop_add_item_rifiuta_ruolo_administrator():
    interazione, server, admin, ruolo = _interazione_admin_con_ruolo_pericoloso()
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

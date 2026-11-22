"""
tests/test_catalogo_r2mod_blocco_mirato.py
==========================================
Blocchi mirati (#115, r2mod): canali scelti (MOD-091), gruppo salvato (MOD-092), blocco cieco (MOD-094), kick o ban
di chi entra (MOD-095), permessi dei ruoli (MOD-096). Database vero, servizio vero.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.security.lockdown as cog_modulo
from core import lockdown_logic as logica
from core import lockdown_service as servizio
from core.repositories.lockdown_repo import lockdown_repo
from tests.support.discord_fakes import fake_member, fake_role
from tests.test_lockdown import GUILD_ID, PROPRIETARIO, _canale, _comando, _server, cog, db  # noqa: F401


def _quattro():
    return [_canale(discord.TextChannel, i) for i in (1, 2, 3, 4)]


def _ruolo(role_id, position, perms, managed=False):
    r = fake_role(role_id, f"r{role_id}", position=position, managed=managed, permissions=discord.Permissions(**perms))
    r.edit = AsyncMock()

    async def _edit(*, permissions=None, reason=None, r=r):
        r.permissions = permissions

    r.edit.side_effect = _edit
    return r


# MOD-091
async def test_si_bloccano_solo_i_canali_scelti_e_il_server_resta_com_e():
    a, b, c, d = _quattro()
    server = _server([a, b, c, d])
    esito = await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova", canali=[a, b])
    assert esito.ok and esito.bloccati == 2
    assert a.ow.send_messages is False and b.ow.send_messages is False
    assert c.chiamate == 0 and d.chiamate == 0
    assert server.verification_level == discord.VerificationLevel.low and "INVITES_DISABLED" not in server.features
    assert "Ingressi: invariati." in esito.messaggio
    await servizio.togli(server)
    assert a.ow.is_empty() and b.ow.is_empty()
    assert await lockdown_repo.get_stato(GUILD_ID) is None


# MOD-091
async def test_il_menu_e_di_chi_comanda_ha_un_tetto_e_il_permesso_si_rilegge():
    server = _server(_quattro())
    vista = cog_modulo.SceltaCanali(MagicMock(), PROPRIETARIO, None, None, False)
    assert vista.menu.max_values == logica.MAX_CANALI_SCELTI == 25
    ok = _comando(server)
    assert await vista.interaction_check(ok) is True
    altro = _comando(server, user_id=1234)
    assert await vista.interaction_check(altro) is False
    senza = _comando(server, gestisce=False)
    assert await vista.interaction_check(senza) is False


# MOD-091
async def test_il_bottone_blocca_senza_scelta_chiede_di_scegliere_e_con_la_scelta_blocca(cog):
    a, b, c, d = _quattro()
    server = _server([a, b, c, d])
    vista = cog_modulo.SceltaCanali(cog, PROPRIETARIO, "prova", None, False)
    i = _comando(server)
    await vista.blocca.callback(i)
    i.response.send_message.assert_awaited_once()
    assert await lockdown_repo.get_stato(GUILD_ID) is None
    vista.scelti = [a.id, c.id]
    i = _comando(server)
    await vista.blocca.callback(i)
    assert a.ow.send_messages is False and c.ow.send_messages is False and b.chiamate == 0


# MOD-092
async def test_il_gruppo_salvato_si_blocca_con_un_comando_e_ha_un_tetto_di_25(cog):
    a, b, c, d = _quattro()
    server = _server([a, b, c, d])
    vista = cog_modulo.SceltaCanali(cog, PROPRIETARIO, None, None, False)
    vista.scelti = [b.id, d.id]
    i = _comando(server)
    await vista.salva.callback(i)
    assert (await lockdown_repo.get_config(GUILD_ID)).gruppo_canali == (b.id, d.id)
    await lockdown_repo.imposta_gruppo(GUILD_ID, list(range(100, 140)))
    assert len((await lockdown_repo.get_config(GUILD_ID)).gruppo_canali) == 25
    await lockdown_repo.imposta_gruppo(GUILD_ID, [b.id, d.id])
    i = _comando(server)
    await cog.blocco_canali.callback(cog, i, True)
    assert b.ow.send_messages is False and d.ow.send_messages is False and a.chiamate == 0


# MOD-092
async def test_senza_gruppo_salvato_lo_dice_e_non_blocca(cog):
    server = _server(_quattro())
    i = _comando(server)
    await cog.blocco_canali.callback(cog, i, True)
    assert await lockdown_repo.get_stato(GUILD_ID) is None
    i.response.send_message.assert_awaited_once()


# MOD-094
async def test_il_blocco_cieco_nasconde_crea_il_canale_di_avviso_e_lo_toglie():
    a, b = _canale(discord.TextChannel, 1), _canale(discord.VoiceChannel, 2)
    server = _server([a, b])
    avviso = _canale(discord.TextChannel, 99, name=logica.NOME_CANALE_AVVISO)
    avviso.delete = AsyncMock()
    server.create_text_channel = AsyncMock(return_value=avviso)
    esito = await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova", nascondi=True)
    assert a.ow.view_channel is False and b.ow.view_channel is False and a.ow.send_messages is None
    kw = server.create_text_channel.await_args
    assert kw.args[0] == "server-bloccato" and kw.kwargs["overwrites"][server.default_role].send_messages is False
    assert "<#99>" in esito.messaggio
    server.get_channel = lambda i, tutti={1: a, 2: b, 99: avviso}: tutti.get(i)
    await servizio.togli(server)
    avviso.delete.assert_awaited_once()
    assert a.ow.is_empty() and b.ow.is_empty()


# MOD-094
async def test_senza_il_canale_di_avviso_il_blocco_cieco_parte_lo_stesso():
    a = _canale(discord.TextChannel, 1)
    server = _server([a])
    server.create_text_channel = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=403), "no"))
    esito = await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova", nascondi=True)
    assert esito.ok and a.ow.view_channel is False
    await servizio.togli(server)


def _entra(server, user_id=700, bot=False, admin=False):
    m = fake_member(user_id, bot=bot, guild_permissions=discord.Permissions(administrator=admin))
    m.guild = server
    m.ban = AsyncMock()
    return m


# MOD-095
async def test_chi_entra_durante_il_blocco_viene_espulso_o_bannato_ma_non_i_bot_ne_i_protetti(cog, monkeypatch):
    server = _server([_canale(discord.TextChannel, 1)])
    server.me.id = 999
    espelli, banna = AsyncMock(), AsyncMock()
    monkeypatch.setattr(cog_modulo.bot_roles, "espelli", espelli)
    monkeypatch.setattr(cog_modulo.bot_roles, "banna", banna)
    await cog.on_member_join(_entra(server))
    espelli.assert_not_awaited()  # nessun blocco: nessuna azione
    await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova", ingressi="kick")
    assert servizio.modo_ingressi(GUILD_ID) == "kick"
    await cog.on_member_join(_entra(server))
    espelli.assert_awaited_once()
    assert len(espelli.await_args.kwargs["reason"]) <= 512
    await cog.on_member_join(_entra(server, 701, bot=True))
    await cog.on_member_join(_entra(server, 702, admin=True))
    assert espelli.await_count == 1
    await servizio.togli(server)
    assert servizio.modo_ingressi(GUILD_ID) is None
    await cog.on_member_join(_entra(server, 703))
    assert espelli.await_count == 1


# MOD-095
async def test_il_modo_ban_banna_e_dopo_un_riavvio_il_modo_si_rilegge(cog, monkeypatch):
    server = _server([_canale(discord.TextChannel, 1)])
    server.me.id = 999
    banna = AsyncMock()
    monkeypatch.setattr(cog_modulo.bot_roles, "banna", banna)
    await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova", ingressi="ban")
    servizio._ingressi.clear()  # il bot si riavvia
    await servizio.carica_panici()
    assert servizio.modo_ingressi(GUILD_ID) == "ban"
    await cog.on_member_join(_entra(server))
    banna.assert_awaited_once()
    await servizio.togli(server)


# MOD-095, MOD-096
async def test_kick_ban_e_ruoli_chiedono_il_permesso_vero_a_chi_comanda_e_al_bot():
    server = _server([])
    i = _comando(server, user_id=1234)
    i.user.guild_permissions = discord.Permissions(manage_guild=True)
    server.me.guild_permissions = discord.Permissions(kick_members=True, manage_roles=True)
    assert await cog_modulo._manca_il_permesso(i, "kick", False) is True  # a te manca kick
    i2 = _comando(server, user_id=1234)
    i2.user.guild_permissions = discord.Permissions(manage_guild=True, kick_members=True, manage_roles=True)
    assert await cog_modulo._manca_il_permesso(i2, "kick", True) is False
    assert await cog_modulo._manca_il_permesso(i2, "ban", False) is True  # al bot manca ban
    assert await cog_modulo._manca_il_permesso(i2, None, False) is False


# MOD-096
async def test_si_tolgono_i_permessi_pericolosi_solo_ai_ruoli_sotto_il_bot_e_si_rimettono_solo_quelli():
    alto = _ruolo(10, 80, {"administrator": True})  # sopra il bot
    gestito = _ruolo(11, 5, {"manage_guild": True}, managed=True)
    mod = _ruolo(12, 5, {"ban_members": True, "kick_members": True, "send_messages": True})
    pulito = _ruolo(13, 5, {"send_messages": True})
    server = _server([_canale(discord.TextChannel, 1)])
    server.me.top_role = fake_role(3, position=50)
    server.roles = [fake_role(0, "@everyone", position=0), alto, gestito, mod, pulito]
    server.get_role = lambda rid: {r.id: r for r in server.roles}.get(rid)
    esito = await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova", ruoli=True)
    assert "Ruoli a cui ho tolto i permessi pericolosi: 1" in esito.messaggio
    assert not mod.permissions.ban_members and not mod.permissions.kick_members and mod.permissions.send_messages
    assert alto.permissions.administrator and gestito.permissions.manage_guild  # fuori portata: intatti
    alto.edit.assert_not_awaited()
    pulito.edit.assert_not_awaited()
    # Nel frattempo qualcuno dà a mano «gestire i messaggi»: lo sblocco non lo toglie.
    mod.permissions = discord.Permissions(mod.permissions.value | discord.Permissions(manage_messages=True).value)
    await servizio.togli(server)
    assert mod.permissions.ban_members and mod.permissions.kick_members and mod.permissions.manage_messages
    assert await lockdown_repo.ruoli_da_ripristinare(GUILD_ID) == []
    assert await lockdown_repo.get_stato(GUILD_ID) is None


# MOD-096
async def test_se_un_ruolo_non_si_riapre_il_blocco_resta_per_riprovare():
    mod = _ruolo(12, 5, {"ban_members": True})
    server = _server([_canale(discord.TextChannel, 1)])
    server.me.top_role = fake_role(3, position=50)
    server.roles = [mod]
    server.get_role = lambda rid: mod if rid == 12 else None
    await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova", ruoli=True)
    mod.edit.side_effect = discord.HTTPException(MagicMock(status=403), "no")
    esito = await servizio.togli(server)
    assert esito.ok is False and await lockdown_repo.get_stato(GUILD_ID) is not None
    async def _ok(*, permissions=None, reason=None):
        mod.permissions = permissions
    mod.edit.side_effect = _ok
    assert (await servizio.togli(server)).ok is True and mod.permissions.ban_members

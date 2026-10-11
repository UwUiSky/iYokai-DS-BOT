"""
tests/test_anti_nuke_guardie_117.py
===================================
Catalogo #117, anti-nuke, le guardie su azioni singole:
SIC-005/006 permessi pericolosi a un ruolo, SIC-007 permessi dei canali,
SIC-008 ruolo pericoloso a un membro, SIC-009 link personalizzato,
SIC-010 prune, SIC-025 chi aggiunge i bot.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

import cogs.security.anti_nuke as modulo
from core.repositories.security_repo import security_repo
from core.security_logic import NUKE_CATEGORY_BAN_KICK, NUKE_CATEGORY_CHANNEL_PERMS
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_role,
    fake_text_channel,
)
from tests.test_anti_nuke_f1 import (  # noqa: F401  (fixture condivise)
    AUTORE_ID,
    GUILD_ID,
    _interazione,
    _server,
    _voce,
    attese,
    cog,
    db_finto,
)

ADMIN = discord.Permissions(administrator=True)
NIENTE = discord.Permissions.none()


def _scelta(valore: str) -> app_commands.Choice:
    return app_commands.Choice(name=valore, value=valore)


async def _guardie(cog, **kw):
    await cog.guardie.callback(cog, _interazione(), **{
        k: (_scelta(v) if k == "permessi_ruoli" else v) for k, v in kw.items()
    })


def _ruolo(server, role_id=70, permessi=NIENTE, membri=0, nome="Mod"):
    ruolo = fake_role(role_id=role_id, name=nome, permissions=permessi)
    ruolo.guild = server
    ruolo.members = [object()] * membri
    ruolo.edit = AsyncMock()
    return ruolo


def _server_con_registro(autore, azione, bersaglio_id):
    server = _server(autore, [[_voce(azione, AUTORE_ID, bersaglio_id)]])
    server.member_count = 10
    return server


# --------------------------------------------------------------------
# SIC-005 / SIC-006
# --------------------------------------------------------------------
async def test_permesso_pericoloso_a_un_ruolo_viene_riportato_com_era(cog):
    await _guardie(cog, permessi_ruoli="all")
    autore = fake_member(user_id=AUTORE_ID)
    server = _server_con_registro(autore, discord.AuditLogAction.role_update, 70)
    prima, dopo = _ruolo(server, permessi=NIENTE), _ruolo(server, permessi=ADMIN)

    await cog.on_guild_role_update(prima, dopo)

    dopo.edit.assert_awaited_once()
    assert dopo.edit.call_args.kwargs["permissions"] == NIENTE
    caso = await security_repo.get_nuke_case(GUILD_ID, 1)
    assert caso.category == "role_perms" and "administrator" in caso.detail


async def test_guardia_spenta_o_autore_fidato_non_tocca_niente(cog):
    autore = fake_member(user_id=AUTORE_ID)
    server = _server_con_registro(autore, discord.AuditLogAction.role_update, 70)
    prima, dopo = _ruolo(server, permessi=NIENTE), _ruolo(server, permessi=ADMIN)
    await cog.on_guild_role_update(prima, dopo)  # guardia spenta di default
    dopo.edit.assert_not_awaited()

    await _guardie(cog, permessi_ruoli="all")
    await cog.trusted_add.callback(cog, _interazione(), str(AUTORE_ID))
    await cog.on_guild_role_update(prima, dopo)
    dopo.edit.assert_not_awaited()


async def test_senza_voce_nel_registro_non_si_annulla_niente(cog):
    await _guardie(cog, permessi_ruoli="all")
    autore = fake_member(user_id=AUTORE_ID)
    server = _server(autore, [[]])
    prima, dopo = _ruolo(server, permessi=NIENTE), _ruolo(server, permessi=ADMIN)
    await cog.on_guild_role_update(prima, dopo)
    dopo.edit.assert_not_awaited()


async def test_modo_pubblici_controlla_solo_everyone_e_i_ruoli_di_quasi_tutti(cog):
    await _guardie(cog, permessi_ruoli="public")
    autore = fake_member(user_id=AUTORE_ID)
    server = _server_con_registro(autore, discord.AuditLogAction.role_update, 70)

    privato_prima, privato = _ruolo(server, permessi=NIENTE, membri=2), _ruolo(server, permessi=ADMIN, membri=2)
    await cog.on_guild_role_update(privato_prima, privato)
    privato.edit.assert_not_awaited()

    pubblico_prima, pubblico = _ruolo(server, permessi=NIENTE, membri=6), _ruolo(server, permessi=ADMIN, membri=6)
    await cog.on_guild_role_update(pubblico_prima, pubblico)
    pubblico.edit.assert_awaited_once()


# --------------------------------------------------------------------
# SIC-007
# --------------------------------------------------------------------
async def test_cambi_ai_permessi_dei_canali_contano_e_si_ripristinano(cog):
    await cog.limits.callback(cog, _interazione(), _scelta(NUKE_CATEGORY_CHANNEL_PERMS), 0, 60)
    await cog.punish_action.callback(cog, _interazione(), _scelta("strip_roles"))
    autore = fake_member(user_id=AUTORE_ID, roles=[fake_role(role_id=52, position=5)])
    server = _server(autore, [[_voce(discord.AuditLogAction.overwrite_update, AUTORE_ID, 7001)]])
    prima_permessi = {object(): discord.PermissionOverwrite(view_channel=True)}
    prima, dopo = fake_text_channel(), fake_text_channel()
    for c, perm in ((prima, prima_permessi), (dopo, {})):
        c.id, c.guild, c.name, c.category_id = 7001, server, "staff", None
        c.overwrites = perm
    dopo.edit = AsyncMock()

    await cog.on_guild_channel_update(prima, dopo)

    autore.edit.assert_awaited_once()  # punito
    dopo.edit.assert_awaited_once()  # permessi riportati com'erano
    assert dopo.edit.call_args.kwargs["overwrites"] is prima_permessi


async def test_un_cambio_che_non_tocca_i_permessi_non_legge_il_registro(cog):
    server = fake_guild(guild_id=GUILD_ID)
    prima, dopo = fake_text_channel(), fake_text_channel()
    for c in (prima, dopo):
        c.guild, c.overwrites = server, {}
    await cog.on_guild_channel_update(prima, dopo)
    server.audit_logs.assert_not_called()


# --------------------------------------------------------------------
# SIC-008
# --------------------------------------------------------------------
async def test_ruolo_pericoloso_dato_da_un_non_fidato_viene_tolto(cog):
    await _guardie(cog, ruoli_ai_membri=True)
    autore = fake_member(user_id=AUTORE_ID)
    server = _server_con_registro(autore, discord.AuditLogAction.member_role_update, 31)
    admin = fake_role(role_id=70, name="Admin", permissions=ADMIN)
    prima, dopo = fake_member(user_id=31, roles=[]), fake_member(user_id=31, roles=[admin])
    dopo.guild = server

    await cog.on_member_update(prima, dopo)

    dopo.remove_roles.assert_awaited_once()
    assert dopo.remove_roles.call_args.args == (admin,)


async def test_ruolo_senza_permessi_pericolosi_non_legge_il_registro(cog):
    await _guardie(cog, ruoli_ai_membri=True)
    server = fake_guild(guild_id=GUILD_ID)
    semplice = fake_role(role_id=70, name="Colore", permissions=NIENTE)
    prima, dopo = fake_member(user_id=31, roles=[]), fake_member(user_id=31, roles=[semplice])
    dopo.guild = server
    await cog.on_member_update(prima, dopo)
    server.audit_logs.assert_not_called()


# --------------------------------------------------------------------
# SIC-009
# --------------------------------------------------------------------
async def test_cambio_del_link_personalizzato_viene_ripristinato(cog):
    await _guardie(cog, link_personalizzato=True)
    autore = fake_member(user_id=AUTORE_ID)
    server = _server_con_registro(autore, discord.AuditLogAction.guild_update, GUILD_ID)
    server.id = GUILD_ID
    prima, dopo = fake_guild(guild_id=GUILD_ID), server
    prima.vanity_url_code, dopo.vanity_url_code = "yokai", "rubato"
    cog.bot.http = MagicMock()
    cog.bot.http.request = AsyncMock()

    await cog.on_guild_update(prima, dopo)

    cog.bot.http.request.assert_awaited_once()
    assert cog.bot.http.request.call_args.kwargs["json"] == {"code": "yokai"}
    caso = await security_repo.get_nuke_case(GUILD_ID, 1)
    assert "ripristinato" in caso.punishment


async def test_se_il_ripristino_del_link_fallisce_lo_dice(cog):
    await _guardie(cog, link_personalizzato=True)
    autore = fake_member(user_id=AUTORE_ID)
    server = _server_con_registro(autore, discord.AuditLogAction.guild_update, GUILD_ID)
    server.id = GUILD_ID
    prima = fake_guild(guild_id=GUILD_ID)
    prima.vanity_url_code, server.vanity_url_code = "yokai", "rubato"
    cog.bot.http = MagicMock()
    cog.bot.http.request = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=403), "no"))

    await cog.on_guild_update(prima, server)

    assert "fallito" in (await security_repo.get_nuke_case(GUILD_ID, 1)).punishment


# --------------------------------------------------------------------
# SIC-010
# --------------------------------------------------------------------
def _voce_prune(rimossi: int, voce_id: int = 9001):
    voce = _voce(discord.AuditLogAction.member_prune, AUTORE_ID)
    voce.id = voce_id
    voce.extra = MagicMock(members_removed=rimossi)
    return voce


async def test_prune_di_massa_scatta_la_punizione(cog):
    await cog.punish_action.callback(cog, _interazione(), _scelta("strip_roles"))
    autore = fake_member(user_id=AUTORE_ID, roles=[fake_role(role_id=52, position=5)])
    server = _server(autore, [[_voce_prune(40)]])
    uscito = fake_member(user_id=31)
    uscito.guild = server

    await cog.on_member_remove(uscito)

    autore.edit.assert_awaited_once()
    caso = await security_repo.get_nuke_case(GUILD_ID, 1)
    assert caso.category == NUKE_CATEGORY_BAN_KICK and "prune" in caso.detail


async def test_la_stessa_voce_di_prune_si_conta_una_volta_sola(cog):
    await cog.limits.callback(cog, _interazione(), _scelta(NUKE_CATEGORY_BAN_KICK), 100, 60)
    autore = fake_member(user_id=AUTORE_ID, roles=[fake_role(role_id=52, position=5)])
    server = _server(autore, [[_voce_prune(3)]])
    contati = []
    originale = cog._handle_event

    async def _spia(*a, **kw):
        contati.append(kw.get("conteggio_azioni"))
        return await originale(*a, **kw)

    cog._handle_event = _spia
    for uid in (31, 32, 33):
        uscito = fake_member(user_id=uid)
        uscito.guild = server
        await cog.on_member_remove(uscito)
    assert [c for c in contati if c and c > 1] == [3]


# --------------------------------------------------------------------
# SIC-025
# --------------------------------------------------------------------
async def test_bot_aggiunto_da_un_non_autorizzato_viene_espulso(cog):
    await _guardie(cog, aggiunta_bot=True)
    autore = fake_member(user_id=AUTORE_ID)
    server = _server_con_registro(autore, discord.AuditLogAction.bot_add, 800)
    bot_nuovo = fake_member(user_id=800, bot=True)
    bot_nuovo.guild = server

    await cog.on_member_join(bot_nuovo)

    bot_nuovo.kick.assert_awaited_once()


async def test_bot_aggiunto_da_un_fidato_resta(cog):
    await _guardie(cog, aggiunta_bot=True)
    await cog.trusted_add.callback(cog, _interazione(), str(AUTORE_ID))
    autore = fake_member(user_id=AUTORE_ID)
    server = _server_con_registro(autore, discord.AuditLogAction.bot_add, 800)
    bot_nuovo = fake_member(user_id=800, bot=True)
    bot_nuovo.guild = server
    await cog.on_member_join(bot_nuovo)
    bot_nuovo.kick.assert_not_awaited()


async def test_un_umano_che_entra_non_legge_il_registro(cog):
    await _guardie(cog, aggiunta_bot=True)
    server = fake_guild(guild_id=GUILD_ID)
    umano = fake_member(user_id=801)
    umano.guild = server
    await cog.on_member_join(umano)
    server.audit_logs.assert_not_called()

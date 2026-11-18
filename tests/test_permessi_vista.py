"""
tests/test_permessi_vista.py
============================
CFG-022, CFG-023, CFG-025, CFG-026 (#122): elenco dei ruoli dello staff del bot, scelta dei ruoli e livello di
permesso di un membro con il motivo (`core/permessi_vista.py`, `/admin-bot config staff|permessi`).
I livelli con nome (admin, mod, ban, sicurezza, log, proprietario del server e del bot) sono quelli di
`core/command_access.Livello`: CFG-025 si ferma lì (D96).
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import permessi_vista as pv
from core.command_access import Livello, TipoRuolo, decidi_accesso
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role

BASE = dict(user_id=10, owner_bot_id=1, guild_owner_id=2, ruoli_utente_ids=[], ruolo_configurato_id=None, ruolo_esiste=True)


def _motivo(livello, **kw):
    return pv.motivo_accesso(livello, **{**BASE, "permessi": discord.Permissions.none(), **kw})


def test_motivi_per_proprietario_permesso_ruolo_e_nessuno():
    assert _motivo(Livello.ADMIN, user_id=2) == pv.MOTIVO_PROPRIETARIO
    assert _motivo(Livello.ADMIN, permessi=discord.Permissions(manage_guild=True)) == pv.MOTIVO_PERMESSO
    assert _motivo(Livello.ADMIN, ruoli_utente_ids=[5], ruolo_configurato_id=5) == pv.MOTIVO_RUOLO
    assert _motivo(Livello.ADMIN, ruoli_utente_ids=[5], ruolo_configurato_id=5, ruolo_esiste=False) == pv.MOTIVO_NESSUNO
    assert _motivo(Livello.ADMIN) == pv.MOTIVO_NESSUNO
    assert _motivo(Livello.OWNER, user_id=1) == pv.MOTIVO_PROPRIETARIO_BOT
    assert _motivo(Livello.OWNER) == pv.MOTIVO_NESSUNO
    assert _motivo(Livello.FOUNDER, user_id=2) == pv.MOTIVO_PROPRIETARIO
    # il permesso di Discord non apre il livello del proprietario del server
    assert _motivo(Livello.FOUNDER, permessi=discord.Permissions.all()) == pv.MOTIVO_NESSUNO


@pytest.mark.parametrize("livello", list(Livello))
@pytest.mark.parametrize("permessi", [discord.Permissions.none(), discord.Permissions.all(), discord.Permissions(ban_members=True)])
def test_il_motivo_non_contraddice_mai_la_decisione_vera(livello, permessi):
    for kw in ({}, {"user_id": 2}, {"ruoli_utente_ids": [5], "ruolo_configurato_id": 5}):
        base = {**BASE, "permessi": permessi, **kw}
        assert (pv.motivo_accesso(livello, **base) != pv.MOTIVO_NESSUNO) == decidi_accesso(livello, **base)


@pytest.fixture
async def db_pronto(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._settings_cache.clear()
    await database_module.db.ensure_guild_exists(920)
    return database_module.db


def _guild_con_ruoli(*ruoli):
    guild = fake_guild(920, owner_id=2)
    mappa = {r.id: r for r in ruoli}
    guild.get_role = lambda i: mappa.get(i)
    return guild


async def test_ruoli_dello_staff_e_livelli_del_membro(db_pronto):
    from core.command_access import imposta_ruolo

    ruolo_mod, ruolo_adm = fake_role(31, "Mod"), fake_role(32, "Adm")
    guild = _guild_con_ruoli(ruolo_mod, ruolo_adm)
    await imposta_ruolo(guild, TipoRuolo.MOD, ruolo_mod, 2)
    staff = {v.tipo: v for v in await pv.ruoli_dello_staff(guild)}
    assert staff[TipoRuolo.MOD].esiste and staff[TipoRuolo.MOD].ruolo_id == 31
    assert "mod-sanzioni" in staff[TipoRuolo.MOD].gruppi
    assert not staff[TipoRuolo.ADMIN].esiste
    membro = fake_member(77, roles=[ruolo_mod], guild_permissions=discord.Permissions.none())
    livelli = {v.livello: v for v in await pv.livelli_del_membro(guild, membro)}
    assert livelli[Livello.MOD].motivo == pv.MOTIVO_RUOLO
    assert not livelli[Livello.ADMIN].ha and not livelli[Livello.MODBAN].ha


async def test_il_comando_staff_scrive_dal_punto_unico_e_rifiuta_il_ruolo_admin_senza_amministratore(db_pronto):
    from cogs.utility.config_permessi import ConfigPermessiCog
    from core.command_access import leggi_ruolo

    r_mod, r_adm = fake_role(31, "Mod"), fake_role(32, "Adm")
    guild = _guild_con_ruoli(r_mod, r_adm)
    cog = ConfigPermessiCog(MagicMock())
    cb = ConfigPermessiCog.staff.callback
    utente = fake_member(5, guild_permissions=discord.Permissions(manage_guild=True))
    utente.__class__ = discord.Member  # isinstance nel comando
    i = fake_interaction(guild=guild, user=utente)
    i.locale = discord.Locale.italian
    await cb(cog, i, mod=r_mod)
    assert await leggi_ruolo(920, TipoRuolo.MOD) == 31
    await cb(cog, i, admin=r_adm)  # chi ha solo «Gestisci server» non sceglie il ruolo admin (D28)
    assert await leggi_ruolo(920, TipoRuolo.ADMIN) is None
    assert "Amministratore" in i.response.send_message.await_args.args[0]
    await cb(cog, i, togli=MagicMock(value="mod"))
    assert await leggi_ruolo(920, TipoRuolo.MOD) is None
    await cb(cog, i, mod=r_mod, togli=MagicMock(value="mod"))
    assert await leggi_ruolo(920, TipoRuolo.MOD) is None  # scegliere e togliere insieme: rifiutato


async def test_il_comando_permessi_non_menziona_nessuno(db_pronto):
    from cogs.utility.config_permessi import ConfigPermessiCog

    guild = _guild_con_ruoli()
    membro = fake_member(77, guild_permissions=discord.Permissions(ban_members=True))
    i = fake_interaction(guild=guild, user=fake_member(5))
    i.locale = discord.Locale.italian
    await ConfigPermessiCog.permessi.callback(ConfigPermessiCog(MagicMock()), i, membro)
    args = i.response.send_message.await_args
    assert "✅ **Ban**" in args.args[0] and "❌ **Admin del bot**" in args.args[0]
    assert args.kwargs["ephemeral"] is True
    assert args.kwargs["allowed_mentions"].users is False

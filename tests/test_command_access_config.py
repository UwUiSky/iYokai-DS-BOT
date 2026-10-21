"""
tests/test_command_access_config.py
===================================
/config import e /config rollback non possono scrivere come ruolo del
bot un id che farebbe passare tutti (@everyone = id del server) o un
ruolo che nel server non esiste.
Funzioni coperte: NF-05 (issue #76)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import discord
import pytest

from cogs.utility.config_history import ConfigHistoryCog, RollbackConfirmView
from core import command_access as ca
from core.database import db
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_role

GUILD = 7700001
RUOLO = 5005005


class _File:
    def __init__(self, contenuto: bytes):
        self._c = contenuto
        self.size = len(contenuto)

    async def read(self):
        return self._c


@pytest.fixture(autouse=True)
def _pool(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    return clean_db


def _guild():
    g = fake_guild(guild_id=GUILD)
    g.get_role.side_effect = lambda rid: fake_role(role_id=rid) if rid == RUOLO else None
    return g


async def _importa(settings: dict) -> str:
    cog = ConfigHistoryCog(bot=None)
    ix = fake_interaction(guild=_guild())
    dati = {"modules": {}, "settings": settings, "language": "it"}
    await cog.import_config.callback(cog, ix, _File(json.dumps(dati).encode()))
    return ix.response.send_message.call_args.args[0]


@pytest.mark.parametrize("chiave", ["admin_role_id", "mod_role_id", "modban_role_id"])
async def test_import_rifiuta_l_id_del_server(chiave):
    msg = await _importa({chiave: GUILD})
    assert "✅" not in msg and chiave in msg
    assert (await db.get_full_config(GUILD))["settings"] == {}


@pytest.mark.parametrize("chiave", ["admin_role_id", "mod_role_id", "modban_role_id"])
async def test_import_rifiuta_un_ruolo_inesistente(chiave):
    msg = await _importa({chiave: 123})
    assert "✅" not in msg and chiave in msg
    assert (await db.get_full_config(GUILD))["settings"] == {}


async def test_import_accetta_un_ruolo_che_esiste():
    msg = await _importa({"admin_role_id": RUOLO})
    assert "✅" in msg
    assert (await db.get_full_config(GUILD))["settings"] == {"admin_role_id": RUOLO}


async def test_rollback_rifiuta_di_ripristinare_l_id_del_server():
    # una vecchia voce di storico con l'id del server come ruolo admin
    await db.set_guild_setting(GUILD, "admin_role_id", GUILD)
    await db.set_guild_setting(GUILD, "admin_role_id", RUOLO)
    voce = (await db.get_config_history(GUILD, limit=1))[0]
    assert voce.old_value == GUILD

    ix = fake_interaction(guild=_guild())
    ix.user.id = 9
    vista = RollbackConfirmView(voce.id, 9)
    await vista.confirm.callback(ix)

    assert (await db.get_full_config(GUILD))["settings"] == {"admin_role_id": RUOLO}
    testo = ix.response.edit_message.call_args.kwargs["content"]
    assert "✅" not in testo and "admin_role_id" in testo


async def test_rollback_normale_funziona_ancora():
    await db.set_guild_setting(GUILD, "report_channel_id", 5)
    await db.set_guild_setting(GUILD, "report_channel_id", 6)
    voce = (await db.get_config_history(GUILD, limit=1))[0]
    ix = fake_interaction(guild=_guild())
    ix.user.id = 9
    await RollbackConfirmView(voce.id, 9).confirm.callback(ix)
    assert (await db.get_full_config(GUILD))["settings"]["report_channel_id"] == 5


# ---- D28: il ruolo admin del bot lo sceglie solo chi ha «Amministratore» ----
def _ix_non_proprietario(permessi: discord.Permissions):
    from tests.support.discord_fakes import fake_member

    return fake_interaction(guild=_guild(), user=fake_member(user_id=9, guild_permissions=permessi))


async def _importa_come(permessi: discord.Permissions, settings: dict) -> str:
    cog = ConfigHistoryCog(bot=None)
    ix = _ix_non_proprietario(permessi)
    dati = {"modules": {}, "settings": settings, "language": "it"}
    await cog.import_config.callback(cog, ix, _File(json.dumps(dati).encode()))
    return ix.response.send_message.call_args.args[0]


async def test_import_ruolo_admin_con_solo_gestisci_server_rifiutato():
    msg = await _importa_come(discord.Permissions(manage_guild=True), {"admin_role_id": RUOLO})
    assert "✅" not in msg and "Amministratore" in msg
    assert (await db.get_full_config(GUILD))["settings"] == {}


async def test_import_ruolo_admin_con_amministratore_accettato():
    msg = await _importa_come(discord.Permissions(administrator=True), {"admin_role_id": RUOLO})
    assert "✅" in msg
    assert (await db.get_full_config(GUILD))["settings"] == {"admin_role_id": RUOLO}


async def test_import_con_lo_stesso_ruolo_admin_di_adesso_accettato():
    await db.set_guild_setting(GUILD, "admin_role_id", RUOLO)
    msg = await _importa_come(discord.Permissions(manage_guild=True), {"admin_role_id": RUOLO, "mod_role_id": RUOLO})
    assert "✅" in msg


async def test_rollback_che_rimette_il_ruolo_admin_serve_amministratore():
    await db.set_guild_setting(GUILD, "admin_role_id", RUOLO)
    await db.set_guild_setting(GUILD, "admin_role_id", None)
    voce = (await db.get_config_history(GUILD, limit=1))[0]

    ix = _ix_non_proprietario(discord.Permissions(manage_guild=True))
    await RollbackConfirmView(voce.id, 9).confirm.callback(ix)
    testo = ix.response.edit_message.call_args.kwargs["content"]
    assert "✅" not in testo and "Amministratore" in testo
    assert await ca.leggi_ruolo(GUILD, ca.TipoRuolo.ADMIN) is None

    ix = _ix_non_proprietario(discord.Permissions(administrator=True))
    await RollbackConfirmView(voce.id, 9).confirm.callback(ix)
    assert await ca.leggi_ruolo(GUILD, ca.TipoRuolo.ADMIN) == RUOLO


# ---- Livello dei permessi di backup: lo cambia solo il proprietario ----
async def test_import_livello_backup_da_admin_rifiutato():
    msg = await _importa_come(discord.Permissions(administrator=True), {"backup_livello_permessi": "admin_tutto"})
    assert "✅" not in msg and "proprietario" in msg
    assert (await db.get_full_config(GUILD))["settings"] == {}


async def test_import_livello_backup_uguale_a_adesso_accettato():
    await db.set_guild_setting(GUILD, "backup_livello_permessi", "admin_crea")
    msg = await _importa_come(discord.Permissions(administrator=True), {"backup_livello_permessi": "admin_crea"})
    assert "✅" in msg


async def test_import_livello_backup_non_valido_rifiutato():
    msg = await _importa_come(discord.Permissions(administrator=True), {"backup_livello_permessi": "tutti"})
    assert "✅" not in msg and "solo_owner" in msg

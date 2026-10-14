"""
tests/test_panel_bridge.py
==========================
Il ponte pannello → bot (SPEC §24): stessa regola d'accesso di `/admin`,
scritture dai punti unici dei comandi (D16), storico condiviso.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import core.database as database_module
from core import panel_bridge
from core.command_access import TipoRuolo, leggi_ruolo
from core.config_schema import ImpostazioneNonValida
from core.database import db
from core.premium import PremiumModule, registry
from tests.support.discord_fakes import fake_guild, fake_member, fake_role

GUILD = 7700
ADMIN = 11
UTENTE = 22


def _server(*, membri, ruoli=()):
    guild = fake_guild(guild_id=GUILD, name="Prova", owner_id=1)
    guild.roles = list(ruoli)
    guild.get_member = MagicMock(side_effect=lambda uid: membri.get(uid))
    guild.get_role = MagicMock(side_effect=lambda rid: next((r for r in ruoli if r.id == rid), None))
    guild.fetch_member = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "no"))
    return guild


@pytest.fixture
def pool(monkeypatch, clean_db, reset_premium_registry):
    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    registry.register(PremiumModule("modulo_web", "Modulo web", "Prova", category="utility"))
    return clean_db


@pytest.mark.asyncio
async def test_serve_gestisci_server_o_ruolo_admin(pool):
    ruolo_admin = fake_role(role_id=500, name="Staff")
    con_permesso = fake_member(ADMIN, guild_permissions=discord.Permissions(manage_guild=True))
    semplice = fake_member(UTENTE, roles=[ruolo_admin])
    guild = _server(membri={ADMIN: con_permesso, UTENTE: semplice}, ruoli=[ruolo_admin])

    assert await panel_bridge.puo_gestire(guild, ADMIN)
    assert not await panel_bridge.puo_gestire(guild, UTENTE)
    assert not await panel_bridge.puo_gestire(guild, 999)  # non è nel server

    await panel_bridge.applica_ruolo(guild, "admin", 500, ADMIN)
    assert await panel_bridge.puo_gestire(guild, UTENTE)


@pytest.mark.asyncio
async def test_scritture_dai_punti_unici_con_storico(pool):
    bot = MagicMock()
    guild = _server(membri={})
    assert await panel_bridge.applica_modulo(bot, guild, "modulo_web", True, ADMIN)
    bot.dispatch.assert_called_once_with("modules_updated", GUILD, "modulo_web", True, ADMIN)
    await panel_bridge.applica_lingua(guild, "en", ADMIN)
    voci = await panel_bridge.storico(GUILD)
    assert {(v.key_name, v.changed_by) for v in voci} == {("modulo_web", ADMIN), ("language", ADMIN)}
    assert [v.key_name for v in await panel_bridge.storico(GUILD, "module")] == ["modulo_web"]


@pytest.mark.asyncio
async def test_valori_non_validi_rifiutati(pool):
    gestito = fake_role(role_id=600, managed=True)
    guild = _server(membri={}, ruoli=[gestito])
    for chiamata in (
        panel_bridge.applica_modulo(None, guild, "inventato", True, ADMIN),
        panel_bridge.applica_lingua(guild, "zz", ADMIN),
        panel_bridge.applica_ruolo(guild, "boss", None, ADMIN),
        panel_bridge.applica_ruolo(guild, "mod", 404, ADMIN),
        panel_bridge.applica_ruolo(guild, "mod", 600, ADMIN),
    ):
        with pytest.raises(ImpostazioneNonValida):
            await chiamata
    assert await leggi_ruolo(GUILD, TipoRuolo.MOD) is None
    assert await db.get_config_history(GUILD) == []


@pytest.mark.asyncio
async def test_stato_server(pool):
    ruolo = fake_role(role_id=501, name="Mod", position=3)
    guild = _server(membri={}, ruoli=[ruolo, fake_role(role_id=GUILD, name="@everyone")])
    stato = await panel_bridge.stato_server(guild)
    assert stato["lingua"] == "it"
    assert [r["id"] for r in stato["ruoli_server"]] == [501]
    assert {m["nome"]: m["attivo"] for m in stato["moduli"]} == {"modulo_web": False}
    assert [r["tipo"] for r in stato["ruoli_bot"]] == ["admin", "mod", "modban"]

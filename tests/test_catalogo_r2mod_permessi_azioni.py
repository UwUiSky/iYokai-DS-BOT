"""
tests/test_catalogo_r2mod_permessi_azioni.py
============================================
CFG-024: un ruolo con il permesso di una sola azione di moderazione la usa senza il permesso di Discord,
e non può dare le altre. Database vero.
"""

import types

import discord
import pytest

from cogs.moderation.opzioni import OpzioniModerazioneCog
from core import command_access as ca
from core import moderation_permessi_azioni as pa
from core.command_access import Livello, AccessoNegato
from core.database import db
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role

G, RUOLO = 100, 500


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    yield
    database_module.db._modules_cache.clear()


def _inter(comando: str | None, *, ruoli=(RUOLO,)):
    server = fake_guild(G, owner_id=1)
    ruoli_veri = {r: fake_role(r, f"r{r}", position=5) for r in ruoli}
    server.get_role = lambda rid: ruoli_veri.get(rid)
    utente = fake_member(77, roles=list(ruoli_veri.values()), guild_permissions=discord.Permissions.none())
    inter = fake_interaction(guild=server, user=utente)
    inter.command = types.SimpleNamespace(qualified_name=comando) if comando else None
    return inter


async def _dai(azione, ruolo=RUOLO):
    await db.ensure_guild_exists(G)
    await db.pool.execute(
        "INSERT INTO moderation_ruoli_azioni (guild_id, role_id, azione) VALUES ($1, $2, $3)", G, ruolo, azione
    )


# CFG-024
async def test_un_ruolo_autorizzato_solo_a_timeout_usa_timeout_e_non_il_resto():
    await _dai("timeout")
    assert await ca.controlla(_inter("mod-sanzioni timeout"), Livello.MOD) is True
    assert await ca.controlla(_inter("mod-sanzioni untimeout"), Livello.MOD) is True
    for comando, livello in (
        ("mod-ban ban", Livello.MODBAN), ("mod-ban kick", Livello.MODBAN), ("mod-ban tempban", Livello.MODBAN),
        ("mod-sanzioni warn", Livello.MOD), ("mod-sanzioni mute", Livello.MOD),
        ("mod-sanzioni massa timeout", Livello.MOD), ("mod-casi caso elimina", Livello.MOD),
    ):
        with pytest.raises(AccessoNegato):
            await ca.controlla(_inter(comando), livello)


# CFG-024
async def test_il_ruolo_deve_essere_quello_di_chi_comanda_e_senza_permesso_resta_rifiutato():
    await _dai("timeout", ruolo=999)
    with pytest.raises(AccessoNegato):
        await ca.controlla(_inter("mod-sanzioni timeout"), Livello.MOD)


# CFG-024
async def test_i_tasti_passano_l_azione_perche_non_hanno_un_comando():
    await _dai("ban")
    assert await ca.puo_usare(_inter(None), Livello.MODBAN, "ban") is True
    assert await ca.puo_usare(_inter(None), Livello.MODBAN, "kick") is False
    assert await ca.puo_usare(_inter(None), Livello.MODBAN) is False


# CFG-024
async def test_le_azioni_non_aprono_i_livelli_admin_e_security():
    await _dai("timeout")
    with pytest.raises(AccessoNegato):
        await ca.controlla(_inter("mod-sanzioni timeout"), Livello.ADMIN)


# CFG-024
async def test_everyone_gestiti_e_ruoli_sopra_chi_concede_si_rifiutano():
    server = fake_guild(G, owner_id=1)
    autore = fake_member(10, roles=[fake_role(1, position=20)])
    assert await pa.concedi(server, fake_role(0, position=0), "timeout", autore) is not None
    assert await pa.concedi(server, fake_role(6, position=5, managed=True), "timeout", autore) is not None
    assert await pa.concedi(server, fake_role(7, position=25), "timeout", autore) is not None
    assert await pa.concedi(server, fake_role(8, position=5), "azione-finta", autore) is not None
    assert await pa.concedi(server, fake_role(9, position=5), "timeout", autore) is None
    assert await pa.elenco(G) == {9: ["timeout"]}
    assert await pa.togli(G, 9, None) == 1


# CFG-024
async def test_il_comando_concede_e_toglie_solo_a_chi_gestisce_il_server():
    server = fake_guild(G, owner_id=1)
    from cogs.moderation._shared import MODULE_ACTIONS

    await db.set_module_active_for_guild(G, MODULE_ACTIONS, True)
    ruolo = fake_role(RUOLO, "Aiuto", position=5)
    cog = OpzioniModerazioneCog(bot=None)
    senza = fake_member(10, roles=[fake_role(1, position=20)], guild_permissions=discord.Permissions.none())
    i = fake_interaction(guild=server, user=senza)
    await cog.azioni.callback(cog, i, ruolo, discord.app_commands.Choice(name="timeout", value="timeout"))
    assert await pa.elenco(G) == {}
    admin = fake_member(11, roles=[fake_role(1, position=20)], guild_permissions=discord.Permissions(manage_guild=True))
    i = fake_interaction(guild=server, user=admin)
    await cog.azioni.callback(cog, i, ruolo, discord.app_commands.Choice(name="timeout", value="timeout"))
    assert await pa.elenco(G) == {RUOLO: ["timeout"]}
    await cog.azioni.callback(cog, i, ruolo, None, True)
    assert await pa.elenco(G) == {}


# VER-018
async def test_il_ruolo_con_l_azione_verifica_verifica_a_mano_ma_non_tocca_altro_di_sicurezza():
    await _dai("verifica")
    assert await ca.controlla(_inter("admin-sicurezza-verifica manuale"), Livello.SECURITY) is True
    assert await ca.controlla(_inter("admin-sicurezza-verifica invia"), Livello.SECURITY) is True
    for comando in ("admin-sicurezza-verifica setup", "admin-sicurezza panico attiva", "admin-sicurezza-verifica whitelist-add"):
        with pytest.raises(AccessoNegato):
            await ca.controlla(_inter(comando), Livello.SECURITY)
    with pytest.raises(AccessoNegato):  # l'azione «verifica» non apre i livelli mod
        await ca.controlla(_inter("admin-sicurezza-verifica manuale"), Livello.MOD)


# VER-018
async def test_il_ruolo_con_solo_timeout_non_verifica():
    await _dai("timeout")
    with pytest.raises(AccessoNegato):
        await ca.controlla(_inter("admin-sicurezza-verifica manuale"), Livello.SECURITY)

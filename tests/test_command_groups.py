"""
tests/test_command_groups.py
============================
I 16 gruppi di primo livello della mappa F7 (D24): nomi, descrizioni,
permessi predefiniti, livello di accesso, aggiunta di comandi.
Funzioni coperte: NF-05 (issue #76)
"""

from __future__ import annotations

import discord
import pytest
from discord import app_commands

from core import command_groups as cg
from core.command_access import Livello

ATTESI = [
    "owner", "admin", "gestione", "moduli", "security", "automod", "mod", "modban",
    "log", "ticket", "voice", "music", "level", "clan", "fun", "utility",
]
PERMESSI = {
    "admin": "manage_guild", "gestione": "manage_guild", "moduli": "manage_guild",
    "automod": "manage_guild", "log": "manage_guild",
    "security": "administrator", "owner": "administrator",
    "mod": "moderate_members", "modban": "ban_members",
}
LIVELLI = {
    "owner": Livello.OWNER, "admin": Livello.ADMIN, "gestione": Livello.ADMIN,
    "moduli": Livello.ADMIN, "automod": Livello.ADMIN, "security": Livello.SECURITY,
    "mod": Livello.MOD, "modban": Livello.MODBAN, "log": Livello.LOG,
}


def test_i_16_gruppi_in_ordine():
    assert list(cg.nomi_gruppi()) == ATTESI


@pytest.mark.parametrize("nome", ATTESI)
def test_gruppo_italiano_guild_only_e_permessi(nome):
    g = cg.ottieni_gruppo(nome)
    assert isinstance(g, app_commands.Group)
    assert g.name == nome
    assert 1 <= len(g.description) <= 100
    assert not g.description.startswith("[")
    assert g.guild_only is True
    attesi = PERMESSI.get(nome)
    if attesi is None:
        assert g.default_permissions is None
    else:
        assert g.default_permissions == discord.Permissions(**{attesi: True})
    assert getattr(g, "livello", None) == LIVELLI.get(nome)


def test_gruppo_sconosciuto():
    with pytest.raises(KeyError):
        cg.ottieni_gruppo("non-esiste")


def test_aggiungi_comando_a_gruppo_e_idempotente():
    gruppi = cg.costruisci_gruppi()

    async def cb(interaction: discord.Interaction):  # pragma: no cover
        pass

    cmd = app_commands.Command(name="prova", description="Prova", callback=cb)
    cg.aggiungi_a_gruppo("fun", cmd, gruppi=gruppi)
    cg.aggiungi_a_gruppo("fun", cmd, gruppi=gruppi)  # secondo caricamento del cog
    assert [c.name for c in gruppi["fun"].commands] == ["prova"]


def test_aggiungi_a_sottogruppo_lo_crea_una_volta_con_il_controllo_del_padre():
    gruppi = cg.costruisci_gruppi()

    async def cb(interaction: discord.Interaction):  # pragma: no cover
        pass

    cmd = app_commands.Command(name="x", description="X", callback=cb)
    cg.aggiungi_a_gruppo("admin", cmd, sottogruppo=("config", "Configurazione del server"), gruppi=gruppi)
    cmd2 = app_commands.Command(name="y", description="Y", callback=cb)
    cg.aggiungi_a_gruppo("admin", cmd2, sottogruppo=("config", "Configurazione del server"), gruppi=gruppi)
    sotto = [c for c in gruppi["admin"].commands if c.name == "config"]
    assert len(sotto) == 1 and isinstance(sotto[0], app_commands.Group)
    assert sorted(c.name for c in sotto[0].commands) == ["x", "y"]
    assert sotto[0].parent is gruppi["admin"]


def test_registra_gruppi_usati_salta_i_vuoti():
    from discord.ext import commands

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    gruppi = cg.costruisci_gruppi()

    async def cb(interaction: discord.Interaction):  # pragma: no cover
        pass

    cg.aggiungi_a_gruppo("fun", app_commands.Command(name="p", description="P", callback=cb), gruppi=gruppi)
    aggiunti = cg.registra_gruppi_usati(bot.tree, gruppi=gruppi)
    assert aggiunti == ["fun"]
    assert [c.name for c in bot.tree.get_commands()] == ["fun"]


def test_nessun_gruppo_registrato_di_default_nell_albero_vero():
    # il modulo, da solo, non cambia l'albero di nessun bot
    from discord.ext import commands

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    assert bot.tree.get_commands() == []

"""
tests/test_f7_admin_moduli_gruppi.py
====================================
I comandi di configurazione stanno in /admin e /moduli, col nome e il
livello giusti (mappa F7 passo 2c): nessun comando di primo livello
vecchio, nessun controllo di permesso duplicato sui comandi, tetti di Discord rispettati.
Funzioni coperte: NF-05 (issue #76)
"""

import discord
from discord import app_commands
from discord.ext import commands

from cogs.utility.backup import setup as backup_setup
from cogs.utility.config_history import setup as config_setup
from cogs.utility.feed_alerts import setup as feed_setup
from cogs.utility.restore import setup as restore_setup
from cogs.utility.scheduled_messages import setup as sched_setup
from cogs.utility.setup import setup as setup_setup
from cogs.utility.sticky_messages import setup as sticky_setup
from core.command_access import Livello
from core.command_groups import GRUPPI
from tests.support.percorsi import percorsi_del_gruppo

ADMIN_ATTESI = {
    "config history", "config rollback", "config reset", "config export", "config import",
    "lingua show", "lingua set",
    "setup attiva", "setup wizard",
    "messaggi programma", "messaggi programmati", "messaggi annulla",
    "messaggi sticky-set", "messaggi sticky-togli",
}
# D25 (15/10): il blocco backup è il gruppo di primo livello /backup.
BACKUP_ATTESI = {"main", "crea", "collega", "promuovi", "restore-utenti", "restore-modo"}
MODULI_ATTESI = {
    "alert feed", "alert webhook", "alert rimuovi", "alert twitch", "alert youtube-live", "alert elenco",
}
VECCHI_TOP = {
    "config", "setup", "setup-wizard", "alerts", "schedule-message", "sticky", "define-main",
    "define-backup", "promuovi-backup", "configura-restore", "restore-users",
}


def _comandi(gruppo):
    for figlio in gruppo.commands:
        if isinstance(figlio, app_commands.Group):
            yield from _comandi(figlio)
        else:
            yield figlio


async def _carica_cog():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    for setup in (config_setup, setup_setup, backup_setup, restore_setup, sched_setup, sticky_setup, feed_setup):
        await setup(bot)
    return bot


async def test_admin_e_moduli_hanno_i_comandi_giusti_e_il_livello_giusto():
    bot = await _carica_cog()
    assert ADMIN_ATTESI <= percorsi_del_gruppo("admin")
    assert MODULI_ATTESI <= percorsi_del_gruppo("moduli")
    assert BACKUP_ATTESI <= percorsi_del_gruppo("backup")
    assert not {p for p in percorsi_del_gruppo("admin") if p.startswith("backup ")}
    assert GRUPPI["admin"].livello is Livello.ADMIN
    assert GRUPPI["moduli"].livello is Livello.ADMIN
    assert GRUPPI["admin"].default_permissions == discord.Permissions(manage_guild=True)
    assert GRUPPI["moduli"].default_permissions == discord.Permissions(manage_guild=True)
    # nessun vecchio comando di primo livello nell'albero
    assert not VECCHI_TOP & {c.name for c in bot.tree.get_commands()}


async def test_admin_e_moduli_rispettano_i_tetti_e_non_duplicano_i_permessi():
    await _carica_cog()
    for nome in ("admin", "moduli"):
        gruppo = GRUPPI[nome]
        assert len(gruppo.commands) <= 25
        for figlio in gruppo.commands:
            if isinstance(figlio, app_commands.Group):
                assert len(figlio.commands) <= 25
                assert not any(isinstance(x, app_commands.Group) for x in figlio.commands)
        for comando in _comandi(gruppo):
            assert len(comando.name) <= 32
            assert not comando.description.startswith("[Admin]"), comando.qualified_name
            assert not comando.checks, f"{comando.qualified_name}: il permesso lo dà il gruppo"

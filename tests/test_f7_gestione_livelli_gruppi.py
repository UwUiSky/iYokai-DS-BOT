"""
tests/test_f7_gestione_livelli_gruppi.py
========================================
Livelli, economia, clan, benvenuto e ruoli stanno nei gruppi giusti, col
nome giusto (mappa F7 passo 3a): /level, /clan (pubblici), /gestione
economia|ruoli|benvenuto (solo admin dal gruppo). Nessun vecchio comando
di primo livello, nessun prefisso [Admin], tetti di Discord rispettati.
Funzioni coperte: NF-05 (issue #76, #24)
"""

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling.leveling import setup as leveling_setup
from cogs.utility.greetings import setup as greetings_setup
from cogs.utility.role_menus import setup as role_menus_setup
from core.command_access import Livello
from core.command_groups import GRUPPI
from tests.support.percorsi import comando_nel_gruppo, percorsi_del_gruppo

LEVEL_ATTESI = {
    "rank", "balance", "daily", "work", "pay", "leaderboard", "cassa", "shop list", "shop buy",
}
CLAN_ATTESI = {
    "crea", "info", "membri", "classifica", "sciogli", "invita", "lascia", "espelli", "promuovi",
    "compra-canale", "bacheca set", "bacheca disable", "tesoreria dona", "tesoreria trasferisci",
    "boost individuale", "boost gilda",
}
ECONOMIA_ATTESI = {
    "economia shop-add", "economia shop-remove", "economia cassa-premium", "economia assegna-lobby",
    "economia assegna-winner", "economia giveaway", "economia vincitori-set", "economia vincitori-off",
}
RUOLI_ATTESI = {
    "ruoli livello-add", "ruoli livello-remove", "ruoli livello-list",
    "ruoli menu-crea", "ruoli menu-aggiungi", "ruoli menu-togli", "ruoli menu-elimina",
}
BENVENUTO_ATTESI = {"benvenuto benvenuto", "benvenuto addio", "benvenuto boost", "benvenuto anteprima"}
VECCHI_TOP = {
    "rank", "balance", "daily", "work", "pay", "leaderboard", "shop", "cassa", "level-roles",
    "monthly-winners", "assegna-lobby", "assegna-winner", "giveaway", "greetings", "rolemenu",
}


def _comandi(gruppo):
    for figlio in gruppo.commands:
        if isinstance(figlio, app_commands.Group):
            yield from _comandi(figlio)
        else:
            yield figlio


async def _carica(clean_db):
    from core.database import db

    await db.connect()
    try:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        bot.wait_until_ready = asyncio.Event().wait  # il task vocale resta in attesa, poi lo ferma remove_cog
        for setup in (leveling_setup, greetings_setup, role_menus_setup):
            await setup(bot)
    finally:
        await db.close()
    return bot


async def _scarica(bot):
    for nome in ("LevelingCog", "GreetingsCog", "RoleMenuCog"):
        await bot.remove_cog(nome)


async def test_comandi_nei_gruppi_giusti(clean_db):
    bot = await _carica(clean_db)
    try:
        assert LEVEL_ATTESI <= percorsi_del_gruppo("level")
        assert CLAN_ATTESI <= percorsi_del_gruppo("clan")
        gestione = percorsi_del_gruppo("gestione")
        assert ECONOMIA_ATTESI <= gestione
        assert RUOLI_ATTESI <= gestione
        assert BENVENUTO_ATTESI <= gestione
        assert not VECCHI_TOP & {c.name for c in bot.tree.get_commands()}
    finally:
        await _scarica(bot)


async def test_livelli_di_accesso(clean_db):
    bot = await _carica(clean_db)
    try:
        assert GRUPPI["level"].livello is None
        assert GRUPPI["clan"].livello is None
        assert GRUPPI["gestione"].livello is Livello.ADMIN
        # i comandi admin di un gruppo pubblico controllano il livello nel codice
        for percorso in ("bacheca set", "bacheca disable"):
            assert len(comando_nel_gruppo("clan", percorso).checks) == 1
        # i comandi pubblici non hanno controlli di permesso propri
        for percorso in ("crea", "boost gilda", "tesoreria dona"):
            assert not comando_nel_gruppo("clan", percorso).checks
    finally:
        await _scarica(bot)


async def test_tetti_e_descrizioni(clean_db):
    bot = await _carica(clean_db)
    try:
        for nome in ("level", "clan", "gestione"):
            gruppo = GRUPPI[nome]
            assert len(gruppo.commands) <= 25
            for figlio in gruppo.commands:
                if isinstance(figlio, app_commands.Group):
                    assert len(figlio.commands) <= 25
                    assert not any(isinstance(x, app_commands.Group) for x in figlio.commands)
        for nome in ("level", "clan"):
            for comando in _comandi(GRUPPI[nome]):
                assert not comando.description.startswith("["), comando.qualified_name
                assert len(comando.name) <= 32
        for comando in _comandi(GRUPPI["gestione"]):
            assert not comando.description.startswith("[Admin]"), comando.qualified_name
            assert not comando.checks, f"{comando.qualified_name}: il permesso lo dà il gruppo"
    finally:
        await _scarica(bot)


async def test_scaricare_il_cog_toglie_i_comandi(clean_db):
    bot = await _carica(clean_db)
    await _scarica(bot)
    assert "rank" not in percorsi_del_gruppo("level")
    assert not any(p.startswith("economia ") for p in percorsi_del_gruppo("gestione"))
    # solo i percorsi dei cog scaricati: GRUPPI è globale e altri test possono lasciarvi comandi loro
    assert not (percorsi_del_gruppo("gestione") & (ECONOMIA_ATTESI | RUOLI_ATTESI | BENVENUTO_ATTESI))


async def test_bacheca_clan_chiede_il_livello_admin_del_bot(clean_db, monkeypatch):
    """`/clan bacheca set|disable`: permesso di Discord OPPURE ruolo admin del bot; altrimenti rifiuto."""
    import types

    import pytest

    from core import command_access as ca
    from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role

    ruolo_admin = 555
    impostazioni = {(77, ca.SETTING_ADMIN_ROLE): ruolo_admin}

    class _Db:
        async def get_guild_setting(self, guild_id, key, default=None):
            return impostazioni.get((guild_id, key), default)

    monkeypatch.setattr(ca, "db", _Db())
    monkeypatch.setattr(ca, "config", types.SimpleNamespace(OWNER_ID=1))

    def interazione(*, perm=None, ruoli=()):
        guild = fake_guild(guild_id=77, owner_id=2)
        guild.get_role.side_effect = lambda rid: fake_role(role_id=rid) if rid == ruolo_admin else None
        membro = fake_member(
            user_id=3,
            roles=[fake_role(role_id=r) for r in ruoli],
            guild_permissions=discord.Permissions(**{perm: True}) if perm else discord.Permissions.none(),
        )
        return fake_interaction(guild=guild, user=membro)

    bot = await _carica(clean_db)
    try:
        for percorso in ("bacheca set", "bacheca disable"):
            check = comando_nel_gruppo("clan", percorso).checks[0]
            assert await check(interazione(perm="manage_guild")) is True
            assert await check(interazione(ruoli=[ruolo_admin])) is True  # non solo manage_guild
            with pytest.raises(ca.AccessoNegato):
                await check(interazione(perm="manage_messages"))
    finally:
        await _scarica(bot)


async def test_nel_gruppo_clan_solo_la_bacheca_ha_controlli_di_permesso(clean_db):
    bot = await _carica(clean_db)
    try:
        con_check = {p for p in CLAN_ATTESI if comando_nel_gruppo("clan", p).checks}
        assert con_check == {"bacheca set", "bacheca disable"}
    finally:
        await _scarica(bot)

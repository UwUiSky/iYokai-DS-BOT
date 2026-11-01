"""
tests/test_f7_gestione_livelli_gruppi.py
========================================
Livelli, economia, clan, benvenuto e ruoli stanno nei gruppi giusti, col
nome giusto (mappa F7 passo 3a, D56): /level, /monete, /clan (pubblici), /economia,
/ruoli, /giveaway, /gestione benvenuto (solo admin dal gruppo). Nessun vecchio comando
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

LEVEL_ATTESI = {"rank", "leaderboard"}
MONETE_ATTESI = {"balance", "daily", "work", "pay", "cassa", "shop list", "shop buy"}
CLAN_ATTESI = {
    "crea", "info", "membri", "classifica", "sciogli", "invita", "lascia", "espelli", "promuovi",
    "compra-canale", "tesoreria dona", "tesoreria trasferisci",
    "boost individuale", "boost gilda",
}
ECONOMIA_ATTESI = {
    "shop-add", "shop-remove", "cassa-premium", "assegna-lobby",
    "assegna-winner", "annunci vincitori-set", "annunci vincitori-off", "annunci clan-set", "annunci clan-off",
}
GIVEAWAY_ATTESI = {"avvia"}
RUOLI_ATTESI = {
    "premio aggiungi", "premio togli", "premio elenco",
    "menu crea", "menu aggiungi", "menu togli", "menu elimina",
}
BENVENUTO_ATTESI = {"benvenuto benvenuto", "benvenuto addio", "benvenuto boost", "benvenuto anteprima"}
VECCHI_TOP = {
    "rank", "balance", "daily", "work", "pay", "leaderboard", "shop", "cassa", "level-roles",
    "monthly-winners", "assegna-lobby", "assegna-winner", "greetings", "rolemenu",
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
        assert MONETE_ATTESI <= percorsi_del_gruppo("monete")
        assert CLAN_ATTESI <= percorsi_del_gruppo("clan")
        gestione = percorsi_del_gruppo("gestione")
        assert ECONOMIA_ATTESI <= percorsi_del_gruppo("economia")
        assert GIVEAWAY_ATTESI <= percorsi_del_gruppo("giveaway")
        assert not {p for p in gestione if p.startswith(("economia", "xp", "monete", "shop-", "giveaway", "ruoli"))}
        assert RUOLI_ATTESI <= percorsi_del_gruppo("ruoli")
        assert BENVENUTO_ATTESI <= gestione
        assert not VECCHI_TOP & {c.name for c in bot.tree.get_commands()}
    finally:
        await _scarica(bot)


async def test_livelli_di_accesso(clean_db):
    bot = await _carica(clean_db)
    try:
        assert GRUPPI["level"].livello is None
        assert GRUPPI["clan"].livello is None
        assert GRUPPI["monete"].livello is None
        assert GRUPPI["gestione"].livello is Livello.ADMIN
        assert GRUPPI["economia"].livello is Livello.ADMIN
        # D56: la bacheca clan è per lo staff, quindi sta in /economia annunci
        assert GRUPPI["clan"].get_command("bacheca") is None
        # i comandi pubblici non hanno controlli di permesso propri
        for percorso in ("crea", "boost gilda", "tesoreria dona"):
            assert not comando_nel_gruppo("clan", percorso).checks
    finally:
        await _scarica(bot)


async def test_tetti_e_descrizioni(clean_db):
    bot = await _carica(clean_db)
    try:
        for nome in ("level", "monete", "clan", "gestione", "economia", "ruoli", "giveaway"):
            gruppo = GRUPPI[nome]
            assert len(gruppo.commands) <= 25
            for figlio in gruppo.commands:
                if isinstance(figlio, app_commands.Group):
                    assert len(figlio.commands) <= 25
                    assert not any(isinstance(x, app_commands.Group) for x in figlio.commands)
        for nome in ("level", "monete", "clan"):
            for comando in _comandi(GRUPPI[nome]):
                assert not comando.description.startswith("["), comando.qualified_name
                assert len(comando.name) <= 32
        for comando in (*_comandi(GRUPPI["gestione"]), *_comandi(GRUPPI["economia"]), *_comandi(GRUPPI["ruoli"])):
            assert not comando.description.startswith("[Admin]"), comando.qualified_name
            assert not comando.checks, f"{comando.qualified_name}: il permesso lo dà il gruppo"
    finally:
        await _scarica(bot)


async def test_scaricare_il_cog_toglie_i_comandi(clean_db):
    bot = await _carica(clean_db)
    await _scarica(bot)
    assert "rank" not in percorsi_del_gruppo("level")
    assert "balance" not in percorsi_del_gruppo("monete")
    # solo i percorsi dei cog scaricati: GRUPPI è globale e altri test possono lasciarvi comandi loro
    assert not (percorsi_del_gruppo("economia") & ECONOMIA_ATTESI)
    assert not (percorsi_del_gruppo("ruoli") & RUOLI_ATTESI)
    assert not (percorsi_del_gruppo("gestione") & BENVENUTO_ATTESI)


async def test_bacheca_clan_chiede_il_livello_admin_del_bot(clean_db, monkeypatch):
    """`/economia annunci clan-set|clan-off`: il gruppo chiede il livello admin del bot (permesso di Discord OPPURE ruolo admin)."""
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
        for percorso in ("annunci clan-set", "annunci clan-off"):
            comando = comando_nel_gruppo("economia", percorso)
            assert comando.parent._livello_effettivo() is Livello.ADMIN
            check = comando.parent.interaction_check
            assert await check(interazione(perm="manage_guild")) is True
            assert await check(interazione(ruoli=[ruolo_admin])) is True  # non solo manage_guild
            with pytest.raises(ca.AccessoNegato):
                await check(interazione(perm="manage_messages"))
    finally:
        await _scarica(bot)


async def test_nel_gruppo_clan_nessun_comando_ha_controlli_di_permesso(clean_db):
    bot = await _carica(clean_db)
    try:
        con_check = {p for p in CLAN_ATTESI if comando_nel_gruppo("clan", p).checks}
        assert con_check == set()
    finally:
        await _scarica(bot)

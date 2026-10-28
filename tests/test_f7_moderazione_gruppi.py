"""
tests/test_f7_moderazione_gruppi.py
===================================
F7 passo 2b: i comandi di moderazione, sicurezza, AutoMod e log stanno nei
gruppi giusti, con il nome giusto e il livello giusto (mappa F7), e i
vecchi nomi di primo livello non esistono più (D4).
Funzioni coperte: NF-05 (issue #76, #3, #40, #24, #31)
"""

import importlib

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from core.command_access import GruppoYokai, Livello

MODULI = (
    "cogs.moderation.actions",
    "cogs.moderation.ban_appeal",
    "cogs.moderation.case_system",
    "cogs.moderation.channel_control",
    "cogs.moderation.clear",
    "cogs.moderation.softban_mute",
    "cogs.moderation.opzioni",
    "cogs.security.anti_nuke",
    "cogs.security.anti_raid",
    "cogs.security.global_ban",
    "cogs.security.lockdown",
    "cogs.security.verify",
    "cogs.security.permission_heatmap",
    "cogs.security.security_score",
    "cogs.security.spam_trap",
    "cogs.automod.automod",
    "cogs.automod.escalation",
    "cogs.automod.parole_odio",
    "cogs.logging.basic_logs",
    "cogs.logging.logs_query",
)

# (gruppo, sottogruppo o None) -> nomi dei figli attesi
ATTESI: dict[tuple[str, str | None], set[str]] = {
    ("mod", None): {"warn", "timeout", "untimeout", "clear", "lock", "unlock", "slowmode", "mute", "unmute"},
    ("mod", "caso"): {"storico", "vedi", "motivo", "elimina", "classifica-staff", "attive", "registra"},
    ("mod", "nota"): {"aggiungi", "elenca", "rimuovi", "modifica", "svuota"},
    ("mod", "avvisi"): {"togli", "azzera", "classifica"},
    ("mod", "blocco"): {"attiva", "togli"},
    ("mod", "opzioni"): {"imposta", "dm", "immuni"},
    ("mod", "massa"): {"timeout", "warn"},
    ("modban", None): {"ban", "tempban", "softban", "kick", "unban"},
    ("modban", "appelli"): {"canale", "elenco"},
    ("modban", "massa"): {"ban", "unban", "kick"},
    ("security", None): {"heatmap", "score", "spamtrap"},
    ("security", "escalation"): {"enable", "disable", "set-reset-days", "set-step", "remove-step", "reset", "status"},
    ("antinuke", None): {
        "enable", "limits", "trusted-add", "trusted-remove", "trusted-list", "punish-action", "recovery", "status",
        "guardie", "casi", "rilascia", "canale-allarmi",
    },
    ("antiraid", None): {
        "enable", "join-rate", "account-age", "username-check", "avatar-check",
        "lockdown-action", "alert-channel", "status", "quarantine-hold", "rilascia",
        "filtro-ingresso", "nomi-vietati", "segnali", "ping-ruoli", "elenco", "segnala", "livello",
    },
    ("security", "panico"): {"attiva", "togli", "configura", "stato"},
    ("security", "globalban"): {"enable", "disable", "status", "controlla"},
    ("security", "verify"): {
        "setup", "panel", "whitelist-add", "whitelist-remove", "blacklist-add", "blacklist-remove",
        "opzioni", "manuale", "tentativi", "statistiche", "tempi", "invia",
    },
    ("automod", None): {"sync", "mute-duration", "log-channel", "status", "violazioni", "violazione-togli"},
    ("automod", "filtri"): {
        "invites", "anti-link-mode", "anti-link-domain", "anti-spam-messages", "anti-spam-emoji",
        "anti-spam-sticker", "anti-caps", "anti-zalgo", "phishing", "forma-testo", "anti-mention", "anti-attachment", "actions-set",
        "messaggi", "contenuto", "canale-media",
    },
    ("automod", "parole"): {"add", "remove", "list"},
    ("automod", "odio"): {"stato", "base", "parola", "nomi", "prova"},
    ("automod", "esenzioni"): {"channel-add", "channel-remove", "role-add", "role-remove"},
    ("log", None): {"canale", "stato", "esporta", "archivio-canale"},
    ("log", "cerca"): {"utente", "canale", "ruolo"},
}

LIVELLI = {
    "mod": Livello.MOD,
    "modban": Livello.MODBAN,
    "security": Livello.SECURITY,
    "antinuke": Livello.SECURITY,
    "antiraid": Livello.SECURITY,
    "automod": Livello.ADMIN,
    "log": Livello.LOG,
}

VECCHI_NOMI = {
    "warn", "kick", "ban", "tempban", "unban", "timeout", "untimeout", "softban", "mute-role",
    "unmute-role", "modcase", "modnote", "lock", "unlock", "slowmode", "clear", "mod-log-setup",
    "escalation", "anti-nuke", "anti-raid", "global-ban", "verify", "permission-heatmap",
    "security-score", "spamtrap-setup", "logs", "logs-setup", "logs-status",
}


@pytest.fixture
async def bot():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    for modulo in MODULI:
        await importlib.import_module(modulo).setup(bot)
    yield bot
    for nome in list(bot.cogs):
        await bot.remove_cog(nome)


def _nodo(bot, gruppo, sotto):
    nodo = bot.tree.get_command(gruppo)
    return nodo.get_command(sotto) if sotto else nodo


@pytest.mark.parametrize("gruppo,sotto", sorted(ATTESI, key=str))
async def test_il_gruppo_ha_i_comandi_giusti(bot, gruppo, sotto):
    nodo = _nodo(bot, gruppo, sotto)
    figli = {c.name for c in nodo.commands if not isinstance(c, app_commands.Group)}
    assert figli == ATTESI[(gruppo, sotto)]


@pytest.mark.parametrize("gruppo", sorted(LIVELLI))
async def test_il_gruppo_ha_il_livello_giusto(bot, gruppo):
    radice = bot.tree.get_command(gruppo)
    assert isinstance(radice, GruppoYokai)
    assert radice.livello is LIVELLI[gruppo]
    for figlio in radice.commands:
        if isinstance(figlio, app_commands.Group):
            assert isinstance(figlio, GruppoYokai)
            assert figlio._livello_effettivo() is LIVELLI[gruppo]


async def test_i_vecchi_nomi_di_primo_livello_sono_spariti(bot):
    presenti = {c.name for c in bot.tree.get_commands()}
    assert presenti.isdisjoint(VECCHI_NOMI)
    # Il Verify mette anche /utility verifica (VER-010), il comando per i membri.
    assert presenti == set(LIVELLI) | {"utility"}


async def test_nessun_prefisso_admin_e_nessun_check_di_permesso_locale(bot):
    for radice in bot.tree.get_commands():
        for nodo in radice.walk_commands():
            assert not nodo.description.startswith("["), nodo.qualified_name
            if isinstance(nodo, app_commands.Command):
                assert nodo.default_permissions is None, nodo.qualified_name
                assert nodo.guild_only is False or radice.guild_only, nodo.qualified_name


async def test_log_canale_ha_il_tipo_con_le_scelte(bot):
    comando = bot.tree.get_command("log").get_command("canale")
    opzioni = {o["name"]: o for o in comando.to_dict(bot.tree)["options"]}
    assert opzioni["channel"]["required"] is True
    assert opzioni["tipo"].get("required", False) is False
    assert {c["value"] for c in opzioni["tipo"]["choices"]} == {"eventi", "messaggi", "voce", "server", "sanzioni"}


class _FakeDb:
    def __init__(self):
        self.scritti = {}

    async def set_guild_setting(self, guild_id, key, value, changed_by=None):
        self.scritti[(guild_id, key)] = value


async def test_log_canale_sanzioni_scrive_il_canale_del_mod_log(monkeypatch):
    from unittest.mock import AsyncMock

    from cogs.logging import basic_logs
    from cogs.moderation._shared import SETTING_MOD_LOG_CHANNEL
    from tests.support.discord_fakes import fake_guild, fake_interaction, fake_text_channel

    finto = _FakeDb()
    monkeypatch.setattr(basic_logs, "db", finto)
    monkeypatch.setattr(basic_logs, "ensure_module_enabled", AsyncMock(return_value=True))
    cog = basic_logs.BasicLogsCog(bot=None)
    ix = fake_interaction(guild=fake_guild(guild_id=77, owner_id=2))
    await cog.logs_setup.callback(cog, ix, fake_text_channel(channel_id=900), "sanzioni")
    assert finto.scritti == {(77, SETTING_MOD_LOG_CHANNEL): 900}


async def test_log_canale_sanzioni_si_ferma_se_il_modulo_e_spento(monkeypatch):
    from unittest.mock import AsyncMock

    from cogs.logging import basic_logs
    from tests.support.discord_fakes import fake_guild, fake_interaction, fake_text_channel

    finto = _FakeDb()
    monkeypatch.setattr(basic_logs, "db", finto)
    monkeypatch.setattr(basic_logs, "ensure_module_enabled", AsyncMock(return_value=False))
    cog = basic_logs.BasicLogsCog(bot=None)
    ix = fake_interaction(guild=fake_guild(guild_id=77, owner_id=2))
    await cog.logs_setup.callback(cog, ix, fake_text_channel(channel_id=900), "sanzioni")
    assert finto.scritti == {}

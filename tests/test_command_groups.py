"""
tests/test_command_groups.py
============================
I 16 gruppi di primo livello della mappa F7 (D24): nomi, descrizioni,
permessi predefiniti, livello di accesso, aggiunta di comandi.
Funzioni coperte: NF-05 (issue #76)
"""

from __future__ import annotations

import inspect
import re

import discord
import pytest
from discord import app_commands

from core import command_groups as cg
from core.command_access import Livello

ADMIN_ATTESI = [
    "admin-bot", "admin-musica", "admin-ai", "admin-automod", "admin-filtri", "admin-sicurezza", "admin-antinuke", "admin-antiraid",
    "admin-moduli", "admin-economia", "admin-livelli", "admin-ruoli", "admin-log", "admin-messaggi", "admin-giveaway", "admin-ticket",
    "admin-ticket-opzioni", "admin-backup", "admin-benvenuto", "admin-vocali",
]
MOD_ATTESI = ["mod-sanzioni", "mod-casi", "mod-canali", "mod-ban"]
ATTESI = [
    "owner", *ADMIN_ATTESI, *MOD_ATTESI, "founder",
    "ticket", "voice", "music", "level", "monete", "clan", "fun", "immagini", "giochi", "sondaggi", "assistente", "gif", "utility",
]
# Eccezioni al permesso `manage_guild` dei gruppi admin (D60): sicurezza e backup chiedono administrator, i ruoli manage_roles.
PERMESSI = {
    **{n: "manage_guild" for n in ADMIN_ATTESI},
    "admin-ruoli": "manage_roles", "admin-backup": "administrator", "admin-sicurezza": "administrator",
    "admin-antinuke": "administrator", "admin-antiraid": "administrator",
    "owner": "administrator", "founder": "administrator",
    "mod-sanzioni": "moderate_members", "mod-casi": "moderate_members", "mod-canali": "moderate_members", "mod-ban": "ban_members",
}
LIVELLI = {
    **{n: Livello.ADMIN for n in ADMIN_ATTESI},
    "admin-sicurezza": Livello.SECURITY, "admin-antinuke": Livello.SECURITY, "admin-antiraid": Livello.SECURITY, "admin-log": Livello.LOG,
    "owner": Livello.OWNER, "founder": Livello.FOUNDER,
    "mod-sanzioni": Livello.MOD, "mod-casi": Livello.MOD, "mod-canali": Livello.MOD, "mod-ban": Livello.MODBAN,
}

# Permesso predefinito di Discord per livello (D56: Discord lo applica solo al primo livello).
PERMESSO_PER_LIVELLO = {
    Livello.OWNER: "administrator", Livello.ADMIN: "manage_guild", Livello.SECURITY: "administrator",
    Livello.LOG: "manage_guild", Livello.MOD: "moderate_members", Livello.MODBAN: "ban_members", Livello.FOUNDER: "administrator",
}
# Eccezioni scritte (livello admin nel codice): i ruoli chiedono manage_roles, il backup administrator.
ECCEZIONI_PERMESSO = {"admin-ruoli": "manage_roles", "admin-backup": "administrator"}


@pytest.mark.parametrize("nome", ATTESI)
def test_ogni_gruppo_ha_livello_e_permesso_corrispondenti(nome):
    """D56: gruppo per tutti (nessun livello, nessun permesso) o per lo staff (livello e permesso coerenti)."""
    g = cg.ottieni_gruppo(nome)
    livello = getattr(g, "livello", None)
    if livello is None:
        assert g.default_permissions is None, f"'/{nome}' è per tutti: niente permesso predefinito"
        return
    atteso = ECCEZIONI_PERMESSO.get(nome, PERMESSO_PER_LIVELLO[livello])
    assert g.default_permissions == discord.Permissions(**{atteso: True})


def _comandi_con_livello(nodo):
    for figlio in nodo.commands:
        if isinstance(figlio, app_commands.Group):
            yield from _comandi_con_livello(figlio)
            continue
        for controllo in figlio.checks:
            livello = getattr(controllo, "livello", None)
            if livello is not None:
                yield figlio, livello
        # Anche il controllo scritto nel corpo del comando (`puo_usare(interaction, Livello.X)`).
        for nome in re.findall(r"puo_usare\(\s*interaction\s*,\s*Livello\.(\w+)", inspect.getsource(figlio.callback)):
            yield figlio, Livello[nome]


async def test_nessun_comando_con_livello_in_un_gruppo_per_tutti():
    """D56: un comando che chiede livello mod/admin/owner non sta in un gruppo senza livello."""
    from tests.support.full_tree import build_full_bot, close_full_bot, connect_db_if_needed

    creato = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti, falliti
        errori = []
        for nome, gruppo in cg.GRUPPI.items():
            if getattr(gruppo, "livello", None) is not None:
                continue
            for comando, livello in _comandi_con_livello(gruppo):
                errori.append(f"/{comando.qualified_name} chiede {livello.value}")
        assert not errori, "Comandi da staff in un gruppo per tutti: " + "; ".join(errori)
    finally:
        await close_full_bot(bot)
        if creato:
            from core.database import db

            await db.close()


def test_i_gruppi_in_ordine():
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
    cg.aggiungi_a_gruppo("admin-bot", cmd, sottogruppo=("config", "Configurazione del server"), gruppi=gruppi)
    cmd2 = app_commands.Command(name="y", description="Y", callback=cb)
    cg.aggiungi_a_gruppo("admin-bot", cmd2, sottogruppo=("config", "Configurazione del server"), gruppi=gruppi)
    sotto = [c for c in gruppi["admin-bot"].commands if c.name == "config"]
    assert len(sotto) == 1 and isinstance(sotto[0], app_commands.Group)
    assert sorted(c.name for c in sotto[0].commands) == ["x", "y"]
    assert sotto[0].parent is gruppi["admin-bot"]


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


# ---- D60: il ruolo e il prefisso del nome ----

_LIVELLO_PER_PREFISSO = {
    "admin-": {Livello.ADMIN, Livello.SECURITY, Livello.LOG},
    "mod-": {Livello.MOD, Livello.MODBAN},
}


def test_il_prefisso_del_nome_dice_il_ruolo_del_gruppo():
    """Un gruppo `admin-…` ha livello admin/sicurezza/log, uno `mod-…` mod/modban, `founder` solo FOUNDER."""
    errori = []
    for nome in cg.nomi_gruppi():
        livello = getattr(cg.ottieni_gruppo(nome), "livello", None)
        if nome == "founder":
            if livello is not Livello.FOUNDER:
                errori.append(f"/{nome}: livello {livello}")
        elif nome == "owner":
            if livello is not Livello.OWNER:
                errori.append(f"/{nome}: livello {livello}")
        elif nome.startswith(tuple(_LIVELLO_PER_PREFISSO)):
            prefisso = next(p for p in _LIVELLO_PER_PREFISSO if nome.startswith(p))
            if livello not in _LIVELLO_PER_PREFISSO[prefisso]:
                errori.append(f"/{nome}: livello {livello} non adatto al prefisso {prefisso}")
        elif livello is not None:
            errori.append(f"/{nome}: ha il livello {livello} ma il nome non dice il ruolo (admin-, mod-, founder)")
    assert not errori, "; ".join(errori)


def test_nessun_gruppo_per_tutti_inizia_con_admin_mod_o_founder():
    """D60: scrivendo `/admin`, `/mod` o `/founder` compaiono solo i gruppi dello staff."""
    per_tutti = [n for n in cg.nomi_gruppi() if getattr(cg.ottieni_gruppo(n), "livello", None) is None]
    assert per_tutti
    sbagliati = [n for n in per_tutti if n.startswith(("admin", "mod", "founder"))]
    assert not sbagliati, f"Gruppi per tutti con il nome di un ruolo: {sbagliati} (cambia nome)"


def test_i_gruppi_staff_sono_venticinque_e_i_vecchi_non_ci_sono_piu():
    staff = [n for n in cg.nomi_gruppi() if n.startswith(("admin-", "mod-")) or n == "founder"]
    assert len(staff) == 25
    vecchi = {"admin", "backup", "gestione", "economia", "moduli", "ruoli", "messaggi", "giveaway", "ticket-gestione", "ticket-pannelli",
              "filtri", "security", "antinuke", "ai", "antiraid", "automod", "mod", "modban", "log"}
    assert not vecchi & set(cg.nomi_gruppi())


def test_founder_e_riservato_al_proprietario_del_server():
    g = cg.ottieni_gruppo("founder")
    assert g.livello is Livello.FOUNDER
    assert g.default_permissions == discord.Permissions(administrator=True)
    assert "proprietario" in g.description and len(g.description) <= 100

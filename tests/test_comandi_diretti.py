"""
tests/test_comandi_diretti.py
=============================
I 10 comandi diretti (D137): `/play`, `/skip`, `/stop`, `/pause`, `/resume`, `/queue`, `/ban`, `/kick`, `/mute`,
`/shadowban` sono comandi di primo livello che chiamano la stessa funzione del comando lungo, con gli stessi permessi,
lo stesso livello, la politica dei comandi spenti e le statistiche legate al PERCORSO VERO.
Funzioni coperte: D137
"""

from __future__ import annotations

from unittest.mock import MagicMock

import discord
import pytest
from discord import app_commands

from core import command_policy as pol
from core.command_groups import GRUPPI
from core.comandi_diretti import DIRETTI, ComandoDiretto, percorso_vero
from tests.support.full_tree import build_full_bot, close_full_bot, connect_db_if_needed


@pytest.fixture
async def albero():
    creato = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    assert not falliti, falliti
    yield bot
    await close_full_bot(bot)
    if creato:
        from core.database import db

        await db.close()


def _lungo(percorso: str) -> app_commands.Command:
    nodo = GRUPPI[percorso.split()[0]]
    for parola in percorso.split()[1:]:
        nodo = nodo.get_command(parola)
    return nodo


def test_la_tabella_ha_dieci_comandi_con_nomi_semplici():
    assert len(DIRETTI) == 10
    assert set(DIRETTI) == {"play", "skip", "stop", "pause", "resume", "queue", "ban", "kick", "mute", "shadowban"}
    assert len(set(DIRETTI.values())) == 10


async def test_ogni_diretto_esiste_ed_e_il_comando_lungo_con_un_altro_nome(albero):
    for nome, percorso in DIRETTI.items():
        diretto = albero.tree.get_command(nome)
        lungo = _lungo(percorso)
        assert isinstance(diretto, ComandoDiretto), nome
        assert diretto.callback is lungo.callback, f"/{nome}: non è la stessa funzione di /{percorso}"
        assert diretto.binding is lungo.binding
        assert diretto.description == lungo.description
        assert [(p.name, p.type, p.required) for p in diretto.parameters] == [(p.name, p.type, p.required) for p in lungo.parameters]
        assert diretto.percorso_vero == percorso == percorso_vero(diretto)


async def test_i_diretti_hanno_i_permessi_e_il_livello_del_gruppo(albero):
    for nome, percorso in DIRETTI.items():
        diretto = albero.tree.get_command(nome)
        radice = GRUPPI[percorso.split()[0]]
        assert diretto.default_permissions == radice.default_permissions, nome
        assert diretto.guild_only is radice.guild_only is True, nome
        livello = getattr(radice, "livello", None)
        livelli = [getattr(c, "livello", None) for c in diretto.checks]
        assert (livello in livelli) if livello is not None else not any(livelli), nome


async def test_i_comandi_di_moderazione_nascosti_a_chi_non_ha_il_permesso(albero):
    assert albero.tree.get_command("ban").default_permissions == discord.Permissions(ban_members=True)
    assert albero.tree.get_command("kick").default_permissions == discord.Permissions(ban_members=True)
    assert albero.tree.get_command("mute").default_permissions == discord.Permissions(moderate_members=True)
    assert albero.tree.get_command("shadowban").default_permissions == discord.Permissions(moderate_members=True)
    assert albero.tree.get_command("play").default_permissions is None


async def test_i_diretti_non_entrano_nell_elenco_dei_percorsi_della_politica(albero):
    percorsi = pol.percorsi_dei_comandi(albero.tree.get_commands())
    assert not set(DIRETTI) & set(percorsi)
    assert set(DIRETTI.values()) <= set(percorsi)
    assert len(percorsi) == len(set(percorsi))


async def test_il_nome_non_si_traduce_e_la_descrizione_e_quella_del_comando_lungo(albero):
    from core import command_translator as tr

    L = app_commands.TranslationContextLocation
    diretto = albero.tree.get_command("play")
    assert tr.tradotto_per(app_commands.TranslationContext(location=L.command_name, data=diretto), "en") is None
    en = tr.tradotto_per(app_commands.TranslationContext(location=L.command_description, data=diretto), "en")
    assert en and en == tr.descrizione_inglese("music play")


async def test_un_comando_spento_nella_politica_spegne_anche_il_diretto(albero, monkeypatch):
    visti = []

    async def finta(interaction, percorso):
        visti.append(percorso)
        return "pol_comando_spento"

    monkeypatch.setattr(pol, "valuta_percorso", finta)
    for nome, percorso in DIRETTI.items():
        interaction = MagicMock()
        interaction.type = discord.InteractionType.application_command
        interaction.is_guild_integration.return_value = True
        interaction.command = albero.tree.get_command(nome)
        assert await pol.valuta_interazione(interaction) == "pol_comando_spento"
        assert visti[-1] == percorso


async def test_le_statistiche_contano_il_percorso_vero(albero, monkeypatch):
    from cogs.utility.command_search import CommandSearchCog

    registrati = []
    cog = CommandSearchCog.__new__(CommandSearchCog)
    cog.repo = MagicMock()

    async def registra(guild_id, user_id, percorso):
        registrati.append(percorso)

    cog.repo.registra = registra
    interaction = MagicMock(guild_id=1, user=MagicMock(id=2))
    interaction.is_guild_integration.return_value = True
    await CommandSearchCog.on_app_command_completion(cog, interaction, albero.tree.get_command("play"))
    assert registrati == ["music play"]


async def test_help_e_un_solo_comando_al_posto_di_chiedi_e_cerca_comando(albero):
    assert albero.tree.get_command("help") is not None
    assert albero.tree.get_command("chiedi") is None and albero.tree.get_command("cerca-comando") is None


async def test_togliere_il_cog_toglie_i_diretti(albero):
    assert albero.tree.get_command("play") is not None
    await albero.remove_cog("MusicCog")
    assert albero.tree.get_command("play") is None
    assert albero.tree.get_command("queue") is None


def test_il_controllo_di_livello_non_finisce_sul_comando_lungo():
    """La lista dei controlli della funzione è condivisa: il diretto deve averne una sua."""
    from discord import app_commands

    from core.command_access import GruppoYokai, Livello
    from core.comandi_diretti import crea_comando_diretto

    async def cb(interaction):  # pragma: no cover
        pass

    cb.__discord_app_commands_checks__ = []
    radice = GruppoYokai(name="mod-ban", description="d", livello=Livello.MODBAN)
    lungo = app_commands.Command(name="ban", description="d", callback=cb)
    radice.add_command(lungo)
    for _ in range(2):  # due ricariche del cog
        diretto = crea_comando_diretto("ban", lungo, cb, radice)
    assert lungo.checks == [] and cb.__discord_app_commands_checks__ == []
    assert len(diretto.checks) == 1

"""
tests/test_user_app.py
======================
NF-36 (#107): iYokai App installabile dall'utente (albero separato) e i
comandi del principale installabili dall'utente (-cerca-comando, -chiedi).
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

import cogs.user_app.personal as personale
from core.user_app_bot import UserAppBot
from core import user_app_logic as logica
from core.user_app_logic import pulisci_link
from tests.support.discord_fakes import fake_interaction



# ---------------------------------------------------------------- logica
def test_pulisci_link_toglie_solo_il_tracciamento():
    assert pulisci_link("https://x.it/a?utm_source=tw&id=3&fbclid=zz") == "https://x.it/a?id=3"
    assert pulisci_link("https://youtu.be/abc?si=XYZ&t=10") == "https://youtu.be/abc?t=10"
    assert pulisci_link("https://x.it/a") == "https://x.it/a"


def test_testo_pulito():
    testo = "**Ciao** _a_ ~~tutti~~ ||segreto|| `x`\n> citazione\n# Titolo\nhttps://x.it/p?utm_medium=a&q=1_2"
    assert logica.testo_pulito(testo) == "Ciao a tutti segreto x\ncitazione\nTitolo\nhttps://x.it/p?q=1_2"
    assert len(logica.testo_pulito("a" * 5000)) == 2000
    assert logica.testo_pulito("") == ""


# ---------------------------------------------------------------- albero
async def _app():
    bot = UserAppBot()
    await bot.carica_cog()
    return bot


async def test_albero_dell_app_solo_installazione_utente_e_ovunque():
    bot = await _app()
    try:
        tutti = bot.tree.get_commands()
        slash = {c.name for c in bot.tree.get_commands(type=discord.AppCommandType.chat_input)}
        assert slash == {"promemoria", "profilo"}
        menu = {c.name for c in tutti if isinstance(c, app_commands.ContextMenu)}
        assert menu == {"Profilo", "Testo pulito"}
        for c in tutti:
            assert c.allowed_installs is not None and c.allowed_installs.user and not c.allowed_installs.guild, c.name
            contesti = c.allowed_contexts
            assert contesti.guild and contesti.dm_channel and contesti.private_channel, c.name
        assert personale.AZIONE_PROMEMORIA in personale.scheduler._handlers
    finally:
        await bot.close()


async def test_il_bot_principale_non_riceve_i_comandi_dell_app():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await personale.setup(bot)
    assert bot.tree.get_commands() == [] and bot.cogs == {}
    await bot.close()


# ---------------------------------------------------------------- promemoria
@pytest.fixture
def pianificatore(monkeypatch):
    finto = SimpleNamespace(
        schedule=AsyncMock(return_value=7),
        list_pending_for_user=AsyncMock(return_value=[]),
        get_pending_action=AsyncMock(return_value=None),
        cancel=AsyncMock(),
    )
    monkeypatch.setattr(personale, "scheduler", finto)
    return finto


def _cog():
    return personale.PersonaleCog.__new__(personale.PersonaleCog)


async def test_crea_promemoria_senza_server(pianificatore):
    cog = _cog()
    interazione = fake_interaction()
    interazione.user.id = 42
    await cog.crea.callback(cog, interazione, "2h", "acqua")
    args = pianificatore.schedule.await_args.args
    assert (args[0], args[1], args[2], args[4]) == (0, 42, personale.AZIONE_PROMEMORIA, {"message": "acqua"})
    assert "`7`" in interazione.response.send_message.await_args.args[0]


async def test_crea_rifiuta_durate_fuori_limite_e_troppi(pianificatore):
    cog = _cog()
    for durata in ("10s", "400d", "boh"):
        interazione = fake_interaction()
        await cog.crea.callback(cog, interazione, durata, "x")
        interazione.response.send_message.assert_awaited_once()
    pianificatore.list_pending_for_user.return_value = [{}] * 25
    interazione = fake_interaction()
    await cog.crea.callback(cog, interazione, "1h", "x")
    assert "25" in interazione.response.send_message.await_args.args[0]
    pianificatore.schedule.assert_not_awaited()


async def test_annulla_solo_i_propri(pianificatore):
    cog = _cog()
    interazione = fake_interaction()
    interazione.user.id = 42
    pianificatore.get_pending_action.return_value = {
        "user_id": 99, "action_type": personale.AZIONE_PROMEMORIA, "executed": False
    }
    await cog.annulla.callback(cog, interazione, 7)
    pianificatore.cancel.assert_not_awaited()
    pianificatore.get_pending_action.return_value = {
        "user_id": 42, "action_type": "reminder_fire", "executed": False
    }
    await cog.annulla.callback(cog, interazione, 7)
    pianificatore.cancel.assert_not_awaited()
    pianificatore.get_pending_action.return_value = {
        "user_id": 42, "action_type": personale.AZIONE_PROMEMORIA, "executed": False
    }
    await cog.annulla.callback(cog, interazione, 7)
    pianificatore.cancel.assert_awaited_once_with(7)


async def test_elenco(pianificatore):
    cog = _cog()
    pianificatore.list_pending_for_user.return_value = [
        {"id": 3, "execute_at": datetime.now(timezone.utc), "payload": {"message": "acqua"}}
    ]
    interazione = fake_interaction()
    await cog.elenco.callback(cog, interazione)
    assert "acqua" in interazione.response.send_message.await_args.kwargs["embed"].description


def _client(errore: bool):
    utente = MagicMock()
    utente.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "chiusi") if errore else None)
    client = MagicMock()
    client.fetch_user = AsyncMock(return_value=utente)
    return client, utente


async def test_consegna_in_dm_e_ripiego_sul_principale():
    cog = _cog()
    app, utente_app = _client(errore=True)
    principale, utente_principale = _client(errore=False)
    app.bot_principale = principale
    cog.bot = app
    await cog.consegna(0, 42, {"message": "acqua"})
    utente_app.send.assert_awaited_once()
    utente_principale.send.assert_awaited_once()
    assert "acqua" in utente_principale.send.await_args.args[0]


# ---------------------------------------------------------------- menu
async def test_menu_testo_pulito_risponde_in_privato():
    cog = _cog()
    interazione = fake_interaction()
    messaggio = MagicMock(spec=discord.Message)
    messaggio.content = "**ciao** @everyone"
    await cog.menu_testo_pulito(interazione, messaggio)
    chiamata = interazione.response.send_message.await_args
    assert chiamata.args[0] == "ciao @everyone"
    assert chiamata.kwargs["ephemeral"] and chiamata.kwargs["allowed_mentions"].everyone is False


# ---------------------------------------------------------------- bot principale
async def test_cerca_comando_e_chiedi_installabili_dall_utente():
    import cogs.utility.command_search as ricerca

    for comando in (ricerca.CommandSearchCog.search, ricerca.CommandSearchCog.chiedi):
        assert comando.allowed_installs.user and comando.allowed_installs.guild
        assert comando.allowed_contexts.dm_channel and comando.allowed_contexts.private_channel


def test_server_senza_il_bot_vale_come_dm():
    from cogs.utility.command_search import _server_del_bot

    def _i(guild_id, installato):
        return SimpleNamespace(guild_id=guild_id, is_guild_integration=lambda: installato)

    assert _server_del_bot(_i(5, False)) is None  # app installata solo sull'utente
    assert _server_del_bot(_i(5, True)) == 5
    assert _server_del_bot(_i(None, False)) is None


# ---------------------------------------------------------------- rilievi del cacciatore-bug (r9nsfw)
def _in_server_senza_il_bot():
    from tests.support.discord_fakes import fake_interaction

    i = fake_interaction()
    i.guild_id = 5
    i.is_guild_integration = lambda: False
    return i


async def test_installata_dall_utente_non_mostra_i_comandi_dello_staff_di_un_altro_server(monkeypatch):
    """Admin in un server dove il bot non c'è: là i comandi dello staff non valgono, come in DM."""
    from cogs.utility import command_search as modulo
    from tests.test_command_search_bug147 import _albero_con_richiedi

    monkeypatch.setattr(modulo, "puo_usare", AsyncMock(return_value=True))
    cog = modulo.CommandSearchCog(_albero_con_richiedi())
    visibili = {c.percorso for c in await cog._comandi_accessibili(_in_server_senza_il_bot())}
    assert "solo-mod" not in visibili and "fun aperto" in visibili


async def test_chiedi_installata_dall_utente_non_legge_la_conoscenza_di_quel_server(monkeypatch):
    import cogs.ai.helpdesk as helpdesk
    import core.ai_servizio as ai_servizio
    from cogs.utility import command_search as modulo
    from tests.test_command_search_bug147 import _albero_con_richiedi

    monkeypatch.setattr(ai_servizio, "servizio_ai", lambda: SimpleNamespace(controlla_accesso=AsyncMock()))
    letti = []

    async def conoscenza(guild_id):
        letti.append(guild_id)
        return ""

    monkeypatch.setattr(helpdesk, "conoscenza_del_server", conoscenza)
    monkeypatch.setattr(helpdesk, "chiedi", AsyncMock(return_value=(None, "locale")))
    monkeypatch.setattr(modulo, "puo_usare", AsyncMock(return_value=False))
    cog = modulo.CommandSearchCog(_albero_con_richiedi())
    assert await cog._risposta_ai(_in_server_senza_il_bot(), "come faccio?") is False
    assert letti == [None]
    assert helpdesk.chiedi.call_args.args[0].guild_id is None

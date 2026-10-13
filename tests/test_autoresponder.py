"""
tests/test_autoresponder.py
===========================
NF-10 (#81): risposte automatiche con condizioni (canale, ruolo, esatta o
parziale), mai ai bot, pausa per canale, tetto per server, testo 2000.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.utility.autoresponder as modulo
from cogs.utility.autoresponder import AutoresponderCog
from core.autoresponder_logic import MAX_RISPOSTE, scegli_risposta, trigger_corrisponde
from core.repositories.autoresponder_repo import AutoresponderRepository
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_message,
    fake_role,
    fake_text_channel,
)
from tests.support.percorsi import comando_nel_gruppo


# ---------------------------------------------------------------- logica pura
@pytest.mark.parametrize(
    "trigger, modo, messaggio, atteso",
    [
        ("ciao", "parziale", "Ciao a tutti", True),
        ("ciao", "parziale", "ciaone", False),  # parola intera
        ("ciao", "parziale", "dico CIAO!", True),
        ("buon giorno", "parziale", "un buon   giorno a te", False),
        ("buon giorno", "parziale", "un buon giorno a te", True),
        ("ciao", "esatta", "Ciao", True),
        ("ciao", "esatta", "ciao a tutti", False),
        ("c++", "parziale", "uso c++ ogni giorno", True),
        (".*", "parziale", "abc", False),  # nessuna regex: il testo vale com'è
    ],
)
def test_trigger_corrisponde(trigger, modo, messaggio, atteso):
    assert trigger_corrisponde(trigger, modo, messaggio) is atteso


def _r(i, trigger, modo="parziale", canale=None, ruolo=None):
    return SimpleNamespace(id=i, trigger=trigger, match_mode=modo, channel_id=canale, role_id=ruolo,
                           response="r", ping_ruoli=False)


def test_scegli_risposta_rispetta_canale_e_ruolo():
    regole = [_r(1, "ciao", canale=5), _r(2, "ciao", ruolo=9), _r(3, "ciao")]
    assert scegli_risposta(regole, "ciao", canale_id=6, ruoli_autore={1}).id == 3
    assert scegli_risposta(regole, "ciao", canale_id=5, ruoli_autore={1}).id == 1
    assert scegli_risposta([regole[1]], "ciao", canale_id=6, ruoli_autore={9}).id == 2
    assert scegli_risposta([regole[1]], "ciao", canale_id=6, ruoli_autore={1}) is None


def test_scegli_risposta_prende_la_piu_specifica():
    regole = [_r(1, "ciao"), _r(2, "ciao a tutti")]
    assert scegli_risposta(regole, "ciao a tutti", canale_id=1, ruoli_autore=set()).id == 2


# --------------------------------------------------------------------- archivio
@pytest.fixture
def repo(clean_db):
    return AutoresponderRepository(pool_provider=lambda: clean_db)


async def _crea(repo, guild=1, trigger="ciao", **kw):
    campi = dict(match_mode="parziale", response="Ciao!", channel_id=None, role_id=None, ping_ruoli=False, created_by=7)
    campi.update(kw)
    return await repo.create(guild, trigger, **campi)


@pytest.mark.asyncio
async def test_crea_elenca_elimina(repo):
    esito, nuovo_id = await _crea(repo)
    assert esito == "ok" and nuovo_id > 0
    assert (await _crea(repo, trigger="CIAO"))[0] == "esiste"  # senza badare alle maiuscole
    assert [r.trigger for r in await repo.list(1)] == ["ciao"]
    assert await repo.delete(1, nuovo_id) is True
    assert await repo.delete(1, nuovo_id) is False
    assert await repo.list(1) == []


@pytest.mark.asyncio
async def test_non_si_elimina_la_risposta_di_un_altro_server(repo):
    _, rid = await _crea(repo, guild=1)
    assert await repo.delete(2, rid) is False
    assert len(await repo.list(1)) == 1


@pytest.mark.asyncio
async def test_tetto_per_server(repo):
    for i in range(MAX_RISPOSTE):
        assert (await _crea(repo, trigger=f"t{i}"))[0] == "ok"
    assert (await _crea(repo, trigger="troppo"))[0] == "pieno"
    assert (await _crea(repo, guild=2, trigger="troppo"))[0] == "ok"


# -------------------------------------------------------------------------- cog
@pytest.fixture
def scena(monkeypatch):
    cog = AutoresponderCog(MagicMock())
    repo = MagicMock()
    repo.list = AsyncMock(return_value=[_r(1, "ciao")])
    repo.create = AsyncMock(return_value=("ok", 3))
    repo.delete = AsyncMock(return_value=True)
    monkeypatch.setattr(modulo, "autoresponder_repo", repo)
    db_finto = MagicMock()
    db_finto.is_module_active_for_guild = AsyncMock(return_value=True)
    monkeypatch.setattr(modulo, "db", db_finto)
    modulo._ultima_risposta.__init__(100)
    modulo._cache_regole.__init__(100)
    cog.repo = repo
    return cog


def _messaggio(contenuto="ciao a tutti", bot=False, canale_id=111):
    server = fake_guild()
    canale = fake_text_channel(canale_id)
    canale.send = AsyncMock()
    autore = fake_member(5, bot=bot)
    autore.display_name = "Mario"
    autore.guild = server
    return fake_message(1, author=autore, channel=canale, guild=server, content=contenuto), canale


@pytest.mark.asyncio
async def test_risponde_una_volta_senza_ping(scena):
    msg, canale = _messaggio()
    await scena.on_message(msg)
    canale.send.assert_awaited_once()
    assert canale.send.await_args.kwargs["allowed_mentions"].everyone is False
    assert canale.send.await_args.kwargs["reference"] is msg


@pytest.mark.asyncio
async def test_mai_ai_bot(scena):
    msg, canale = _messaggio(bot=True)
    await scena.on_message(msg)
    canale.send.assert_not_awaited()
    scena.repo.list.assert_not_awaited()


@pytest.mark.asyncio
async def test_pausa_per_canale(scena):
    msg, canale = _messaggio()
    await scena.on_message(msg)
    await scena.on_message(msg)
    assert canale.send.await_count == 1
    altro, canale2 = _messaggio(canale_id=222)
    await scena.on_message(altro)
    assert canale2.send.await_count == 1


@pytest.mark.asyncio
async def test_nessuna_corrispondenza(scena):
    msg, canale = _messaggio("buongiorno")
    await scena.on_message(msg)
    canale.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_invio_fallito_non_alza_eccezioni(scena):
    msg, canale = _messaggio()
    canale.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "no"))
    await scena.on_message(msg)


@pytest.mark.asyncio
async def test_crea_dice_il_tetto_e_i_duplicati(scena):
    i = fake_interaction(user=fake_member(5))
    i.user.top_role = fake_role(800, "Admin", position=60)
    scena.repo.create.return_value = ("pieno", None)
    await scena.risposta_crea.callback(scena, i, "ciao", "Ciao!", "parziale", None, None)
    assert str(MAX_RISPOSTE) in i.response.send_message.await_args.args[0]
    scena.repo.create.return_value = ("esiste", None)
    i2 = fake_interaction(user=i.user)
    await scena.risposta_crea.callback(scena, i2, "ciao", "Ciao!", "parziale", None, None)
    assert "già" in i2.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_albero_dei_comandi():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    for nome in ("risposta-crea", "risposta-elimina", "risposte"):
        assert comando_nel_gruppo("moduli", f"comandi {nome}") is not None
    crea = {o["name"]: o for o in comando_nel_gruppo("moduli", "comandi risposta-crea").to_dict(bot.tree)["options"]}
    assert crea["risposta"]["max_length"] == 2000 and crea["parola"]["max_length"] == 100

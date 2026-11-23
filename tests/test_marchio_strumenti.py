"""
tests/test_marchio_strumenti.py
===============================
CFG-032 (#128, D111) # CFG-032: strumenti del bot con marchio proprio: risincronizza i comandi, registro degli
ultimi errori (senza token né dati privati) e permessi di chi li usa.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

import core.whitelabel_bot as wl
from cogs.utility import marchio as modulo
from core import marchio_errori as errori
from core.command_sync import SALTATA, SINCRONIZZATA
from core.repositories.whitelabel_repo import Marchio
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

pytestmark = pytest.mark.asyncio

TOKEN = ".".join(["MTIzNDU2Nzg5MDEyMzQ1Njc4", "abcdef", "ghijklmnopqrstuvwxyz0123456"])


@pytest.fixture(autouse=True)
def _registro_pulito():
    errori._registro.clear()
    yield
    errori._registro.clear()


def _marchio(creato_da=77):
    return Marchio(500, 4242, 777, "Mio Bot", None, True, "attivo", None, creato_da)


class _Stato:
    def __init__(self):
        self.valori = {}

    async def leggi(self, scope):
        return self.valori.get(scope)

    async def salva(self, scope, impronta):
        self.valori[scope] = impronta


def _bot_con_comando():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())

    @bot.tree.command(name="prova", description="Un comando di prova")
    async def prova(interaction: discord.Interaction):
        pass

    return bot


async def test_il_registro_non_conserva_testi_ne_token():
    risposta = MagicMock(status=403, reason="Forbidden")
    errori.registra(500, "comandi", discord.HTTPException(risposta, {"code": 50001, "message": f"token {TOKEN} utente 123456789012345678"}))
    errori.registra(500, "login", discord.LoginFailure(f"Improper token {TOKEN}"))
    righe = errori.elenco(500)
    assert [r.tipo for r in righe] == ["LoginFailure", "HTTPException"]  # il più recente per primo
    visto = " ".join(f"{r.origine} {r.tipo} {r.dettaglio}" for r in righe)
    assert TOKEN not in visto and "123456789012345678" not in visto and "MTIz" not in visto
    assert righe[1].dettaglio == "HTTP 403, codice 50001"
    assert "123456789012345678" not in modulo.riga_errore(righe[1])


async def test_il_registro_tiene_gli_ultimi_20_per_server():
    for _ in range(25):
        errori.registra(500, "client", RuntimeError("x"))
    errori.registra(501, "client", ValueError("y"))
    assert len(errori.elenco(500)) == errori.MAX_ERRORI and len(errori.elenco(501)) == 1
    errori.registra(500, "origine inventata", RuntimeError("x"))
    assert errori.elenco(500)[0].origine == "client"


async def test_la_sincronizzazione_forzata_riscrive_anche_se_l_albero_e_uguale():
    bot = _bot_con_comando()
    client = MagicMock()
    client.http.bulk_upsert_guild_commands = AsyncMock()
    stato = _Stato()
    assert await wl.sincronizza_comandi_marchio(client, bot, 500, 777, stato) == SINCRONIZZATA
    assert await wl.sincronizza_comandi_marchio(client, bot, 500, 777, stato) == SALTATA
    assert await wl.sincronizza_comandi_marchio(client, bot, 500, 777, stato, forza=True) == SINCRONIZZATA
    assert client.http.bulk_upsert_guild_commands.await_count == 2


async def test_una_sincronizzazione_fallita_finisce_nel_registro():
    bot = _bot_con_comando()
    client = MagicMock()
    client.http.bulk_upsert_guild_commands = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403, reason="x"), "Missing Access"))
    assert await wl.sincronizza_comandi_marchio(client, bot, 500, 777, _Stato(), forza=True) == "errore"
    assert errori.elenco(500)[0].origine == "comandi" and errori.elenco(500)[0].dettaglio == "HTTP 403"


def _gestore_acceso(monkeypatch, esito=SINCRONIZZATA):
    gestore = wl.GestoreMarchio(_bot_con_comando())
    client = MagicMock()
    client.is_ready.return_value = True
    client.application_id_marchio = 777
    gestore._client[500] = client
    gestore._task[500] = asyncio.get_event_loop().create_future()  # task «in esecuzione»
    chiamate = AsyncMock(return_value=esito)
    monkeypatch.setattr(wl, "sincronizza_comandi_marchio", chiamate)
    monkeypatch.setattr("core.database.db._pool", MagicMock(), raising=False)
    return gestore, chiamate


async def test_risincronizza_ha_attesa_e_non_parte_a_bot_spento(monkeypatch):
    gestore, chiamate = _gestore_acceso(monkeypatch)
    assert (await gestore.risincronizza(999))[0] == "mar_non_acceso"
    assert (await gestore.risincronizza(500))[0] == "mar_sync_ok"
    assert chiamate.await_args.kwargs["forza"] is True
    chiave, valori = await gestore.risincronizza(500)
    assert chiave == "mar_sync_attesa" and valori["secondi"] > 0 and chiamate.await_count == 1


async def test_risincronizza_fallita_non_fa_scattare_l_attesa(monkeypatch):
    gestore, chiamate = _gestore_acceso(monkeypatch, esito="errore")
    for _ in range(2):
        assert (await gestore.risincronizza(500))[0] == "mar_sync_errore"
    assert chiamate.await_count == 2


def test_permessi_solo_proprietario_del_server_o_chi_ha_collegato_il_bot():
    m = _marchio(creato_da=77)
    assert wl.puo_usare_strumenti(42, 42, m)  # proprietario del server
    assert wl.puo_usare_strumenti(77, 42, m)  # chi ha collegato il bot
    assert not wl.puo_usare_strumenti(7, 42, m)  # un admin qualunque
    assert not wl.puo_usare_strumenti(42, 42, None)  # nessun marchio


async def test_il_comando_rifiuta_chi_non_possiede_il_bot_con_marchio(monkeypatch):
    repo = SimpleNamespace(get=AsyncMock(return_value=_marchio()))
    monkeypatch.setattr(modulo, "whitelabel_repo", repo)
    cog = modulo.MarchioCog(commands.Bot(command_prefix="!", intents=discord.Intents.none()))
    cog.gestore.risincronizza = AsyncMock(return_value=("mar_sync_ok", {}))
    guild = fake_guild(500, owner_id=42)
    for azione in ("risincronizza", "errori"):
        i = fake_interaction(guild=guild, user=fake_member(user_id=7))
        await cog._strumenti(i, azione)
        assert "proprietario" in i.response.send_message.call_args.args[0]
    cog.gestore.risincronizza.assert_not_awaited()
    i = fake_interaction(guild=guild, user=fake_member(user_id=77))
    await cog._strumenti(i, "risincronizza")
    cog.gestore.risincronizza.assert_awaited_once_with(500)


async def test_il_comando_errori_mostra_il_registro_senza_dati_privati(monkeypatch):
    repo = SimpleNamespace(get=AsyncMock(return_value=_marchio()))
    monkeypatch.setattr(modulo, "whitelabel_repo", repo)
    cog = modulo.MarchioCog(commands.Bot(command_prefix="!", intents=discord.Intents.none()))
    i = fake_interaction(guild=fake_guild(500, owner_id=42), user=fake_member(user_id=42))
    await cog._strumenti(i, "errori")
    assert "Nessun errore" in i.response.send_message.call_args.args[0]
    errori.registra(500, "login", discord.LoginFailure(f"Improper token {TOKEN}"))
    i = fake_interaction(guild=fake_guild(500, owner_id=42), user=fake_member(user_id=42))
    await cog._strumenti(i, "errori")
    testo = i.response.send_message.call_args.args[0]
    assert "LoginFailure" in testo and TOKEN not in testo

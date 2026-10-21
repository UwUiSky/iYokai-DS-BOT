"""
tests/test_whitelabel_bot.py
============================
NF-38 (#109): bot con marchio proprio (token cifrato, verifica, ciclo di vita del client, comando).
"""

import dataclasses
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

import core.premium as premium_module
from core import whitelabel_bot as wl
from core.oauth_crypto import generate_key
from core.repositories.whitelabel_repo import WhitelabelRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

pytestmark = pytest.mark.asyncio

CHIAVE = generate_key()
TOKEN = ".".join(["MTIzNDU2Nzg5MDEyMzQ1Njc4", "abcdef", "ghijklmnopqrstuvwxyz0123456"])


@pytest.fixture
async def repo(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    r = WhitelabelRepository(pool_provider=lambda: clean_db, chiave_provider=lambda: CHIAVE)
    monkeypatch.setattr(wl, "whitelabel_repo", r)
    monkeypatch.setattr("cogs.utility.marchio.whitelabel_repo", r)

    class _Config:
        PREMIUM_ALPHA_UNLOCK_ALL = True
        MAIN_GUILD_ID = 999

    monkeypatch.setattr(premium_module, "config", _Config())
    return r


def _config(**kw):
    base = dict(
        YOKAI_BOT_TOKEN="principale", YOKAI_CREATOR_TOKEN="creatore", YOKAI_MOD_TOKEN="mod", NSFW_TOKEN="",
        MUSIC_TOKENS=["m1", "m2"],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _guild(guild_id=500, me_id=1):
    g = fake_guild(guild_id)
    g.me = SimpleNamespace(id=me_id)
    return g


async def _finto_verifica(monkeypatch, bot_user_id=4242, nome="Mio Bot"):
    monkeypatch.setattr(wl, "verifica_token", AsyncMock(return_value=wl.InfoApplicazione(bot_user_id, 9000, nome)))


def test_token_di_sistema_non_si_collegano():
    assert wl.token_di_sistema(_config()) == {"principale", "creatore", "mod", "m1", "m2"}


async def test_il_token_si_salva_cifrato_e_si_rilegge(repo, monkeypatch, clean_db):
    await _finto_verifica(monkeypatch)
    marchio = await wl.collega_marchio(_guild(), TOKEN, 77, config=_config())
    assert marchio.bot_name == "Mio Bot" and marchio.application_id == 9000 and marchio.last_state == "fermo"
    grezzo = await clean_db.fetchrow("SELECT * FROM whitelabel_bots")
    assert TOKEN not in str(dict(grezzo)) and grezzo["encrypted_token"] != TOKEN
    letto, token = await repo.get_con_token(500)
    assert token == TOKEN and letto.created_by == 77
    assert "client_id=9000" in wl.link_invito(letto) and "guild_id=500" in wl.link_invito(letto)


async def test_token_rifiutati(repo, monkeypatch):
    await _finto_verifica(monkeypatch)
    for cattivo in ("principale", "m2", "   "):
        with pytest.raises(wl.TokenRifiutato) as e:
            await wl.collega_marchio(_guild(), cattivo, 77, config=_config())
        assert e.value.motivo == "mar_token_non_valido"
    # è il bot principale stesso (stesso utente)
    with pytest.raises(wl.TokenRifiutato) as e:
        await wl.collega_marchio(_guild(me_id=4242), TOKEN, 77, config=_config())
    assert e.value.motivo == "mar_token_non_valido"
    # già usato da un altro server
    await wl.collega_marchio(_guild(500), TOKEN, 77, config=_config())
    with pytest.raises(wl.TokenRifiutato) as e:
        await wl.collega_marchio(_guild(501), TOKEN + "x", 78, config=_config())
    assert e.value.motivo == "mar_gia_usato"


async def test_senza_chiave_di_cifratura_il_token_non_si_salva(repo, monkeypatch, clean_db):
    await _finto_verifica(monkeypatch)
    senza = WhitelabelRepository(pool_provider=lambda: clean_db, chiave_provider=lambda: "")
    monkeypatch.setattr(wl, "whitelabel_repo", senza)
    with pytest.raises(wl.TokenRifiutato) as e:
        await wl.collega_marchio(_guild(), TOKEN, 77, config=_config())
    assert e.value.motivo == "mar_chiave_mancante"
    assert await clean_db.fetchval("SELECT count(*) FROM whitelabel_bots") == 0


async def test_verifica_token_traduce_gli_errori_di_discord(monkeypatch):
    class _Client:
        def __init__(self, *a, **k):
            self.user = None

        async def login(self, token):
            raise discord.LoginFailure("Improper token")

        async def close(self):
            self.chiuso = True

    monkeypatch.setattr(wl.discord, "Client", _Client)
    with pytest.raises(wl.TokenRifiutato) as e:
        await wl.verifica_token("x" * 30)
    assert e.value.motivo == "mar_token_non_valido" and "x" * 30 not in str(e.value)


async def test_stati_testo_e_scollegamento(repo, monkeypatch):
    await _finto_verifica(monkeypatch)
    await wl.collega_marchio(_guild(), TOKEN, 77, config=_config())
    assert await repo.imposta_testo_stato(500, "Server di prova")
    await repo.imposta_stato(500, wl.STATO_ATTIVO)
    assert (await repo.get(500)).last_state == "attivo" and (await repo.get(500)).status_text == "Server di prova"
    assert [m.guild_id for m in await repo.elenco_abilitati()] == [500]
    assert await repo.imposta_abilitato(500, False)
    assert await repo.elenco_abilitati() == []
    assert await repo.elimina(500) and await repo.get(500) is None


class _BotFinto:
    def __init__(self, guild_ids):
        self._guild_ids = set(guild_ids)

    def get_guild(self, gid):
        return SimpleNamespace(id=gid, owner_id=None, get_member=lambda _i: None) if gid in self._guild_ids else None


async def test_il_gestore_non_avvia_senza_premium_ne_senza_marchio(repo, monkeypatch):
    class _Config:
        PREMIUM_ALPHA_UNLOCK_ALL = False
        MAIN_GUILD_ID = 999

    monkeypatch.setattr(premium_module, "config", _Config())
    gestore = wl.GestoreMarchio(_BotFinto([500]))
    assert await gestore.avvia(500) is False  # nessun marchio
    await _finto_verifica(monkeypatch)
    await wl.collega_marchio(_guild(), TOKEN, 77, config=_config())
    assert await gestore.avvia(500) is False  # nessun premium
    assert (await repo.get(500)).last_state == wl.STATO_SENZA_PREMIUM
    assert not gestore.in_esecuzione(500)


async def test_il_gestore_avvia_e_ferma_il_client(repo, monkeypatch):
    avviati = []

    class _ClientFinto:
        def __init__(self, guild_id, testo):
            self.guild_id, self.testo_stato, self.chiuso = guild_id, testo, False

        async def start(self, token):
            avviati.append(token)
            import asyncio

            await asyncio.sleep(3600)

        async def close(self):
            self.chiuso = True

        def is_ready(self):
            return False

    monkeypatch.setattr(wl, "_ClientMarchio", _ClientFinto)
    await _finto_verifica(monkeypatch)
    await wl.collega_marchio(_guild(), TOKEN, 77, config=_config())
    gestore = wl.GestoreMarchio(_BotFinto([500]))
    assert await gestore.avvia(500) is True
    import asyncio

    await asyncio.sleep(0)
    assert avviati == [TOKEN] and gestore.in_esecuzione(500)
    assert await gestore.avvia(500) is True and avviati == [TOKEN]  # non parte due volte
    await gestore.ferma(500)
    assert not gestore.in_esecuzione(500) and (await repo.get(500)).last_state == "fermo"


async def test_riconcilia_ferma_chi_non_ha_piu_il_server_o_il_marchio(repo, monkeypatch):
    class _ClientFinto:
        def __init__(self, guild_id, testo):
            self.guild_id = guild_id

        async def start(self, token):
            import asyncio

            await asyncio.sleep(3600)

        async def close(self):
            pass

    monkeypatch.setattr(wl, "_ClientMarchio", _ClientFinto)
    await _finto_verifica(monkeypatch)
    await wl.collega_marchio(_guild(), TOKEN, 77, config=_config())
    bot = _BotFinto([500])
    gestore = wl.GestoreMarchio(bot)
    await gestore.riconcilia()
    assert gestore.in_esecuzione(500)
    bot._guild_ids.clear()  # il bot principale è stato cacciato dal server
    await gestore.riconcilia()
    assert not gestore.in_esecuzione(500)
    await repo.elimina(500)
    await gestore.riconcilia()


async def test_il_client_lascia_i_server_che_non_sono_suoi(repo, monkeypatch):
    client = wl._ClientMarchio(500, "ciao")
    sua, altra = MagicMock(), MagicMock()
    sua.id, altra.id = 500, 600
    altra.leave = AsyncMock()
    sua.leave = AsyncMock()
    await client.on_guild_join(altra)
    altra.leave.assert_awaited_once()
    await client.on_guild_join(sua)
    sua.leave.assert_not_awaited()
    await client.close()


async def test_comando_marchio(repo, monkeypatch):
    from cogs.utility.marchio import MarchioCog

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = MarchioCog(bot)
    cog.gestore = SimpleNamespace(
        avvia=AsyncMock(return_value=True), ferma=AsyncMock(), aggiorna_testo=AsyncMock(), ferma_tutti=AsyncMock()
    )
    scelta = lambda v: app_commands.Choice(name=v, value=v)  # noqa: E731

    def nuova():
        i = fake_interaction(guild=_guild(), user=fake_member(77))
        i.locale = discord.Locale.italian
        return i

    i = nuova()
    await cog.marchio.callback(cog, i, scelta("stato"), None)
    assert "Nessun bot" in i.response.send_message.call_args.args[0]

    i = nuova()
    await cog.marchio.callback(cog, i, scelta("imposta"), None)
    modal = i.response.send_modal.call_args.args[0]
    assert modal.token.max_length == 120 and len(modal.title) <= 45

    await _finto_verifica(monkeypatch)
    monkeypatch.setattr("cogs.utility.marchio.config", _config())
    i = nuova()
    await cog.collega(i, TOKEN)
    assert "Mio Bot" in i.followup.send.call_args.args[0] and TOKEN not in i.followup.send.call_args.args[0]
    cog.gestore.avvia.assert_awaited_with(500)

    i = nuova()
    await cog.marchio.callback(cog, i, scelta("testo"), "Server di prova")
    assert (await repo.get(500)).status_text == "Server di prova"
    cog.gestore.aggiorna_testo.assert_awaited_with(500, "Server di prova")

    i = nuova()
    await cog.marchio.callback(cog, i, scelta("stato"), None)
    descrizione = i.response.send_message.call_args.kwargs["embed"].description
    assert "Mio Bot" in descrizione and "Server di prova" in descrizione

    i = nuova()
    await cog.marchio.callback(cog, i, scelta("ferma"), None)
    assert (await repo.get(500)).enabled is False
    i = nuova()
    await cog.marchio.callback(cog, i, scelta("rimuovi"), None)
    assert await repo.get(500) is None


async def test_senza_premium_il_comando_si_rifiuta(repo, monkeypatch):
    from cogs.utility.marchio import MarchioCog

    class _Config:
        PREMIUM_ALPHA_UNLOCK_ALL = False
        MAIN_GUILD_ID = 999

    monkeypatch.setattr(premium_module, "config", _Config())
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = MarchioCog(bot)
    i = fake_interaction(guild=_guild(), user=fake_member(77))
    i.locale = discord.Locale.italian
    await cog.marchio.callback(cog, i, app_commands.Choice(name="imposta", value="imposta"), None)
    assert "premium" in i.response.send_message.call_args.args[0]
    i.response.send_modal.assert_not_called()

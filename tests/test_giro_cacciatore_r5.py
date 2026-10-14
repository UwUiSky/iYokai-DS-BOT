"""
tests/test_giro_cacciatore_r5.py
================================
Difetti trovati dal giro del cacciatore di bug su feat/r5-cor (aggiornamento a caldo, marchio, abbonamenti Discord,
storico): ogni test fallisce senza la correzione.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core import hot_patch as hp
from core import premium_entitlement_service as servizio
from core import whitelabel_bot as wl
from core.repositories.entitlement_repo import entitlement_repo
from tests.test_hot_patch import _BotFinto as BotCaldo
from tests.test_hot_patch import _Registro
from tests.test_premium_entitlement import _diritto, db_pronto  # noqa: F401
from tests.test_whitelabel_bot import TOKEN, _BotFinto, _config, _finto_verifica, _guild, repo  # noqa: F401

pytestmark = pytest.mark.filterwarnings("ignore::pytest.PytestWarning")


# ---------------------------------------------------------------- aggiornamento a caldo
def test_un_a_capo_nel_nome_non_passa():
    for cattivo in ("cogs/utility/a\n.py", "cogs/uti\nlity/a.py", "cogs/utility/a.py\n.py"):
        with pytest.raises(hp.PatchRifiutata):
            hp.valida_percorso(cattivo)


@pytest.fixture
def radice(tmp_path):
    (tmp_path / "cogs" / "utility").mkdir(parents=True)
    (tmp_path / "core").mkdir()
    (tmp_path / "cogs" / "utility" / "a.py").write_text("async def setup(bot):\n    pass\n")
    (tmp_path / "cogs" / "utility" / "_viste.py").write_text("V = 1\n")
    return tmp_path


async def _applica(bot, pacchetto, radice):
    return await hp.applica_patch(
        bot, pacchetto, sorgente="github", applicato_da=1, radice=radice,
        cartella_copie=radice / "data" / "c", registro=_Registro(),
    )


async def test_un_file_di_appoggio_in_cogs_non_fa_fallire_l_aggiornamento(radice):
    (radice / "cogs" / "utility" / "a.py").write_text("from cogs.utility import _viste\nasync def setup(bot):\n    pass\n")
    bot = BotCaldo(caricati=["cogs.utility.a"])
    esito = await _applica(bot, {"cogs/utility/_viste.py": b"V = 2\n"}, radice)
    assert esito.esito == "ok"
    # l'appoggio non si carica come cog; chi lo usa si ricarica per prendere il codice nuovo
    assert ("load", "cogs.utility._viste") not in bot.chiamate
    assert ("reload", "cogs.utility.a") in bot.chiamate


async def test_due_aggiornamenti_insieme_vanno_uno_alla_volta(radice):
    attivi, massimo = 0, 0

    class _Lento(BotCaldo):
        async def reload_extension(self, m):
            nonlocal attivi, massimo
            attivi += 1
            massimo = max(massimo, attivi)
            await asyncio.sleep(0.02)
            attivi -= 1

    bot = _Lento(caricati=["cogs.utility.a"])
    nuovo = b"async def setup(bot):\n    pass\n"
    await asyncio.gather(*(_applica(bot, {"cogs/utility/a.py": nuovo}, radice) for _ in range(3)))
    assert massimo == 1


# ---------------------------------------------------------------- abbonamenti Discord
async def test_l_allineamento_legge_oltre_i_100_diritti(db_pronto):
    visti = {}

    class _Bot:
        def entitlements(self, **kw):
            visti.update(kw)

            async def genera():
                for i in range(1, 251 if kw.get("limit") is None else kw["limit"] + 1):
                    yield _diritto(ent_id=i, guild_id=1000 + i)

            return genera()

    assert await servizio.allinea_con_discord(_Bot()) == 250
    assert "limit" in visti and visti["limit"] is None  # il default di discord.py è 100


async def test_un_evento_arrivato_durante_la_lettura_non_si_chiude(db_pronto):
    class _Bot:
        def entitlements(self, **kw):
            async def genera():
                yield _diritto(ent_id=1, guild_id=500)
                # intanto Discord manda l'evento di un nuovo acquisto: la lettura non lo vedrà
                await servizio.registra_evento(_diritto(ent_id=2, guild_id=501))

            return genera()

    await servizio.allinea_con_discord(_Bot())
    assert await servizio.server_ha_abbonamento(501)


# ---------------------------------------------------------------- marchio
class _ClientFinto:
    aperti: list = []

    def __init__(self, guild_id, testo):
        self.guild_id, self.chiuso = guild_id, False
        _ClientFinto.aperti.append(self)

    async def start(self, token):
        self.token = token
        await asyncio.sleep(3600)

    async def close(self):
        self.chiuso = True


async def test_due_avvii_insieme_aprono_un_solo_client(repo, monkeypatch):
    _ClientFinto.aperti = []
    monkeypatch.setattr(wl, "_ClientMarchio", _ClientFinto)
    await _finto_verifica(monkeypatch)
    await wl.collega_marchio(_guild(), TOKEN, 77, config=_config())
    gestore = wl.GestoreMarchio(_BotFinto([500]))
    await asyncio.gather(gestore.avvia(500), gestore.avvia(500), gestore.avvia(500))
    assert len(_ClientFinto.aperti) == 1
    await gestore.ferma(500)


async def test_un_token_illeggibile_non_blocca_gli_altri_marchi(repo, monkeypatch, clean_db):
    _ClientFinto.aperti = []
    monkeypatch.setattr(wl, "_ClientMarchio", _ClientFinto)
    await _finto_verifica(monkeypatch)
    await wl.collega_marchio(_guild(500), TOKEN, 77, config=_config())
    await clean_db.execute("UPDATE whitelabel_bots SET encrypted_token = 'rovinato' WHERE guild_id = 500")
    # secondo server con un token valido (id bot diverso)
    await clean_db.execute(
        "INSERT INTO whitelabel_bots (guild_id, encrypted_token, bot_account_id, application_id, bot_name, created_by)"
        " VALUES (600, 'x', 8, 8, 'B', 1)"
    )
    from core.oauth_crypto import encrypt_token
    from tests.test_whitelabel_bot import CHIAVE

    await clean_db.execute("UPDATE whitelabel_bots SET encrypted_token = $1 WHERE guild_id = 600", encrypt_token(TOKEN + "2", CHIAVE))
    gestore = wl.GestoreMarchio(_BotFinto([500, 600]))
    await gestore.riconcilia()
    assert gestore.in_esecuzione(600) and not gestore.in_esecuzione(500)
    assert (await repo.get(500)).last_state == "errore"
    await gestore.ferma_tutti()


async def test_ricollegare_con_un_token_nuovo_riavvia_il_client(repo, monkeypatch):
    from cogs.utility.marchio import MarchioCog
    from tests.support.discord_fakes import fake_interaction, fake_member
    import discord
    from discord.ext import commands

    _ClientFinto.aperti = []
    monkeypatch.setattr(wl, "_ClientMarchio", _ClientFinto)
    await _finto_verifica(monkeypatch)
    monkeypatch.setattr("cogs.utility.marchio.config", _config())
    cog = MarchioCog(commands.Bot(command_prefix="!", intents=discord.Intents.default()))
    cog.gestore = wl.GestoreMarchio(_BotFinto([500]))
    for token in (TOKEN, TOKEN + "nuovo"):
        i = fake_interaction(guild=_guild(), user=fake_member(77))
        i.locale = discord.Locale.italian
        await cog.collega(i, token)
        await asyncio.sleep(0)
    vivi = [c for c in _ClientFinto.aperti if not c.chiuso]
    assert len(vivi) == 1 and vivi[0].token == TOKEN + "nuovo"
    await cog.gestore.ferma_tutti()


# ---------------------------------------------------------------- storico
def test_la_vista_prima_dopo_sta_in_2000_anche_con_chiave_lunga():
    from core.config_history_logic import dettaglio_prima_dopo

    voce = SimpleNamespace(
        id=1234567890, change_type="setting", key_name="k" * 100, changed_by=123456789012345678,
        created_at=datetime.now(timezone.utc), old_value="x" * 5000, new_value="y" * 5000,
    )
    assert len(dettaglio_prima_dopo(voce)) <= 2000

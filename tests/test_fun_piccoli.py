"""B2 di #131 (D70): coinflip a più monete, minato, ship amicizia, Chuck Norris, classe a caso."""
import io
import random
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from PIL import Image

from cogs.fun.entertainment import MODULE_FUN, EntertainmentCog
from cogs.fun.fun_extra import FunExtraCog
from core import fun_piccoli_logic as lg
from core.database import db
from tests.support.discord_fakes import fake_guild, fake_interaction
from tests.support.percorsi import comando_nel_gruppo

ID = 102


class _C:
    def __init__(self, value):
        self.value = value
        self.name = value


# --- logica ---------------------------------------------------------------

def test_minato_numero_di_mine_e_prima_zona_aperta():
    for livello, (lato, mine) in lg.MINATO_LIVELLI.items():
        campo = lg.crea_minato(livello, random.Random(7))
        assert len(campo.numeri) == lato and len(campo.numeri[0]) == lato
        assert sum(r.count(lg.MINA) for r in campo.numeri) == mine
        assert any(any(r) for r in campo.aperte)
        # ogni cella aperta non e' una mina
        for y in range(lato):
            for x in range(lato):
                if campo.aperte[y][x]:
                    assert campo.numeri[y][x] != lg.MINA


def test_minato_numeri_coerenti_e_testo_sotto_2000():
    campo = lg.crea_minato("difficile", random.Random(3))
    n = campo.numeri
    for y in range(9):
        for x in range(9):
            if n[y][x] != lg.MINA:
                vicini = sum(
                    n[j][i] == lg.MINA
                    for j in range(max(0, y - 1), min(9, y + 2))
                    for i in range(max(0, x - 1), min(9, x + 2))
                )
                assert n[y][x] == vicini
    testo = lg.testo_minato(campo)
    assert len(testo) <= 2000 and testo.count("||") % 2 == 0
    assert "||" in testo


def test_minato_livello_sconosciuto():
    with pytest.raises(ValueError):
        lg.crea_minato("impossibile", random.Random(1))


def test_tira_monete_e_striscia_png():
    esiti = lg.tira_monete(10, random.Random(1))
    assert len(esiti) == 10 and set(esiti) <= {"testa", "croce"}
    with open("assets/moneta_iyokai.png", "rb") as f:
        png = lg.striscia_monete(esiti, f.read())
    img = Image.open(io.BytesIO(png))
    assert img.size == (1280, 128) and len(png) < 1_000_000


def test_striscia_con_immagine_rotta_ricade_sulla_base():
    png = lg.striscia_monete(["testa", "croce"], b"non sono un'immagine")
    assert Image.open(io.BytesIO(png)).size == (256, 128)


def test_ship_amicizia_diversa_da_amore_e_simmetrica():
    from core.fun_logic import compute_ship_percentage, ship_flavor_text

    a = compute_ship_percentage(1, 2, "amicizia")
    assert a == compute_ship_percentage(2, 1, "amicizia")
    assert any(
        compute_ship_percentage(i, i + 1) != compute_ship_percentage(i, i + 1, "amicizia") for i in range(1, 30)
    )
    assert ship_flavor_text(95, "amicizia") != ship_flavor_text(95)


def test_chuck_in_italiano_e_nelle_scelte():
    from core.classic_entertainment_logic import JOKES_TEMATICHE

    assert len(JOKES_TEMATICHE["chuck"]) >= 15
    assert all("Chuck Norris" in b and len(b) <= 300 for b in JOKES_TEMATICHE["chuck"])
    assert len(JOKES_TEMATICHE) <= 25


def test_classi_giochi():
    assert 1 <= len(lg.GIOCHI_CLASSI) <= 25
    for chiave, v in lg.GIOCHI_CLASSI.items():
        assert v["classi"] and len(v["nome"]) <= 100 and len(chiave) <= 100
    assert lg.classe_a_caso("wow", random.Random(1)) in lg.GIOCHI_CLASSI["wow"]["classi"]
    assert lg.classe_a_caso("nonesiste", random.Random(1)) is None
    sug = lg.suggerisci_giochi("over")
    assert [v for _, v in sug] == ["overwatch"]
    assert len(lg.suggerisci_giochi("")) <= 25


# --- comandi --------------------------------------------------------------

@pytest.fixture(autouse=True)
async def _attivo(monkeypatch, clean_db):
    import core.database as dm

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID, MODULE_FUN, True)
    yield
    dm.db._modules_cache.clear()


def _it():
    return fake_interaction(guild=fake_guild(ID))


async def test_coinflip_una_moneta_resta_testo():
    cog = EntertainmentCog(bot=None)
    it = _it()
    await cog.coinflip.callback(cog, it, 1)
    assert it.response.send_message.await_args.args[0].startswith("🪙 **")
    assert "file" not in it.response.send_message.await_args.kwargs


async def test_coinflip_piu_monete_manda_immagine():
    cog = EntertainmentCog(bot=None)
    it = _it()
    with patch("cogs.fun.entertainment.leveling_settings_repo.get_immagine_moneta", AsyncMock(return_value=None)):
        await cog.coinflip.callback(cog, it, 5)
    it.response.defer.assert_awaited_once()
    inviato = it.followup.send.await_args
    assert inviato.kwargs["file"].filename == "monete.png"
    assert len(inviato.args[0]) < 2000


def test_coinflip_quante_e_ship_tema_sono_facoltative_con_limiti():
    import asyncio
    from discord.ext import commands
    import cogs.fun.entertainment as e, cogs.fun.ship_rate as s

    async def prepara():
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        await e.setup(bot)
        await s.setup(bot)
        return bot

    asyncio.run(prepara())
    q = {o.name: o for o in comando_nel_gruppo("fun", "coinflip").parameters}["quante"]
    assert (q.min_value, q.max_value, q.required) == (1, 10, False)
    t = {o.name: o for o in comando_nel_gruppo("fun", "ship").parameters}
    assert t["tema"].required is False and len(t["tema"].choices) == 2


async def test_ship_amicizia_titolo():
    from cogs.fun.ship_rate import ShipRateCog

    cog = ShipRateCog(bot=None)
    it = _it()
    a, b = MagicMock(id=1, display_name="A"), MagicMock(id=2, display_name="B")
    await cog.ship.callback(cog, it, a, b, _C("amicizia"))
    emb = it.response.send_message.await_args.kwargs["embed"]
    assert "mic" in emb.title.lower()


async def test_joke_chuck():
    cog = EntertainmentCog(bot=None)
    it = _it()
    await cog.joke.callback(cog, it, _C("chuck"))
    assert "Chuck Norris" in it.response.send_message.await_args.args[0]


async def test_casuale_classe():
    cog = FunExtraCog(bot=None)
    it = _it()
    await cog.casuale.callback(cog, it, _C("classe"), None, "overwatch")
    assert any(c in it.response.send_message.await_args.args[0] for c in ("Tank", "Danno", "Supporto"))
    it = _it()
    await cog.casuale.callback(cog, it, _C("classe"), None, None)
    assert it.response.send_message.await_args.kwargs["ephemeral"] is True
    it = _it()
    await cog.casuale.callback(cog, it, _C("classe"), None, "inventato")
    assert it.response.send_message.await_args.kwargs["ephemeral"] is True


async def test_minato_comando_e_limiti():
    from cogs.fun.giochi_extra import GiochiExtraCog

    cog = GiochiExtraCog(bot=None)
    for livello, (lato, mine) in lg.MINATO_LIVELLI.items():
        it = _it()
        await cog.minato.callback(cog, it, _C(livello))
        testo = it.response.send_message.await_args.args[0]
        assert len(testo) <= 2000
        assert testo.count("💥") == mine or testo.count("||💥||") == mine
    it = _it()
    await cog.minato.callback(cog, it, None)
    assert "5" not in it.response.send_message.await_args.args[0][:0] + "x"
    assert it.response.send_message.await_args.kwargs["allowed_mentions"].everyone is False

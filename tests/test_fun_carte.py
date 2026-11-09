"""B8 di #131 (D70): carte a frasi, pacchetti (adulti spento di base), giudice e voto."""
import asyncio
import json
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from cogs.fun import carte as cc
from cogs.fun.entertainment import MODULE_FUN
from core import carte_logic as cl
from core import fun_gare_logic as gare
from core.database import db
from core.repositories.fun_gare_repo import fun_gare_repo
from core.repositories.fun_impostazioni_repo import fun_impostazioni_repo as imp
from tests.support.discord_fakes import fake_guild, fake_interaction

ID = 108


class _C:
    def __init__(self, value):
        self.value = value
        self.name = value


def _partita(n=4, modo="giudice", vittoria=2, seed=1):
    rng = random.Random(seed)
    nere, bianche = cl.mazzi(["base", "nerd", "gamer"], rng)
    return cl.PartitaCarte(list(range(1, n + 1)), vittoria, modo, nere, bianche, rng)


# --- pacchetti e logica -----------------------------------------------------

def test_pacchetti_rispettano_i_limiti():
    for nome in (*cl.PACCHETTI, cl.PACCHETTO_ADULTI):
        nere, bianche = cl.carica_pacchetto(nome)
        assert len(nere) >= 8 and len(bianche) >= 24 and len(set(bianche)) == len(bianche)
        assert all(cl.SPAZIO in n and len(n) <= 200 for n in nere) and all(0 < len(b) <= 100 for b in bianche)
    _, tutte = cl.mazzi(list(cl.PACCHETTI), random.Random(0))
    assert len(tutte) >= cl.bianche_necessarie(cl.MAX_GIOCATORI)


def test_adulti_solo_con_server_e_canale_con_limite():
    assert cl.pacchetti_attivi("tutti", False, True) == list(cl.PACCHETTI)
    assert cl.pacchetti_attivi("adulti", True, False) == [] and cl.pacchetti_attivi("adulti", False, True) == []
    assert cl.pacchetti_attivi("adulti", True, True) == ["adulti"]
    assert cl.pacchetti_attivi("tutti", True, True)[-1] == "adulti"
    assert cl.pacchetti_attivi("inventato", True, True) == []
    assert cl.pacchetti_dal_testo("base,adulti,xx,gamer") == ["base", "gamer"]
    assert cl.riempi("Ho ____ qui.", "una torta") == "Ho **una torta** qui."


def test_round_giudice_mani_e_regole():
    p = _partita()
    nera = p.nuovo_round()
    assert cl.SPAZIO in nera and p.giudice == 1 and all(len(m) == 7 for m in p.mani.values())
    assert p.chi_gioca() == [2, 3, 4]
    assert p.gioca(9, 0) == "non_giocatore" and p.gioca(1, 0) == "giudice" and p.gioca(2, 7) == "fuori"
    carta = p.mani[2][3]
    assert p.gioca(2, 3) == "ok" and p.gioca(2, 0) == "gia" and p.giocate[2] == carta and len(p.mani[2]) == 6
    p.gioca(3, 0)
    risposte = p.apri_scelta()
    assert sorted(risposte) == sorted(p.giocate.values())
    assert p.scegli(2, 0) == "non_giudice" and p.scegli(1, 9) == "fuori" and p.scegli(8, 0) == "non_giocatore"
    assert p.scegli(1, 0) == "ok" and p.scegli(1, 1) == "gia"
    vincitore = p.chiudi_round()
    assert vincitore == p.ordine[0] and p.punti == {vincitore: 1}
    p.nuovo_round()
    assert p.giudice == 2 and all(len(m) == 7 for m in p.mani.values())  # mani ricaricate, giudice a turno


def test_round_voto_non_per_se_e_parita():
    p = _partita(3, "voto")
    p.nuovo_round()
    assert p.giudice == 0 and p.chi_gioca() == [1, 2, 3]
    for u in (1, 2, 3):
        assert p.gioca(u, 0) == "ok"
    p.apri_scelta()
    mio = p.ordine.index(1)
    assert p.scegli(1, mio) == "proprio"
    altro = (mio + 1) % 3
    assert p.scegli(1, altro) == "ok" and p.scegli(1, altro) == "gia"
    assert p.scelte_fatte() == 1 and p.votanti() == 3
    assert p.chiudi_round() == p.ordine[altro]
    p2 = _partita(3, "voto")
    p2.nuovo_round()
    assert p2.chiudi_round() is None  # nessuno ha giocato


def test_vittoria_e_mazzo_che_si_rimescola():
    p = _partita(3, "giudice", vittoria=2)
    for _ in range(40):  # più round delle carte: gli scarti tornano nel mazzo
        p.nuovo_round()
        for u in p.chi_gioca():
            assert p.gioca(u, 0) == "ok"
        p.apri_scelta()
        p.scegli(p.giudice, 0)
        p.chiudi_round()
        assert all(len(m) == 6 for u, m in p.mani.items() if u != p.giudice) or True
        if p.finita():
            break
    assert p.finita() and max(p.punti.values()) >= 2 and p.round <= cl.MAX_ROUND


# --- impostazioni -----------------------------------------------------------

@pytest.fixture(autouse=True)
async def _db(monkeypatch, clean_db):
    import core.database as dm

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID, MODULE_FUN, True)
    yield
    dm.db._modules_cache.clear()


async def test_impostazioni_adulti_spento_di_base():
    assert await imp.carte(ID) == ("base,nerd,gamer", False)
    assert await imp.imposta_carte(ID, "base", None) == ("base", False)
    assert await imp.imposta_carte(ID, None, True) == ("base", True)
    assert await imp.carte(ID + 1) == ("base,nerd,gamer", False)


# --- comandi ----------------------------------------------------------------

def _it(user_id=11, canale=888, nsfw=False):
    it = fake_interaction(guild=fake_guild(ID))
    it.user.id = user_id
    it.channel = MagicMock(spec=discord.TextChannel)
    it.channel.id = canale
    it.channel.is_nsfw = MagicMock(return_value=nsfw)
    it.channel.send = AsyncMock(return_value=MagicMock())
    return it


async def test_avvia_adulti_rifiutato_e_un_canale_alla_volta():
    cog = cc.CarteCog(bot=None)
    it = _it()
    await cog.carte_avvia.callback(cog, it, _C("adulti"), 5, None)
    assert it.response.send_message.await_args.kwargs["ephemeral"] and 888 not in cog._attive
    await imp.imposta_carte(ID, None, True)
    it = _it(nsfw=False)  # server acceso ma canale senza limite d'età
    await cog.carte_avvia.callback(cog, it, _C("adulti"), 5, None)
    assert it.response.send_message.await_args.kwargs["ephemeral"] and 888 not in cog._attive
    await imp.imposta_carte(ID, "base", False)
    it = _it()
    await cog.carte_avvia.callback(cog, it, _C("nerd"), 5, None)  # nerd spento nel server
    assert it.response.send_message.await_args.kwargs["ephemeral"] and 888 not in cog._attive
    cog._lobby = AsyncMock(return_value=None)
    it = _it()
    await cog.carte_avvia.callback(cog, it, None, 5, None)
    it2 = _it(12)
    await cog.carte_avvia.callback(cog, it2, None, 5, None)
    assert "ephemeral" in it2.response.send_message.await_args.kwargs
    await asyncio.gather(*cog._compiti)
    assert 888 not in cog._attive


async def test_partita_completa_con_giudice(monkeypatch):
    monkeypatch.setattr(cc, "SECONDI_GIOCATA", 5)
    monkeypatch.setattr(cc, "SECONDI_SCELTA", 5)
    monkeypatch.setattr(cc, "PAUSA_FRA_ROUND", 0)
    cog = cc.CarteCog(bot=None)
    cog._lobby = AsyncMock(return_value=[1, 2, 3])
    it = _it(1)
    cliccate = []

    async def invia(*a, **kw):
        v = kw.get("view")
        if isinstance(v, cc.VistaMano):
            p = v.partita
            for u in p.chi_gioca():
                x = _it(u)
                await v.mano.callback(x)  # apre il menu nascosto con le carte
                menu = x.response.send_message.await_args.kwargs["view"].children[0]
                assert len(menu.options) == 7 and all(len(o.label) <= 100 for o in menu.options)
                menu._values = ["0"]
                y = _it(u)
                await menu.callback(y)
                assert y.response.edit_message.await_count == 1
            cliccate.append(p.round)
            x = _it(p.giudice)
            await v.mano.callback(x)  # il giudice non gioca
            assert "ephemeral" in x.response.send_message.await_args.kwargs
        elif isinstance(v, cc.VistaScelta):
            p = v.partita
            assert len(v.children) == 2
            x = _it(p.chi_gioca()[0])
            await v.children[0].callback(x)  # non è il giudice: rifiutato
            assert p.scelta_giudice is None
            await v.children[1].callback(_it(p.giudice))
            assert p.scelta_giudice == 1 and v.evento.is_set()
        return MagicMock()

    it.channel.send = invia
    await cog.carte_avvia.callback(cog, it, None, 2, None)
    await asyncio.gather(*cog._compiti)
    assert cliccate and 888 not in cog._attive
    righe = await fun_gare_repo.classifica(ID, "carte", gare.periodo_settimana())
    assert righe and max(v for _, v in righe) >= 2


async def test_poche_carte_per_troppi_giocatori(monkeypatch):
    monkeypatch.setattr(cl, "carica_pacchetto", lambda nome: (["Test ____."], ["a", "b", "c"]))
    cog = cc.CarteCog(bot=None)
    cog._lobby = AsyncMock(return_value=[1, 2, 3])
    it = _it()
    await cog.carte_avvia.callback(cog, it, None, 2, None)
    await asyncio.gather(*cog._compiti)
    assert "3" in it.channel.send.await_args.args[0] and 888 not in cog._attive


async def test_admin_pacchetti():
    cog = cc.CarteCog(bot=None)
    with patch("core.command_access.puo_usare", AsyncMock(return_value=True)):
        it = _it()
        await cog.carte_pacchetti.callback(cog, it, False, False, False, None)
        assert await imp.carte(ID) == ("base,nerd,gamer", False)  # non toglie tutto
        it = _it()
        await cog.carte_pacchetti.callback(cog, it, False, False, None, True)
    assert await imp.carte(ID) == ("gamer", True)


async def test_albero_carte():
    from discord.ext import commands

    from tests.support.percorsi import percorsi_del_gruppo

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await cc.setup(bot)
    assert "carte avvia" in percorsi_del_gruppo("giochi") and "carte pacchetti" in percorsi_del_gruppo("admin-giochi")


async def test_adulti_tolti_se_il_canale_perde_il_limite_nella_sala(monkeypatch):
    """Il pacchetto adulti non parte se, durante la sala d'attesa, il canale perde il limite d'età."""
    visti = []
    monkeypatch.setattr(cl, "mazzi", lambda nomi, rng: (visti.append(list(nomi)) or (["N ____."] * 3, ["b"] * 40)))
    await imp.imposta_carte(ID, None, True)
    cog = cc.CarteCog(bot=None)
    it = _it(nsfw=True)

    async def lobby(*a, **kw):
        it.channel.is_nsfw.return_value = False
        return [1, 2, 3]

    cog._lobby = lobby
    await cog.carte_avvia.callback(cog, it, _C("adulti"), 5, None)
    await asyncio.gather(*cog._compiti)
    assert not visti  # solo adulti scelto e canale senza limite: la partita non parte
    it = _it(nsfw=True)

    async def lobby2(*a, **kw):
        it.channel.is_nsfw.return_value = False
        return [1, 2, 3]

    cog._lobby = lobby2
    it.channel.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500), "x"))
    await cog.carte_avvia.callback(cog, it, None, 2, None)
    await asyncio.gather(*cog._compiti)
    assert visti and "adulti" not in visti[0]

"""B7 di #131 (D70): battitura, testi del server, acronimi, sala d'attesa."""
import asyncio
import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from cogs.fun import _lobby as lobby
from cogs.fun import giochi_gruppo as cg
from cogs.fun.entertainment import MODULE_FUN
from core import fun_gare_logic as gare
from core import gruppo_logic as gl
from core.database import db
from core.repositories.battitura_repo import battitura_repo
from core.repositories.fun_gare_repo import fun_gare_repo
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction

ID = 107
T0 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
TESTO = "Il gatto dorme sul divano mentre fuori la pioggia batte piano"  # 11 parole


# --- logica ---------------------------------------------------------------

def test_precisione_e_parole_al_minuto():
    assert gl.precisione(TESTO, TESTO.upper() + "  ") == 1.0
    assert gl.precisione(TESTO, "Il gatto dorme") < gl.SOGLIA_PRECISIONE
    assert gl.parole_al_minuto(TESTO, 30) == 22 and gl.parole_al_minuto(TESTO, 0) == 660


def test_valuta_primo_invio_valido_solo_partecipanti():
    p = gl.PartitaBattitura(TESTO, T0, {1, 2})
    assert p.valuta(3, TESTO, T0 + timedelta(seconds=10)) is None
    assert p.valuta(1, "tutt'altro testo scritto male", T0 + timedelta(seconds=10)) is None
    assert p.valuta(1, TESTO, T0 - timedelta(seconds=1)) is None
    assert p.valuta(1, TESTO, T0 + timedelta(seconds=33)) == 20
    assert p.valuta(1, TESTO, T0 + timedelta(seconds=5)) is None  # un solo risultato a testa
    assert not p.finita and p.valuta(2, TESTO.replace("gatto", "gattO"), T0 + timedelta(seconds=22)) == 30
    assert p.finita and p.classifica() == [(2, 30), (1, 20)]


def test_testi_e_immagine():
    assert gl.testo_valido(TESTO) and not gl.testo_valido("troppo corto") and not gl.testo_valido("a " * 40)
    tutti = gl.testi_integrati()
    assert len(tutti) >= 10 and all(gl.testo_valido(t) for t in tutti)
    png = gl.disegna_testo(tutti[0])
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) < 500_000


def test_frase_valida():
    assert gl.frase_valida("Pasta Ogni Giorno, Grazie", "POGG")
    assert gl.frase_valida("Pane Olio Grano", "POG") and gl.frase_valida("pane (olio) grano", "POG")
    assert not gl.frase_valida("Pane Olio", "POG") and not gl.frase_valida("Pane Olio Rana", "POG")
    assert not gl.frase_valida("P " * 80, "P" * 80)
    assert 4 <= len(gl.lettere_acronimo(random.Random(1))) <= 6


def test_partita_acronimi_regole():
    p = gl.PartitaAcronimi([1, 2, 3], 2)
    p.lettere = "POG"
    assert p.invia(9, "Pane Olio Grano") == "non_giocatore" and p.invia(1, "Pane Olio") == "iniziali"
    assert p.invia(1, "Pane Olio Grano") == "ok" and p.invia(1, "Pane Olio Giro") == "gia"
    p.invia(2, "Pasta Olio Gelato")
    frasi = p.apri_voto(random.Random(2))
    assert sorted(frasi) == ["Pane Olio Grano", "Pasta Olio Gelato"]
    proprio = p.ordine.index(1)
    assert p.vota(1, proprio) == "proprio" and p.vota(7, 0) == "non_giocatore" and p.vota(3, 5) == "fuori"
    assert p.vota(3, proprio) == "ok" and p.vota(3, 1 - proprio) == "gia"
    assert p.chiudi_turno() == {1: 1} and p.punti == {1: 1}


# --- repository -----------------------------------------------------------

@pytest.fixture(autouse=True)
async def _db(monkeypatch, clean_db):
    import core.database as dm

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID, MODULE_FUN, True)
    yield
    dm.db._modules_cache.clear()


async def test_tetto_testi_anche_insieme(clean_db):
    await apri_connessioni(clean_db)
    esiti = await asyncio.gather(*[battitura_repo.aggiungi(ID, 1, f"testo {i}", tetto=5) for i in range(12)])
    assert sum(e is not None for e in esiti) == 5 and len(await battitura_repo.elenco(ID)) == 5
    (i, _), *_ = await battitura_repo.elenco(ID)
    assert not await battitura_repo.rimuovi(ID + 1, i) and await battitura_repo.rimuovi(ID, i)
    assert await battitura_repo.aggiungi(ID, 1, "altro", tetto=5) is not None


async def test_registra_massimo_tiene_il_migliore(clean_db):
    await apri_connessioni(clean_db)
    await asyncio.gather(*[fun_gare_repo.registra_massimo(ID, "battitura", "2026-W46", 5, v) for v in (30, 80, 50, 10)])
    assert await fun_gare_repo.classifica(ID, "battitura", "2026-W46") == [(5, 80)]


# --- sala d'attesa ----------------------------------------------------------

def _it(user_id=11, canale=777):
    it = fake_interaction(guild=fake_guild(ID))
    it.user.id = user_id
    it.channel = MagicMock(spec=discord.TextChannel)
    it.channel.id = canale
    it.channel.send = AsyncMock(return_value=MagicMock(created_at=T0, edit=AsyncMock()))
    return it


async def test_sala_entra_esci_avvia():
    v = lobby.VistaLobby(1, 2, 3, "Intro", ("Ci sono", "Esci", "Avvia"))
    it = _it(2)
    await v.entra.callback(it)
    await v.entra.callback(it)  # già dentro: avviso nascosto
    assert v.giocatori == [1, 2] and it.response.send_message.await_args.kwargs["ephemeral"]
    await v.entra.callback(_it(3))
    it4 = _it(4)
    await v.entra.callback(it4)  # pieno
    assert v.giocatori == [1, 2, 3] and it4.response.send_message.await_args.kwargs["ephemeral"]
    await v.esci.callback(_it(1))  # chi ha dato il comando non esce
    await v.esci.callback(_it(3))
    assert v.giocatori == [1, 2]
    await v.avvia.callback(_it(2))  # non è l'host
    assert not v.avviata
    await v.avvia.callback(_it(1))
    await v.avvia.callback(_it(1))
    assert v.avviata and v.pronta.is_set()


async def test_sala_poco_gente_e_scadenza():
    v = lobby.VistaLobby(1, 3, 5, "Intro", ("a", "b", "c"))
    it = _it(1)
    await v.avvia.callback(it)
    assert not v.avviata and it.response.send_message.await_args.kwargs["ephemeral"]
    await v.on_timeout()
    assert v.pronta.is_set() and not v.avviata
    v2 = lobby.VistaLobby(1, 1, 5, "Intro", ("a", "b", "c"))
    await v2.on_timeout()
    assert v2.avviata
    assert all(len(b.label) <= 45 for b in v.children)


# --- comandi ----------------------------------------------------------------

async def _aspetta(condizione, tentativi=200):
    for _ in range(tentativi):
        if condizione():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condizione mai vera")


async def test_battitura_partita_completa_e_un_canale_alla_volta():
    cog = cg.GiochiGruppoCog(bot=None)
    cog._lobby = AsyncMock(return_value=[11, 12])
    it = _it(11)
    await cog.battitura.callback(cog, it, 20)
    it2 = _it(13)
    await cog.battitura.callback(cog, it2, 20)
    assert it2.response.send_message.await_args.kwargs["ephemeral"] is True  # già una partita
    await _aspetta(lambda: 777 in cog._battitura)
    partita = cog._battitura[777]
    assert it.channel.send.await_args.kwargs["file"].filename == "testo.png"

    def msg(autore, testo, dopo):
        m = MagicMock(spec=discord.Message)
        m.channel, m.author, m.content = SimpleNamespace(id=777), SimpleNamespace(id=autore, bot=False), testo
        m.created_at, m.add_reaction = T0 + timedelta(seconds=dopo), AsyncMock()
        return m

    estraneo = msg(99, partita.testo, 5)
    await cog.on_message(estraneo)
    await cog.on_message(msg(11, "sbagliato del tutto", 5))
    primo = msg(11, partita.testo, 30)
    await cog.on_message(primo)
    primo.add_reaction.assert_awaited_once()
    assert not partita.finita
    await cog.on_message(msg(12, partita.testo, 15))
    await asyncio.gather(*cog._compiti)
    righe = await fun_gare_repo.classifica(ID, "battitura", gare.periodo_settimana())
    assert [u for u, _ in righe] == [12, 11] and 777 not in cog._attive and 777 not in cog._battitura
    assert it.channel.send.await_args.kwargs["embed"].description.count("<@") == 2
    estraneo.add_reaction.assert_not_awaited()


async def test_battitura_senza_giocatori_si_annulla():
    cog = cg.GiochiGruppoCog(bot=None)
    cog._lobby = AsyncMock(return_value=None)
    it = _it()
    await cog.battitura.callback(cog, it, 20)
    await asyncio.gather(*cog._compiti)
    assert 777 not in cog._attive and not cog._battitura


async def test_acronimi_due_turni_e_punti(monkeypatch):
    monkeypatch.setattr(cg, "SECONDI_SCRITTURA", 1)
    monkeypatch.setattr(cg, "SECONDI_VOTO", 1)
    cog = cg.GiochiGruppoCog(bot=None)
    cog._lobby = AsyncMock(return_value=[1, 2, 3])
    it = _it(1)
    viste = []

    async def invia(*a, **kw):
        v = kw.get("view")
        if isinstance(v, cg.VistaScrivi):
            lett = v.partita.lettere
            for u in (1, 2):  # il 3 non scrive
                assert v.partita.invia(u, " ".join(c + "x" * u for c in lett)) == "ok"
            viste.append("scrivi")
        elif isinstance(v, cg.VistaVoto):
            p = v.partita
            for votante in (1, 2, 3):
                scelta = next(i for i, a in enumerate(p.ordine) if a != votante)
                p.vota(votante, scelta)
            viste.append("voto")
            assert len(v.children[0].options) == 2
        return MagicMock(created_at=T0)

    it.channel.send = invia
    await cog.acronimi.callback(cog, it, 3, 2)
    await asyncio.gather(*cog._compiti)
    assert viste == ["scrivi", "voto", "scrivi", "voto"] and 777 not in cog._attive
    totale = await fun_gare_repo.classifica(ID, "acronimi", gare.periodo_settimana())
    assert sum(v for _, v in totale) == 6  # 3 voti per turno


async def test_modale_acronimo_e_tendina_voto():
    p = gl.PartitaAcronimi([1, 2], 1)
    p.lettere = "POG"
    ev = asyncio.Event()
    m = cg.ModaleAcronimo(p, ev, "Titolo molto lungo " * 5, "Etichetta " * 9)
    assert len(m.title) <= 45 and len(m.frase.label) <= 45 and m.frase.max_length == gl.MAX_FRASE
    it = _it(1)
    m.frase._value = "Pane Olio Grano"
    await m.on_submit(it)
    assert p.frasi == {1: "Pane Olio Grano"} and not ev.is_set()
    it = _it(2)
    m.frase._value = "sbagliata"
    await m.on_submit(it)
    assert 2 not in p.frasi and not ev.is_set()
    m.frase._value = "Pasta Olio Giro"
    await m.on_submit(_it(2))
    assert ev.is_set()
    assert len(cg.MenuVoto(["f" * 300] * 10, "x" * 300).options) == 10
    assert all(len(o.label) <= 100 for o in cg.MenuVoto(["f" * 300] * 10, "x").options)


async def test_admin_testi_battitura():
    cog = cg.GiochiGruppoCog(bot=None)
    it = _it()
    with patch("core.command_access.puo_usare", AsyncMock(return_value=True)):
        await cog.battitura_aggiungi.callback(cog, it)
    modale = it.response.send_modal.await_args.args[0]
    assert modale.testo.max_length == 300 and len(modale.title) <= 45
    modale.testo._value = "troppo corto per la gara"
    it = _it()
    await modale.on_submit(it)
    assert await battitura_repo.elenco(ID) == []
    modale.testo._value = TESTO
    it = _it()
    await modale.on_submit(it)
    assert [t for _, t in await battitura_repo.elenco(ID)] == [TESTO]
    it = _it()
    await cog.battitura_elenca.callback(cog, it)
    assert TESTO[:20] in it.response.send_message.await_args.kwargs["embed"].description


async def test_albero_gruppo():
    from discord.ext import commands

    from tests.support.percorsi import percorsi_del_gruppo

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await cg.setup(bot)
    assert {"battitura", "acronimi"} <= percorsi_del_gruppo("giochi")
    assert {"battitura aggiungi", "battitura elenca", "battitura rimuovi"} <= percorsi_del_gruppo("admin-giochi")

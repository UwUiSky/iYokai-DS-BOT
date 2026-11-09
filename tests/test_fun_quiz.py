"""B6 di #131 (D70): quiz base, domande del server, regole, punteggi senza corse."""
import asyncio
import json
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from cogs.fun import quiz as cq
from cogs.fun.entertainment import MODULE_FUN
from core import quiz_logic as q
from core.database import db
from core.repositories.fun_gare_repo import fun_gare_repo
from core.repositories.quiz_repo import quiz_repo
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction

ID = 106


class _C:
    def __init__(self, value):
        self.value = value
        self.name = value


def _dom(i=0):
    return q.Domanda(f"Domanda {i}?", ("giusta", "b", "c", "d"), "tema")


# --- logica ---------------------------------------------------------------

def test_csv_e_json_validi():
    csv_ = "Capitale?,Roma,Milano,Napoli,Torino,geo\nDue più due?,4,3,5,6\n".encode()
    righe = q.leggi_file(csv_, "d.csv")
    assert [r.risposte[0] for r in righe] == ["Roma", "4"] and righe[0].tema == "geo" and righe[1].tema == ""
    js = json.dumps([{"domanda": "X?", "risposte": ["a", "b", "c", "d"], "tema": "t"}]).encode()
    assert q.leggi_file(js, "d.json")[0].testo == "X?"
    assert q.leggi_file(b"\xef\xbb\xbfX?,a,b,c,d", "d.csv")[0].testo == "X?"


@pytest.mark.parametrize(
    "contenuto,nome,errore",
    [
        (b"x" * (q.MAX_BYTE_FILE + 1), "a.csv", "quiz_file_grande"),
        (b"\xff\xfe\x00", "a.csv", "quiz_file_illeggibile"),
        (b"[1,2]", "a.json", "quiz_file_illeggibile"),
        (b"", "a.csv", "quiz_file_vuoto"),
        (("x" * 201 + ",a,b,c,d").encode(), "a.csv", "quiz_file_domanda"),
        (b"X?,a,b,c", "a.csv", "quiz_file_risposte"),
        (("X?,a,b,c," + "y" * 81).encode(), "a.csv", "quiz_file_risposte"),
        (b"X?,a,A,c,d", "a.csv", "quiz_file_doppie"),
        ("\n".join(f"D{i}?,a,b,c,d" for i in range(301)).encode(), "a.csv", "quiz_file_troppe"),
    ],
)
def test_file_errati(contenuto, nome, errore):
    with pytest.raises(q.FileErrato, match=errore):
        q.leggi_file(contenuto, nome)


def test_mescola_tiene_la_giusta_e_domande_integrate():
    rng = random.Random(3)
    for _ in range(50):
        m = q.mescola(_dom(), rng)
        assert m.risposte[m.giusta] == "giusta" and sorted(m.risposte) == ["b", "c", "d", "giusta"]
    tutte = q.domande_integrate()
    assert len(tutte) >= 30 and len(q.domande_integrate("scienza")) >= 10
    assert all(len(d.testo) <= q.MAX_DOMANDA and all(len(r) <= q.MAX_RISPOSTA for r in d.risposte) for d in tutte)
    assert all(len({r.casefold() for r in d.risposte}) == 4 for d in tutte)


def test_partita_una_risposta_a_testa_e_punti():
    p = q.PartitaQuiz([q.mescola(_dom(i), random.Random(i)) for i in range(2)], q.RegoleQuiz(punti=7))
    g = p.corrente.giusta
    assert p.rispondi(1, g) and not p.rispondi(1, (g + 1) % 4) and not p.rispondi(2, 9)
    assert p.rispondi(2, (g + 1) % 4)
    assert p.chiudi_domanda() == [1] and p.punti == {1: 7} and p.risposte == {} and not p.finita
    p.rispondi(1, p.corrente.giusta)
    p.chiudi_domanda()
    assert p.finita and p.punti == {1: 14}
    assert q.classifica_partita({5: 1, 3: 9, 4: 9}) == [(3, 9), (4, 9), (5, 1)]


def test_bot_sbaglia_e_indovina():
    esiti = []
    for i in range(300):
        p = q.PartitaQuiz([q.mescola(_dom(), random.Random(i))], q.RegoleQuiz())
        q.fai_giocare_bot(p, 9, random.Random(i))
        esiti.append(p.risposte[9] == p.corrente.giusta)
    assert 0.45 < sum(esiti) / 300 < 0.75


# --- repository -----------------------------------------------------------

@pytest.fixture(autouse=True)
async def _db(monkeypatch, clean_db):
    import core.database as dm

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID, MODULE_FUN, True)
    yield
    dm.db._modules_cache.clear()


async def test_tetto_300_anche_con_caricamenti_insieme(clean_db):
    await apri_connessioni(clean_db)
    lotto = [_dom(i) for i in range(100)]
    esiti = await asyncio.gather(*[quiz_repo.aggiungi(ID, 1, lotto) for _ in range(5)])
    assert sorted(esiti) == [False, False, True, True, True]
    assert len(await quiz_repo.elenco(ID)) == 300
    assert await quiz_repo.aggiungi(ID, 1, [_dom()]) is False
    assert await quiz_repo.aggiungi(ID + 1, 1, [_dom()]) is True


async def test_domande_rimozione_e_giuste():
    await quiz_repo.aggiungi(ID, 1, [_dom(1), _dom(2)])
    (i1, _, _), _ = await quiz_repo.elenco(ID)
    assert (await quiz_repo.domande(ID))[0].risposte[0] == "giusta"
    assert await quiz_repo.rimuovi(ID + 1, i1) is False  # di un altro server
    assert await quiz_repo.rimuovi(ID, i1) is True and await quiz_repo.rimuovi(ID, i1) is False


async def test_regole_cambiano_solo_i_campi_dati():
    assert await quiz_repo.regole(ID) == q.RegoleQuiz()
    r = await quiz_repo.imposta_regole(ID, 20, None, None, True)
    assert r == q.RegoleQuiz(punti=20, secondi=30, mostra_risposta=True, bot_gioca=True)
    r = await quiz_repo.imposta_regole(ID, None, 60, False, None)
    assert r == q.RegoleQuiz(punti=20, secondi=60, mostra_risposta=False, bot_gioca=True)


async def test_aggiungi_punti_insieme_non_perde_nulla(clean_db):
    await apri_connessioni(clean_db)
    await asyncio.gather(*[fun_gare_repo.aggiungi_punti(ID, "quiz", "2026-W46", 7, 10) for _ in range(8)])
    assert await fun_gare_repo.classifica(ID, "quiz", "2026-W46") == [(7, 80)]


# --- comandi --------------------------------------------------------------

def _it(user_id=11, canale=777):
    it = fake_interaction(guild=fake_guild(ID))
    it.user.id = user_id
    it.channel = MagicMock(spec=discord.TextChannel)
    it.channel.id = canale
    it.channel.send = AsyncMock(return_value=MagicMock(edit=AsyncMock()))
    return it


async def test_avvia_una_partita_per_canale_e_gioco_completo(monkeypatch):
    monkeypatch.setattr(cq.asyncio, "sleep", AsyncMock())
    cog = cq.QuizCog(bot=SimpleNamespace(user=SimpleNamespace(id=999)))
    it = _it()
    await cog.quiz_avvia.callback(cog, it, 3, _C("scienza"), 5, 10)
    assert 777 in cog._attive
    it2 = _it(12)
    await cog.quiz_avvia.callback(cog, it2, 3, None, None, None)
    assert it2.response.send_message.await_args.kwargs["ephemeral"] is True  # già in corso
    await asyncio.gather(*cog._compiti)
    assert 777 not in cog._attive
    assert it.channel.send.await_count == 4  # 3 domande + classifica finale
    assert it.channel.send.await_args_list[0].kwargs["view"].children[0].label == "A"


async def test_clic_risposte_e_punti_in_classifica(monkeypatch):
    partita = q.PartitaQuiz([q.mescola(_dom(), random.Random(1))], q.RegoleQuiz(punti=10, secondi=10))
    vista = cq.VistaDomanda(partita)
    g = partita.corrente.giusta
    it = _it(5)
    await vista.children[g].callback(it)
    await vista.children[g].callback(it)  # secondo clic: ignorato
    assert partita.risposte == {5: g}
    assert it.response.send_message.await_count == 2 and it.response.send_message.await_args.kwargs["ephemeral"]
    monkeypatch.setattr(cq.asyncio, "sleep", AsyncMock())
    cog = cq.QuizCog(bot=SimpleNamespace(user=SimpleNamespace(id=999)))
    cog._attive.add(777)
    it = _it()
    partita2 = q.PartitaQuiz([q.mescola(_dom(), random.Random(1))], q.RegoleQuiz(punti=10, secondi=10, bot_gioca=True))
    messaggi = []

    async def invia(**kw):
        messaggi.append(kw)
        if "view" in kw:
            await kw["view"].children[partita2.corrente.giusta].callback(_it(5))
        return MagicMock(edit=AsyncMock())

    it.channel.send = invia
    await cog._gioca(it, it.channel, partita2)
    righe = await fun_gare_repo.classifica(ID, "quiz", cq.gare.periodo_settimana())
    assert (5, 10) in righe and 777 not in cog._attive


async def test_classifica_vuota_e_con_dati():
    cog = cq.QuizCog(bot=None)
    it = _it()
    await cog.quiz_classifica.callback(cog, it, None)
    assert "<@" not in it.response.send_message.await_args.kwargs["embed"].description
    await fun_gare_repo.aggiungi_punti(ID, "quiz", cq.gare.periodo_settimana(), 3, 25)
    it = _it()
    await cog.quiz_classifica.callback(cog, it, _C("sempre"))
    assert "<@3>" in it.response.send_message.await_args.kwargs["embed"].description


async def test_carica_elenca_rimuovi_regole():
    cog = cq.QuizCog(bot=None)
    for comando in (cog.quiz_carica, cog.quiz_elenca, cog.quiz_rimuovi, cog.quiz_regole):
        assert comando.callback  # esistono con il decoratore di livello
    file = SimpleNamespace(size=50, filename="d.csv", read=AsyncMock(return_value=b"X?,a,b,c,d\nY?,a,b,c,d"))
    with patch("core.command_access.puo_usare", AsyncMock(return_value=True)):
        it = _it()
        await cog.quiz_carica.callback(cog, it, file)
    assert len(await quiz_repo.elenco(ID)) == 2
    assert "2" in it.followup.send.await_args.args[0]
    file.read = AsyncMock(return_value=b"X?,a,b")
    it = _it()
    await cog.quiz_carica.callback(cog, it, file)
    assert len(await quiz_repo.elenco(ID)) == 2
    it = _it()
    await cog.quiz_regole.callback(cog, it, 15, None, None, True)
    assert (await quiz_repo.regole(ID)).punti == 15
    it = _it()
    await cog.quiz_elenca.callback(cog, it)
    assert it.response.send_message.await_args.kwargs["embed"].description.count("`") >= 4


async def test_albero_quiz():
    from discord.ext import commands

    from tests.support.percorsi import percorsi_del_gruppo

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await cq.setup(bot)
    assert {"quiz avvia", "quiz classifica"} <= percorsi_del_gruppo("giochi")
    assert {"quiz carica", "quiz elenca", "quiz rimuovi", "quiz regole"} <= percorsi_del_gruppo("admin-giochi")


async def test_clic_a_domanda_chiusa_non_conta_sulla_successiva():
    """Un clic che arriva dopo la chiusura della domanda non finisce tra le risposte della successiva."""
    partita = q.PartitaQuiz([q.mescola(_dom(), random.Random(1)), q.mescola(_dom(), random.Random(2))], q.RegoleQuiz(punti=10, secondi=10))
    vecchia = cq.VistaDomanda(partita)
    partita.chiudi_domanda()
    it = _it(5)
    await vecchia.children[0].callback(it)
    assert partita.risposte == {} and it.response.send_message.await_args.kwargs["ephemeral"]
    nuova = cq.VistaDomanda(partita)
    await nuova.children[0].callback(_it(5))
    assert partita.risposte == {5: 0}

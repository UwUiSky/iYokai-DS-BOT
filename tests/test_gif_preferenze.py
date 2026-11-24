"""
tests/test_gif_preferenze.py
============================
FUN-138 (D124): preferenze delle GIF. Salvate, usate quando la fonte lo permette, senza preferenze tutto come
prima, nel registro dei dati (esportabili e cancellabili).
"""

import random
from unittest.mock import AsyncMock, MagicMock

import pytest

import cogs.fun.gif as cog
from core import gif_preferenze_logic as logica
from core.gif_catalogo import Voce
from core.gif_fonti import Fonte, Gif, ServizioGif
from core.repositories.gif_preferenze_repo import GifPreferenzeRepository
from tests.support.discord_fakes import fake_interaction, fake_member

VOCE = Voce("dab", "FUN-081", "reazione", {"en": "Dab"}, (), "anime dab", {"nekosbest": "dab"})


def test_senza_preferenze_la_voce_resta_uguale():
    assert logica.voce_con_preferenze(VOCE, logica.Preferenze(), random.Random(1)) is VOCE


def test_preferenze_cambiano_la_ricerca_e_l_id():
    p = logica.Preferenze(tipo="non_anime", personaggi=("mario",))
    v = logica.voce_con_preferenze(VOCE, p, random.Random(1))
    assert v.ricerca.startswith("Mario") and v.ricerca.endswith("-anime") and v.id != VOCE.id and v.fonti == VOCE.fonti
    assert len(v.ricerca) <= 50


def test_genere_senza_preferiti_sceglie_dal_catalogo():
    p = logica.Preferenze(genere="femminile", tipo="anime")
    pers = logica.personaggio_per(p, random.Random(3))
    assert pers.genere == "f" and pers.tipo == "anime"


def test_preferiti_tetto_e_catalogo_chiuso():
    p = logica.Preferenze()
    p, esito = logica.aggiungi_preferito(p, "Naruto Uzumaki")
    assert esito == "ok" and p.personaggi == ("naruto-uzumaki",)
    assert logica.aggiungi_preferito(p, "naruto-uzumaki")[1] == "gia"
    assert logica.aggiungi_preferito(p, "Personaggio inventato")[1] == "sconosciuto"
    for pers in list(logica.catalogo())[:logica.MAX_PREFERITI]:
        p, _ = logica.aggiungi_preferito(p, pers)
    assert logica.aggiungi_preferito(p, "elsa")[1] in ("tetto", "gia")
    assert len(p.personaggi) <= logica.MAX_PREFERITI


def test_suggerimenti_al_massimo_25():
    assert len(logica.suggerimenti("")) <= 25 and logica.suggerimenti("zzzzqq") == []
    assert all(len(v) <= 100 for _n, v in logica.suggerimenti("a"))


@pytest.mark.asyncio
async def test_il_servizio_usa_le_preferenze_solo_con_una_fonte_che_cerca():
    richieste = []

    async def scarica(url):
        richieste.append(url)
        return '{"data": [{"images": {"original": {"url": "https://media.giphy.com/x.gif"}}}]}'

    giphy = Fonte("giphy", "https://api.giphy.com/v1", "k")
    s = ServizioGif([giphy], scarica, random.Random(1))
    gif = await s.prendi(VOCE, logica.Preferenze(tipo="non_anime", personaggi=("mario",)))
    assert gif and "Mario" in richieste[0] and "-anime" in richieste[0]
    # senza preferenze la richiesta è quella di prima
    s2 = ServizioGif([giphy], scarica, random.Random(1))
    await s2.prendi(VOCE)
    assert "Mario" not in richieste[1]


@pytest.mark.asyncio
async def test_senza_fonte_che_cerca_le_preferenze_non_cambiano_niente():
    chiamate = []

    async def scarica(url):
        chiamate.append(url)
        return '{"results": [{"url": "https://nekos.best/api/v2/dab/1.gif"}]}'

    s = ServizioGif([Fonte("nekosbest", "https://nekos.best/api/v2")], scarica, random.Random(1))
    gif = await s.prendi(VOCE, logica.Preferenze(tipo="non_anime"))
    assert gif is not None and "nekos.best/api/v2/dab" in chiamate[0]


# ------------------------------------------------------------------ database
@pytest.fixture
def repo(clean_db):
    return GifPreferenzeRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_salvate_lette_e_azzerate(repo):
    assert (await repo.leggi(5)).vuote
    p = logica.Preferenze("femminile", "anime", ("elsa", "nezuko-kamado"))
    await repo.salva(5, p)
    assert await repo.leggi(5) == p
    assert await repo.azzera(5) is True
    assert (await repo.leggi(5)).vuote


@pytest.mark.asyncio
async def test_preferenze_vuote_non_lasciano_una_riga(repo, clean_db):
    await repo.salva(6, logica.Preferenze("maschile"))
    await repo.salva(6, logica.Preferenze())
    assert await clean_db.fetchval("SELECT count(*) FROM gif_preferenze WHERE user_id = 6") == 0


@pytest.mark.asyncio
async def test_valori_non_validi_rifiutati(repo):
    with pytest.raises(ValueError):
        await repo.salva(7, logica.Preferenze(genere="boh"))


def test_la_tabella_e_nel_registro_dei_dati():
    from core.data_registry import REGISTRO

    voce = next(t for t in REGISTRO if t.nome == "gif_preferenze")
    assert voce.esporta and voce.utente == "cancella" and voce.colonne_utente == ("user_id",)


# ------------------------------------------------------------------ comando
@pytest.mark.asyncio
async def test_comando_salva_e_mostra(monkeypatch):
    repo = MagicMock()
    repo.leggi = AsyncMock(return_value=logica.Preferenze())
    repo.salva = AsyncMock()
    monkeypatch.setattr(cog, "gif_preferenze_repo", repo)
    monkeypatch.setattr(cog, "testo_per", AsyncMock(side_effect=lambda i, k, **kw: f"{k}:{kw}"))
    c = cog.GifCog(MagicMock())
    inter = fake_interaction(user=fake_member(user_id=9))
    tipo = MagicMock(value="anime")
    await c.preferenze.callback(c, inter, None, tipo, "elsa", None, False)
    salvate = repo.salva.await_args.args[1]
    assert salvate.tipo == "anime" and salvate.personaggi == ("elsa",)
    assert inter.response.send_message.await_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_preferenze_che_non_si_leggono_non_fermano_la_gif(monkeypatch):
    repo = MagicMock()
    repo.leggi = AsyncMock(side_effect=OSError)
    monkeypatch.setattr(cog, "gif_preferenze_repo", repo)
    assert (await cog._preferenze_di(1)).vuote

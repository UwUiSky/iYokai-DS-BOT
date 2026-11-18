"""
tests/test_music_r4_playlist.py
===============================
Catalogo MUS (issue #126) giro r4mus, blocco 2: playlist a mano. MUS-073 crea,
MUS-074 aggiungi, MUS-075 togli, MUS-076 niente doppioni, MUS-077 rinomina,
MUS-079 dettaglio dei brani a pagine. Logica pura, repository su PostgreSQL, comandi con finti.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import cogs.music.playlist as modulo
from cogs.music.playlist import MusicPlaylistCog
from core.music_playlist_logic import (
    BRANI_PER_PAGINA,
    MAX_BRANI_PER_PLAYLIST,
    MAX_PLAYLIST_PER_UTENTE,
    BranoSalvato,
    aggiungi_senza_doppioni,
    pagina_brani,
    togli_doppioni,
    togli_posizione,
)
from core.repositories.music_playlist_repo import LimitePlaylistRaggiunto, MusicPlaylistRepository
from tests.test_music_playlist import _Risposte


def _b(i, uri=True):
    return BranoSalvato(f"Brano {i}", f"https://x/{i}" if uri else None, 60000, f"QAAA{i}")


# --------------------------- logica pura ---------------------------
def test_mus076_doppioni_tolti_resta_la_prima_comparsa():
    elenco, tolti = togli_doppioni([_b(1), _b(2), _b(1), _b(3, uri=False), _b(3, uri=False)])
    assert [b.titolo for b in elenco] == ["Brano 1", "Brano 2", "Brano 3"]
    assert tolti == 2


def test_mus076_stesso_indirizzo_in_maiuscole_e_un_doppione():
    a = BranoSalvato("A", "https://X/Y", 1, "e1")
    b = BranoSalvato("B", "https://x/y", 1, "e2")
    assert togli_doppioni([a, b])[1] == 1


def test_mus074_aggiungi_conta_doppioni_e_tetto():
    esistenti = [_b(i) for i in range(MAX_BRANI_PER_PLAYLIST - 1)]
    elenco, agg, dop, fuori = aggiungi_senza_doppioni(esistenti, [_b(0), _b(900), _b(901)])
    assert (agg, dop, fuori) == (1, 1, 1)
    assert len(elenco) == MAX_BRANI_PER_PLAYLIST


def test_mus075_togli_posizione():
    brani = [_b(1), _b(2), _b(3)]
    elenco, tolto = togli_posizione(brani, 2)
    assert tolto.titolo == "Brano 2" and [b.titolo for b in elenco] == ["Brano 1", "Brano 3"]
    assert togli_posizione(brani, 0)[1] is None and togli_posizione(brani, 4)[1] is None
    assert len(brani) == 3  # l'originale non cambia


def test_mus079_pagine_del_dettaglio():
    brani = [_b(i) for i in range(BRANI_PER_PAGINA + 3)]
    righe, pagine = pagina_brani(brani, 1)
    assert pagine == 2 and len(righe) == BRANI_PER_PAGINA and righe[0].startswith("`1.`")
    righe2, _ = pagina_brani(brani, 2)
    assert len(righe2) == 3 and righe2[0].startswith(f"`{BRANI_PER_PAGINA + 1}.`")
    assert pagina_brani(brani, 99)[0] == righe2  # pagina oltre la fine: l'ultima
    assert pagina_brani([], 1) == ([], 1)


# --------------------------- repository ---------------------------
@pytest.fixture
def repo(clean_db):
    return MusicPlaylistRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_mus073_crea_vuota_e_tetto(repo):
    assert await repo.crea_vuota(1, "Nuova") is True
    assert await repo.crea_vuota(1, "Nuova") is False
    assert await repo.get(1, "Nuova") == []
    for i in range(MAX_PLAYLIST_PER_UTENTE - 1):
        await repo.crea_vuota(1, f"P{i}")
    with pytest.raises(LimitePlaylistRaggiunto):
        await repo.crea_vuota(1, "Una di troppo")
    assert await repo.crea_vuota(2, "Nuova") is True  # un altro utente ha le sue


@pytest.mark.asyncio
async def test_mus076_il_salvataggio_toglie_i_doppioni(repo):
    await repo.save(1, "Doppia", [_b(1), _b(1), _b(2)])
    assert [b.titolo for b in await repo.get(1, "Doppia")] == ["Brano 1", "Brano 2"]


@pytest.mark.asyncio
async def test_mus074_075_aggiorna_brani_e_playlist_mancante(repo):
    await repo.crea_vuota(1, "Mia")
    esito = await repo.aggiorna_brani(1, "Mia", lambda e: aggiungi_senza_doppioni(e, [_b(1), _b(2)])[:1] + (None,))
    assert [b.titolo for b in await repo.get(1, "Mia")] == ["Brano 1", "Brano 2"]
    tolto = await repo.aggiorna_brani(1, "Mia", lambda e: togli_posizione(e, 1))
    assert tolto.titolo == "Brano 1"
    assert [b.titolo for b in await repo.get(1, "Mia")] == ["Brano 2"]
    assert await repo.aggiorna_brani(1, "Non c'è", lambda e: (e, 1)) is None
    assert await repo.aggiorna_brani(2, "Mia", lambda e: (e, 1)) is None  # di un altro utente


@pytest.mark.asyncio
async def test_mus077_rinomina(repo):
    await repo.crea_vuota(1, "Vecchia")
    await repo.crea_vuota(1, "Altra")
    assert await repo.rinomina(1, "Vecchia", "Altra") == "esiste"
    assert await repo.rinomina(1, "Manca", "X") == "manca"
    assert await repo.rinomina(2, "Vecchia", "X") == "manca"
    assert await repo.rinomina(1, "Vecchia", "Nuova") == "ok"
    assert await repo.get(1, "Vecchia") is None and await repo.get(1, "Nuova") == []


# --------------------------- comandi ---------------------------
class _Musica:
    def __init__(self, risultati=None):
        self._cerca_su = AsyncMock(return_value=risultati)


def _cog(musica, repo, monkeypatch, nodo=object()):
    monkeypatch.setattr(modulo, "music_playlist_repo", repo)
    nodi = SimpleNamespace(node_for=lambda chiave: nodo)
    bot = SimpleNamespace(get_cog=lambda n: musica if n == "MusicCog" else None, music_nodes=nodi)
    return MusicPlaylistCog(bot)


def _interazione(user_id=1):
    risposte = _Risposte()
    invii = []

    async def _segui(testo=None, **kw):
        invii.append(testo)

    i = SimpleNamespace(
        guild=SimpleNamespace(id=10), guild_id=10, user=SimpleNamespace(id=user_id),
        response=risposte, followup=SimpleNamespace(send=_segui),
    )
    return i, risposte, invii


def _traccia(i):
    return SimpleNamespace(title=f"Brano {i}", uri=f"https://x/{i}", length=1000, encoded=f"QAAA{i}")


@pytest.mark.asyncio
async def test_crea_comando(repo, monkeypatch):
    cog = _cog(_Musica(), repo, monkeypatch)
    i, r, _ = _interazione()
    await cog.crea.callback(cog, i, nome="  Mia  lista ")
    assert "Mia lista" in r.testi[-1] and await repo.get(1, "Mia lista") == []
    await cog.crea.callback(cog, i, nome="Mia lista")
    assert "già" in r.testi[-1]
    await cog.crea.callback(cog, i, nome="a/b")  # nome non valido
    assert "Nome non valido" in r.testi[-1]


@pytest.mark.asyncio
async def test_aggiungi_cerca_e_non_duplica(repo, monkeypatch):
    await repo.crea_vuota(1, "Mia")
    musica = _Musica([_traccia(1)])
    cog = _cog(musica, repo, monkeypatch)
    i, _, invii = _interazione()
    await cog.aggiungi.callback(cog, i, nome="Mia", brano="una canzone")
    assert "1 brani aggiunti" in invii[-1]
    assert [b.encoded for b in await repo.get(1, "Mia")] == ["QAAA1"]
    cog.pausa_ricerche._ultimo.clear()
    await cog.aggiungi.callback(cog, i, nome="Mia", brano="una canzone")
    assert "1 doppioni" in invii[-1] and len(await repo.get(1, "Mia")) == 1


@pytest.mark.asyncio
async def test_aggiungi_ha_una_pausa_per_utente(repo, monkeypatch):
    await repo.crea_vuota(1, "Mia")
    musica = _Musica([_traccia(1)])
    cog = _cog(musica, repo, monkeypatch)
    i, r, _ = _interazione()
    await cog.aggiungi.callback(cog, i, nome="Mia", brano="a")
    await cog.aggiungi.callback(cog, i, nome="Mia", brano="b")
    assert musica._cerca_su.await_count == 1
    assert "Piano" in r.testi[-1]


@pytest.mark.asyncio
async def test_aggiungi_rifiuta_percorsi_e_playlist_mancante(repo, monkeypatch):
    await repo.crea_vuota(1, "Mia")
    musica = _Musica([_traccia(1)])
    cog = _cog(musica, repo, monkeypatch)
    i, _, invii = _interazione()
    await cog.aggiungi.callback(cog, i, nome="Mia", brano="local:/etc/passwd")
    assert musica._cerca_su.await_count == 0  # mai a Lavalink
    cog.pausa_ricerche._ultimo.clear()
    await cog.aggiungi.callback(cog, i, nome="Manca", brano="x")
    assert "Non hai una playlist" in invii[-1]


@pytest.mark.asyncio
async def test_aggiungi_senza_nodo_non_cerca(repo, monkeypatch):
    await repo.crea_vuota(1, "Mia")
    musica = _Musica([_traccia(1)])
    cog = _cog(musica, repo, monkeypatch, nodo=None)
    i, _, invii = _interazione()
    await cog.aggiungi.callback(cog, i, nome="Mia", brano="x")
    assert musica._cerca_su.await_count == 0 and invii


@pytest.mark.asyncio
async def test_togli_e_rinomina_comandi(repo, monkeypatch):
    await repo.save(1, "Mia", [_b(1), _b(2)])
    cog = _cog(_Musica(), repo, monkeypatch)
    i, r, _ = _interazione()
    await cog.togli.callback(cog, i, nome="Mia", posizione=1)
    assert "Brano 1" in r.testi[-1] and len(await repo.get(1, "Mia")) == 1
    await cog.togli.callback(cog, i, nome="Mia", posizione=9)
    assert "posizione 9" in r.testi[-1]
    await cog.togli.callback(cog, i, nome="Manca", posizione=1)
    assert "Non hai una playlist" in r.testi[-1]
    await cog.rinomina.callback(cog, i, nome="Mia", nuovo="Nuova")
    assert "Nuova" in r.testi[-1] and await repo.get(1, "Nuova") is not None


@pytest.mark.asyncio
async def test_elenco_con_nome_mostra_i_brani(repo, monkeypatch):
    await repo.save(1, "Mia", [_b(1), _b(2)])
    cog = _cog(_Musica(), repo, monkeypatch)
    inviati = []

    class _R(_Risposte):
        async def send_message(self, testo=None, **kw):
            inviati.append(kw.get("embed"))

    i, _, _ = _interazione()
    i.response = _R()
    await cog.elenco.callback(cog, i, nome="Mia", pagina=1)
    assert "Brano 2" in inviati[-1].description and "(2)" in inviati[-1].title

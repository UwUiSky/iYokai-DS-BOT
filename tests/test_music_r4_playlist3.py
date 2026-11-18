"""
tests/test_music_r4_playlist3.py
================================
Catalogo MUS (issue #126) giro r4mus, blocco 4: MUS-086 playlist a più mani (collaboratori) e
MUS-085 bottone «preferito» del player. Repository su PostgreSQL, comandi e bottone con finti.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

import cogs.music.playlist as modulo
import cogs.music.request_channel as rc
from cogs.music.playlist import MusicPlaylistCog
from cogs.music.request_channel import MusicRequestCog, PlayerRichiesteView
from core.music_playlist_logic import (
    MAX_COLLABORATORI,
    MAX_PLAYLIST_PER_UTENTE,
    NOME_PREFERITI,
    BranoSalvato,
)
from core.repositories.music_playlist_repo import MusicGuildPlaylistRepository, MusicPlaylistRepository
from tests.test_music_playlist import _Risposte
from tests.test_music_r4_playlist import _interazione, _traccia
from tests.test_music_r4_playlist2 import _Musica, _b


@pytest.fixture
def repo(clean_db):
    return MusicPlaylistRepository(pool_provider=lambda: clean_db)


def _cog(musica, repo, monkeypatch):
    monkeypatch.setattr(modulo, "music_playlist_repo", repo)
    nodi = SimpleNamespace(node_for=lambda chiave: object())
    bot = SimpleNamespace(get_cog=lambda n: musica if n == "MusicCog" else None, music_nodes=nodi)
    return MusicPlaylistCog(bot)


def _persona(uid, bot=False):
    return SimpleNamespace(id=uid, bot=bot)


# --------------------------- MUS-086 repository ---------------------------
@pytest.mark.asyncio
async def test_mus086_collaboratori_tetto_e_permessi(repo):
    await repo.save(1, "Mia", [_b(1)])
    assert await repo.aggiungi_collaboratore(1, "Manca", 2) == "manca"
    assert await repo.aggiungi_collaboratore(1, "Mia", 2) == "ok"
    assert await repo.aggiungi_collaboratore(1, "Mia", 2) == "gia"
    assert await repo.puo_modificare(1, "Mia", 2) is True
    assert await repo.puo_modificare(1, "Mia", 3) is False
    assert await repo.puo_modificare(1, "Mia", 1) is True  # il proprietario
    assert await repo.puo_modificare(1, "Manca", 1) is False
    for u in range(10, 10 + MAX_COLLABORATORI - 1):
        assert await repo.aggiungi_collaboratore(1, "Mia", u) == "ok"
    assert await repo.aggiungi_collaboratore(1, "Mia", 99) == "pieno"
    assert await repo.condivise_con(2) == [(1, "Mia")]
    assert await repo.togli_collaboratore(1, "Mia", 2) is True and await repo.togli_collaboratore(1, "Mia", 2) is False


@pytest.mark.asyncio
async def test_mus086_rinominare_o_cancellare_segue_i_collaboratori(repo):
    await repo.save(1, "Mia", [_b(1)])
    await repo.aggiungi_collaboratore(1, "Mia", 2)
    assert await repo.rinomina(1, "Mia", "Nuova") == "ok"
    assert await repo.puo_modificare(1, "Nuova", 2) is True
    assert await repo.delete(1, "Nuova") is True
    assert await repo.condivise_con(2) == []


# --------------------------- MUS-086 comandi ---------------------------
@pytest.mark.asyncio
async def test_mus086_comando_collabora(repo, monkeypatch):
    await repo.save(1, "Mia", [_b(1)])
    cog = _cog(_Musica(), repo, monkeypatch)
    i, r, _ = _interazione(1)
    await cog.collabora.callback(cog, i, nome="Mia", utente=_persona(2), togli=False)
    assert "ora può modificare" in r.testi[-1]
    await cog.collabora.callback(cog, i, nome="Mia", utente=_persona(2), togli=False)
    assert "già tra" in r.testi[-1]
    await cog.collabora.callback(cog, i, nome="Mia", utente=_persona(1), togli=False)  # se stesso
    assert "te stesso" in r.testi[-1]
    await cog.collabora.callback(cog, i, nome="Mia", utente=_persona(7, bot=True), togli=False)
    assert "bot" in r.testi[-1]
    await cog.collabora.callback(cog, i, nome="Mia", utente=None, togli=False)
    assert "<@2>" in r.testi[-1]
    await cog.collabora.callback(cog, i, nome="Mia", utente=_persona(2), togli=True)
    assert "non può più" in r.testi[-1]


@pytest.mark.asyncio
async def test_mus086_collaboratore_aggiunge_e_toglie_un_estraneo_no(repo, monkeypatch):
    await repo.save(1, "Mia", [_b(1)])
    await repo.aggiungi_collaboratore(1, "Mia", 2)
    musica = _Musica([_traccia(5)])
    cog = _cog(musica, repo, monkeypatch)
    # il collaboratore (2) aggiunge un brano alla playlist del proprietario (1)
    i, _, invii = _interazione(2)
    await cog.aggiungi.callback(cog, i, nome="Mia", brano="x", di=_persona(1))
    assert [b.encoded for b in await repo.get(1, "Mia")] == ["QAAA1", "QAAA5"]
    # e può toglierlo
    await cog.togli.callback(cog, i, nome="Mia", posizione=2, di=_persona(1))
    assert len(await repo.get(1, "Mia")) == 1
    # un estraneo (3) non può né aggiungere, né togliere, né vedere
    i3, r3, _ = _interazione(3)
    cog.pausa_ricerche._ultimo.clear()
    await cog.aggiungi.callback(cog, i3, nome="Mia", brano="x", di=_persona(1))
    await cog.togli.callback(cog, i3, nome="Mia", posizione=1, di=_persona(1))
    await cog.elenco.callback(cog, i3, nome="Mia", pagina=1, di=_persona(1))
    assert len(await repo.get(1, "Mia")) == 1
    assert r3.testi.count("Non hai una playlist con questo nome.") == 3
    assert musica._cerca_su.await_count == 1  # la ricerca dell'estraneo non è partita


@pytest.mark.asyncio
async def test_mus086_il_collaboratore_non_cancella_ne_condivide(repo, monkeypatch):
    """rinomina, elimina, condividi, aggiorna e collabora non hanno `di`: valgono solo per le proprie."""
    await repo.save(1, "Mia", [_b(1)])
    await repo.aggiungi_collaboratore(1, "Mia", 2)
    cog = _cog(_Musica(), repo, monkeypatch)
    i, r, _ = _interazione(2)
    await cog.elimina.callback(cog, i, nome="Mia")
    await cog.rinomina.callback(cog, i, nome="Mia", nuovo="Mia2")
    await cog.condividi.callback(cog, i, nome="Mia", nuovo=False, revoca=False)
    assert await repo.get(1, "Mia") is not None and await repo.get(2, "Mia") is None
    assert await repo.nomi(2) == set()  # niente è nato a nome del collaboratore
    assert await repo.da_codice("AAAAAAAA") is None


@pytest.mark.asyncio
async def test_mus086_carica_di_un_altro_solo_se_collaboratore(repo, monkeypatch):
    await repo.save(1, "Mia", [_b(1)])
    await repo.aggiungi_collaboratore(1, "Mia", 2)
    musica = _Musica()
    cog = _cog(musica, repo, monkeypatch)

    async def _decodifica(nodo, nome, brani):
        return "ok"

    monkeypatch.setattr(modulo, "decodifica_brani", _decodifica)
    i3, _, _ = _interazione(3)
    await cog.carica.callback(cog, i3, nome="Mia", di=_persona(1))
    assert musica.accodate == []
    i2, _, _ = _interazione(2)
    await cog.carica.callback(cog, i2, nome="Mia", di=_persona(1))
    assert musica.accodate == [("Mia", "ok")]


@pytest.mark.asyncio
async def test_mus086_elenco_mostra_le_condivise_con_te(repo, monkeypatch):
    await repo.save(1, "Mia", [_b(1)])
    await repo.aggiungi_collaboratore(1, "Mia", 2)
    cog = _cog(_Musica(), repo, monkeypatch)
    inviati = []

    class _R(_Risposte):
        async def send_message(self, testo=None, **kw):
            inviati.append(kw.get("embed"))

    i, _, _ = _interazione(2)
    i.response = _R()
    await cog.elenco.callback(cog, i, nome=None, pagina=1, di=None)
    assert "<@1>" in inviati[-1].description and "Mia" in inviati[-1].description


# --------------------------- MUS-085 preferiti ---------------------------
def _cog_richieste(repo, monkeypatch):
    monkeypatch.setattr(rc, "music_playlist_repo", repo)
    return MusicRequestCog(bot=SimpleNamespace(get_cog=lambda n: None))


def _player(titolo=1):
    return SimpleNamespace(current=_traccia(titolo))


@pytest.mark.asyncio
async def test_mus085_il_cuore_salva_in_preferiti_senza_doppioni(repo, monkeypatch):
    cog = _cog_richieste(repo, monkeypatch)
    i, _, _ = _interazione(5)
    testo = await cog.salva_preferito(i, _player(1))
    assert "Preferiti" in testo and "Brano 1" in testo
    cog.pausa_preferiti._ultimo.clear()
    assert "già" in await cog.salva_preferito(i, _player(1))
    cog.pausa_preferiti._ultimo.clear()
    await cog.salva_preferito(i, _player(2))
    assert [b.encoded for b in await repo.get(5, NOME_PREFERITI)] == ["QAAA1", "QAAA2"]


@pytest.mark.asyncio
async def test_mus085_pausa_e_niente_in_ascolto(repo, monkeypatch):
    cog = _cog_richieste(repo, monkeypatch)
    i, _, _ = _interazione(5)
    assert "nessun brano" in await cog.salva_preferito(i, SimpleNamespace(current=None))
    assert "Piano" in await cog.salva_preferito(i, _player(1))  # subito dopo: pausa
    assert await repo.get(5, NOME_PREFERITI) is None


@pytest.mark.asyncio
async def test_mus085_con_25_playlist_i_preferiti_gia_esistenti_funzionano(repo, monkeypatch):
    cog = _cog_richieste(repo, monkeypatch)
    await repo.crea_vuota(5, NOME_PREFERITI)
    for n in range(MAX_PLAYLIST_PER_UTENTE - 1):
        await repo.crea_vuota(5, f"P{n}")
    i, _, _ = _interazione(5)
    assert "Brano 1" in await cog.salva_preferito(i, _player(1))
    # senza i Preferiti e con 25 playlist: messaggio chiaro, niente eccezioni
    i2, _, _ = _interazione(6)
    for n in range(MAX_PLAYLIST_PER_UTENTE):
        await repo.crea_vuota(6, f"Q{n}")
    assert "25" in await cog.salva_preferito(i2, _player(1))


@pytest.mark.asyncio
async def test_mus085_il_bottone_e_nel_player_e_passa_dal_cuore():
    vista = PlayerRichiesteView(None)
    custom = {getattr(b, "custom_id", None): b for b in vista.children}
    assert "iyokai_musreq_preferito" in custom and custom["iyokai_musreq_preferito"].row == 1
    assert sum(1 for b in vista.children if b.row == 0) == 5
    cog = MusicRequestCog(bot=SimpleNamespace(get_cog=lambda n: None))
    cog.salva_preferito = AsyncMock(return_value="ok")
    musica = SimpleNamespace(_giocatore_attivo=AsyncMock(return_value=_player()))
    cog.bot.get_cog = lambda n: musica
    i, _, invii = _interazione(5)
    i.followup = SimpleNamespace(send=AsyncMock())
    await cog.premi(i, "preferito")
    cog.salva_preferito.assert_awaited_once()
    i.followup.send.assert_awaited_once()

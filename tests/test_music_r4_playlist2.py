"""
tests/test_music_r4_playlist2.py
================================
Catalogo MUS (issue #126) giro r4mus, blocco 3: MUS-072 salva da link, MUS-083 aggiorna dal link
di origine, MUS-084 codice per condividere, MUS-081 playlist del server, MUS-087 cancellazione
dei dati dell'utente. Logica pura, repository su PostgreSQL, comandi con finti.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import cogs.music.playlist as modulo
from cogs.music.playlist import MusicPlaylistCog
from core.data_registry import REGISTRO
from core.music_playlist_logic import (
    ALFABETO_CODICE,
    CODICE_LUNGHEZZA,
    MAX_PLAYLIST_PER_SERVER,
    BranoSalvato,
    codice_valido,
    link_origine_valido,
    nome_per_copia,
    nuovo_codice,
)
from core.repositories.music_playlist_repo import (
    LimitePlaylistRaggiunto,
    MusicGuildPlaylistRepository,
    MusicPlaylistRepository,
)
import wavelink

from core.music_playlist_logic import dati_playlist_wavelink
from tests.test_music_playlist import _Risposte, _payload_traccia
from tests.test_music_r4_playlist import _interazione, _traccia


def _b(i):
    return BranoSalvato(f"Brano {i}", f"https://x/{i}", 60000, f"QAAA{i}")


# --------------------------- logica pura ---------------------------
def test_mus084_codice_casuale_con_l_alfabeto_leggibile():
    codici = {nuovo_codice() for _ in range(50)}
    assert len(codici) == 50
    for c in codici:
        assert len(c) == CODICE_LUNGHEZZA and all(ch in ALFABETO_CODICE for ch in c)
    assert not set("0O1I") & set(ALFABETO_CODICE)


def test_mus084_codice_scritto_dall_utente():
    assert codice_valido("abcd-2345") == "ABCD2345"
    assert codice_valido(" abcd 2345 ") == "ABCD2345"
    for male in ("", "ABC", "ABCD234O", "ABCD23456", None, "ABCD234!"):
        assert codice_valido(male) is None


def test_mus084_nome_della_copia():
    assert nome_per_copia("Rock", set()) == "Rock"
    assert nome_per_copia("Rock", {"Rock"}) == "Rock (2)"
    assert nome_per_copia("Rock", {"Rock", "Rock (2)"}) == "Rock (3)"
    lungo = "x" * 50
    assert len(nome_per_copia(lungo, {lungo})) <= 50


def test_mus072_link_di_origine():
    assert link_origine_valido("https://open.spotify.com/playlist/1") == "https://open.spotify.com/playlist/1"
    for male in ("http://x/y", "ftp://x", "https://x/a b", "titolo", None, "https://" + "a" * 300):
        assert link_origine_valido(male) is None


# --------------------------- repository ---------------------------
@pytest.fixture
def repo(clean_db):
    return MusicPlaylistRepository(pool_provider=lambda: clean_db)


@pytest.fixture
def repo_server(clean_db):
    return MusicGuildPlaylistRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_mus083_origine_si_salva_e_si_azzera_senza_link(repo):
    await repo.save(1, "Da link", [_b(1)], "https://x/pl")
    assert await repo.origine(1, "Da link") == "https://x/pl"
    await repo.save(1, "Da link", [_b(2)])  # salvata a mano: non ha più un'origine
    assert await repo.origine(1, "Da link") is None


@pytest.mark.asyncio
async def test_mus084_codice_stabile_nuovo_e_revoca(repo):
    await repo.save(1, "Mia", [_b(1)])
    c1 = await repo.codice(1, "Mia")
    assert c1 and await repo.codice(1, "Mia") == c1  # lo stesso finché non lo cambi
    c2 = await repo.codice(1, "Mia", nuovo=True)
    assert c2 != c1
    assert await repo.da_codice(c1) is None  # il vecchio non vale più
    proprietario, nome, brani = await repo.da_codice(c2)
    assert (proprietario, nome, [b.titolo for b in brani]) == (1, "Mia", ["Brano 1"])
    assert await repo.codice(1, "Manca") is None
    assert await repo.revoca_codice(1, "Mia") is True and await repo.revoca_codice(1, "Mia") is False
    assert await repo.da_codice(c2) is None


@pytest.mark.asyncio
async def test_mus081_playlist_del_server_tetto_e_isolamento(repo_server):
    assert await repo_server.save(5, "Festa", [_b(1), _b(1), _b(2)], user_id=9) is True
    assert await repo_server.save(5, "Festa", [_b(3)], user_id=9) is False
    assert [b.titolo for b in await repo_server.get(5, "Festa")] == ["Brano 3"]
    assert await repo_server.get(6, "Festa") is None  # un altro server non la vede
    for i in range(MAX_PLAYLIST_PER_SERVER - 1):
        await repo_server.save(5, f"P{i}", [_b(1)], user_id=9)
    with pytest.raises(LimitePlaylistRaggiunto):
        await repo_server.save(5, "Troppa", [_b(1)], user_id=9)
    assert len(await repo_server.list_for_guild(5)) == MAX_PLAYLIST_PER_SERVER
    assert await repo_server.delete(5, "Festa") is True and await repo_server.delete(5, "Festa") is False


def test_mus087_i_dati_musicali_dell_utente_si_cancellano():
    """MUS-087: la cancellazione dei dati (/utility privacy) copre playlist e collaborazioni."""
    per_nome = {t.nome: t for t in REGISTRO}
    assert per_nome["music_playlists"].utente == "cancella"
    assert per_nome["music_playlist_collabs"].utente == "cancella"
    assert per_nome["music_guild_playlists"].colonna_server == "guild_id"


@pytest.mark.asyncio
async def test_mus087_cancellare_l_utente_toglie_le_sue_playlist(clean_db):
    await clean_db.execute("INSERT INTO music_playlists (user_id, name) VALUES (77, 'A'), (77, 'B'), (78, 'C')")
    sql = {t.nome: t for t in REGISTRO}["music_playlists"].sql_cancella_utente()
    await clean_db.execute(sql, 77)
    assert await clean_db.fetchval("SELECT count(*) FROM music_playlists") == 1


# --------------------------- comandi ---------------------------
class _Musica:
    def __init__(self, risultati=None, player=None):
        self._cerca_su = AsyncMock(return_value=risultati)
        self.player = player
        self.accodate = []

    async def _giocatore_attivo(self, interaction):
        return self.player

    async def controlli_base(self, interaction):
        return True

    async def accoda(self, guild, membro, query, rispondi, **kw):
        risultati, nodo = await kw["cerca"]("nodo", None)
        self.accodate.append((query, risultati))
        return 3


def _cog(musica, repo, repo_server, monkeypatch):
    monkeypatch.setattr(modulo, "music_playlist_repo", repo)
    monkeypatch.setattr(modulo, "music_guild_playlist_repo", repo_server)
    nodi = SimpleNamespace(node_for=lambda chiave: object())
    bot = SimpleNamespace(get_cog=lambda n: musica if n == "MusicCog" else None, music_nodes=nodi)
    return MusicPlaylistCog(bot)


class _Gestore:
    manage_guild = True


@pytest.mark.asyncio
async def test_salva_da_link_ricorda_l_origine(repo, repo_server, monkeypatch):
    musica = _Musica([_traccia(1), _traccia(1)])
    cog = _cog(musica, repo, repo_server, monkeypatch)
    i, _, invii = _interazione()
    await cog.salva.callback(cog, i, nome="Dal web", link="https://soundcloud.com/a/sets/b")
    assert "1 brani" in invii[-1]
    assert await repo.origine(1, "Dal web") == "https://soundcloud.com/a/sets/b"
    musica._cerca_su.assert_awaited_once()


@pytest.mark.asyncio
async def test_salva_da_link_rifiuta_http_e_percorsi(repo, repo_server, monkeypatch):
    musica = _Musica([_traccia(1)])
    cog = _cog(musica, repo, repo_server, monkeypatch)
    for male in ("http://x/y", "file:///etc/passwd", "local:/x", "/etc/passwd"):
        i, r, _ = _interazione()
        cog.pausa_ricerche._ultimo.clear()
        await cog.salva.callback(cog, i, nome="X", link=male)
        assert "https" in r.testi[-1]
    assert musica._cerca_su.await_count == 0 and await repo.get(1, "X") is None


@pytest.mark.asyncio
async def test_aggiorna_rilegge_il_link_e_ha_la_pausa(repo, repo_server, monkeypatch):
    await repo.save(1, "Dal web", [_b(1)], "https://x/pl")
    await repo.save(1, "A mano", [_b(1)])
    lista = wavelink.Playlist(dati_playlist_wavelink("x", [_payload_traccia(5), _payload_traccia(6)]))
    musica = _Musica(lista)
    cog = _cog(musica, repo, repo_server, monkeypatch)
    i, r, invii = _interazione()
    await cog.aggiorna.callback(cog, i, nome="A mano")
    assert "non è stata salvata da un link" in r.testi[-1] and musica._cerca_su.await_count == 0
    await cog.aggiorna.callback(cog, i, nome="Dal web")
    assert [b.encoded for b in await repo.get(1, "Dal web")] == ["QAAA5", "QAAA6"]
    await cog.aggiorna.callback(cog, i, nome="Dal web")  # subito dopo: pausa
    assert musica._cerca_su.await_count == 1 and "Piano" in r.testi[-1]


@pytest.mark.asyncio
async def test_condividi_e_ricevi_fanno_una_copia(repo, repo_server, monkeypatch):
    await repo.save(1, "Rock", [_b(1), _b(2)])
    await repo.save(2, "Rock", [_b(9)])
    cog = _cog(_Musica(), repo, repo_server, monkeypatch)
    i1, r1, _ = _interazione(1)
    await cog.condividi.callback(cog, i1, nome="Rock", nuovo=False, revoca=False)
    codice = await repo.codice(1, "Rock")
    assert codice in r1.testi[-1]
    i2, r2, _ = _interazione(2)
    await cog.ricevi.callback(cog, i2, codice=codice.lower())
    assert "Rock (2)" in r2.testi[-1]  # il nome era già preso
    assert [b.encoded for b in await repo.get(2, "Rock (2)")] == ["QAAA1", "QAAA2"]
    assert [b.encoded for b in await repo.get(2, "Rock")] == ["QAAA9"]  # la sua non cambia
    # la copia è sua: modificarla non tocca l'originale
    await repo.save(2, "Rock (2)", [_b(7)])
    assert len(await repo.get(1, "Rock")) == 2


@pytest.mark.asyncio
async def test_ricevi_codice_sbagliato_e_pausa(repo, repo_server, monkeypatch):
    cog = _cog(_Musica(), repo, repo_server, monkeypatch)
    i, r, _ = _interazione(3)
    await cog.ricevi.callback(cog, i, codice="ABCD2345")
    assert "non valido" in r.testi[-1]
    await cog.ricevi.callback(cog, i, codice="ABCD2346")  # subito dopo: frenato
    assert "Piano" in r.testi[-1]


@pytest.mark.asyncio
async def test_condividi_revoca_e_playlist_di_altri(repo, repo_server, monkeypatch):
    await repo.save(1, "Rock", [_b(1)])
    cog = _cog(_Musica(), repo, repo_server, monkeypatch)
    i, r, _ = _interazione(1)
    await cog.condividi.callback(cog, i, nome="Rock", nuovo=False, revoca=True)
    assert "nessun codice" in r.testi[-1]
    i2, r2, _ = _interazione(2)
    await cog.condividi.callback(cog, i2, nome="Rock", nuovo=False, revoca=False)  # non è sua
    assert "Non hai una playlist" in r2.testi[-1]


def _utente(permessi):
    class _U:
        id = 1
        guild_permissions = permessi

    return _U()


@pytest.mark.asyncio
async def test_playlist_del_server_serve_gestisci_server(repo, repo_server, monkeypatch):
    player = SimpleNamespace(current=_traccia(1), queue=[_traccia(2)])
    cog = _cog(_Musica(player=player), repo, repo_server, monkeypatch)
    i, r, _ = _interazione()
    i.user = _utente(SimpleNamespace(manage_guild=False))
    await cog.server_salva.callback(cog, i, nome="Festa")
    assert "Gestisci server" in r.testi[-1] and await repo_server.get(10, "Festa") is None
    i.user = _utente(_Gestore())
    await cog.server_salva.callback(cog, i, nome="Festa")
    assert [b.encoded for b in await repo_server.get(10, "Festa")] == ["QAAA1", "QAAA2"]
    # tutti possono caricarla e vederla, solo chi gestisce la cancella
    i.user = _utente(SimpleNamespace(manage_guild=False))
    await cog.server_elimina.callback(cog, i, nome="Festa")
    assert await repo_server.get(10, "Festa") is not None
    i.user = _utente(_Gestore())
    await cog.server_elimina.callback(cog, i, nome="Festa")
    assert await repo_server.get(10, "Festa") is None


@pytest.mark.asyncio
async def test_playlist_del_server_carica(repo, repo_server, monkeypatch):
    await repo_server.save(10, "Festa", [_b(1)], user_id=9)
    musica = _Musica()
    cog = _cog(musica, repo, repo_server, monkeypatch)
    chiamate = []

    async def _decodifica(nodo, nome, brani):
        chiamate.append((nome, [b.encoded for b in brani]))
        return "decodificata"

    monkeypatch.setattr(modulo, "decodifica_brani", _decodifica)
    i, _, invii = _interazione()
    await cog.server_carica.callback(cog, i, nome="Festa")
    assert chiamate == [("Festa", ["QAAA1"])] and musica.accodate == [("Festa", "decodificata")]
    await cog.server_carica.callback(cog, i, nome="Manca")
    assert "non ha una playlist" in invii[-1]

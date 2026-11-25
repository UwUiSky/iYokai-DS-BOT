"""
tests/test_music_r4_riserva.py
==============================
Catalogo MUS (issue #126) giro r4mus, blocco 6: MUS-041 e MUS-040 playlist di riserva a coda finita,
MUS-045 playlist «Oggi», MUS-042 coda salvata e ripristinata.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import wavelink

import cogs.music.eventi as ev
from cogs.music.eventi import MusicEventiCog
from core.music_playlist_logic import NOME_PLAYLIST_DEL_GIORNO, BranoSalvato
from core.music_settings_logic import MusicSettings
from core.repositories.music_playlist_repo import MusicGuildPlaylistRepository, MusicSavedQueueRepository
from tests.test_music_queue_cmds import _player


def _b(i):
    return BranoSalvato(f"Brano {i}", f"https://x/{i}", 60000, f"QAAA{i}")


@pytest.fixture
def repo_server(clean_db):
    return MusicGuildPlaylistRepository(pool_provider=lambda: clean_db)


@pytest.fixture
def repo_coda(clean_db):
    return MusicSavedQueueRepository(pool_provider=lambda: clean_db)


def _traccia(i):
    return SimpleNamespace(title=f"T{i}", length=1000, is_stream=False, encoded=f"E{i}", uri=f"https://x/{i}", extras=SimpleNamespace())


def _giocatore(umani=1, riserva="Festa"):
    p = _player([])
    p.current = None
    p.play = AsyncMock()
    p.node = object()
    p.guild = SimpleNamespace(id=5)
    p.channel = SimpleNamespace(id=9, members=[SimpleNamespace(bot=False)] * umani + [SimpleNamespace(bot=True)])
    return p


def _patch(monkeypatch, imp, brani=None, tracce=None):
    monkeypatch.setattr(ev, "load_music_settings", AsyncMock(return_value=imp))
    monkeypatch.setattr(ev.music_guild_playlist_repo, "get", AsyncMock(return_value=brani))
    lista = SimpleNamespace(tracks=tracce or [])
    import cogs.music.playlist as pl

    monkeypatch.setattr(pl, "decodifica_brani", AsyncMock(return_value=lista if tracce else None))


@pytest.mark.asyncio
async def test_riserva_parte_a_coda_finita_con_qualcuno_in_canale(monkeypatch):
    p = _giocatore()
    _patch(monkeypatch, MusicSettings(fallback_playlist="Festa"), [_b(1)], [_traccia(1), _traccia(2), _traccia(3)])
    cog = MusicEventiCog(bot=MagicMock())
    assert await cog.riserva(p, attesa=0) is True
    p.play.assert_awaited_once()
    assert len(p.queue) == 2


@pytest.mark.asyncio
async def test_riserva_non_parte_senza_ascoltatori_senza_scelta_o_con_pausa(monkeypatch):
    cog = MusicEventiCog(bot=MagicMock())
    _patch(monkeypatch, MusicSettings(fallback_playlist="Festa"), [_b(1)], [_traccia(1)])
    assert await cog.riserva(_giocatore(umani=0), attesa=0) is False  # canale vuoto
    _patch(monkeypatch, MusicSettings(), [_b(1)], [_traccia(1)])
    assert await cog.riserva(_giocatore(), attesa=0) is False  # nessuna playlist scelta
    _patch(monkeypatch, MusicSettings(fallback_playlist="Festa"), [_b(1)], [_traccia(1)])
    p = _giocatore()
    assert await cog.riserva(p, attesa=0) is True
    assert await cog.riserva(_giocatore(), attesa=0) is False  # pausa tra due avvii dello stesso server


@pytest.mark.asyncio
async def test_riserva_rispetta_parole_vietate_e_se_arriva_altro_si_ferma(monkeypatch):
    cog = MusicEventiCog(bot=MagicMock())
    _patch(monkeypatch, MusicSettings(fallback_playlist="Festa", banned_words="t1"), [_b(1)], [_traccia(1)])
    assert await cog.riserva(_giocatore(), attesa=0) is False  # tutti i brani vietati
    cog2 = MusicEventiCog(bot=MagicMock())
    p = _giocatore()
    p.current = _traccia(9)  # nel frattempo un utente ha messo un brano
    _patch(monkeypatch, MusicSettings(fallback_playlist="Festa"), [_b(1)], [_traccia(1)])
    assert await cog2.riserva(p, attesa=0) is False
    p.play.assert_not_called()


@pytest.mark.asyncio
async def test_fine_brano_lancia_la_riserva_ma_non_se_sostituito(monkeypatch):
    cog = MusicEventiCog(bot=MagicMock())
    cog.riserva = AsyncMock()
    p = _giocatore()
    await cog.su_fine_brano(SimpleNamespace(player=p, reason="finished"))
    await asyncio.sleep(0)
    cog.riserva.assert_awaited_once()
    cog.riserva.reset_mock()
    await cog.su_fine_brano(SimpleNamespace(player=p, reason="replaced"))
    await asyncio.sleep(0)
    cog.riserva.assert_not_called()


@pytest.mark.asyncio
async def test_mus045_oggi_aggiunge_senza_doppioni_e_riparte_ogni_giorno(repo_server, clean_db):
    assert await repo_server.aggiungi_del_giorno(5, _b(1)) is True
    assert await repo_server.aggiungi_del_giorno(5, _b(1)) is False  # doppione
    assert await repo_server.aggiungi_del_giorno(5, _b(2)) is True
    assert [b.titolo for b in await repo_server.get(5, NOME_PLAYLIST_DEL_GIORNO)] == ["Brano 1", "Brano 2"]
    await clean_db.execute("UPDATE music_guild_playlists SET created_at = now() - interval '2 days'")
    assert await repo_server.aggiungi_del_giorno(5, _b(3)) is True  # nuovo giorno: si riparte
    assert [b.titolo for b in await repo_server.get(5, NOME_PLAYLIST_DEL_GIORNO)] == ["Brano 3"]
    assert await repo_server.get(6, NOME_PLAYLIST_DEL_GIORNO) is None


@pytest.mark.asyncio
async def test_mus045_senza_posto_nel_server_non_scrive(repo_server):
    for n in range(25):
        await repo_server.save(5, f"P{n}", [_b(1)], 1)
    assert await repo_server.aggiungi_del_giorno(5, _b(1)) is False


@pytest.mark.asyncio
async def test_mus045_inizio_brano_scrive_solo_se_acceso(monkeypatch):
    cog = MusicEventiCog(bot=MagicMock())
    scrive = AsyncMock()
    monkeypatch.setattr(ev.music_guild_playlist_repo, "aggiungi_del_giorno", scrive)
    ev_ = SimpleNamespace(player=_giocatore(), track=_traccia(1))
    monkeypatch.setattr(ev, "load_music_settings", AsyncMock(return_value=MusicSettings()))
    await cog.su_inizio_brano(ev_)
    scrive.assert_not_called()
    monkeypatch.setattr(ev, "load_music_settings", AsyncMock(return_value=MusicSettings(daily_playlist=True)))
    await cog.su_inizio_brano(ev_)
    scrive.assert_awaited_once()


@pytest.mark.asyncio
async def test_mus042_coda_salvata_si_scrive_si_legge_e_si_svuota(repo_coda):
    await repo_coda.salva(5, 9, [_b(1), _b(2)])
    assert [b.titolo for b in await repo_coda.leggi(5, 9)] == ["Brano 1", "Brano 2"]
    assert await repo_coda.leggi(5, 10) == []  # un altro canale
    await repo_coda.salva(5, 9, [])
    assert await repo_coda.leggi(5, 9) == []


@pytest.mark.asyncio
async def test_mus042_salvataggio_solo_se_acceso(monkeypatch):
    cog = MusicEventiCog(bot=MagicMock())
    salva = AsyncMock()
    monkeypatch.setattr(ev.music_saved_queue_repo, "salva", salva)
    monkeypatch.setattr(ev, "ATTESA_SALVATAGGIO", 0)
    p = _giocatore()
    p.current = _traccia(1)
    monkeypatch.setattr(ev, "load_music_settings", AsyncMock(return_value=MusicSettings()))
    await cog._salva_coda(p, 5, 9)
    salva.assert_not_called()
    monkeypatch.setattr(ev, "load_music_settings", AsyncMock(return_value=MusicSettings(persist_queue=True)))
    await cog._salva_coda(p, 5, 9)
    assert salva.await_args.args[:2] == (5, 9) and len(salva.await_args.args[2]) == 1
    # un solo salvataggio per canale alla volta
    cog.pianifica_salvataggio(p)
    cog.pianifica_salvataggio(p)
    assert len(cog._salvataggi) == 1
    await asyncio.gather(*cog._salvataggi.values())


@pytest.mark.asyncio
async def test_mus042_ripristina_usa_la_coda_del_canale_e_la_decodifica(monkeypatch):
    import cogs.music.player as pm
    import cogs.music.playlist as pl

    cog = pm.MusicCog(bot=MagicMock())
    cog.controlli_base = AsyncMock(return_value=True)
    cog.accoda = AsyncMock()
    leggi = AsyncMock(return_value=[_b(1)])
    monkeypatch.setattr(pm.music_saved_queue_repo, "leggi", leggi)
    decod = AsyncMock(return_value="lista")
    monkeypatch.setattr(pl, "decodifica_brani", decod)
    i = MagicMock()
    i.guild.id, i.user.voice.channel.id = 5, 9
    i.response.defer = AsyncMock()
    i.response.send_message = AsyncMock()
    monkeypatch.setattr(pm, "load_music_settings", AsyncMock(return_value=MusicSettings()))
    await cog.coda_ripristina.callback(cog, i)  # spenta: niente
    cog.accoda.assert_not_called()
    monkeypatch.setattr(pm, "load_music_settings", AsyncMock(return_value=MusicSettings(persist_queue=True)))
    await cog.coda_ripristina.callback(cog, i)
    leggi.assert_awaited_with(5, 9)
    cerca = cog.accoda.call_args.kwargs["cerca"]
    assert await cerca("nodo", None) == ("lista", "nodo")  # passa dalla decodifica con i controlli di sicurezza
    leggi.return_value = []
    cog.accoda.reset_mock()
    await cog.coda_ripristina.callback(cog, i)
    cog.accoda.assert_not_called()

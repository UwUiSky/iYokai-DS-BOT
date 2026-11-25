"""
tests/test_music_autonomia.py
=============================
La musica va avanti da sola: nodi Lavalink che ripartono dopo una caduta, ritorno al nodo preferito,
avviso all'owner, slot musicali rilasciati sempre (sessione) e liberati dal controllo periodico.
Funzioni coperte: consiglio 25/11/2026, critici 7 e 8 (blocco C)
"""

from __future__ import annotations

import ast
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import wavelink

from core import music_nodes, music_sorveglianza as ms
from core.music_fleet import MusicFleet
from core.music_fleet_logic import TOTAL_WORKERS
from core.music_logic import LavalinkNodeConfig
from core.music_nodes import MAIN_KEY, MusicNodeManager
from core.repositories.music_session_repo import music_session_repo

RADICE = Path(__file__).resolve().parent.parent


class _Client:
    async def wait_until_ready(self):
        return None


def _connetti(stato):
    """Connessione finta: ok se `stato["su"]`, altrimenti il nodo resta scollegato."""

    async def connetti(nodo, client):
        if stato["su"]:
            nodo._status = wavelink.NodeStatus.CONNECTED
        else:
            nodo._status = wavelink.NodeStatus.DISCONNECTED
            nodo._websocket = None

    return connetti


def _gestore(stato, pubblici=1):
    async def leggi(nodo):
        return "4.2.0"

    return MusicNodeManager(
        [LavalinkNodeConfig(f"http://pub{i}.test:80", "pw") for i in range(pubblici)],
        LavalinkNodeConfig("http://127.0.0.1:2333", "pw"),
        connetti=_connetti(stato), leggi_versione=leggi, retries=1, attesa_pronto=0.2, pause_riprova=(0.05,),
    )


async def _aspetta(condizione, secondi=5.0):
    fine = asyncio.get_running_loop().time() + secondi
    while not condizione():
        assert asyncio.get_running_loop().time() < fine, "condizione mai verificata"
        await asyncio.sleep(0.02)


async def _chiudi(g):
    with patch("wavelink.Pool.close", new=AsyncMock()):
        await g.close()


def _connessi(g):
    return {n.identifier.split("@")[0] for n in g.nodi_di(MAIN_KEY) if n.status is wavelink.NodeStatus.CONNECTED}


async def test_nodo_caduto_riparte_da_solo_e_il_preferito_torna_in_testa(monkeypatch):
    monkeypatch.setattr(music_nodes, "RIPARTENZA_DOPO_CADUTA", 0.05)
    stato = {"su": True}
    g = _gestore(stato)
    g.avvia(_Client(), MAIN_KEY)
    await _aspetta(lambda: len(_connessi(g)) == 2)
    pubblico = g.nodi_di(MAIN_KEY)[0]

    # Lavalink cade: wavelink chiude il nodo e lancia l'evento.
    stato["su"] = False
    pubblico._status = wavelink.NodeStatus.DISCONNECTED
    pubblico._has_closed = True
    assert g.node_for(MAIN_KEY).identifier.startswith("iyokai-local-node")  # si passa al locale
    with patch.object(MusicNodeManager, "_scarta", new=AsyncMock()):
        await g.su_nodo_chiuso(pubblico)
        await asyncio.sleep(0.3)  # tenta e fallisce: riprova con pause
        assert pubblico.status is not wavelink.NodeStatus.CONNECTED
        # Lavalink torna.
        stato["su"] = True
        await _aspetta(lambda: pubblico.status is wavelink.NodeStatus.CONNECTED)
    assert g.node_for(MAIN_KEY) is pubblico  # il preferito (pubblico) torna davanti al locale
    await _chiudi(g)


async def test_il_controllo_periodico_fa_ripartire_un_nodo_senza_evento(monkeypatch):
    monkeypatch.setattr(music_nodes, "RIPARTENZA_DOPO_CADUTA", 0.0)
    stato = {"su": True}
    g = _gestore(stato)
    g.avvia(_Client(), MAIN_KEY)
    await _aspetta(lambda: len(_connessi(g)) == 2)
    pubblico = g.nodi_di(MAIN_KEY)[0]
    await asyncio.gather(*g.tasks)
    pubblico._status = wavelink.NodeStatus.DISCONNECTED
    assert g.riparti_nodi_caduti() == 1
    await _aspetta(lambda: pubblico.status is wavelink.NodeStatus.CONNECTED)
    assert g.riparti_nodi_caduti() == 0
    await _chiudi(g)


async def test_un_nodo_con_tentativo_in_corso_non_ne_riceve_un_secondo():
    stato = {"su": False}
    g = _gestore(stato)
    g.avvia(_Client(), MAIN_KEY)
    await asyncio.sleep(0.1)
    assert g.riparti_nodi_caduti() == 0  # i tentativi di avvio sono ancora attivi
    await _chiudi(g)


# ---------------------------------------------------------------- avviso all'owner


def test_avviso_solo_se_lavalink_aveva_funzionato_e_resta_giu(monkeypatch):
    chiamate = []
    finto = SimpleNamespace(
        caduto=lambda bot, nome, det="": chiamate.append(("giu", nome)),
        tornato=lambda bot, nome: chiamate.append(("su", nome)),
    )
    monkeypatch.setattr(ms, "avvisi_owner", finto)
    stato = {"srv": False}
    gestore = SimpleNamespace(riparti_nodi_caduti=lambda: 0, stato_per_servizio=lambda: dict(stato))
    s = ms.SorveglianzaMusica(object(), gestore, None)

    s.controlla_nodi(adesso=0)
    s.controlla_nodi(adesso=1000)
    assert ("giu", "lavalink:srv") not in chiamate  # mai collegato: Lavalink è facoltativo
    stato["srv"] = True
    s.controlla_nodi(adesso=1001)
    stato["srv"] = False
    s.controlla_nodi(adesso=1002)
    s.controlla_nodi(adesso=1002 + ms.ATTESA_AVVISO_GIU_SECONDI - 1)
    assert ("giu", "lavalink:srv") not in chiamate  # giù da poco
    s.controlla_nodi(adesso=1002 + ms.ATTESA_AVVISO_GIU_SECONDI)
    assert ("giu", "lavalink:srv") in chiamate


# ---------------------------------------------------------------- slot musicali


class _WorkerFinto:
    def __init__(self, voice_client=None, pronto=True):
        self._guild = SimpleNamespace(voice_client=voice_client)
        self._pronto = pronto

    def is_ready(self):
        return self._pronto

    def get_guild(self, guild_id):
        return self._guild


def _flotta(workers=None):
    workers = workers or [_WorkerFinto() for _ in range(TOTAL_WORKERS)]
    return MusicFleet(workers), workers


@pytest.fixture
async def repo(clean_db, monkeypatch):
    from core.database import db

    monkeypatch.setattr(db, "_pool", clean_db)
    return clean_db


async def test_sessione_libera_lo_slot_anche_con_un_errore_imprevisto(repo):
    flotta, workers = _flotta()
    assert await music_session_repo.assign_free_worker(1, 10, set()) == 1
    with pytest.raises(RuntimeError):
        async with flotta.sessione(1, 10, workers[0], workers[0].get_guild(1)):
            raise RuntimeError("errore imprevisto in mezzo")
    assert await music_session_repo.get_worker_for_channel(1, 10) is None


async def test_sessione_non_libera_sotto_un_player_che_suona(repo):
    flotta, workers = _flotta([_WorkerFinto(voice_client=object())] + [_WorkerFinto() for _ in range(TOTAL_WORKERS - 1)])
    await music_session_repo.assign_free_worker(1, 10, set())
    async with flotta.sessione(1, 10, workers[0], workers[0].get_guild(1)):
        pass
    assert await music_session_repo.get_worker_for_channel(1, 10) == 1


async def test_il_rilascio_con_worker_index_non_tocca_lo_slot_di_un_altro(repo):
    await music_session_repo.assign_free_worker(1, 10, set())  # worker 1
    await music_session_repo.release_session(1, 10, worker_index=2)
    assert await music_session_repo.get_worker_for_channel(1, 10) == 1
    await music_session_repo.release_session(1, 10, worker_index=1)
    assert await music_session_repo.get_worker_for_channel(1, 10) is None


async def test_il_controllo_libera_solo_gli_slot_persi(repo):
    vivo = SimpleNamespace(channel=SimpleNamespace(id=20))
    workers = [_WorkerFinto(), _WorkerFinto(voice_client=vivo), _WorkerFinto(), _WorkerFinto(pronto=False), _WorkerFinto()]
    flotta, _ = _flotta(workers[:TOTAL_WORKERS])
    for canale in (10, 20, 30, 40):
        await music_session_repo.assign_free_worker(1, canale, set())  # workers 1..4
    # La riga 30 è appena nata: ha tempo per far entrare il bot.
    await repo.execute("UPDATE music_sessions SET assigned_at = now() - interval '10 minutes' WHERE channel_id <> 30")
    assert await flotta.libera_slot_persi() == 1  # solo il canale 10 (worker 1 non è in vocale)
    assert await music_session_repo.get_worker_for_channel(1, 10) is None
    assert await music_session_repo.get_worker_for_channel(1, 20) == 2  # sessione viva
    assert await music_session_repo.get_worker_for_channel(1, 30) == 3  # in grazia
    assert await music_session_repo.get_worker_for_channel(1, 40) == 4  # worker non pronto: non si sa


# ---------------------------------------------------------------- cricchetto


def test_cricchetto_i_cog_fuori_dalla_musica_non_usano_metodi_privati_del_player():
    colpe = []
    for percorso in sorted((RADICE / "cogs").rglob("*.py")):
        if "music" in percorso.parts:
            continue
        albero = ast.parse(percorso.read_text(encoding="utf-8"))
        for n in ast.walk(albero):
            if (
                isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name)
                and n.value.id in {"musica", "music_cog"}
                and n.attr.startswith("_")
                and not n.attr.startswith("__")
            ):
                colpe.append(f"{percorso.relative_to(RADICE)}:{n.lineno} {n.attr}")
    assert not colpe, "usa i metodi pubblici del player: " + ", ".join(colpe)


def test_cricchetto_il_player_non_rilascia_gli_slot_a_mano_nei_rami():
    """Il rilascio sta in `MusicFleet.sessione` (un solo punto, con `finally`): niente rami con la sua copia a mano."""
    albero = ast.parse((RADICE / "cogs" / "music" / "player.py").read_text(encoding="utf-8"))
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.AsyncFunctionDef) and nodo.name == "_play_nel_canale":
            chiamate = [
                n.lineno for n in ast.walk(nodo)
                if isinstance(n, ast.Attribute) and n.attr in {"rilascia_se_libero", "release_session"}
            ]
            assert not chiamate, f"rilascio a mano in _play_nel_canale, righe {chiamate}"
            return
    raise AssertionError("_play_nel_canale non trovata")

"""
tests/test_music_istanze_dinamiche.py
=====================================
D30: le istanze music crescono oltre 5 (MUSIC_TOKEN_6…20 dal .env) e
nessun comando dei server tocca la radio del bot principale.
"""

import re
from pathlib import Path

import pytest

from core.config import MUSIC_WORKER_MAX, _load_config
from core.music_fleet import MusicFleet
from core.music_fleet_logic import find_free_worker


class _Bot:
    def __init__(self, i):
        self.worker_index = i


def _pulisci(monkeypatch):
    for i in range(6, MUSIC_WORKER_MAX + 3):
        monkeypatch.delenv(f"MUSIC_TOKEN_{i}", raising=False)


def test_di_base_i_token_sono_cinque(monkeypatch):
    _pulisci(monkeypatch)
    assert len(_load_config().MUSIC_TOKENS) == 5


def test_i_token_dal_sesto_si_leggono_senza_toccare_il_codice(monkeypatch):
    _pulisci(monkeypatch)
    monkeypatch.setenv("MUSIC_TOKEN_6", "t6")
    monkeypatch.setenv("MUSIC_TOKEN_7", "t7")
    cfg = _load_config()
    assert cfg.MUSIC_TOKENS[5:] == ["t6", "t7"]
    assert "t6" not in repr(cfg)


def test_un_buco_ferma_la_lettura(monkeypatch):
    _pulisci(monkeypatch)
    monkeypatch.setenv("MUSIC_TOKEN_6", "t6")
    monkeypatch.setenv("MUSIC_TOKEN_8", "t8")
    assert len(_load_config().MUSIC_TOKENS) == 6


def test_il_tetto_vale(monkeypatch):
    _pulisci(monkeypatch)
    for i in range(6, MUSIC_WORKER_MAX + 3):
        monkeypatch.setenv(f"MUSIC_TOKEN_{i}", f"t{i}")
    assert len(_load_config().MUSIC_TOKENS) == MUSIC_WORKER_MAX


def test_i_primi_cinque_restano_obbligatori(monkeypatch):
    monkeypatch.delenv("MUSIC_TOKEN_3", raising=False)
    with pytest.raises(SystemExit):
        _load_config()


def test_la_flotta_accetta_piu_di_cinque_e_assegna_il_settimo():
    flotta = MusicFleet([_Bot(i) for i in range(1, 9)])
    assert flotta.total_workers == 8
    assert find_free_worker({1, 2, 3, 4, 5, 6}, flotta.total_workers) == 7
    assert find_free_worker(set(range(1, 9)), flotta.total_workers) is None


def test_main_crea_tanti_worker_quanti_i_token():
    sorgente = Path("main.py").read_text(encoding="utf-8")
    assert "len(config.MUSIC_TOKENS)" in sorgente
    assert "range(1, 6)" not in sorgente


def test_i_comandi_dei_server_non_toccano_il_player_del_bot_principale():
    """Fuori dalla sezione /owner radio, il voice_client usato è sempre quello di un worker."""
    sorgente = Path("cogs/music/player.py").read_text(encoding="utf-8")
    inizio_radio = sorgente.index("# /owner radio")
    fuori = sorgente[:inizio_radio]
    for riga in fuori.splitlines():
        if ".voice_client" in riga:
            assert "worker_guild.voice_client" in riga, riga.strip()


def test_i_comandi_radio_sono_solo_del_proprietario():
    sorgente = Path("cogs/music/player.py").read_text(encoding="utf-8")
    radio = sorgente[sorgente.index("# /owner radio"):]
    assert len(re.findall(r'"owner",\s*nome=', radio)) >= 5
    assert "sottogruppo=RADIO" in radio

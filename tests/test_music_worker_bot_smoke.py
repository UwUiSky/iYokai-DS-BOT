"""
tests/test_music_worker_bot_smoke.py
========================================
Smoke test di MusicWorkerBot — un'istanza si crea correttamente,
non ha comandi propri (i comandi arrivano SOLO dal bot principale).
"""

from core.music_worker_bot import MusicWorkerBot


def test_music_worker_bot_si_istanzia_senza_comandi_propri():
    worker = MusicWorkerBot(worker_index=3)

    assert worker.worker_index == 3
    assert list(worker.tree.get_commands()) == []


def test_music_worker_bot_ha_gli_intent_voce():
    worker = MusicWorkerBot(worker_index=1)

    assert worker.intents.voice_states is True

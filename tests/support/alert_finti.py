"""
tests/support/alert_finti.py
============================
Per i test dei watcher con repository finti: il repository delle opzioni degli
avvisi (core/repositories/alert_options_repo.py) risponde "nessuna opzione",
senza aprire il database. Si importa il fixture nel modulo di test.
"""

import pytest


class RepoOpzioniFinto:
    def __init__(self, opzioni=None, ruoli=None):
        self.opzioni = opzioni or {}
        self.ruoli = ruoli or {}
        self.ultimi_messaggi = {}

    async def get_many(self, kind, sub_ids):
        return {i: self.opzioni[(kind, i)] for i in sub_ids if (kind, i) in self.opzioni}

    async def get(self, kind, sub_id):
        from core.alert_options_logic import AlertOptions

        return self.opzioni.get((kind, sub_id), AlertOptions())

    async def get_live_roles(self, guild_ids):
        return {g: r for g, r in self.ruoli.items() if g in guild_ids}

    async def set_last_message(self, kind, sub_id, guild_id, message_id):
        self.ultimi_messaggi[(kind, sub_id)] = message_id


@pytest.fixture(autouse=True)
def repo_opzioni_finto(monkeypatch):
    finto = RepoOpzioniFinto()
    for percorso in ("core.live_alert_flow.alert_options_repo", "core.feed_watcher.alert_options_repo"):
        monkeypatch.setattr(percorso, finto)
    return finto

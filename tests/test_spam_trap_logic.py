"""
tests/test_spam_trap_logic.py
================================
Test di core/spam_trap_logic.py — logica pura, nessuna dipendenza da
Discord. I confini temporali (7/14/30 giorni) sono il punto più
delicato: coperti esplicitamente con casi limite.
"""

from datetime import datetime, timedelta, timezone

from core.spam_trap_logic import (
    APPEAL_COOLDOWN_SECONDS,
    can_appeal,
    diff_invite_uses,
    partition_messages_for_deletion,
    purge_window,
)


class TestCanAppeal:
    def test_mai_fatto_appello_puo_farlo(self):
        assert can_appeal(last_appeal_at=None) is True

    def test_appello_recente_non_puo_rifarlo(self):
        ora = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        ultimo = ora - timedelta(hours=1)
        assert can_appeal(ultimo, now=ora) is False

    def test_appello_dopo_24h_puo_rifarlo(self):
        ora = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        ultimo = ora - timedelta(seconds=APPEAL_COOLDOWN_SECONDS)
        assert can_appeal(ultimo, now=ora) is True

    def test_appena_sotto_24h_non_puo(self):
        ora = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        ultimo = ora - timedelta(seconds=APPEAL_COOLDOWN_SECONDS - 1)
        assert can_appeal(ultimo, now=ora) is False


class TestPartitionMessagesForDeletion:
    def test_messaggio_recente_e_bulk_eligible(self):
        ora = datetime(2026, 1, 15, tzinfo=timezone.utc)
        messaggi = [(1, ora - timedelta(days=5))]
        bulk, individuali = partition_messages_for_deletion(messaggi, now=ora)
        assert bulk == [1]
        assert individuali == []

    def test_messaggio_vecchio_e_individuale(self):
        ora = datetime(2026, 1, 15, tzinfo=timezone.utc)
        messaggi = [(1, ora - timedelta(days=20))]
        bulk, individuali = partition_messages_for_deletion(messaggi, now=ora)
        assert bulk == []
        assert individuali == [1]

    def test_esattamente_a_14_giorni_e_bulk_eligible(self):
        # Il confine è "più recente di 14 giorni" -> esattamente 14
        # giorni fa deve ancora rientrare nel bulk (>=).
        ora = datetime(2026, 1, 15, tzinfo=timezone.utc)
        messaggi = [(1, ora - timedelta(days=14))]
        bulk, individuali = partition_messages_for_deletion(messaggi, now=ora)
        assert bulk == [1]

    def test_un_secondo_oltre_i_14_giorni_e_individuale(self):
        ora = datetime(2026, 1, 15, tzinfo=timezone.utc)
        messaggi = [(1, ora - timedelta(days=14, seconds=1))]
        bulk, individuali = partition_messages_for_deletion(messaggi, now=ora)
        assert individuali == [1]

    def test_lista_mista_partizionata_correttamente(self):
        ora = datetime(2026, 1, 15, tzinfo=timezone.utc)
        messaggi = [
            (1, ora - timedelta(days=2)),   # bulk
            (2, ora - timedelta(days=10)),  # bulk
            (3, ora - timedelta(days=20)),  # individuale
            (4, ora - timedelta(days=25)),  # individuale
        ]
        bulk, individuali = partition_messages_for_deletion(messaggi, now=ora)
        assert set(bulk) == {1, 2}
        assert set(individuali) == {3, 4}

    def test_lista_vuota(self):
        bulk, individuali = partition_messages_for_deletion([])
        assert bulk == []
        assert individuali == []


class TestPurgeWindow:
    def test_finestra_e_da_30_a_7_giorni_fa(self):
        ora = datetime(2026, 1, 31, tzinfo=timezone.utc)
        inizio, fine = purge_window(now=ora)
        assert inizio == ora - timedelta(days=30)
        assert fine == ora - timedelta(days=7)
        assert inizio < fine


class TestDiffInviteUses:
    def test_un_solo_codice_aumentato_viene_identificato(self):
        prima = {"abc123": 5, "xyz789": 2}
        dopo = {"abc123": 6, "xyz789": 2}
        assert diff_invite_uses(prima, dopo) == "abc123"

    def test_nessun_codice_aumentato_restituisce_none(self):
        prima = {"abc123": 5}
        dopo = {"abc123": 5}
        assert diff_invite_uses(prima, dopo) is None

    def test_piu_codici_aumentati_e_ambiguo_restituisce_none(self):
        prima = {"abc123": 5, "xyz789": 2}
        dopo = {"abc123": 6, "xyz789": 3}
        assert diff_invite_uses(prima, dopo) is None

    def test_codice_nuovo_non_presente_prima_viene_ignorato(self):
        # Creato e usato tra un fetch e l'altro: trattato come
        # indeterminato per cautela, non assunto come "quello giusto".
        prima = {"abc123": 5}
        dopo = {"abc123": 5, "nuovo000": 1}
        assert diff_invite_uses(prima, dopo) is None

    def test_dizionari_vuoti(self):
        assert diff_invite_uses({}, {}) is None

"""
tests/test_server_stats_logic.py
====================================
Test di core/server_stats_logic.py — logica pura.
"""

from datetime import date, datetime, timezone

from core.server_stats_logic import compute_daily_net_change, fill_missing_days


class TestComputeDailyNetChange:
    def test_un_solo_join(self):
        eventi = [(datetime(2026, 1, 1, tzinfo=timezone.utc), "member_join")]
        assert compute_daily_net_change(eventi) == {date(2026, 1, 1): 1}

    def test_un_solo_leave(self):
        eventi = [(datetime(2026, 1, 1, tzinfo=timezone.utc), "member_remove")]
        assert compute_daily_net_change(eventi) == {date(2026, 1, 1): -1}

    def test_join_e_leave_nello_stesso_giorno_si_bilanciano(self):
        eventi = [
            (datetime(2026, 1, 1, 8, tzinfo=timezone.utc), "member_join"),
            (datetime(2026, 1, 1, 20, tzinfo=timezone.utc), "member_remove"),
        ]
        assert compute_daily_net_change(eventi) == {date(2026, 1, 1): 0}

    def test_piu_join_dello_stesso_giorno_si_sommano(self):
        eventi = [
            (datetime(2026, 1, 1, 1, tzinfo=timezone.utc), "member_join"),
            (datetime(2026, 1, 1, 2, tzinfo=timezone.utc), "member_join"),
            (datetime(2026, 1, 1, 3, tzinfo=timezone.utc), "member_join"),
        ]
        assert compute_daily_net_change(eventi) == {date(2026, 1, 1): 3}

    def test_giorni_diversi_restano_separati(self):
        eventi = [
            (datetime(2026, 1, 1, tzinfo=timezone.utc), "member_join"),
            (datetime(2026, 1, 2, tzinfo=timezone.utc), "member_join"),
        ]
        assert compute_daily_net_change(eventi) == {
            date(2026, 1, 1): 1,
            date(2026, 1, 2): 1,
        }

    def test_tipi_evento_estranei_vengono_ignorati(self):
        eventi = [
            (datetime(2026, 1, 1, tzinfo=timezone.utc), "member_join"),
            (datetime(2026, 1, 1, tzinfo=timezone.utc), "role_update"),
            (datetime(2026, 1, 1, tzinfo=timezone.utc), "nickname_update"),
        ]
        assert compute_daily_net_change(eventi) == {date(2026, 1, 1): 1}

    def test_lista_vuota(self):
        assert compute_daily_net_change([]) == {}


class TestFillMissingDays:
    def test_riempie_i_giorni_mancanti_con_zero(self):
        risultato = fill_missing_days(
            {date(2026, 1, 1): 5}, start=date(2026, 1, 1), end=date(2026, 1, 3)
        )
        assert risultato == {
            date(2026, 1, 1): 5,
            date(2026, 1, 2): 0,
            date(2026, 1, 3): 0,
        }

    def test_non_altera_i_giorni_gia_presenti(self):
        risultato = fill_missing_days(
            {date(2026, 1, 1): 5, date(2026, 1, 2): -3},
            start=date(2026, 1, 1),
            end=date(2026, 1, 2),
        )
        assert risultato[date(2026, 1, 1)] == 5
        assert risultato[date(2026, 1, 2)] == -3

    def test_intervallo_di_un_solo_giorno(self):
        risultato = fill_missing_days({}, start=date(2026, 1, 1), end=date(2026, 1, 1))
        assert risultato == {date(2026, 1, 1): 0}

    def test_dizionario_vuoto_in_ingresso(self):
        risultato = fill_missing_days({}, start=date(2026, 1, 1), end=date(2026, 1, 3))
        assert risultato == {
            date(2026, 1, 1): 0,
            date(2026, 1, 2): 0,
            date(2026, 1, 3): 0,
        }

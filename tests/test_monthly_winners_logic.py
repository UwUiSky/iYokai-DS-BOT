"""
tests/test_monthly_winners_logic.py
=======================================
Test di core/monthly_winners_logic.py — logica pura.
"""

from datetime import datetime, timezone

from core.monthly_winners_logic import (
    build_announcement_text,
    format_period_label,
    format_podium,
    previous_period_key,
    should_announce,
)


def _t(anno, mese, giorno=1, ora=0):
    return datetime(anno, mese, giorno, ora, tzinfo=timezone.utc)


class TestPreviousPeriodKey:
    def test_mese_normale(self):
        assert previous_period_key(_t(2026, 9, 15)) == "2026-08"

    def test_passaggio_d_anno(self):
        assert previous_period_key(_t(2027, 1, 1)) == "2026-12"

    def test_primo_giorno_del_mese_a_mezzanotte(self):
        assert previous_period_key(_t(2026, 10, 1, 0)) == "2026-09"


class TestShouldAnnounce:
    def test_mai_annunciato_nulla(self):
        assert should_announce(None, _t(2026, 10, 1)) is True

    def test_mese_precedente_gia_annunciato(self):
        assert should_announce("2026-09", _t(2026, 10, 1)) is False

    def test_un_mese_vecchio_annunciato_ma_non_l_ultimo(self):
        assert should_announce("2026-08", _t(2026, 10, 1)) is True

    def test_piu_tick_nello_stesso_mese_non_ripetono(self):
        # Dopo il primo annuncio di ottobre (per settembre), tutti i
        # tick successivi di ottobre non devono annunciare di nuovo.
        assert should_announce("2026-09", _t(2026, 10, 20)) is False


class TestFormatPeriodLabel:
    def test_settembre(self):
        assert format_period_label("2026-09") == "settembre 2026"

    def test_dicembre(self):
        assert format_period_label("2026-12") == "dicembre 2026"


class TestFormatPodium:
    def test_podio_completo_con_medaglie(self):
        testo = format_podium([(1, 500), (2, 300), (3, 100)], "XP")
        assert "🥇 <@1> — **500** XP" in testo
        assert "🥈 <@2>" in testo
        assert "🥉 <@3>" in testo

    def test_oltre_tre_voci_mostra_solo_il_podio(self):
        testo = format_podium([(i, 100 - i) for i in range(1, 8)], "XP")
        assert "<@4>" not in testo

    def test_meno_di_tre_partecipanti(self):
        testo = format_podium([(1, 50)], "coin")
        assert "🥇 <@1> — **50** coin" in testo
        assert "🥈" not in testo

    def test_nessuna_attivita_testo_esplicito(self):
        assert "Nessuna attività" in format_podium([], "XP")


def test_build_announcement_text():
    titolo, podio_xp, podio_coin = build_announcement_text(
        "2026-09", [(1, 500)], [(2, 90)]
    )
    assert titolo == "🏆 Vincitori di settembre 2026"
    assert "<@1>" in podio_xp
    assert "<@2>" in podio_coin

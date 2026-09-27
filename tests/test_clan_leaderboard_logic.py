"""
tests/test_clan_leaderboard_logic.py
========================================
Test di core/clan_leaderboard_logic.py — logica pura.
previous_period_key/should_announce/format_period_label sono già
testati in tests/test_monthly_winners_logic.py (funzioni condivise,
non duplicate qui) — qui solo il testo del podio specifico dei clan.
"""

from core.clan_leaderboard_logic import (
    build_clan_announcement_text,
    format_clan_podium,
)


class TestFormatClanPodium:
    def test_podio_completo_con_medaglie(self):
        testo = format_clan_podium([("ABC", "I Guerrieri", 9000), ("XYZ", "I Draghi", 4000), ("QWE", "Gli Orsi", 100)])
        assert "🥇 **[ABC] I Guerrieri** — **9000** XP" in testo
        assert "🥈 **[XYZ] I Draghi**" in testo
        assert "🥉 **[QWE] Gli Orsi**" in testo

    def test_oltre_tre_voci_mostra_solo_il_podio(self):
        testo = format_clan_podium([(f"C{i}", f"Clan {i}", 100 - i) for i in range(1, 8)])
        assert "Clan 4" not in testo

    def test_meno_di_tre_partecipanti(self):
        testo = format_clan_podium([("ABC", "Solo Uno", 50)])
        assert "🥇 **[ABC] Solo Uno** — **50** XP" in testo
        assert "🥈" not in testo

    def test_nessuna_attivita_testo_esplicito(self):
        assert "Nessuna gilda" in format_clan_podium([])


def test_build_clan_announcement_text():
    titolo, podio = build_clan_announcement_text("2026-09", [("ABC", "I Guerrieri", 9000)])
    assert titolo == "🏆 Top 3 gilde di settembre 2026"
    assert "[ABC] I Guerrieri" in podio

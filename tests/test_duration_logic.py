"""
tests/test_duration_logic.py
================================
Test di parse_duration() (core/duration_logic.py). Logica pura,
nessuna dipendenza da Discord o dal database — si testa in isolamento
come core/permissions.py. Spostato qui da cogs/moderation/_shared.py
quando è arrivato un secondo consumatore reale (cogs/utility/
reminders.py) — vedi core/duration_logic.py per il motivo.
"""

import pytest

from core.duration_logic import MAX_DURATION_SECONDS, parse_duration


class TestParseDuration:
    @pytest.mark.parametrize(
        "testo,attesi_secondi",
        [
            ("30s", 30),
            ("1s", 1),
            ("45m", 45 * 60),
            ("1m", 60),
            ("12h", 12 * 3600),
            ("1h", 3600),
            ("7d", 7 * 86400),
            ("1d", 86400),
            ("2w", 2 * 604800),
            ("1w", 604800),
        ],
    )
    def test_conversioni_corrette(self, testo, attesi_secondi):
        assert parse_duration(testo) == attesi_secondi

    def test_case_insensitive(self):
        assert parse_duration("7D") == parse_duration("7d")
        assert parse_duration("12H") == parse_duration("12h")

    def test_spazi_vengono_ignorati(self):
        assert parse_duration("  7d  ") == parse_duration("7d")

    @pytest.mark.parametrize(
        "testo_invalido",
        [
            "",
            "7",           # manca l'unità
            "d",           # manca il numero
            "7x",          # unità sconosciuta
            "-7d",         # numero negativo
            "0d",          # zero non è una durata valida
            "7.5d",        # decimali non supportati
            "1h30m",       # combinazioni non supportate
            "settegiorni",
        ],
    )
    def test_formati_invalidi_sollevano_errore_chiaro(self, testo_invalido):
        with pytest.raises(ValueError):
            parse_duration(testo_invalido)

    @pytest.mark.parametrize("testo", ["9999999999w", "261w", "1826d", "999999999999999999999s"])
    def test_oltre_il_tetto_di_cinque_anni_viene_rifiutata(self, testo):
        """
        Una durata enorme farebbe saltare il calcolo della data di
        scadenza (OverflowError) o darebbe un ban "a tempo" di secoli.
        """
        with pytest.raises(ValueError, match="5 anni"):
            parse_duration(testo)

    def test_cinque_anni_esatti_sono_ammessi(self):
        assert parse_duration("1825d") == MAX_DURATION_SECONDS
        assert parse_duration("260w") < MAX_DURATION_SECONDS

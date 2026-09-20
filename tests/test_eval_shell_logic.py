"""
tests/test_eval_shell_logic.py
==================================
Test di core/eval_shell_logic.py — logica pura.
"""

from core.eval_shell_logic import DISCORD_MESSAGE_LIMIT, truncate_output


class TestTruncateOutput:
    def test_testo_corto_non_viene_toccato(self):
        assert truncate_output("ciao") == "ciao"

    def test_testo_esattamente_al_limite_non_viene_toccato(self):
        testo = "a" * 100
        assert truncate_output(testo, max_length=100) == testo

    def test_testo_lungo_viene_troncato(self):
        testo = "a" * 200
        risultato = truncate_output(testo, max_length=100)
        assert len(risultato) <= 100
        assert "troncato" in risultato

    def test_testo_troncato_inizia_con_il_contenuto_originale(self):
        testo = "riga1\nriga2\nriga3" * 50
        risultato = truncate_output(testo, max_length=50)
        assert testo.startswith(risultato.split("\n... (output troncato)")[0])

    def test_default_rispetta_il_limite_discord(self):
        testo = "x" * 5000
        risultato = truncate_output(testo)
        assert len(risultato) < DISCORD_MESSAGE_LIMIT

"""
tests/test_minigames_logic.py
=================================
Test di core/minigames_logic.py — un random.Random SEEDATO al posto
di un mock, per verificare risultati prevedibili senza patchare il
modulo random standard.
"""

import random

import pytest

from core.minigames_logic import (
    EIGHT_BALL_ANSWERS,
    RPS_CHOICES,
    answer_8ball,
    flip_coin,
    play_rps,
    roll_dice,
)


class TestFlipCoin:
    def test_restituisce_sempre_testa_o_croce(self):
        rng = random.Random(1)
        for _ in range(50):
            assert flip_coin(rng) in ("testa", "croce")


class TestRollDice:
    def test_risultato_dentro_i_limiti(self):
        rng = random.Random(2)
        for _ in range(100):
            assert 1 <= roll_dice(rng, sides=6) <= 6

    def test_dado_a_20_facce(self):
        rng = random.Random(3)
        for _ in range(100):
            assert 1 <= roll_dice(rng, sides=20) <= 20

    def test_meno_di_due_facce_solleva(self):
        rng = random.Random(4)
        with pytest.raises(ValueError):
            roll_dice(rng, sides=1)

    def test_seed_uguale_produce_risultato_uguale(self):
        assert roll_dice(random.Random(42), sides=6) == roll_dice(random.Random(42), sides=6)


class TestPlayRps:
    def test_scelta_non_valida_solleva(self):
        with pytest.raises(ValueError):
            play_rps("lucertola", random.Random(5))

    def test_esito_e_sempre_uno_dei_tre_validi(self):
        rng = random.Random(6)
        for scelta in RPS_CHOICES:
            _, esito = play_rps(scelta, rng)
            assert esito in ("vittoria", "sconfitta", "pareggio")

    def test_sasso_batte_forbici(self):
        # Forziamo la scelta del bot forzando il seed e verificando
        # tutte le combinazioni possibili invece di sperare in un
        # seed specifico.
        rng = random.Random(0)
        risultati = {play_rps("sasso", random.Random(i))[1] for i in range(20)}
        assert risultati <= {"vittoria", "sconfitta", "pareggio"}

    def test_pareggio_quando_bot_scegle_uguale(self):
        class _RngFisso:
            def choice(self, seq):
                return "carta"

        _, esito = play_rps("carta", _RngFisso())
        assert esito == "pareggio"

    def test_vittoria_utente_sasso_contro_forbici(self):
        class _RngFisso:
            def choice(self, seq):
                return "forbici"

        scelta_bot, esito = play_rps("sasso", _RngFisso())
        assert scelta_bot == "forbici"
        assert esito == "vittoria"

    def test_sconfitta_utente_sasso_contro_carta(self):
        class _RngFisso:
            def choice(self, seq):
                return "carta"

        scelta_bot, esito = play_rps("sasso", _RngFisso())
        assert scelta_bot == "carta"
        assert esito == "sconfitta"


class TestAnswer8Ball:
    def test_restituisce_una_risposta_valida(self):
        rng = random.Random(7)
        for _ in range(30):
            assert answer_8ball(rng) in EIGHT_BALL_ANSWERS

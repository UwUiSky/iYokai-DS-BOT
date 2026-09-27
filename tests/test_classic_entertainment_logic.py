"""
tests/test_classic_entertainment_logic.py
==============================================
Test di core/classic_entertainment_logic.py — logica pura.
"""

import random

from core.classic_entertainment_logic import (
    FACTS,
    JOKES,
    QUOTES,
    random_fact,
    random_joke,
    random_quote,
)


def test_random_joke_restituisce_una_barzelletta_valida():
    rng = random.Random(1)
    for _ in range(20):
        assert random_joke(rng) in JOKES


def test_random_quote_restituisce_una_citazione_valida():
    rng = random.Random(2)
    for _ in range(20):
        assert random_quote(rng) in QUOTES


def test_random_fact_restituisce_una_curiosita_valida():
    rng = random.Random(3)
    for _ in range(20):
        assert random_fact(rng) in FACTS


def test_le_liste_non_sono_vuote():
    assert len(JOKES) > 0
    assert len(QUOTES) > 0
    assert len(FACTS) > 0

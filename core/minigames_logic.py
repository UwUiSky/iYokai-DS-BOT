"""
core/minigames_logic.py
===========================
Logica pura dei mini-giochi (SPEC.md §16.1): testa/croce, dado, carta/
forbice/sasso, palla magica 8. A differenza di core/fun_logic.py
(Ship/Rate, deterministici via hash — stessa coppia/stesso testo
danno sempre lo stesso risultato), qui il risultato DEVE essere
genuinamente casuale ad ogni chiamata: è il punto di un mini-gioco.

Ogni funzione accetta un `random.Random` già istanziato dal
chiamante (mai `random` globale usato direttamente qui dentro) — così
i test possono passare un generatore SEEDATO e verificare un
risultato prevedibile, senza mai patchare il modulo `random`
standard.
"""

from __future__ import annotations

import random

RPS_CHOICES = ("sasso", "carta", "forbici")

# sasso batte forbici, forbici batte carta, carta batte sasso
_RPS_BEATS = {"sasso": "forbici", "forbici": "carta", "carta": "sasso"}

EIGHT_BALL_ANSWERS = (
    "Sì, decisamente.",
    "È certo.",
    "Senza alcun dubbio.",
    "Sì.",
    "Molto probabile.",
    "Le prospettive sono buone.",
    "Probabilmente sì.",
    "Non ci conterei.",
    "La mia risposta è no.",
    "Le mie fonti dicono di no.",
    "Prospettive non molto buone.",
    "Molto dubbio.",
    "Chiedi di nuovo più tardi.",
    "Meglio non dirtelo ora.",
    "Non posso prevederlo ora.",
    "Concentrati e richiedi.",
)


def flip_coin(rng: random.Random) -> str:
    """'testa' o 'croce', 50/50."""
    return rng.choice(("testa", "croce"))


def roll_dice(rng: random.Random, sides: int = 6) -> int:
    """Un tiro tra 1 e `sides` incluso. `sides` < 2 non ha senso per
    un dado (nessuna scelta possibile) — il chiamante valida prima
    di arrivare qui, questa funzione si fida dell'input."""
    if sides < 2:
        raise ValueError("Un dado deve avere almeno 2 facce.")
    return rng.randint(1, sides)


def play_rps(user_choice: str, rng: random.Random) -> tuple[str, str]:
    """
    Restituisce (scelta_del_bot, esito) dove esito è "vittoria",
    "sconfitta" o "pareggio" dal punto di vista dell'utente.
    `user_choice` deve già essere una delle RPS_CHOICES normalizzate
    (minuscolo, senza spazi) — il chiamante valida l'input libero.
    """
    if user_choice not in RPS_CHOICES:
        raise ValueError(f"Scelta non valida: {user_choice!r}")

    scelta_bot = rng.choice(RPS_CHOICES)
    if scelta_bot == user_choice:
        return scelta_bot, "pareggio"
    if _RPS_BEATS[user_choice] == scelta_bot:
        return scelta_bot, "vittoria"
    return scelta_bot, "sconfitta"


def answer_8ball(rng: random.Random) -> str:
    """La domanda stessa non influenza la risposta (è per questo che
    non la prende come parametro) — la palla magica 8 risponde a
    caso, non "capisce" la domanda, esattamente come il giocattolo
    originale."""
    return rng.choice(EIGHT_BALL_ANSWERS)

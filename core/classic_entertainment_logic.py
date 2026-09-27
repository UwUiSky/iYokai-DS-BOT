"""
core/classic_entertainment_logic.py
=======================================
Logica pura di "altri comandi di intrattenimento classici" (SPEC.md
§16.8): barzelletta, citazione, curiosità casuali. Liste curate a
mano, incorporate qui — nessuna chiamata di rete per questi tre
comandi: a differenza di §16.4 (comandi animal, che hanno bisogno di
immagini vere da un'API) e §16.9 (ricerca immagini), qui il
contenuto è testuale e non ha bisogno di essere "fresco" ogni volta,
quindi una lista locale è la scelta più semplice che funzioni davvero
senza dipendenze esterne o chiavi API.
"""

from __future__ import annotations

import random

JOKES = (
    "Perché i programmatori confondono Halloween e Natale? Perché OCT 31 == DEC 25.",
    "Un byte entra in un bar. Il barista gli chiede: \"Tutto bene?\" — \"Un po' bit-uto.\"",
    "Ci sono 10 tipi di persone al mondo: chi capisce il binario e chi no.",
    "Perché gli sviluppatori preferiscono la modalità scura? Perché la luce attira i bug.",
    "Un SQL entra in un bar, vede due tavoli e chiede: \"Posso fare un JOIN?\"",
    "Ho scritto un programma che conta all'infinito. Sto ancora aspettando i risultati.",
    "\"Funziona sul mio computer\" — ultime parole famose prima del deploy in produzione.",
)

QUOTES = (
    "\"La semplicità è la sofisticazione suprema.\" — Leonardo da Vinci",
    "\"Il futuro appartiene a chi crede nella bellezza dei propri sogni.\" — Eleanor Roosevelt",
    "\"Non è la specie più forte a sopravvivere, ma quella più adattabile.\" — Charles Darwin",
    "\"Ciò che non ci uccide ci rende più forti.\" — Friedrich Nietzsche",
    "\"L'unico modo per fare un ottimo lavoro è amare quello che fai.\" — Steve Jobs",
    "\"La vita è quello che ci accade mentre siamo occupati a fare altri progetti.\" — John Lennon",
)

FACTS = (
    "Il miele non scade mai, se conservato correttamente: sono stati trovati vasetti di miele "
    "commestibile nelle tombe egizie.",
    "Un fulmine è più caldo della superficie del Sole per una frazione di secondo.",
    "I polpi hanno tre cuori e il sangue blu.",
    "Le impronte digitali dei koala sono così simili a quelle umane che possono contaminare "
    "una scena del crimine.",
    "Venere è il pianeta più caldo del sistema solare, non Mercurio, nonostante sia più lontano "
    "dal Sole.",
    "Un giorno su Venere (una rotazione completa) dura più di un anno venusiano.",
)


def random_joke(rng: random.Random) -> str:
    return rng.choice(JOKES)


def random_quote(rng: random.Random) -> str:
    return rng.choice(QUOTES)


def random_fact(rng: random.Random) -> str:
    return rng.choice(FACTS)

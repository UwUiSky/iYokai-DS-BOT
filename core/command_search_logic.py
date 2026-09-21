"""
core/command_search_logic.py
================================
Logica pura di /search (nessuna infrastruttura di embedding/NLP
disponibile in questo progetto): punteggio per sovrapposizione di
parole tra la query e nome+descrizione di ogni comando, con un bonus
se la query intera compare come sottostringa. Semplice ma sufficiente
per query in linguaggio naturale corte tipiche di un comando slash
("banna qualcuno", "crea un sondaggio").
"""

from __future__ import annotations

import re


STOPWORD_ITALIANE = frozenset(
    {
        "il", "lo", "la", "i", "gli", "le", "un", "uno", "una",
        "di", "a", "da", "in", "con", "su", "per", "tra", "fra",
        "e", "o", "ma", "che", "non", "si", "mi", "ti", "ci", "vi",
        "io", "tu", "lui", "lei", "noi", "voi", "loro",
        "voglio", "vorrei", "puoi", "potresti", "come", "cosa",
        "qualcuno", "qualcosa", "quale", "questo", "questa",
        "favore", "grazie", "per favore",
    }
)


def _tokenizza(testo: str) -> set[str]:
    parole = set(re.findall(r"[a-zàèéìòù0-9]+", testo.lower()))
    return parole - STOPWORD_ITALIANE


def _condividono_radice(parola_a: str, parola_b: str, prefisso_minimo: int = 4) -> bool:
    """
    Confronto per prefisso condiviso — non uno stemmer vero, ma
    sufficiente a far combaciare forme verbali italiane comuni della
    stessa radice ("bannare" vs "banna", "silenzia" vs "silenziare")
    senza aggiungere una libreria di NLP per un progetto che non ne
    ha altrimenti bisogno. Trovato necessario scrivendo il test: una
    query naturale come "voglio bannare qualcuno" non condivideva
    NESSUN token esatto con "banna" (comando) — il confronto per
    insieme di parole da solo non basta per l'italiano coniugato.
    """
    lunghezza_comune = min(len(parola_a), len(parola_b))
    if lunghezza_comune < prefisso_minimo:
        return parola_a == parola_b
    return parola_a[:prefisso_minimo] == parola_b[:prefisso_minimo]


def score_command(query: str, name: str, description: str) -> float:
    """
    Punteggio di rilevanza — non normalizzato a [0, 1] in modo
    rigoroso (il bonus sottostringa può farlo superare 1), pensato
    solo per ORDINARE i risultati e per un confronto con una soglia
    minima, non come probabilità.
    """
    parole_query = _tokenizza(query)
    if not parole_query:
        return 0.0

    testo_comando = f"{name} {description}"
    parole_comando = _tokenizza(testo_comando)

    corrispondenze = 0.0
    for parola in parole_query:
        if parola in parole_comando:
            corrispondenze += 1.0
        elif any(_condividono_radice(parola, pc) for pc in parole_comando):
            corrispondenze += 0.7  # radice condivisa, non un match esatto

    punteggio = corrispondenze / len(parole_query)

    if query.strip().lower() in testo_comando.lower():
        punteggio += 0.5

    return punteggio


def search_commands(
    query: str,
    commands: list[tuple[str, str]],
    threshold: float = 0.34,
    limit: int = 3,
) -> list[tuple[str, str, float]]:
    """
    commands è una lista di (nome, descrizione). Restituisce i
    migliori risultati SOPRA la soglia, ordinati per punteggio
    decrescente — una soglia troppo bassa restituirebbe risultati
    non pertinenti quanto quello vero, una troppo alta perderebbe
    corrispondenze legittime con parole diverse ma sinonimiche
    (limite intrinseco di un punteggio per sovrapposizione di parole,
    non un vero motore semantico).
    """
    risultati = [
        (nome, descrizione, score_command(query, nome, descrizione))
        for nome, descrizione in commands
    ]
    risultati = [r for r in risultati if r[2] >= threshold]
    risultati.sort(key=lambda r: r[2], reverse=True)
    return risultati[:limit]

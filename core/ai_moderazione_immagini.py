"""
core/ai_moderazione_immagini.py
===============================
Moderazione delle immagini tramite lo snodo AI (FUN-017, D122): legge la risposta di un fornitore di moderazione
(formato `/moderations` compatibile OpenAI, categorie e punteggi) e dice solo se l'immagine è per adulti.
Funzioni pure. Il tipo di lavoro dello snodo è `moderazione_immagine`: lo fa solo un fornitore che lo dichiara in
`AI_TIPI_<NOME>`; senza fornitore il controllo non c'è (il chiamante decide che cosa fare, D123).
Funzioni coperte: SPEC §24 (FUN-017, D122)
"""

from __future__ import annotations

TIPO = "moderazione_immagine"
SOGLIA_ADULTI = 0.5  # punteggio da cui «sexual» conta come per adulti, anche se il fornitore non l'ha segnalata
SOGLIA_MINORI = 0.2  # più bassa: su «sexual/minors» si preferisce rifiutare


def e_per_adulti(risposta: dict) -> bool:
    """True se la risposta segnala contenuti sessuali. Risposta illeggibile: solleva ValueError (il chiamante tratta come «non so»)."""
    try:
        r = risposta["results"][0]
        categorie = r.get("categories") or {}
        punti = r.get("category_scores") or {}
        if not isinstance(categorie, dict) or not isinstance(punti, dict):
            raise TypeError
        return bool(
            categorie.get("sexual") or categorie.get("sexual/minors")
            or float(punti.get("sexual", 0) or 0) >= SOGLIA_ADULTI
            or float(punti.get("sexual/minors", 0) or 0) >= SOGLIA_MINORI
        )
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise ValueError("risposta di moderazione illeggibile") from exc

"""
core/template_renderer.py
==========================
Sostituzione sicura di placeholder `{nome}` in template personalizzati
dall'utente (alert RSS, webhook custom). NON usa `str.format`: un
template come `{title:>999999999}` con `str.format` alloca centinaia
di MB/GB di RAM e può far crollare l'intero processo (bot principale
e worker musicali insieme).
Funzioni coperte: SPEC §10.9 (SEC-6)
"""

from __future__ import annotations

import re

MAX_OUTPUT_LENGTH = 2000

# Solo `{nome}` con lettere minuscole e underscore — niente format
# spec (`:...`), niente indici posizionali, niente attributi/item
# lookup (`{obj.attr}`, `{lista[0]}`): quella sintassi appartiene a
# str.format e non deve mai essere valutata su testo scelto da un
# utente esterno.
_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")


def render_template(testo: str, valori: dict[str, str]) -> str:
    """
    Sostituisce ogni `{nome}` presente in `valori` col suo valore.
    Un placeholder sconosciuto (typo dell'utente, es. `{titolo}`
    invece di `{title}`) resta scritto com'era, così l'utente lo nota
    e lo corregge — non è un errore. Una `{` spaiata non è
    un'eccezione: il regex semplicemente non la trova come
    placeholder e la lascia intatta. Il risultato è troncato a
    MAX_OUTPUT_LENGTH caratteri, indipendentemente da quanto grandi
    sono i valori sostituiti.
    """

    def _sostituisci(match: re.Match[str]) -> str:
        nome = match.group(1)
        if nome in valori:
            return str(valori[nome])
        return match.group(0)

    risultato = _PLACEHOLDER_RE.sub(_sostituisci, testo)
    return risultato[:MAX_OUTPUT_LENGTH]

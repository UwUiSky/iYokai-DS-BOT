"""
core/fun_logic.py
====================
Logica pura di Ship (SPEC.md §16.5), Rate (§16.7) e Misura (§23.16, NF-40). Deterministica
via hash, non random.randint() ad ogni chiamata — stessa coppia di
utenti o stesso testo devono dare sempre lo stesso risultato,
altrimenti /fun ship @a @b darebbe un numero diverso ogni volta che
qualcuno lo richiama, che sembra un bug più che una feature scherzosa
(la gente si aspetta un risultato "loro", stabile, non un dado).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date


def compute_ship_percentage(user_id_a: int, user_id_b: int) -> int:
    """
    0-100, simmetrico: ship(a, b) == ship(b, a), perché l'ordine in
    cui i due utenti vengono menzionati nel comando non deve cambiare
    il risultato — ordiniamo gli ID prima di calcolare l'hash.
    """
    a, b = sorted((user_id_a, user_id_b))
    chiave = f"{a}-{b}".encode("utf-8")
    hash_bytes = hashlib.sha256(chiave).digest()
    return hash_bytes[0] % 101


def ship_flavor_text(percentage: int) -> str:
    if percentage >= 90:
        return "Anime gemelle. 💍"
    if percentage >= 70:
        return "C'è del potenziale! 💕"
    if percentage >= 40:
        return "Potrebbe funzionare... o no. 🤔"
    if percentage >= 15:
        return "Meglio restare amici. 😅"
    return "Acqua e olio. 🧊"


def compute_rate_score(text: str) -> int:
    """0-10, deterministico sul testo normalizzato (spazi ai bordi e
    maiuscole/minuscole non devono cambiare il voto di "Pizza" contro
    " pizza ")."""
    chiave = text.strip().lower().encode("utf-8")
    hash_bytes = hashlib.sha256(chiave).digest()
    return hash_bytes[0] % 11


def rate_flavor_text(score: int) -> str:
    if score >= 9:
        return "Perfezione assoluta. 🌟"
    if score >= 7:
        return "Niente male! 👍"
    if score >= 4:
        return "Nella media. 🤷"
    if score >= 1:
        return "Si può migliorare. 😬"
    return "Un disastro totale. 💀"


# ----------------------------------------------------------------------
# Misura (NF-40): misuratore a tema libero, alternativa neutra a SPEC §16.6.
# ----------------------------------------------------------------------
MAX_TEMA_MISURA = 60

# Parole che indicano caratteristiche protette (orientamento, origine, religione,
# salute, disabilità, politica…): un misuratore non le giudica. Ogni modello
# vale da INIZIO di parola (così "celebrare" non contiene "ebre"); chi non deve
# avere desinenze lunghe ha la parola intera.
_PAROLE_VIETATE = re.compile(
    r"\b(?:"
    r"gays?|lesb\w*|omosess\w*|eterosess\w*|bisess\w*|transess\w*|transgender\w*|trans|"
    r"queer|lgbt\w*|razz[ae]|razzial\w*|razzis\w*|etnia|etnie|etnic\w*|neg(?:ro|ri|ra|re)|"
    r"religio\w*|musulman\w*|islam\w*|ebre[oaie]|ebraic\w*|cristian\w*|cattolic\w*|"
    r"ate(?:o|i|a|e|ism\w*|ist\w*)|buddis\w*|indu|induism\w*|induist\w*|"
    r"disabil\w*|handicap\w*|autis\w*|malat\w*|depress\w*|tumor\w*|cancro|"
    r"immigrat\w*|stranier\w*|nazional\w*|politic\w*|comunist\w*|fascist\w*|"
    r"sessualit\w*|orientamento|"
    r"race|races|racial|racism|racist|ethnic\w*|religion\w*|muslim\w*|jewish|christian\w*|"
    r"disabled|sexuality|straight"
    r")\b"
)

# Lettere di altri alfabeti che a occhio sono latine: senza questa tabella
# "gаy" (con la a cirillica) passerebbe il filtro.
_SOMIGLIANTI = str.maketrans(
    {
        "а": "a", "в": "b", "е": "e", "ё": "e", "й": "i", "к": "k", "м": "m",
        "н": "h", "о": "o", "р": "p", "с": "c", "т": "t", "у": "y", "х": "x", "і": "i", "ї": "i",
        "ј": "j", "ѕ": "s", "ԁ": "d", "ɡ": "g", "ɑ": "a",
        "α": "a", "β": "b", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "τ": "t",
        "υ": "y", "χ": "x", "η": "n",
    }
)


def _normalizza_per_filtro(tema: str) -> str:
    """
    Il tema com'è visto dal filtro: senza accenti, maiuscole, caratteri invisibili
    o decorazioni; lettere cirilliche/greche simili a quelle latine rese latine;
    la punteggiatura come spazio; le lettere staccate ("g a y", "g.a.y") riunite.
    """
    testo = unicodedata.normalize("NFKC", tema).lower().translate(_SOMIGLIANTI)
    testo = unicodedata.normalize("NFKD", testo)
    testo = "".join(c for c in testo if unicodedata.category(c) not in ("Mn", "Cf"))
    testo = re.sub(r"[^a-z0-9]+", " ", testo.encode("ascii", "ignore").decode("ascii")).strip()
    # Una fila di lettere singole (almeno tre) è una parola scritta a pezzi.
    return re.sub(r"\b(?:[a-z] ){2,}[a-z]\b", lambda m: m.group(0).replace(" ", ""), testo)


def _normalizza_tema(tema: str) -> str:
    senza_accenti = unicodedata.normalize("NFKD", tema).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", senza_accenti).strip().lower()


def tema_ammesso(tema: str) -> bool:
    """Vero se il tema non è vuoto e non misura una caratteristica protetta."""
    normale = _normalizza_per_filtro(tema)
    if not normale:
        return False
    return _PAROLE_VIETATE.search(normale) is None


def compute_misura(user_id: int, tema: str, giorno: date) -> int:
    """
    0-100, stabile per la stessa persona, lo stesso tema e lo stesso giorno
    (domani il risultato cambia). Maiuscole e spazi nel tema non contano.
    """
    chiave = f"{user_id}|{_normalizza_tema(tema)}|{giorno.isoformat()}".encode("utf-8")
    return hashlib.sha256(chiave).digest()[0] % 101

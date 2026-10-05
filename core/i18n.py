"""
core/i18n.py
===============
SPEC.md §2.3 (Lingua per server) — INFRASTRUTTURA minima, non un
sistema i18n applicato a tutto il bot. Onestamente: la stragrande
maggioranza dei messaggi del progetto resta scritta in italiano nei
singoli cog, come da disciplina di questa sessione. Questo modulo
esiste per dare a `db.get_guild_language()`/`set_guild_language()`
(vedi core/database.py) un consumatore REALE — non infrastruttura
"pronta ma inutilizzata" — su un piccolo insieme di stringhe generiche
condivise, non su ogni singolo comando.

Se/quando un futuro passaggio deciderà di tradurre il bot per intero,
questo dizionario è il punto da estendere: `t(key, language)` più
chiavi, non un'architettura diversa.
"""

# DA FARE (issue #77, fase F8): NF-06, Lingue italiano e inglese, e
#   `/utility cerca-comando`. Vedi revisione/02-piano/NUOVE_FUNZIONI.md.

from __future__ import annotations

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "module_not_active": {
        "it": "Questo modulo non è attivo su questo server.",
        "en": "This module is not active on this server.",
    },
    "guild_only_command": {
        "it": "Questo comando è disponibile solo dentro un server.",
        "en": "This command is only available inside a server.",
    },
    "admin_only": {
        "it": "Solo un amministratore può usare questo comando.",
        "en": "Only an administrator can use this command.",
    },
    "operation_cancelled": {
        "it": "Operazione annullata.",
        "en": "Operation cancelled.",
    },
}

DEFAULT_LANGUAGE = "it"


def t(key: str, language: str) -> str:
    """
    Restituisce la traduzione di `key` nella lingua richiesta, con
    fallback all'italiano se la lingua non è supportata o la chiave
    non ha una traduzione per quella lingua, e la chiave stessa come
    ultimo fallback (mai un KeyError per un typo su una chiave).
    """
    voce = _TRANSLATIONS.get(key)
    if voce is None:
        return key
    return voce.get(language, voce.get(DEFAULT_LANGUAGE, key))

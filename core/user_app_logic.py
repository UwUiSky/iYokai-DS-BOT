"""
core/user_app_logic.py
======================
Logica di iYokai App (NF-36), l'applicazione che l'utente installa su di
sé: testo pulito di un messaggio (A11) e promemoria personali.
Funzioni semplici, senza Discord.
Funzioni coperte: SPEC §B (NF-36)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MAX_RISPOSTA = 2000
# Parametri che servono solo a tracciare chi apre il link.
_TRACCIAMENTO = re.compile(
    r"^(utm_\w+|fbclid|gclid|dclid|msclkid|igshid|igsh|si|mc_cid|mc_eid|ref_src|ref_url|_hsenc|_hsmi|yclid|twclid)$",
    re.IGNORECASE,
)
_URL = re.compile(r"https?://[^\s<>()\[\]]+")
_FORMATTAZIONE = (
    (re.compile(r"```[a-zA-Z0-9_+-]*\n?"), ""),  # blocchi di codice
    (re.compile(r"\|\|(.+?)\|\|", re.S), r"\1"),  # spoiler
    (re.compile(r"(\*\*\*|\*\*|__|\*|_|~~|`)(.+?)\1", re.S), r"\2"),  # grassetto, corsivo, barrato, codice
    (re.compile(r"^\s{0,3}(#{1,3}|-#|>>>|>)\s+", re.M), ""),  # titoli, sottotesto, citazioni
)


def pulisci_link(url: str) -> str:
    """Toglie da un link i parametri di tracciamento; il resto resta com'è."""
    parti = urlsplit(url)
    if not parti.query:
        return url
    tenuti = [(k, v) for k, v in parse_qsl(parti.query, keep_blank_values=True) if not _TRACCIAMENTO.match(k)]
    return urlunsplit(parti._replace(query=urlencode(tenuti)))


def testo_pulito(contenuto: str) -> str:
    """Il testo senza formattazione di Discord e con i link ripuliti, entro 2000 caratteri."""
    link: list[str] = []

    def _segnaposto(m: re.Match) -> str:
        link.append(pulisci_link(m.group(0)))
        return f"\x00{len(link) - 1}\x00"

    testo = _URL.sub(_segnaposto, contenuto or "")
    for modello, sostituto in _FORMATTAZIONE:
        testo = modello.sub(sostituto, testo)
    testo = re.sub(r"\x00(\d+)\x00", lambda m: link[int(m.group(1))], testo).strip()
    return testo[:MAX_RISPOSTA]


# ---- promemoria personali ----
MAX_PROMEMORIA = 25
DURATA_MINIMA = 60
DURATA_MASSIMA = 365 * 24 * 3600


def errore_durata(secondi: int) -> str | None:
    if secondi < DURATA_MINIMA:
        return "Il promemoria deve partire tra almeno 1 minuto."
    if secondi > DURATA_MASSIMA:
        return "Il promemoria può partire al massimo tra un anno."
    return None


AZIONE_PROMEMORIA = "app_promemoria"
SENZA_SERVER = 0  # i promemoria dell'app non appartengono a un server


async def programma_promemoria(user_id: int, secondi: int, testo: str, pianificatore=None) -> int | None:
    """Il numero del promemoria nuovo, o None se la persona ne ha già `MAX_PROMEMORIA` in sospeso."""
    if pianificatore is None:
        from core.scheduler import scheduler as pianificatore

    if len(await pianificatore.list_pending_for_user(user_id, AZIONE_PROMEMORIA, MAX_PROMEMORIA)) >= MAX_PROMEMORIA:
        return None
    quando = datetime.now(timezone.utc) + timedelta(seconds=secondi)
    return await pianificatore.schedule(SENZA_SERVER, user_id, AZIONE_PROMEMORIA, quando, {"message": testo[:1500]})

"""
core/server_stats_logic.py
=============================
Logica pura di Server Stats (SPEC.md §14.18). Riduce una lista di
eventi join/leave (dal log eventi unificato, core/repositories/
event_log_repo.py) a un conteggio di variazione netta per giorno —
non tenta di ricostruire la popolazione storica assoluta del server
(richiederebbe di sapere il conteggio esatto al giorno zero, che non
abbiamo), mostra invece l'ANDAMENTO (quanti sono entrati/usciti ogni
giorno), che è quello che un grafico di crescita deve comunicare.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta


def compute_daily_net_change(
    events: list[tuple[datetime, str]],
) -> dict[date, int]:
    """
    events è una lista di (timestamp, event_type) — event_type deve
    essere "member_join" o "member_remove", qualunque altro valore
    viene ignorato silenziosamente (il chiamante può passare una
    lista mista senza doverla pre-filtrare).

    Restituisce {data: variazione_netta}, con SOLO i giorni che
    hanno avuto almeno un evento — un giorno senza eventi non compare
    (0 impliciti), il chiamante decide come trattare i buchi quando
    disegna il grafico.
    """
    variazioni: dict[date, int] = {}
    for timestamp, event_type in events:
        if event_type not in ("member_join", "member_remove"):
            continue
        giorno = timestamp.date()
        delta = 1 if event_type == "member_join" else -1
        variazioni[giorno] = variazioni.get(giorno, 0) + delta
    return variazioni


def fill_missing_days(daily_counts: dict[date, int], start: date, end: date) -> dict[date, int]:
    """
    Completa i buchi tra start e end (inclusi) con 0 — utile per
    disegnare un grafico con l'asse dei giorni continuo, senza salti
    che farebbero sembrare le barre più vicine di quanto siano in
    realtà.
    """
    risultato: dict[date, int] = {}
    giorno_corrente = start
    while giorno_corrente <= end:
        risultato[giorno_corrente] = daily_counts.get(giorno_corrente, 0)
        giorno_corrente = date.fromordinal(giorno_corrente.toordinal() + 1)
    return risultato


def totale_membri_per_giorno(membri_ora: int, variazioni: dict[date, int], dal: date, al: date) -> dict[date, int]:
    """STA-018: il numero di membri a fine di ogni giorno, ricostruito all'indietro dal numero di oggi.

    Si parte da `membri_ora` (alla fine di `al`) e si tolgono le variazioni nette dei giorni dopo.
    Mai sotto zero: se il registro degli eventi è incompleto il numero si ferma a 0.
    """
    risultato: dict[date, int] = {}
    totale = membri_ora
    giorno = al
    while giorno >= dal:
        risultato[giorno] = max(0, totale)
        totale -= variazioni.get(giorno, 0)
        giorno -= timedelta(days=1)
    return dict(sorted(risultato.items()))


def ritenzione(ingressi: list[tuple[int, datetime]], uscite: list[tuple[int, datetime]], adesso: datetime) -> dict:
    """STA-053: di chi è entrato nel periodo, quanti sono ancora qui e quanti se ne sono andati presto.

    Un membro è «uscito» se dopo il suo ingresso c'è un'uscita. Rientri: conta l'ultimo ingresso.
    """
    ultimo_ingresso: dict[int, datetime] = {}
    for utente, quando in ingressi:
        if utente not in ultimo_ingresso or quando > ultimo_ingresso[utente]:
            ultimo_ingresso[utente] = quando
    prima_uscita: dict[int, datetime] = {}
    for utente, quando in sorted(uscite, key=lambda x: x[1]):
        if utente in ultimo_ingresso and quando >= ultimo_ingresso[utente] and utente not in prima_uscita:
            prima_uscita[utente] = quando
    n = len(ultimo_ingresso)
    usciti = len(prima_uscita)
    entro_1g = sum(1 for u, q in prima_uscita.items() if q - ultimo_ingresso[u] <= timedelta(days=1))
    entro_7g = sum(1 for u, q in prima_uscita.items() if q - ultimo_ingresso[u] <= timedelta(days=7))
    vecchi = [u for u, q in ultimo_ingresso.items() if adesso - q >= timedelta(days=7)]
    restano_7g = sum(1 for u in vecchi if u not in prima_uscita or prima_uscita[u] - ultimo_ingresso[u] > timedelta(days=7))
    return {
        "ingressi": n, "rimasti": n - usciti, "usciti": usciti,
        "percentuale": round(100 * (n - usciti) / n, 1) if n else 0.0,
        "usciti_entro_1g": entro_1g, "usciti_entro_7g": entro_7g,
        "dopo_7g_restano": round(100 * restano_7g / len(vecchi), 1) if vecchi else None,
    }


def _cella_sicura(valore) -> str:
    testo = str(valore)
    return "'" + testo if testo[:1] in ("=", "+", "-", "@", "\t", "\r") and not testo.lstrip("-").isdigit() else testo


def tabella_in_csv(intestazione: list[str], righe: list[list], massimo: int = 50_000) -> bytes:
    """STA-056: CSV con ';' (Excel italiano non lo capirebbe con la virgola), celle sicure contro le formule."""
    uscita = io.StringIO()
    scrittore = csv.writer(uscita, delimiter=";", lineterminator="\n")
    scrittore.writerow([_cella_sicura(c) for c in intestazione])
    for riga in righe[:massimo]:
        scrittore.writerow([_cella_sicura(c) for c in riga])
    return ("\ufeff" + uscita.getvalue()).encode("utf-8")

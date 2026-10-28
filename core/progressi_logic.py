"""
core/progressi_logic.py
=======================
Missioni del giorno, serie di giorni, traguardi, stagione mensile (il «battle pass») e
profilo globale con soli dati positivi. Funzioni pure, senza Discord né database.
Funzioni coperte: SPEC §23.17 (NF-41, D49)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# ---------------------------------------------------------------- eventi contati
EVENTO_MESSAGGI = "messaggi"  # un messaggio che ha dato XP
EVENTO_VOCALE = "vocale"  # un minuto di presenza vocale che ha dato XP
EVENTO_DAILY = "daily"  # la ricompensa giornaliera riscossa

SEZIONI = ("missioni", "traguardi", "serie", "stagione", "globale")


# ---------------------------------------------------------------- missioni
@dataclass(frozen=True)
class Missione:
    chiave: str
    testo: str
    obiettivo: int
    premio: int  # monete


MISSIONI: tuple[Missione, ...] = (
    Missione(EVENTO_MESSAGGI, "Scrivi 15 messaggi che danno XP", 15, 30),
    Missione(EVENTO_VOCALE, "Passa 30 minuti in vocale", 30, 40),
    Missione(EVENTO_DAILY, "Riscuoti la ricompensa giornaliera", 1, 20),
)
MISSIONE_PER_CHIAVE = {m.chiave: m for m in MISSIONI}


def stato_missione(missione: Missione, progresso: int, riscattata: bool) -> str:
    """Una riga: casella, testo, avanzamento. Il progresso non supera mai l'obiettivo."""
    fatto = min(progresso, missione.obiettivo)
    casella = "✅" if riscattata else ("🎁" if fatto >= missione.obiettivo else "⬜")
    return f"{casella} {missione.testo} ({fatto}/{missione.obiettivo}, premio {missione.premio})"


# ---------------------------------------------------------------- serie
SERIE_BONUS_OGNI = 7  # ogni 7 giorni di fila arriva un bonus
SERIE_BONUS_PER_GIORNO = 5  # monete per giorno di serie
SERIE_BONUS_MAX = 200


def aggiorna_serie(serie: int, record: int, ultimo: date | None, oggi: date) -> tuple[int, int, date]:
    """
    Una riscossione giornaliera il giorno `oggi`: la serie sale se l'ultima era ieri, resta se è già
    oggi, riparte da 1 se c'è stato un buco. Restituisce (serie, record, ultimo giorno).
    """
    if ultimo == oggi:
        return serie, max(record, serie), oggi
    nuova = serie + 1 if ultimo is not None and ultimo == oggi - timedelta(days=1) else 1
    return nuova, max(record, nuova), oggi


def serie_attuale(serie: int, ultimo: date | None, oggi: date) -> int:
    """La serie che si vede oggi: se l'ultima riscossione è più vecchia di ieri la serie è finita."""
    if ultimo is None or ultimo < oggi - timedelta(days=1):
        return 0
    return serie


def bonus_serie(serie: int) -> int:
    """Monete extra al giorno di serie giusto (7, 14, 21...), altrimenti 0."""
    if serie <= 0 or serie % SERIE_BONUS_OGNI != 0:
        return 0
    return min(serie * SERIE_BONUS_PER_GIORNO, SERIE_BONUS_MAX)


# ---------------------------------------------------------------- traguardi
@dataclass(frozen=True)
class Traguardo:
    chiave: str
    emoji: str
    testo: str
    statistica: str  # nome del campo di Statistiche
    soglia: int


@dataclass(frozen=True)
class Statistiche:
    livello: int = 0
    record_serie: int = 0
    missioni_completate: int = 0
    stagioni_complete: int = 0


TRAGUARDI: tuple[Traguardo, ...] = (
    Traguardo("livello_5", "🌱", "Livello 5", "livello", 5),
    Traguardo("livello_10", "🌿", "Livello 10", "livello", 10),
    Traguardo("livello_25", "🌳", "Livello 25", "livello", 25),
    Traguardo("livello_50", "🏔️", "Livello 50", "livello", 50),
    Traguardo("serie_7", "🔥", "7 giorni di fila", "record_serie", 7),
    Traguardo("serie_30", "☄️", "30 giorni di fila", "record_serie", 30),
    Traguardo("missioni_10", "🎯", "10 missioni completate", "missioni_completate", 10),
    Traguardo("missioni_100", "🏆", "100 missioni completate", "missioni_completate", 100),
    Traguardo("stagione_completa", "🎖️", "Una stagione completata", "stagioni_complete", 1),
)
TRAGUARDO_PER_CHIAVE = {t.chiave: t for t in TRAGUARDI}


def traguardi_raggiunti(stat: Statistiche) -> set[str]:
    """Le chiavi dei traguardi che le statistiche soddisfano."""
    return {t.chiave for t in TRAGUARDI if getattr(stat, t.statistica) >= t.soglia}


def testo_traguardi(ottenuti: set[str]) -> str:
    """Tutti i traguardi, quelli presi con la loro emoji, gli altri in grigio."""
    righe = [
        f"{t.emoji} {t.testo}" if t.chiave in ottenuti else f"▫️ ~~{t.testo}~~"
        for t in TRAGUARDI
    ]
    return "\n".join(righe)


# ---------------------------------------------------------------- stagione
STAGIONE_GRADINI = 10
STAGIONE_XP_PER_GRADINO = 1500
STAGIONE_PREMIO_PER_GRADINO = 40  # monete: il gradino n vale n * 40


def gradini_raggiunti(xp_mese: int) -> int:
    return max(0, min(STAGIONE_GRADINI, xp_mese // STAGIONE_XP_PER_GRADINO))


def premio_gradini(da_escluso: int, a_incluso: int) -> int:
    """Monete dei gradini da `da_escluso + 1` a `a_incluso`."""
    return sum(n * STAGIONE_PREMIO_PER_GRADINO for n in range(da_escluso + 1, a_incluso + 1))


def testo_stagione(xp_mese: int, riscattati: int, stagione: str) -> str:
    raggiunti = gradini_raggiunti(xp_mese)
    righe = [f"**Stagione {stagione}** · {xp_mese} XP questo mese"]
    for n in range(1, STAGIONE_GRADINI + 1):
        casella = "✅" if n <= riscattati else ("🎁" if n <= raggiunti else "⬜")
        righe.append(f"{casella} Gradino {n}: {n * STAGIONE_XP_PER_GRADINO} XP, premio {n * STAGIONE_PREMIO_PER_GRADINO}")
    if raggiunti < STAGIONE_GRADINI:
        mancano = (raggiunti + 1) * STAGIONE_XP_PER_GRADINO - xp_mese
        righe.append(f"Al prossimo gradino mancano {mancano} XP.")
    return "\n".join(righe)


# ---------------------------------------------------------------- profilo globale (solo dati positivi)
@dataclass(frozen=True)
class ProfiloGlobale:
    server: int  # in quanti server ha un livello
    livello_massimo: int
    record_serie: int
    traguardi: int  # numero di traguardi (chiavi diverse) ottenuti in almeno un server


def testo_profilo_globale(p: ProfiloGlobale) -> str:
    """Solo cose belle e solo numeri: niente nomi di server, niente sanzioni, niente monete."""
    return (
        f"Server in cui giochi: **{p.server}**\n"
        f"Livello più alto: **{p.livello_massimo}**\n"
        f"Serie più lunga: **{p.record_serie}** giorni\n"
        f"Traguardi diversi ottenuti: **{p.traguardi}** su {len(TRAGUARDI)}"
    )

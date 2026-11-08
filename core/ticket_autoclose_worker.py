"""
core/ticket_autoclose_worker.py
===============================
Regole pure dei ticket fermi: categoria «in attesa dell'utente» (TKT-029), regole di inattività
per pannello (TKT-064) e riserva di canali già pronti (TKT-035). Niente oggetti Discord.
Funzioni coperte: SPEC §13.20 (TKT-029, TKT-035, TKT-064)
Dipende da: core/ticket_opzioni_logic.py (opzioni del pannello)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

MAX_REGOLE_PANNELLO = 5
MIN_MINUTI = 5
MAX_MINUTI = 43200  # 30 giorni
MAX_TESTO_REGOLA = 1000
MAX_RISERVA = 5
MAX_RIPETIZIONI = 3  # un messaggio ripetuto si manda al massimo 3 volte finché nessuno scrive
PAUSA_SPOSTAMENTO_MINUTI = 10  # un ticket si sposta al massimo ogni 10 minuti
MAX_CANALI_PER_CATEGORIA = 50
CHI = ("utente", "staff", "chiunque")
AZIONI = ("chiudi", "elimina", "messaggio")


class ErroreRegola(ValueError):
    """Regola o impostazione non valida (il testo si mostra all'admin)."""


@dataclass(frozen=True)
class Regola:
    id: int
    panel_id: int
    chi: str
    minuti: int
    azione: str
    testo: str | None = None
    ripeti: bool = False


def regola_valida(chi: str, minuti: int, azione: str, testo: str | None, ripeti: bool) -> tuple[str, int, str, str | None, bool]:
    """Controlla una regola nuova. Il messaggio ha bisogno del testo; ripetere ha senso solo con il messaggio."""
    if chi not in CHI:
        raise ErroreRegola("«chi» deve essere utente, staff o chiunque.")
    if azione not in AZIONI:
        raise ErroreRegola("L'azione deve essere chiudi, elimina o messaggio.")
    if not MIN_MINUTI <= minuti <= MAX_MINUTI:
        raise ErroreRegola(f"I minuti vanno da {MIN_MINUTI} a {MAX_MINUTI}.")
    pulito = (testo or "").strip() or None
    if pulito is not None and len(pulito) > MAX_TESTO_REGOLA:
        raise ErroreRegola(f"Il testo può avere al massimo {MAX_TESTO_REGOLA} caratteri.")
    if azione == "messaggio" and pulito is None:
        raise ErroreRegola("Per l'azione «messaggio» serve il testo.")
    if ripeti and azione != "messaggio":
        raise ErroreRegola("Solo il messaggio si può ripetere: chiudere o eliminare avviene una volta.")
    return chi, minuti, azione, pulito, ripeti


def regola_scattata(
    regola: Regola,
    *,
    creato: datetime,
    ultimo_utente: datetime | None,
    ultimo_staff: datetime | None,
    ultima_attivita: datetime | None,
    ultima_esecuzione: datetime | None,
    adesso: datetime,
) -> bool:
    """
    Vero se nessuno (utente, staff o chiunque) scrive da `minuti` e la regola non è già stata eseguita.
    Un messaggio ripetuto si ferma dopo MAX_RIPETIZIONI invii; riparte quando qualcuno scrive.
    """
    if regola.chi == "utente":
        riferimento = ultimo_utente
    elif regola.chi == "staff":
        riferimento = ultimo_staff
    else:
        riferimento = ultima_attivita
    riferimento = riferimento or creato
    if ultima_esecuzione is not None:
        if not regola.ripeti and ultima_esecuzione >= riferimento:
            return False  # già fatta e nessuno ha scritto dopo
        if ultima_esecuzione - riferimento >= timedelta(minutes=regola.minuti * MAX_RIPETIZIONI):
            return False  # già mandato MAX_RIPETIZIONI volte senza risposta
        riferimento = max(riferimento, ultima_esecuzione)
    return adesso - riferimento >= timedelta(minutes=regola.minuti)


def _spostabile(spostato_at: datetime | None, adesso: datetime) -> bool:
    return spostato_at is None or adesso - spostato_at >= timedelta(minutes=PAUSA_SPOSTAMENTO_MINUTI)


def da_mettere_in_attesa(
    *,
    attesa_minuti: int,
    in_attesa: bool,
    ultimo_utente: datetime | None,
    ultimo_staff: datetime | None,
    spostato_at: datetime | None,
    adesso: datetime,
) -> bool:
    """Lo staff ha scritto per ultimo da `attesa_minuti` e il ticket non è già in attesa."""
    if not attesa_minuti or in_attesa or ultimo_staff is None or not _spostabile(spostato_at, adesso):
        return False
    if ultimo_utente is not None and ultimo_utente >= ultimo_staff:
        return False
    return adesso - ultimo_staff >= timedelta(minutes=attesa_minuti)


def da_riportare_indietro(
    *,
    in_attesa: bool,
    in_attesa_da: datetime | None,
    ultimo_utente: datetime | None,
    spostato_at: datetime | None,
    adesso: datetime,
) -> bool:
    """L'utente ha scritto dopo lo spostamento in attesa."""
    if not in_attesa or ultimo_utente is None:
        return False
    if in_attesa_da is not None and ultimo_utente <= in_attesa_da:
        return False
    return _spostabile(spostato_at, adesso)


def categoria_con_posto(canali_nella_categoria: int) -> bool:
    """Discord: al massimo 50 canali per categoria."""
    return canali_nella_categoria < MAX_CANALI_PER_CATEGORIA


def canali_da_creare(riserva: int, presenti: int) -> int:
    """Quanti canali di riserva mancano. Se ne crea uno per giro: niente creazioni di massa."""
    return 1 if min(max(riserva, 0), MAX_RISERVA) > presenti else 0

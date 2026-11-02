"""
core/immagini_azione_logic.py
=============================
Cosa fare dopo l'esito del filtro immagini (D62), in logica pura: cancellare, avvisare nel canale,
timeout, DM all'autore, riga nel log. Le azioni sono quelle scelte dal server (cancella, avvisa,
timeout); un'immagine malevola del primo invio di un autore mette comunque in timeout. Coda piena o
sandbox ferma: il messaggio resta, tranne per un account nuovo (meno di 7 giorni, o nel server da
meno di 1 giorno), che deve «riprovare fra poco».
Funzioni coperte: SPEC §6 (D62)
"""

from __future__ import annotations

from dataclasses import dataclass

from core.immagini_byte_logic import MALEVOLA, PULITA
from core.immagini_opzioni import OpzioniImmagini
from core.immagini_pipeline import NON_ANALIZZATA_CODA, NON_ANALIZZATA_GRANDE, NON_ANALIZZATA_SANDBOX, EsitoImmagine

GIORNI_ACCOUNT_NUOVO = 7
GIORNI_NEL_SERVER_NUOVO = 1

DM_RIMOSSA = "amimg_dm_rimossa"
DM_TIMEOUT = "amimg_dm_timeout"
DM_RIPROVA = "amimg_dm_riprova"


@dataclass(frozen=True)
class Decisione:
    cancella: bool = False
    avvisa_nel_canale: bool = False
    timeout_minuti: int | None = None
    dm: str | None = None
    log: bool = False
    avvisa_owner: bool = False  # coda piena: l'owner del bot va avvisato (con il tetto di uno ogni 10 minuti)


def autore_a_rischio(giorni_account: float, giorni_nel_server: float | None) -> bool:
    """Account con meno di 7 giorni, oppure nel server da meno di 1 giorno."""
    return giorni_account < GIORNI_ACCOUNT_NUOVO or (giorni_nel_server is not None and giorni_nel_server < GIORNI_NEL_SERVER_NUOVO)


def decidi(esito: EsitoImmagine, opzioni: OpzioniImmagini, *, a_rischio: bool, primo_invio: bool) -> Decisione:
    if esito.non_analizzata == NON_ANALIZZATA_GRANDE:
        return Decisione()
    if esito.non_analizzata in (NON_ANALIZZATA_CODA, NON_ANALIZZATA_SANDBOX):
        if a_rischio:
            return Decisione(cancella=True, dm=DM_RIPROVA, log=True, avvisa_owner=esito.non_analizzata == NON_ANALIZZATA_CODA)
        return Decisione(log=True, avvisa_owner=esito.non_analizzata == NON_ANALIZZATA_CODA)
    if esito.verdetto == PULITA:
        return Decisione()
    if esito.solo_avviso:
        return Decisione(log=True)
    timeout = opzioni.timeout_minuti if (opzioni.azione == "timeout" or (esito.verdetto == MALEVOLA and primo_invio)) else None
    if opzioni.azione == "avvisa" and timeout is None:
        return Decisione(avvisa_nel_canale=True, log=True)
    if timeout is not None:
        return Decisione(cancella=True, timeout_minuti=timeout, dm=DM_TIMEOUT, log=True)
    return Decisione(cancella=True, dm=DM_RIMOSSA, log=True)

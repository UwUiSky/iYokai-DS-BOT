"""
core/cerca_ai_logic.py
======================
Logica pura di «cerca qualsiasi cosa»: istruzioni per il servizio con ricerca web, pulizia della risposta
(link pericolosi mai mostrati, link senza anteprima, menzioni spente, testo troncato) e limite per persona.
Funzioni coperte: SPEC §25 (UTL-216; D124, D19, D55)
Dipende da: core/controllo_link.py
"""

from __future__ import annotations

import re
import time
from collections import OrderedDict, deque

from core import controllo_link

MAX_DOMANDA = 300
MAX_RISPOSTA = 1800
MAX_LINK_MOSTRATI = 6
PAUSA_SECONDI = 20
MAX_AL_GIORNO = 15
MAX_PERSONE = 2000
TIPI_RICERCA = ("rapida", "web", "video")

_ISTRUZIONI = {
    "rapida": "Rispondi alla domanda in modo breve e diretto (al massimo 6 righe), usando la ricerca sul web.",
    "web": "Cerca sul web e riassumi i risultati più utili in elenco breve, con il link della fonte per ognuno.",
    "video": "Cerca video pertinenti (YouTube o altri siti). Per ognuno scrivi il titolo e il link, al massimo 5.",
}
_BASE = (
    "Usa la ricerca sul web. Rispondi nella lingua della domanda, senza inventare: se non trovi niente dillo. "
    "Mai contenuti per adulti, illegali o pericolosi. Scrivi i link per esteso, uno per fonte. "
)
_MASCHERATO = re.compile(r"\[([^\]]{0,200})\]\((https?://[^\s)]+)\)")
_LINK = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_CONTROLLO = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​-‏‪-‮⁦-⁩]")
SEGNO_RIMOSSO = "⛔ link bloccato"


def istruzioni(tipo: str) -> str:
    return _BASE + _ISTRUZIONI.get(tipo, _ISTRUZIONI["rapida"])


def pulisci_domanda(testo: str) -> str:
    return re.sub(r"\s+", " ", _CONTROLLO.sub(" ", testo or "")).strip()[:MAX_DOMANDA]


async def pulisci_risposta(testo: str) -> tuple[str, int]:
    """
    La risposta pronta da mostrare e quanti link sono stati tolti. Un link mascherato `[x](url)` diventa
    «x url» (si vede dove porta); ogni link è controllato da `controllo_link`; i pericolosi e quelli oltre il
    tetto sono tolti; quelli buoni vanno tra `<>` (niente anteprima); `@everyone`/`@here` sono spenti.
    """
    testo = _CONTROLLO.sub("", testo or "")
    testo = _MASCHERATO.sub(lambda m: f"{m.group(1)} {m.group(2)}", testo)
    tolti = 0
    visti: dict[str, str] = {}

    async def sostituzione(link: str) -> str:
        nonlocal tolti
        link = link.rstrip(".,;:!?)]}*_~|")
        if link not in visti:
            if len(visti) >= MAX_LINK_MOSTRATI:
                visti[link] = SEGNO_RIMOSSO
            else:
                visti[link] = SEGNO_RIMOSSO if await controllo_link.e_link_pericoloso(link) else f"<{link}>"
        if visti[link] == SEGNO_RIMOSSO:
            tolti += 1
        return visti[link]

    pezzi: list[str] = []
    fine = 0
    for m in _LINK.finditer(testo):
        grezzo = m.group(0)
        pulito = grezzo.rstrip(".,;:!?)]}*_~|")
        pezzi.append(testo[fine:m.start()])
        pezzi.append(await sostituzione(pulito) + grezzo[len(pulito):])
        fine = m.end()
    pezzi.append(testo[fine:])
    testo = "".join(pezzi)
    testo = re.sub(r"@(everyone|here)", "@​\\1", testo)
    testo = re.sub(r"<@[!&]?\d+>", "", testo)
    if len(testo) > MAX_RISPOSTA:
        testo = testo[: MAX_RISPOSTA - 1].rstrip() + "…"
    return testo.strip(), tolti


class LimitePersona:
    """Una pausa tra due ricerche e un tetto al giorno per persona, in memoria e con un massimo di persone."""

    def __init__(self, orologio=time.monotonic) -> None:
        self._orologio = orologio
        self._ricerche: OrderedDict[int, deque[float]] = OrderedDict()

    def prova(self, utente_id: int) -> tuple[bool, int]:
        """(ammessa, secondi da aspettare). Se ammessa, la ricerca è già contata."""
        ora = self._orologio()
        coda = self._ricerche.setdefault(utente_id, deque())
        self._ricerche.move_to_end(utente_id)
        while coda and coda[0] < ora - 86400:
            coda.popleft()
        if coda and ora - coda[-1] < PAUSA_SECONDI:
            return False, int(PAUSA_SECONDI - (ora - coda[-1])) + 1
        if len(coda) >= MAX_AL_GIORNO:
            return False, int(coda[0] + 86400 - ora) + 1
        coda.append(ora)
        while len(self._ricerche) > MAX_PERSONE:
            self._ricerche.popitem(last=False)
        return True, 0

    def restituisci(self, utente_id: int) -> None:
        """La ricerca non è partita (servizio assente): non si conta."""
        coda = self._ricerche.get(utente_id)
        if coda:
            coda.pop()

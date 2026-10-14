"""
core/ai_router.py
=================
Lo snodo del motore AI: sceglie il fornitore per tipo di lavoro, fascia e
quota rimasta; conta richieste e token per finestra (minuto, giorno);
salta un fornitore oltre l'85 % di una quota o in pausa dopo un errore;
passa al successivo senza che l'utente se ne accorga.
Funzioni coperte: SPEC §25.1, §25.10, §25.13, §25.94, §25.95 (AI-R-001..003, AI-R-007, AI-R-008, AI-R-101, AI-R-102)
Dipende da: core/ai_providers.py (configurazione e trasporto)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass

from core.ai_cost_logic import costo_millesimi, stima_token
from core.ai_providers import FASCE, ErroreFornitore, EsitoChiamata, Fornitore

logger = logging.getLogger("iyokai.ai_router")

SOGLIA_QUOTA = 0.85
PAUSA_BASE_SECONDI = 60
PAUSA_MAX_SECONDI = 3600
_FINESTRE = {"minuto": 60, "giorno": 86400}


class NessunFornitore(Exception):
    """Nessun fornitore adatto e libero: il chiamante dà la risposta locale."""


@dataclass(frozen=True)
class EsitoMotore:
    testo: str = ""
    immagine: bytes | None = None
    fornitore: str = ""
    token_in: int = 0
    token_out: int = 0
    costo_millesimi: int = 0


class StatoFornitori:
    """Conti per finestra, pause dopo gli errori, quote dichiarate dai fornitori. Tutto in memoria."""

    def __init__(self) -> None:
        # (nome, finestra) -> [inizio, richieste, token]
        self._conti: dict[tuple[str, str], list[float]] = {}
        self._pausa_fino: dict[str, float] = {}
        self._errori_di_fila: dict[str, int] = defaultdict(int)
        self._dichiarato: dict[str, tuple[float, float]] = {}  # nome -> (uso 0-1, fino a)

    def _conto(self, nome: str, finestra: str, ora: float) -> list[float]:
        voce = self._conti.get((nome, finestra))
        if voce is None or ora - voce[0] >= _FINESTRE[finestra]:
            voce = [ora, 0, 0]
            self._conti[(nome, finestra)] = voce
        return voce

    def registra(self, nome: str, token: int, ora: float | None = None) -> None:
        ora = time.monotonic() if ora is None else ora
        for finestra in _FINESTRE:
            voce = self._conto(nome, finestra, ora)
            voce[1] += 1
            voce[2] += token
        self._errori_di_fila[nome] = 0

    def uso(self, f: Fornitore, ora: float | None = None) -> float:
        """La quota più consumata del fornitore, da 0 a 1 (0 se nessun limite è noto)."""
        ora = time.monotonic() if ora is None else ora
        m, g = self._conto(f.nome, "minuto", ora), self._conto(f.nome, "giorno", ora)
        rapporti = [0.0]
        for limite, usato in ((f.limiti.rpm, m[1]), (f.limiti.rpg, g[1]), (f.limiti.tpm, m[2]), (f.limiti.tpg, g[2])):
            if limite:
                rapporti.append(usato / limite)
        dichiarato = self._dichiarato.get(f.nome)
        if dichiarato and dichiarato[1] > ora:
            rapporti.append(dichiarato[0])
        return max(rapporti)

    def leggi_intestazioni(self, nome: str, intestazioni, ora: float | None = None) -> None:
        """Quote dichiarate dal servizio (`x-ratelimit-*`): valgono per il minuto successivo."""
        ora = time.monotonic() if ora is None else ora
        basse = {str(k).lower(): v for k, v in dict(intestazioni or {}).items()}
        peggiore = None
        for cosa in ("requests", "tokens"):
            try:
                limite = float(basse[f"x-ratelimit-limit-{cosa}"])
                resto = float(basse[f"x-ratelimit-remaining-{cosa}"])
            except (KeyError, ValueError):
                continue
            if limite > 0:
                uso = 1 - resto / limite
                peggiore = uso if peggiore is None else max(peggiore, uso)
        if peggiore is not None:
            self._dichiarato[nome] = (peggiore, ora + 60)

    def metti_in_pausa(self, nome: str, retry_after: float | None, ora: float | None = None) -> float:
        """Pausa dopo un errore: `Retry-After` se c'è, altrimenti sempre più lunga a ogni errore di fila."""
        ora = time.monotonic() if ora is None else ora
        self._errori_di_fila[nome] += 1
        if retry_after is not None:
            durata = min(retry_after, PAUSA_MAX_SECONDI)
        else:
            durata = min(PAUSA_BASE_SECONDI * 2 ** (self._errori_di_fila[nome] - 1), PAUSA_MAX_SECONDI)
        self._pausa_fino[nome] = ora + durata
        return durata

    def in_pausa(self, nome: str, ora: float | None = None) -> bool:
        ora = time.monotonic() if ora is None else ora
        return self._pausa_fino.get(nome, 0) > ora

    def riepilogo(self, f: Fornitore, ora: float | None = None) -> dict:
        ora = time.monotonic() if ora is None else ora
        g = self._conto(f.nome, "giorno", ora)
        return {"richieste_oggi": int(g[1]), "token_oggi": int(g[2]), "uso": self.uso(f, ora), "in_pausa": self.in_pausa(f.nome, ora)}


def scegli_fornitori(
    fornitori: list[Fornitore],
    tipo: str,
    fascia: str,
    stato: StatoFornitori,
    *,
    usa_pagamento: bool = False,
    solo_gratuiti: bool = False,
    ora: float | None = None,
) -> list[Fornitore]:
    """
    I fornitori da provare, in ordine: sanno fare il tipo, fascia almeno quella chiesta,
    non in pausa, sotto l'85 % delle quote. Vince la fascia più bassa che basta, poi
    la quota più libera; a parità, l'ordine di `AI_FORNITORI`.
    """
    minimo = FASCE.index(fascia) if fascia in FASCE else 0
    adatti = []
    for posizione, f in enumerate(fornitori):
        if tipo not in f.tipi or f.livello < minimo:
            continue
        if f.a_pagamento and not usa_pagamento:
            continue
        if solo_gratuiti and f.costo_cent_milione > 0:
            continue
        if stato.in_pausa(f.nome, ora):
            continue
        uso = stato.uso(f, ora)
        if uso >= SOGLIA_QUOTA:
            continue
        adatti.append((f.livello, round(uso, 2), posizione, f))
    adatti.sort(key=lambda t: t[:3])
    return [t[3] for t in adatti]


class MotoreAI:
    """Prova i fornitori scelti uno dopo l'altro. Il trasporto è quello vero o, nei test, uno finto."""

    def __init__(self, fornitori: list[Fornitore], trasporto, *, usa_pagamento: bool = False) -> None:
        self.fornitori = fornitori
        self.trasporto = trasporto
        self.usa_pagamento = usa_pagamento
        self.stato = StatoFornitori()

    @property
    def configurato(self) -> bool:
        return bool(self.fornitori)

    def sa_fare(self, tipo: str) -> bool:
        return any(tipo in f.tipi and (self.usa_pagamento or not f.a_pagamento) for f in self.fornitori)

    async def esegui(
        self, tipo: str, fascia: str, *, messaggi: list[dict] | None = None, prompt: str = "",
        max_token: int = 600, solo_gratuiti: bool = False,
    ) -> EsitoMotore:
        candidati = scegli_fornitori(
            self.fornitori, tipo, fascia, self.stato, usa_pagamento=self.usa_pagamento, solo_gratuiti=solo_gratuiti
        )
        for f in candidati:
            try:
                if tipo == "immagine":
                    esito: EsitoChiamata = await self.trasporto.immagine(f, prompt)
                else:
                    esito = await self.trasporto.completa(f, messaggi or [], max_token)
            except ErroreFornitore as exc:
                durata = self.stato.metti_in_pausa(f.nome, exc.retry_after)
                logger.warning("Fornitore AI %s in pausa per %.0f s (errore %s).", f.nome, durata, exc.stato)
                continue
            token_in = esito.token_in or stima_token(" ".join(str(m.get("content", "")) for m in messaggi or []) + prompt)
            token_out = esito.token_out or (stima_token(esito.testo) if esito.testo else 0)
            self.stato.registra(f.nome, token_in + token_out)
            self.stato.leggi_intestazioni(f.nome, esito.intestazioni)
            return EsitoMotore(
                testo=esito.testo, immagine=esito.immagine, fornitore=f.nome, token_in=token_in,
                token_out=token_out, costo_millesimi=costo_millesimi(f.costo_cent_milione, token_in + token_out),
            )
        raise NessunFornitore(tipo)

    async def controlla_chiavi(self) -> dict[str, bool]:
        """Per ogni fornitore: la chiave risponde? (chiamata che non consuma token)."""
        esiti = {}
        for f in self.fornitori:
            try:
                esiti[f.nome] = bool(await self.trasporto.controlla(f))
            except Exception:
                esiti[f.nome] = False
        return esiti

    def quote_in_esaurimento(self) -> list[str]:
        return [f.nome for f in self.fornitori if self.stato.uso(f) >= SOGLIA_QUOTA]


def avviso_chiavi(
    esiti: dict[str, bool], esaurite: list[str], gia_segnalati: frozenset[str]
) -> tuple[str | None, frozenset[str]]:
    """
    Testo del messaggio privato all'owner dopo il controllo orario (AI-R-103), solo quando
    qualcosa cambia: chiavi che non rispondono e quote oltre l'85 %. Mai la chiave.
    """
    problemi = frozenset({f"chiave:{n}" for n, ok in esiti.items() if not ok} | {f"quota:{n}" for n in esaurite})
    nuovi = problemi - gia_segnalati
    if not nuovi:
        return None, problemi
    righe = ["Controllo dei fornitori AI:"]
    righe += [f"- {p.split(':', 1)[1]}: la chiave non risponde (scaduta o sbagliata?)" for p in sorted(nuovi) if p.startswith("chiave:")]
    righe += [f"- {p.split(':', 1)[1]}: quota oltre l'85 %, lo salto fino al rinnovo" for p in sorted(nuovi) if p.startswith("quota:")]
    return "\n".join(righe), problemi

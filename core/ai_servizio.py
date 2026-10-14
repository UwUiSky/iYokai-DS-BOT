"""
core/ai_servizio.py
===================
La sola porta dei moduli verso l'AI. Ogni funzione dice tipo di lavoro,
fascia e se il testo contiene messaggi di utenti; qui si fanno, in ordine:
AI configurata e accesa nel server (consenso dell'admin), canale non
spento, privacy, richieste vietate, limite al minuto, cache e libreria,
quote e tetto di spesa, lore, dati personali tolti, chiamata, pulizia
della risposta, conti. Se l'AI non può rispondere, `AINonDisponibile`
porta il motivo e il testo da mostrare: ogni funzione ha la sua risposta
locale.
Funzioni coperte: SPEC §25.1–§25.4, §25.9, §25.12, §25.18–§25.20, §25.33, §25.48 (NF-24)
Dipende da: core/ai_router.py, core/ai_cache_logic.py, core/ai_guardrail_logic.py,
core/ai_cost_logic.py, core/repositories/ai_repo.py
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict, deque
from dataclasses import dataclass

from core.ai_cache_logic import CacheAI, ambito, chiave
from core.ai_cost_logic import LimitatoreUtente, quota_superata, tetto_raggiunto, usa_credito_immagine
from core.ai_guardrail_logic import componi_messaggi, pulisci_dati_personali, pulisci_uscita, richiesta_vietata
from core.ai_providers import TrasportoHTTP, leggi_fornitori, usa_chiavi_a_pagamento
from core.ai_router import MotoreAI, NessunFornitore
from core.ai_testi_logic import testo_lore

logger = logging.getLogger("iyokai.ai_servizio")

TOKEN_PER_LUNGHEZZA = {"corta": 250, "media": 600, "lunga": 1200}
MAX_STORIA = 6

MESSAGGI_LOCALI: dict[str, str] = {
    "non_configurata": "L'AI non è configurata su questo bot: il proprietario deve aggiungere almeno un "
    "fornitore nel file `.env`. Nel frattempo rispondo senza AI.",
    "spenta": "L'AI è spenta in questo server. Un amministratore può accenderla con `/ai attiva`.",
    "canale": "L'AI è spenta in questo canale.",
    "privacy": "Il server ha scelto di non mandare messaggi degli utenti all'AI.",
    "vietata": "Questa richiesta non è permessa.",
    "troppe": "Troppe richieste in poco tempo: riprova tra un minuto.",
    "tetto": "Il server ha raggiunto il tetto di spesa del mese per l'AI.",
    "quota_utente": "Hai finito le richieste AI di oggi in questo server.",
    "quota_utente_30": "Hai finito le richieste AI gratuite di questo periodo: si rinnovano ogni 30 giorni.",
    "quota_funzione": "Questa funzione ha finito le richieste AI di oggi in questo server.",
    "quota_immagini": "Hai finito le immagini della settimana.",
    "fornitori_fermi": "I servizi AI sono occupati o fermi in questo momento. Riprova più tardi.",
}


class AINonDisponibile(Exception):
    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo

    @property
    def testo(self) -> str:
        return MESSAGGI_LOCALI.get(self.motivo, MESSAGGI_LOCALI["fornitori_fermi"])


@dataclass(frozen=True)
class RichiestaAI:
    user_id: int
    funzione: str
    tipo: str
    testo: str
    guild_id: int | None = None
    channel_id: int | None = None
    fascia: str = "bassa"
    istruzioni: str = ""
    messaggi_utenti: bool = False
    lingua: str = ""
    riusa: bool = True
    conversazione: tuple | None = None  # chiave della memoria corta (None = senza memoria)
    max_token: int | None = None


@dataclass(frozen=True)
class RispostaAI:
    testo: str = ""
    immagine: bytes | None = None
    fornitore: str = ""
    da_cache: bool = False


class MemoriaCorta:
    """Ultimi messaggi di una conversazione, in memoria, per al più `minuti` (AI-R-035, AI-R-018)."""

    def __init__(self, max_conversazioni: int = 2000) -> None:
        self._dati: OrderedDict[tuple, deque] = OrderedDict()
        self._max = max_conversazioni

    def leggi(self, chiave_conv: tuple, minuti: int, ora: float | None = None) -> list[dict]:
        ora = time.monotonic() if ora is None else ora
        coda = self._dati.get(chiave_conv)
        if not coda or minuti <= 0:
            return []
        while coda and coda[0][0] < ora - minuti * 60:
            coda.popleft()
        return [m for _, m in coda]

    def aggiungi(self, chiave_conv: tuple, domanda: str, risposta: str, ora: float | None = None) -> None:
        ora = time.monotonic() if ora is None else ora
        coda = self._dati.setdefault(chiave_conv, deque(maxlen=MAX_STORIA))
        coda.append((ora, {"role": "user", "content": domanda}))
        coda.append((ora, {"role": "assistant", "content": risposta}))
        self._dati.move_to_end(chiave_conv)
        while len(self._dati) > self._max:
            self._dati.popitem(last=False)

    def dimentica(self, guild_id: int | None = None) -> None:
        for k in [k for k in self._dati if guild_id is None or k[0] == guild_id]:
            del self._dati[k]


class ServizioAI:
    def __init__(self, motore: MotoreAI, repo=None) -> None:
        if repo is None:
            from core.repositories.ai_repo import ai_repo as repo
        self.motore = motore
        self.repo = repo
        self.cache = CacheAI()
        self.memoria = MemoriaCorta()
        self.limitatore = LimitatoreUtente()

    @property
    def configurato(self) -> bool:
        return self.motore.configurato

    async def controlla_accesso(self, guild_id: int | None, channel_id: int | None = None, tipo: str = "chat"):
        """La config del server se l'AI può lavorare lì, altrimenti `AINonDisponibile`."""
        if not self.motore.configurato or not self.motore.sa_fare(tipo):
            raise AINonDisponibile("non_configurata")
        if guild_id is None:
            return None
        cfg = await self.repo.get_config(guild_id)
        if not cfg.attivo:
            raise AINonDisponibile("spenta")
        if channel_id is not None and channel_id in cfg.canali_spenti:
            raise AINonDisponibile("canale")
        return cfg

    async def richiedi(self, r: RichiestaAI) -> RispostaAI:
        cfg = await self.controlla_accesso(r.guild_id, r.channel_id, r.tipo)
        if cfg is not None and r.messaggi_utenti and cfg.privacy == "senza_messaggi":
            raise AINonDisponibile("privacy")
        if richiesta_vietata(r.testo, cfg.parole_vietate if cfg else ()):
            raise AINonDisponibile("vietata")
        if not self.limitatore.consenti(r.user_id):
            raise AINonDisponibile("troppe")

        testo = pulisci_dati_personali(r.testo)
        lore = testo_lore(cfg.lore_tema, cfg.lore_testo) if cfg else ""
        istruzioni = r.istruzioni + (f"\n[lore] {lore}" if lore else "")
        amb = ambito(r.guild_id, r.messaggi_utenti)
        usa_cache = r.riusa and r.conversazione is None and r.tipo != "immagine"
        if usa_cache:
            salvata = self.cache.trova(amb, r.tipo, istruzioni + r.lingua, testo)
            if salvata is None:
                salvata = await self.repo.cache_trova(amb, chiave(r.tipo, istruzioni + r.lingua, testo))
                if salvata is not None:
                    self.cache.metti(amb, r.tipo, istruzioni + r.lingua, testo, salvata)
            if salvata is not None:
                return RispostaAI(testo=salvata, da_cache=True)

        guild_conti = r.guild_id or 0
        uso = await self.repo.uso(guild_conti, r.user_id, r.funzione)
        quote = cfg.quote if cfg else None
        if quote is not None:
            motivo = quota_superata(quote, uso, immagine=r.tipo == "immagine")
            if motivo:
                raise AINonDisponibile(motivo)
        solo_gratuiti = quote is None or tetto_raggiunto(quote, uso)

        minuti = cfg.conservazione_minuti if cfg else 10
        storia = self.memoria.leggi(r.conversazione, minuti) if r.conversazione else []
        messaggi = componi_messaggi(r.istruzioni, testo, lore=lore, lingua=r.lingua, storia=storia)
        max_token = r.max_token or TOKEN_PER_LUNGHEZZA.get(cfg.lunghezza if cfg else "media", 600)
        try:
            esito = await self.motore.esegui(
                r.tipo, r.fascia, messaggi=messaggi, prompt=testo, max_token=max_token, solo_gratuiti=solo_gratuiti
            )
        except NessunFornitore:
            raise AINonDisponibile("fornitori_fermi") from None

        risposta = pulisci_uscita(esito.testo, 4000) if esito.testo else ""
        await self.repo.registra_uso(
            guild_conti, r.user_id, r.funzione, esito.fornitore, immagine=r.tipo == "immagine",
            token_in=esito.token_in, token_out=esito.token_out, costo_millesimi=esito.costo_millesimi,
        )
        if r.tipo == "immagine" and quote is not None and usa_credito_immagine(quote, uso):
            await self.repo.crediti_usa(guild_conti, r.user_id)
        if usa_cache and risposta:
            k = self.cache.metti(amb, r.tipo, istruzioni + r.lingua, testo, risposta)
            await self.repo.cache_metti(amb, k, r.tipo, risposta)
        if r.conversazione and risposta:
            self.memoria.aggiungi(r.conversazione, testo, risposta)
        return RispostaAI(testo=risposta, immagine=esito.immagine, fornitore=esito.fornitore)


_servizio: ServizioAI | None = None


def servizio_ai() -> ServizioAI:
    """Il servizio condiviso, costruito al primo uso dal `.env`."""
    global _servizio
    if _servizio is None:
        fornitori, scarti = leggi_fornitori()
        for motivo in scarti:
            logger.warning("Fornitore AI scartato: %s", motivo)
        _servizio = ServizioAI(MotoreAI(fornitori, TrasportoHTTP(), usa_pagamento=usa_chiavi_a_pagamento()))
    return _servizio


def imposta_servizio_ai(servizio: ServizioAI | None) -> None:
    """Sostituisce il servizio (test con fornitore finto, ricarica del `.env`)."""
    global _servizio
    _servizio = servizio

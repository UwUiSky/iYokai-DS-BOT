"""
core/ai_servizio.py
===================
La sola porta dei moduli verso l'AI. Ogni funzione dice tipo di lavoro,
fascia e se il testo contiene messaggi di utenti; qui si fanno, in ordine:
AI configurata e accesa nel server (consenso dell'admin), canale non
spento, privacy, richieste vietate, limite al minuto, cache e libreria,
quote e tetto di spesa (posto prenotato nel database), lore, dati personali tolti, chiamata, pulizia
della risposta, conti. Se l'AI non può rispondere, `AINonDisponibile`
porta il motivo e il testo da mostrare: ogni funzione ha la sua risposta
locale.
Funzioni coperte: SPEC §25.1–§25.4, §25.9, §25.12, §25.18–§25.20, §25.22, §25.23, §25.33, §25.48 (NF-24)
Dipende da: core/ai_router.py, core/ai_cache_logic.py, core/ai_guardrail_logic.py,
core/ai_cost_logic.py, core/ai_coda_logic.py, core/repositories/ai_repo.py
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, replace

from core.ai_cache_logic import LIBRERIA_COMUNE, CacheAI, ambito, chiave
from core.ai_coda_logic import CodaAI, CodaPiena
from core.ai_cost_logic import LimitatoreUtente, prova_attiva, prova_finita, stima_token
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
    "premium": "L'AI è una funzione premium: questo server non l'ha sbloccata. Accendendola con `/ai attiva` parte una prova gratuita.",
    "prova_finita": "La prova gratuita dell'AI è finita: per continuare serve il premium.",
    "manutenzione": "L'AI è in manutenzione: riprova più tardi. Il resto del bot funziona.",
    "coda_piena": "Ci sono troppe richieste AI in fila: riprova tra poco.",
    "coda_scaduta": "L'AI ci mette troppo a rispondere: riprova tra poco.",
    "spenta": "L'AI è spenta in questo server. Un amministratore può accenderla con `/ai attiva`.",
    "canale": "L'AI è spenta in questo canale.",
    "privacy": "Il server ha scelto di non mandare messaggi degli utenti all'AI.",
    "utente_spento": "Hai spento l'assistente AI per te: puoi riaccenderlo con `/utility ai preferenza`.",
    "vietata": "Questa richiesta non è permessa.",
    "troppe": "Troppe richieste in poco tempo: riprova tra un minuto.",
    "tetto": "Il server ha raggiunto il tetto di spesa del mese per l'AI.",
    "quota_utente": "Hai finito le richieste AI di oggi in questo server.",
    "quota_utente_30": "Hai finito le richieste AI gratuite di questo periodo: si rinnovano ogni 30 giorni.",
    "quota_funzione": "Questa funzione ha finito le richieste AI di oggi in questo server.",
    "quota_immagini": "Hai finito le immagini della settimana.",
    "fornitori_fermi": "I servizi AI sono occupati o fermi in questo momento. Riprova più tardi.",
}


async def ai_sbloccata(guild_id: int, prova_inizio, bot=None) -> bool:
    """
    Il server può usare l'AI: il modulo non è premium (D13), il server l'ha sbloccato o la prova
    gratuita è in corso (§25.23). Unico controllo per comandi, -chiedi, menzione e funzioni automatiche.
    """
    from core.premium import guild_has_premium_access, registry

    if not registry.is_module_premium("ai") or prova_attiva(prova_inizio):
        return True
    return await guild_has_premium_access(guild_id, "ai", bot=bot)


class AINonDisponibile(Exception):
    def __init__(self, motivo: str, dettaglio: str = "") -> None:
        super().__init__(motivo)
        self.motivo = motivo
        self.dettaglio = dettaglio

    @property
    def testo(self) -> str:
        base = MESSAGGI_LOCALI.get(self.motivo, MESSAGGI_LOCALI["fornitori_fermi"])
        return f"{base}\n{self.dettaglio}" if self.dettaglio else base


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
    # False per i lavori che il server fa da solo (moderazione, traduzione automatica):
    # non contano sulla quota della persona né sul suo limite al minuto.
    conta_utente: bool = True


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
        self.coda = CodaAI()
        self._manutenzione: tuple[float, str | None] = (0.0, None)
        self._preferenze: dict[int, tuple[float, bool]] = {}

    @property
    def configurato(self) -> bool:
        return self.motore.configurato

    async def controlla_accesso(self, guild_id: int | None, channel_id: int | None = None, tipo: str = "chat"):
        """La config del server se l'AI può lavorare lì, altrimenti `AINonDisponibile`."""
        if not self.motore.configurato or not self.motore.sa_fare(tipo):
            raise AINonDisponibile("non_configurata")
        avviso = await self._messaggio_manutenzione()
        if avviso is not None:
            raise AINonDisponibile("manutenzione", avviso)
        if guild_id is None:
            return None
        cfg = await self.repo.get_config(guild_id)
        if not cfg.attivo:
            raise AINonDisponibile("spenta")
        if not await ai_sbloccata(guild_id, cfg.prova_inizio):
            raise AINonDisponibile("prova_finita" if prova_finita(cfg.prova_inizio) else "premium")
        if channel_id is not None and channel_id in cfg.canali_spenti:
            raise AINonDisponibile("canale")
        return cfg

    async def _messaggio_manutenzione(self) -> str | None:
        """Il messaggio di manutenzione globale (None = in servizio). Letto dal database al più ogni 15 secondi."""
        scade, valore = self._manutenzione
        if time.monotonic() >= scade:
            valore = await self.repo.manutenzione()
            self._manutenzione = (time.monotonic() + 15, valore)
        return valore

    def ricarica_manutenzione(self) -> None:
        """Dopo un cambio dell'owner: il prossimo controllo rilegge il database."""
        self._manutenzione = (0.0, None)

    async def assistente_acceso(self, user_id: int) -> bool:
        """La preferenza personale (AI-R-094), letta dal database al più ogni 60 secondi per persona."""
        scade, valore = self._preferenze.get(user_id, (0.0, True))
        if time.monotonic() >= scade:
            valore = await self.repo.assistente_acceso(user_id)
            self._preferenze[user_id] = (time.monotonic() + 60, valore)
            if len(self._preferenze) > 5000:
                self._preferenze.clear()
        return valore

    def dimentica_preferenza(self, user_id: int) -> None:
        self._preferenze.pop(user_id, None)

    async def richiedi(self, r: RichiestaAI) -> RispostaAI:
        cfg = await self.controlla_accesso(r.guild_id, r.channel_id, r.tipo)
        if r.conta_utente and not await self.assistente_acceso(r.user_id):
            raise AINonDisponibile("utente_spento")
        if cfg is not None and r.messaggi_utenti and cfg.privacy == "senza_messaggi":
            raise AINonDisponibile("privacy")
        if richiesta_vietata(r.testo, cfg.parole_vietate if cfg else ()):
            raise AINonDisponibile("vietata")
        if r.conta_utente and not self.limitatore.consenti(r.user_id):
            raise AINonDisponibile("troppe")

        testo = pulisci_dati_personali(r.testo)
        lore = pulisci_dati_personali(testo_lore(cfg.lore_tema, cfg.lore_testo)) if cfg else ""
        istruzioni_pulite = pulisci_dati_personali(r.istruzioni)
        istruzioni = istruzioni_pulite + (f"\n[lore] {lore}" if lore else "")
        # La traduzione contiene il testo della persona: resta nel server, mai nella libreria comune.
        amb = ambito(r.guild_id, r.messaggi_utenti or r.tipo == "traduzione")
        usa_cache = r.riusa and r.conversazione is None and r.tipo != "immagine"
        if r.tipo == "traduzione" and amb == LIBRERIA_COMUNE:
            usa_cache = False
        if usa_cache:
            salvata = self.cache.trova(amb, r.tipo, istruzioni + r.lingua, testo)
            if salvata is None:
                salvata = await self.repo.cache_trova(amb, chiave(r.tipo, istruzioni + r.lingua, testo))
                if salvata is not None:
                    self.cache.metti(amb, r.tipo, istruzioni + r.lingua, testo, salvata)
            if salvata is not None:
                return RispostaAI(testo=salvata, da_cache=True)

        guild_conti = r.guild_id or 0
        utente_conti = r.user_id if r.conta_utente else 0
        esito, risposta = await self._chiama(r, cfg, testo, lore, istruzioni_pulite, guild_conti, utente_conti)

        if usa_cache and risposta:
            k = self.cache.metti(amb, r.tipo, istruzioni + r.lingua, testo, risposta)
            await self.repo.cache_metti(amb, k, r.tipo, risposta)
        if r.conversazione and risposta:
            self.memoria.aggiungi(r.conversazione, testo, risposta)
        return RispostaAI(testo=risposta, immagine=esito.immagine, fornitore=esito.fornitore)

    async def _chiama(self, r: RichiestaAI, cfg, testo, lore, istruzioni, guild_conti, utente_conti):
        quote = cfg.quote() if cfg else None
        if quote is not None and not r.conta_utente:
            quote = replace(quote, utente_giorno=0, utente_30_giorni=0)
        minuti = cfg.conservazione_minuti if cfg else 10
        storia = self.memoria.leggi(r.conversazione, minuti) if r.conversazione else []
        messaggi = componi_messaggi(istruzioni, testo, lore=lore, lingua=r.lingua, storia=storia)
        max_token = r.max_token or TOKEN_PER_LUNGHEZZA.get(cfg.lunghezza if cfg else "media", 600)

        # Quote e tetto: posto prenotato nel database prima della chiamata (atomico tra persone
        # e processi), poi confermato con i numeri veri o annullato se la chiamata non va.
        try:
            async with self.coda.posto(guild_conti):
                return await self._con_posto(r, quote, messaggi, max_token, guild_conti, utente_conti, testo)
        except CodaPiena as exc:
            raise AINonDisponibile(exc.motivo) from None

    async def _con_posto(self, r, quote, messaggi, max_token, guild_conti, utente_conti, testo):
        token_previsti = stima_token(" ".join(str(m.get("content", "")) for m in messaggi)) + max_token
        p = await self.repo.prenota(
            guild_conti, utente_conti, r.funzione, quote=quote, immagine=r.tipo == "immagine",
            costo_stimato=self.motore.costo_massimo(r.tipo, token_previsti),
        )
        if p.motivo:
            raise AINonDisponibile(p.motivo)
        try:
            esito = await self.motore.esegui(
                r.tipo, r.fascia, messaggi=messaggi, prompt=testo, max_token=max_token, solo_gratuiti=p.solo_gratuiti
            )
        except BaseException as exc:
            await self.repo.annulla(p)
            if isinstance(exc, NessunFornitore):
                raise AINonDisponibile("fornitori_fermi") from None
            raise

        risposta = pulisci_uscita(esito.testo, 4000) if esito.testo else ""
        await self.repo.conferma(
            p, esito.fornitore, token_in=esito.token_in, token_out=esito.token_out, costo_millesimi=esito.costo_millesimi
        )
        return esito, risposta


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


async def imposta_manutenzione_ai(acceso: bool, messaggio: str, user_id: int | None) -> None:
    """Il solo punto che mette l'AI in manutenzione (o la rimette in servizio): `/ai manutenzione` e pannello web."""
    servizio = servizio_ai()
    await servizio.repo.imposta_manutenzione(acceso, messaggio.strip()[:300], user_id)
    servizio.ricarica_manutenzione()


def imposta_servizio_ai(servizio: ServizioAI | None) -> None:
    """Sostituisce il servizio (test con fornitore finto, ricarica del `.env`)."""
    global _servizio
    _servizio = servizio

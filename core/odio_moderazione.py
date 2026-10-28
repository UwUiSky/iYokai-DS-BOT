"""
core/odio_moderazione.py
========================
Giudizio su una parola sospetta (D35): l'AI guarda il contesto («Simone Negri lavora
al supermercato» passa, un insulto no). Con l'AI ferma, spenta, senza consenso o in
errore vale il lato sicuro: il messaggio si cancella. Il testo e' pulito dai dati
personali dal servizio AI prima dell'invio (D19); il lavoro e' «moderazione» e non conta
sulla quota della persona. Le decisioni si ricordano per frase normalizzata.
Una parola offensiva che l'AI indica e che i filtri non conoscono va in libreria come candidata.
Funzioni coperte: SPEC §6 (D35)
Dipende da: core/ai_servizio.py, core/odio_giudizio_logic.py, core/odio_libreria_service.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core import automod_parole_opzioni as opzioni_parole
from core.ai_servizio import AINonDisponibile, RichiestaAI, servizio_ai
from core.automod_parole_logic import pezzi, trova
from core.odio_giudizio_logic import ISTRUZIONI, MAX_TESTO_AI, CacheGiudizi, Giudizio, leggi_risposta
from core.odio_libreria_service import libreria_odio

logger = logging.getLogger("iyokai.odio_moderazione")

FUNZIONE_AI = "moderazione_odio"

AZIONE_PASSA = "passa"
AZIONE_CANCELLA = "cancella"

MOTIVO_AI = "ai"
MOTIVO_CACHE = "cache"
MOTIVO_AI_FERMA = "ai_ferma"  # spenta, senza consenso, quota finita, fornitori fermi, errore
MOTIVO_AI_INCERTA = "ai_incerta"  # risposta non leggibile

cache_giudizi = CacheGiudizi()


@dataclass(frozen=True)
class Esito:
    azione: str
    motivo: str
    giudizio: Giudizio | None = None

    @property
    def cancella(self) -> bool:
        return self.azione == AZIONE_CANCELLA


async def giudica_sospetta(
    guild_id: int, channel_id: int, user_id: int, testo: str, servizio=None, cache: CacheGiudizi | None = None
) -> Esito:
    """Cancellare il messaggio o lasciarlo passare. Non solleva mai: ogni problema e' il lato sicuro."""
    cache = cache if cache is not None else cache_giudizi
    salvato = cache.trova(guild_id, testo)
    if salvato is not None:
        return Esito(AZIONE_CANCELLA if salvato.insulto else AZIONE_PASSA, MOTIVO_CACHE, salvato)
    try:
        servizio = servizio or servizio_ai()
        risposta = await servizio.richiedi(RichiestaAI(
            user_id=user_id, funzione=FUNZIONE_AI, tipo="giudizio", testo=testo[:MAX_TESTO_AI],
            guild_id=guild_id, channel_id=channel_id, fascia="bassa", istruzioni=ISTRUZIONI,
            messaggi_utenti=True, conta_utente=False, max_token=120,
        ))
    except AINonDisponibile as errore:
        logger.info("AI non disponibile per il giudizio (%s): lato sicuro", errore.motivo)
        return Esito(AZIONE_CANCELLA, MOTIVO_AI_FERMA)
    except Exception:
        logger.exception("Errore nel giudizio dell'AI: lato sicuro")
        return Esito(AZIONE_CANCELLA, MOTIVO_AI_FERMA)
    giudizio = leggi_risposta(risposta.testo)
    if giudizio is None:
        return Esito(AZIONE_CANCELLA, MOTIVO_AI_INCERTA)
    cache.metti(guild_id, testo, giudizio)
    return Esito(AZIONE_CANCELLA if giudizio.insulto else AZIONE_PASSA, MOTIVO_AI, giudizio)


async def segnala_varianti(guild_id: int, testo: str, giudizio: Giudizio, archivio=None) -> int:
    """
    Le parole offensive indicate dall'AI che i filtri non conoscono vanno in libreria come candidate.
    Si accetta solo una parola che sta davvero nel messaggio: l'AI non puo' inventarne di nuove.
    Restituisce quante ne sono state segnalate.
    """
    if not giudizio.insulto or not giudizio.parole:
        return 0
    presenti = set(pezzi(testo))
    filtro, _ = await opzioni_parole.filtro_del_server(guild_id, archivio)
    sospette, _ = await opzioni_parole.filtro_sospette(guild_id, archivio)
    nuove = []
    for parola in giudizio.parole:
        parti = pezzi(parola)
        if not parti or not set(parti) <= presenti:
            continue
        if trova(parola, filtro) is not None or trova(parola, sospette) is not None:
            continue
        nuove.append(parola)
    if not nuove:
        return 0
    return len(await libreria_odio.segnala(guild_id, tuple(nuove), giudizio.lingua))

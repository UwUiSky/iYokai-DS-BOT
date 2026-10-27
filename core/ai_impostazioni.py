"""
core/ai_impostazioni.py
=======================
Il punto unico (D16) per le scelte AI di un server che comandi `/ai` e pannello
web cambiano allo stesso modo: accensione con il consenso (e prova gratuita),
privacy, memoria, lunghezza delle risposte e quote. Valida, scrive e ripulisce.
Funzioni coperte: SPEC §24.2, §24.3, §25.4, §25.23, §25.82 (NF-20, NF-24)
Dipende da: core/repositories/ai_repo.py, core/ai_cost_logic.py, core/ai_servizio.py
"""

from __future__ import annotations

from core.ai_cost_logic import GIORNI_PROVA, prova_attiva
from core.config_schema import ImpostazioneNonValida

TESTO_CONSENSO = (
    "Accendendo l'AI, i testi delle richieste (e, per riassunti, ticket e moderazione, i messaggi "
    "degli utenti) vengono mandati ai fornitori AI configurati dal proprietario del bot. Si usano "
    "solo fornitori che dichiarano di **non addestrare** modelli con ciò che ricevono. Prima "
    "dell'invio si tolgono menzioni, ID, e-mail e inviti. L'AI propone, una persona decide: "
    "nessuna punizione parte da sola. Puoi spegnere tutto in ogni momento."
)

PRIVACY = ("completa", "senza_messaggi")
LUNGHEZZE = ("corta", "media", "lunga")
# campo del database -> (minimo, massimo, nome per l'utente)
INTERVALLI = {
    "conservazione_minuti": (0, 1440, "La memoria della conversazione (minuti)"),
    "tetto_mensile_cent": (0, 1_000_000, "Il tetto di spesa (centesimi)"),
    "quota_utente_giorno": (0, 10_000, "Le richieste al giorno per persona"),
    "quota_utente_30g": (0, 100_000, "Le richieste ogni 30 giorni per persona"),
    "quota_funzione_giorno": (0, 100_000, "Le richieste al giorno per funzione"),
    "quota_immagini_settimana": (0, 1000, "Le immagini a settimana per persona"),
    "prezzo_pacchetto_immagini": (0, 100_000_000, "Il prezzo del pacchetto di immagini"),
}


def valida_scelte(campi: dict) -> dict:
    """I soli campi ammessi, già controllati. Rifiuta con un testo pronto per l'utente."""
    puliti: dict = {}
    for nome, valore in campi.items():
        if nome == "privacy":
            if valore not in PRIVACY:
                raise ImpostazioneNonValida("Privacy non valida: scegli " + " o ".join(PRIVACY) + ".")
        elif nome == "lunghezza":
            if valore not in LUNGHEZZE:
                raise ImpostazioneNonValida("Lunghezza non valida: scegli " + ", ".join(LUNGHEZZE) + ".")
        elif nome in INTERVALLI:
            minimo, massimo, titolo = INTERVALLI[nome]
            if isinstance(valore, bool) or not isinstance(valore, int) or not minimo <= valore <= massimo:
                raise ImpostazioneNonValida(f"{titolo} deve essere un numero da {minimo} a {massimo}.")
        else:
            raise ImpostazioneNonValida("Scelta sconosciuta.")
        puliti[nome] = valore
    if not puliti:
        raise ImpostazioneNonValida("Indica almeno un valore.")
    return puliti


async def imposta_scelte(guild_id: int, **campi):
    """Salva privacy, memoria, lunghezza o quote. Memoria a 0: la conversazione in corso si dimentica."""
    from core.ai_servizio import servizio_ai
    from core.repositories.ai_repo import ai_repo

    puliti = valida_scelte(campi)
    cfg = await ai_repo.imposta(guild_id, **puliti)
    if puliti.get("conservazione_minuti") == 0:
        servizio_ai().memoria.dimentica(guild_id)
    return cfg


async def _serve_la_prova(guild_id: int) -> bool:
    """L'AI è premium e il server non l'ha sbloccata: vale la prova (una volta sola)."""
    from core.premium import guild_has_premium_access, registry

    return registry.is_module_premium("ai") and not await guild_has_premium_access(guild_id, "ai")


async def accendi_ai(guild_id: int, user_id: int) -> str:
    """
    Dà il consenso e accende l'AI. Chiamare solo dopo che la persona ha letto il testo del
    consenso (bottone o casella). Se l'AI è premium e non sbloccata parte la prova gratuita.
    Restituisce il testo da mostrare.
    """
    from core.repositories.ai_repo import ai_repo

    await ai_repo.registra_consenso(guild_id, user_id, True)
    testo = "AI accesa in questo server."
    if await _serve_la_prova(guild_id):
        prima = await ai_repo.get_config(guild_id)
        cfg = await ai_repo.avvia_prova(guild_id)
        if prima.prova_inizio is None:
            testo += f" L'AI è premium: parte una prova gratuita di {GIORNI_PROVA} giorni."
        elif not prova_attiva(cfg.prova_inizio):
            testo += " La prova gratuita è già finita: per usare l'AI serve il premium."
    return testo


async def spegni_ai(guild_id: int, user_id: int) -> str:
    from core.repositories.ai_repo import ai_repo

    await ai_repo.registra_consenso(guild_id, user_id, False)
    return "AI spenta in questo server."

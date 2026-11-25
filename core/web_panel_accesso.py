"""
core/web_panel_accesso.py
=========================
Chi può usare il pannello web di un server e con quali limiti. Livelli: «admin» (Gestisci server, ruolo admin
del bot, proprietario: scrivono sempre e decidono i ruoli del pannello), «scrittura» e «lettura» (ruoli scelti dal
server, diversi dagli admin di Discord). In più la politica dei comandi del server (spegnere un comando, ruoli
richiesti o ignorati) vale anche per le scritture del pannello: ogni area del pannello ha il gruppo di comandi
che la rispecchia.
Funzioni coperte: SPEC §24.8 (CFG-002, CFG-027, issue #122)
Dipende da: core/command_policy.py, core/command_groups.py, core/repositories/web_panel_ruoli_repo.py
"""

from __future__ import annotations

import asyncio
import logging

from core import command_policy
from core.config_schema import ImpostazioneNonValida
from core.database import db

logger = logging.getLogger("iyokai.web_panel_accesso")

LETTURA = "lettura"
SCRITTURA = "scrittura"
ADMIN = "admin"
LIVELLI_RUOLO = (LETTURA, SCRITTURA)
MAX_RUOLI_PER_LIVELLO = 10

# --- La tabella unica «rotta -> livello» (blocco A, voce 2) ---------------------------------------------------
# Ogni rotta registrata nel pannello sta qui, con chi la può usare. Il middleware del pannello legge questa tabella
# (una rotta che non c'è viene rifiutata) e `_server` non scende mai sotto il livello scritto qui: un handler
# dimenticato non apre niente. Un test controlla che ogni rotta registrata ci sia, e prova ogni rotta con
# lettura, scrittura, admin ed estraneo.
PUBBLICA = "pubblica"          # senza accesso: pagine pubbliche e di ingresso
SESSIONE = "sessione"          # serve solo aver fatto l'accesso (pagine personali)
PROPRIETARIO = "proprietario"  # solo il proprietario del bot
DESKTOP = "desktop"            # API di iYokai Desktop: ha il suo token (core/desktop_api.py)
LIVELLI_SERVER = (LETTURA, SCRITTURA, ADMIN)  # per le rotte /server/<id>/...: livello minimo nel server

_SERVER = "/server/{guild_id}"
_VOCI: dict[str, tuple[str, ...]] = {
    PUBBLICA: (
        "GET /", "GET /accedi", "GET /callback", "POST /esci", "GET /allegato/{token}", "GET /static/pannello.css",
        "GET /static/{nome}", "GET /privacy", "GET /termini", "GET /wiki", "GET /wiki/{percorso}", "GET /api/v1/stats",
        "GET /invito/{slug}", "GET /stats/{guild_id}", "GET /n/{guild_id}", "GET /c/{slug}", "GET /tela/{guild_id}",
        "GET /tela/{guild_id}/immagine.png", "GET /attivita/radio", "GET /attivita/radio/stato", "GET /modelli",
        "GET /join/{nome}", "GET /join/{nome}/accedi", "GET /join/{nome}/colori.css", "GET /verifica/{token}",
        "POST /verifica/{token}",
    ),
    SESSIONE: (
        "GET /miei-dati", "POST /miei-dati", "GET /miei-inviti", "POST /miei-inviti",
        "GET /istantanea/{segreto}", "POST /join/{nome}/avvia", "GET /ruoli-collegati", "POST /ruoli-collegati/avvia",
        "POST /ruoli-collegati/verifica/avvia", "POST /ruoli-collegati/verifica/scollega",
        "POST /ruoli-collegati/connessioni/avvia", "POST /ruoli-collegati/connessioni/dimentica",
        "GET /ruoli-collegati/twitch", "GET /ruoli-collegati/discord", "POST /ruoli-collegati/scollega",
        "GET /premium", "POST /premium/patreon/collega", "POST /premium/patreon/scollega",
    ),
    PROPRIETARIO: (
        "GET /proprietario", "POST /proprietario/ai", "POST /proprietario/premium", "GET /proprietario/storico-vpn",
        "GET /proprietario/modelli", "GET /proprietario/modelli/{modello}",
        "POST /proprietario/modelli/{modello}/decidi", "POST /proprietario/modelli/{modello}/modifica",
    ),
    DESKTOP: (
        "GET /api/desktop/io", "GET /api/desktop/server", "GET /api/desktop/eventi", "GET /api/desktop/storico",
        "GET /api/desktop/risposte", "POST /api/desktop/traduci", "GET /api/desktop/staff/azioni",
        "POST /api/desktop/staff/azione", "GET /api/desktop/radio",
    ),
    # Solo admin: ruoli del bot, moduli (accendere e spegnere), marchio, aspetto, permessi, lingua, chi usa il
    # pannello, backup e ripristino, impostazioni che toccano dati e chiavi del server.
    ADMIN: tuple(
        f"{m} {_SERVER}{p}" for m, p in (
            ("POST", "/modulo"), ("POST", "/ruolo"), ("POST", "/lingua"), ("POST", "/permessi"),
            ("GET", "/accesso"), ("POST", "/accesso"),
            ("GET", "/marchio"), ("POST", "/marchio"),
            ("GET", "/aspetto"), ("POST", "/aspetto"), ("POST", "/aspetto/immagine"),
            ("GET", "/backup"), ("GET", "/backup/{copia}"), ("GET", "/backup/{copia}/elimina"), ("POST", "/backup/{copia}/elimina"),
            ("GET", "/join"), ("POST", "/join"),
            ("GET", "/statistiche"), ("POST", "/statistiche"), ("GET", "/classifica"), ("POST", "/classifica"),
            ("GET", "/api"), ("POST", "/api"),
            ("POST", "/ticket/trascrizioni/opzioni"),
        )
    ),
    SCRITTURA: tuple(
        f"POST {_SERVER}{p}" for p in (
            "/modulo/{nome}", "/ai", "/ai/altro", "/ai/interruttori", "/inviti", "/vocali", "/editor/embed",
            "/editor/benvenuto", "/ticket/{ticket}/rispondi",
        )
    ),
    LETTURA: tuple(
        f"GET {_SERVER}{p}" for p in (
            "", "/panoramica", "/storico", "/premium", "/modulo/{nome}", "/ai", "/ai/altro", "/ai/interruttori",
            "/ai/riepilogo", "/ai/uso", "/inviti", "/vocali", "/editor/embed", "/editor/benvenuto", "/ticket",
            "/ticket/{ticket}", "/ticket/{ticket}/stato", "/ticket/trascrizioni", "/ticket/trascrizioni/{id}",
            "/moderazione/archivio/{caso}", "/avvisi",
        )
    ) + (f"POST {_SERVER}/avvisi",),  # le preferenze di chi guarda, non del server: bastano a chi vede il pannello
}
TABELLA_ROTTE: dict[tuple[str, str], str] = {}
for _livello, _voci in _VOCI.items():
    for _voce in _voci:
        _metodo, _percorso = _voce.split(" ", 1)
        if (_metodo, _percorso) in TABELLA_ROTTE:  # un doppione è un errore di chi scrive la tabella: il bot non parte
            raise ValueError(f"rotta doppia nella tabella del pannello: {_voce}")
        TABELLA_ROTTE[(_metodo, _percorso)] = _livello


def livello_rotta(metodo: str, canonico: str) -> str | None:
    """Il livello della rotta (HEAD vale come GET), o None se la tabella non la conosce: chi chiama la rifiuta."""
    return TABELLA_ROTTE.get(("GET" if metodo == "HEAD" else metodo, canonico))


# Area del pannello (secondo pezzo del percorso /server/<id>/<area>) -> gruppo di comandi che la rispecchia.
GRUPPO_PER_AREA = {
    "ai": "admin-ai",
    "inviti": "admin-inviti",
    "benvenuto": "admin-benvenuto",
    "vocali": "admin-vocali",
    "embed": "admin-messaggi",
    "backup": "admin-backup",
    "ticket": "admin-ticket",
}
# Modulo (pagina /server/<id>/modulo/<nome>) -> gruppo di comandi.
GRUPPO_PER_MODULO = {
    "verify": "admin-sicurezza",
    "music": "admin-musica",
    "tickets": "admin-ticket",
    "moderation_actions": "mod-sanzioni",
    "moderation_report": "mod-sanzioni",
    "automod": "admin-automod",
    "invites": "admin-inviti",
    "custom_commands": "admin-messaggi-tag",
    "suggestions": "admin-moduli",
    "spam_trap": "admin-sicurezza",
    "fun": "admin-moduli",
}

_blocchi: dict[int, asyncio.Lock] = {}


def percorso_comando(percorso_http: str, nome_modulo: str | None = None) -> str | None:
    """Il gruppo di comandi che rispecchia la pagina, o None (le pagine dell'impianto del bot restano sempre aperte)."""
    pezzi = [p for p in percorso_http.split("/") if p]
    if len(pezzi) >= 3 and pezzi[0] == "server":
        if pezzi[2] == "modulo":
            nome = nome_modulo or (pezzi[3] if len(pezzi) > 3 else None)
            return GRUPPO_PER_MODULO.get(nome or "")
        return GRUPPO_PER_AREA.get(pezzi[2])
    return None


def livello_da_ruoli(ruoli_utente: set[int], ruoli_pannello: dict[str, frozenset[int]]) -> str | None:
    """«scrittura» batte «lettura»; nessun ruolo = None."""
    if ruoli_utente & ruoli_pannello.get(SCRITTURA, frozenset()):
        return SCRITTURA
    if ruoli_utente & ruoli_pannello.get(LETTURA, frozenset()):
        return LETTURA
    return None


def basta(livello: str | None, richiesto: str) -> bool:
    """Un admin scrive e legge; la scrittura legge; la lettura solo legge."""
    ordine = {None: 0, LETTURA: 1, SCRITTURA: 2, ADMIN: 3}
    return ordine.get(livello, 0) >= ordine[richiesto]


async def leggi_ruoli(guild_id: int) -> dict[str, frozenset[int]]:
    from core.repositories.web_panel_ruoli_repo import web_panel_ruoli_repo

    return await web_panel_ruoli_repo.leggi(guild_id)


async def imposta_ruoli(guild, livello: str, ruoli_ids: list[int], changed_by: int | None) -> bool:
    """
    Sostituisce i ruoli di un livello. Controlli: livello noto, ruoli del server (non @everyone, non gestiti),
    al massimo 10, nessun doppione. True se qualcosa è cambiato. Storto = ImpostazioneNonValida.
    """
    from core.repositories.web_panel_ruoli_repo import web_panel_ruoli_repo

    if livello not in LIVELLI_RUOLO:
        raise ImpostazioneNonValida("Livello non valido.")
    unici = list(dict.fromkeys(ruoli_ids))
    if len(unici) > MAX_RUOLI_PER_LIVELLO:
        raise ImpostazioneNonValida(f"Al massimo {MAX_RUOLI_PER_LIVELLO} ruoli per livello.")
    for ruolo_id in unici:
        ruolo = guild.get_role(ruolo_id)
        if ruolo is None or ruolo.id == guild.id or getattr(ruolo, "managed", False):
            raise ImpostazioneNonValida("Ruolo non valido per questo server.")
    blocco = _blocchi.setdefault(guild.id, asyncio.Lock())
    async with blocco:
        prima = await web_panel_ruoli_repo.leggi(guild.id)
        if prima[livello] == frozenset(unici):
            return False
        await web_panel_ruoli_repo.sostituisci(guild.id, livello, unici, changed_by)
    try:
        await db._record_config_change(
            guild.id, changed_by, "setting", f"panel_ruoli_{livello}", sorted(prima[livello]), unici
        )
    except Exception:  # lo storico non deve far fallire il salvataggio
        logger.warning("Storico dei ruoli del pannello non scritto nel server %s.", guild.id, exc_info=True)
    return True


async def policy_blocca(guild, membro, percorso: str | None, *, esente: bool) -> bool:
    """
    CFG-027: True se la politica dei comandi del server vieta questa azione a questa persona. Nessun canale
    (il pannello non è in un canale). Mai eccezioni: una politica rotta non chiude il pannello.
    """
    if percorso is None:
        return False
    try:
        politica = await command_policy.leggi_politica(guild.id)
        if politica.vuota:
            return False
        motivo = command_policy.valuta(
            politica, percorso=percorso, canali=[], ruoli=[r.id for r in getattr(membro, "roles", ())],
            user_id=membro.id, esente=esente,
        )
    except Exception:  # noqa: BLE001
        logger.warning("Politica dei comandi non leggibile nel server %s.", guild.id, exc_info=True)
        return False
    return motivo is not None

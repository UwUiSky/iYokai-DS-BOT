"""
core/invite_links_logic.py
==========================
Parte pura dei link d'invito personali «finto vanity» (nomi dell'indirizzo, tipo di ingresso,
chi può avere il link). Niente Discord e niente database: si prova con test semplici.
Funzioni coperte: SPEC §23 (NF-27, link personali r10)
"""

from __future__ import annotations

import re
import unicodedata

# Tipi di ingresso salvati in invite_joins.kind
TIPO_PERSONALE = "personale"
TIPO_NORMALE = "normale"
TIPO_VANITY = "vanity"
TIPO_SCONOSCIUTO = "sconosciuto"
TIPI_INGRESSO = (TIPO_PERSONALE, TIPO_NORMALE, TIPO_VANITY, TIPO_SCONOSCIUTO)
ETICHETTE_TIPO = {
    TIPO_PERSONALE: "link personale dal sito",
    TIPO_NORMALE: "invito normale",
    TIPO_VANITY: "indirizzo personalizzato del server",
    TIPO_SCONOSCIUTO: "invito sconosciuto",
}

SETTING_CANALE_LOG = "inviti_log_channel_id"
SETTING_RUOLO_LINK = "inviti_link_role_id"

MAX_PARTE = 30  # lettere per il nome del server e per quello dell'utente
MAX_SLUG = 80
MAX_TENTATIVI_SLUG = 50
FORMA_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,78}[a-z0-9])$")

# Esiti per chi chiede il link (testi in `testo_esito`).
OK = "ok"
MODULO_SPENTO = "modulo_spento"
RUOLO_MANCANTE = "ruolo_mancante"
NON_NEL_SERVER = "non_nel_server"
INVITI_DISABILITATI = "inviti_disabilitati"
SENZA_PERMESSO = "senza_permesso"
NESSUN_CANALE = "nessun_canale"
ERRORE_DISCORD = "errore_discord"

_TESTI_ESITO = {
    MODULO_SPENTO: "Il modulo inviti non è attivo su questo server.",
    RUOLO_MANCANTE: "Su questo server il link personale è riservato a un ruolo che non hai.",
    NON_NEL_SERVER: "Non risulti membro di questo server.",
    INVITI_DISABILITATI: "Questo server ha messo in pausa gli inviti: i link personali non funzionano finché non li riattiva.",
    SENZA_PERMESSO: "Il bot non ha il permesso «Crea invito» in nessun canale: un amministratore deve darglielo.",
    NESSUN_CANALE: "Il bot non trova un canale dove creare l'invito.",
    ERRORE_DISCORD: "Discord non ha creato l'invito: riprova tra poco.",
}


def testo_esito(esito: str) -> str:
    return _TESTI_ESITO.get(esito, "Non è stato possibile.")


def slugifica(testo: str, massimo: int = MAX_PARTE) -> str:
    """Minuscolo, solo a-z 0-9 e trattini (le lettere accentate perdono l'accento)."""
    base = unicodedata.normalize("NFKD", str(testo)).encode("ascii", "ignore").decode("ascii").lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base[:massimo].strip("-")


def slug_base(nome_server: str, nome_utente: str) -> str:
    """`<nome-server>-<nome-utente>`; se un nome non ha lettere si usa un segnaposto fisso."""
    server = slugifica(nome_server) or "server"
    utente = slugifica(nome_utente) or "membro"
    return f"{server}-{utente}"[:MAX_SLUG].strip("-")


def slug_con_suffisso(base: str, numero: int) -> str:
    """La prima volta il nome pulito, poi `-2`, `-3`… (sempre entro MAX_SLUG)."""
    if numero <= 1:
        return base
    coda = f"-{numero}"
    return base[: MAX_SLUG - len(coda)].strip("-") + coda


def slug_valido(slug: str) -> bool:
    return isinstance(slug, str) and len(slug) <= MAX_SLUG and FORMA_SLUG.fullmatch(slug) is not None


def tipo_ingresso(codice: str | None, *, codice_vanity: str | None, link_personale: bool) -> str:
    """Come è entrato un membro, dal codice che il tracker ha riconosciuto."""
    if codice is None:
        return TIPO_SCONOSCIUTO
    if link_personale:
        return TIPO_PERSONALE
    if codice_vanity and codice == codice_vanity:
        return TIPO_VANITY
    return TIPO_NORMALE


def ruolo_ammesso(ruolo_richiesto: int | None, ruoli_membro: set[int]) -> bool:
    """Senza ruolo richiesto il link è di tutti."""
    return ruolo_richiesto is None or ruolo_richiesto in ruoli_membro


def indirizzo_link(url_pubblico: str, slug: str) -> str:
    return f"{url_pubblico.rstrip('/')}/invito/{slug}"


def indirizzo_discord(codice: str) -> str:
    return f"https://discord.gg/{codice}"

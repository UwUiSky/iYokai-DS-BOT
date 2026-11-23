"""
core/rete_protezione_logic.py
=============================
Regole pure della rete di protezione tra server (VER-025, D111, D112): quali motivi sono «gravi», chi può segnalare,
tetti anti-spam, durata del timeout, chi non si colpisce mai. Nessun Discord e nessun database: si prova con i test.
Funzioni coperte: SPEC §6.22 (VER-025)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

CATEGORIE = ("truffa", "raggiro", "frode", "spam_server", "tossicita_grave", "account_compromesso")
GRAVITA = ("media", "alta", "critica")
GRAVITA_DI_BASE = {
    "truffa": "alta", "raggiro": "alta", "frode": "alta", "spam_server": "media",
    "tossicita_grave": "alta", "account_compromesso": "critica",
}

# Parole che, nel motivo di un caso, dicono la categoria. Il testo del caso non lascia mai il server d'origine.
_PAROLE = (
    ("account_compromesso", ("account compromesso", "account rubato", "account hackerato")),
    ("truffa", ("truffa", "phishing", "scam", "link malevoli")),
    ("raggiro", ("raggiro", "social engineering")),
    ("frode", ("frode", "fraudolent")),
    ("spam_server", ("inviti ad altri server", "invito ad altri server", "spam di server", "pubblicita' di server", "pubblicità di server")),
    ("tossicita_grave", ("minacce gravi", "minacce", "molestie", "discriminazione", "incitamento all'odio", "odio razziale")),
)

AZIONI_CHE_SEGNALANO = frozenset({"ban", "tempban", "softban", "kick", "timeout", "mute_role", "isolamento"})  # un avviso (warn) o una nota non bastano
MIN_MEMBRI_ORIGINE = 50  # un server piccolo o fatto apposta non fa partire avvisi
MIN_GIORNI_BOT_ORIGINE = 7  # il bot deve essere nel server da almeno una settimana
TETTO_CONSEGNE_AL_GIORNO = 5  # avvisi che un server può ricevere in un giorno, da tutti
TETTO_SEGNALAZIONI_ORIGINE_AL_GIORNO = 10  # avvisi che un server può far partire in un giorno
PAUSA_STESSO_UTENTE_ORE = 24  # lo stesso utente e la stessa categoria non si segnalano due volte nello stesso giorno
MAX_SERVER_PER_SEGNALAZIONE = 100  # tetto di server avvisati per una sola segnalazione
TIMEOUT_ORE_BASE = 24
TIMEOUT_ORE_MAX = 28 * 24  # limite di Discord: 28 giorni
MAX_MOTIVO = 512


def categoria_da_motivo(motivo: str | None) -> str | None:
    """La categoria grave che il motivo di un caso racconta, o None se non è grave. Nessun altro dato esce dal caso."""
    testo = (motivo or "").casefold()
    if not testo:
        return None
    for categoria, parole in _PAROLE:
        if any(p in testo for p in parole):
            return categoria
    return None


def gravita_di(categoria: str, azione: str = "") -> str:
    """Gravità dell'avviso: quella della categoria; un ban alza di un gradino (non oltre «critica»)."""
    base = GRAVITA_DI_BASE.get(categoria, "media")
    if azione == "ban" and base != "critica":
        return GRAVITA[GRAVITA.index(base) + 1]
    return base


def origine_puo_segnalare(
    membri: int, bot_entrato_il: datetime | None, ora: datetime, bloccato: bool, segnalazioni_oggi: int = 0
) -> str | None:
    """Codice del rifiuto («bloccato», «piccolo», «nuovo», «tetto»), o None se il server può far partire un avviso."""
    if bloccato:
        return "bloccato"
    if membri < MIN_MEMBRI_ORIGINE:
        return "piccolo"
    if bot_entrato_il is None or ora - _con_fuso(bot_entrato_il) < timedelta(days=MIN_GIORNI_BOT_ORIGINE):
        return "nuovo"
    if segnalazioni_oggi >= TETTO_SEGNALAZIONI_ORIGINE_AL_GIORNO:
        return "tetto"
    return None


def _con_fuso(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def destinazione_puo_ricevere(ricezione: bool, consegne_oggi: int) -> bool:
    """Un server che ha spento la ricezione, o che ha già raggiunto il tetto del giorno, non riceve."""
    return ricezione and consegne_oggi < TETTO_CONSEGNE_AL_GIORNO


def ore_timeout_valide(ore) -> int:
    """Ore di timeout scelte dal server, portate nei limiti (da 1 ora a 28 giorni). Valore strano = base."""
    if isinstance(ore, bool) or not isinstance(ore, int):
        return TIMEOUT_ORE_BASE
    return max(1, min(ore, TIMEOUT_ORE_MAX))


def timeout_fino_a(ora: datetime, ore: int) -> datetime:
    return _con_fuso(ora) + timedelta(hours=ore_timeout_valide(ore))


def bot_puo_colpire(
    *, e_proprietario: bool, e_bot: bool, e_il_nostro_bot: bool, bot_sopra: bool, bot_ha_permesso: bool
) -> str | None:
    """Codice del rifiuto, o None se il bot può agire sul membro: mai proprietari, mai bot, mai sé stesso; gerarchia e permesso."""
    if e_proprietario:
        return "proprietario"
    if e_bot or e_il_nostro_bot:
        return "bot"
    if not bot_ha_permesso:
        return "permesso"
    if not bot_sopra:
        return "gerarchia"
    return None


def motivo_rete(categoria: str, origine_nome: str | None = None) -> str:
    """Motivo del caso scritto nei server colpiti dalla rete: categoria sì, testi dell'utente mai. Entro 512 caratteri."""
    base = f"Rete di protezione: account compromesso ({categoria})"
    if origine_nome:
        base += f", segnalato da {origine_nome}"
    return base[:MAX_MOTIVO]


def puo_togliere_timeout(*, e_proprietario_bot: bool, e_proprietario_server: bool) -> bool:
    """L'owner del bot e gli owner dei server possono togliere il timeout messo dalla rete."""
    return e_proprietario_bot or e_proprietario_server


def proposta_ammessa(*, origine: int, destinazione: int, origine_aderisce: bool, dest_aderisce: bool, origine_caso: str) -> str | None:
    """Rete dei ban. Codice del rifiuto o None. Un ban nato dalla rete non fa partire altri ban (niente catene)."""
    if origine_caso == "rete":
        return "catena"
    if origine == destinazione:
        return "stesso_server"
    if not origine_aderisce or not dest_aderisce:
        return "non_aderente"
    return None

"""
core/security_join_logic.py
===========================
Logica degli ingressi per l'anti-raid, senza Discord: filtri con azione
propria (età, bot non verificati, nomi pubblicitari, nomi vietati), segnali
di raid sugli ultimi ingressi (account creati vicini, nomi simili), registro
in memoria degli ultimi ingressi e segnale di rete tra server.
Funzioni coperte: SPEC §7.1 (SIC-023, 024, 026–031, 033, 035, 037, 038)
"""

from __future__ import annotations

import fnmatch
import re
import unicodedata
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher

from core.bounded_cache import BoundedCache

# ---------------------------------------------------------------- filtri
FILTRO_ETA = "eta"
FILTRO_BOT_NON_VERIFICATO = "bot_non_verificato"
FILTRO_NOME_PUBBLICITARIO = "nome_pubblicitario"
FILTRO_NOME_VIETATO = "nome_vietato"
FILTRI_INGRESSO = (FILTRO_ETA, FILTRO_BOT_NON_VERIFICATO, FILTRO_NOME_PUBBLICITARIO, FILTRO_NOME_VIETATO)

AZIONE_NIENTE = "niente"
AZIONI_FILTRO = (AZIONE_NIENTE, "quarantena", "timeout", "kick", "ban")
# Ordine di gravità: se scattano più filtri vale l'azione più forte.
_GRAVITA = {azione: i for i, azione in enumerate(AZIONI_FILTRO)}

MAX_NOMI_VIETATI = 100
MAX_SCHEMA = 64
MAX_MESSAGGIO_DM = 500

_INVITO_NEL_NOME = re.compile(
    r"(?:discord(?:app)?\s*\.\s*(?:gg|com\s*/\s*invite)|\.gg\s*/|dsc\s*\.\s*gg)", re.IGNORECASE
)


def normalizza_nome(nome: str) -> str:
    """Minuscole, accenti tolti, solo lettere e cifre."""
    testo = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", testo)


def nome_pubblicitario(nomi) -> bool:
    """Un invito Discord nel nome utente o nel nome visualizzato (SIC-027)."""
    return any(isinstance(n, str) and _INVITO_NEL_NOME.search(n) for n in nomi)


def nome_vietato(nomi, schemi) -> str | None:
    """
    Il primo schema della lista che corrisponde a un nome (SIC-028). Lo schema
    è una parola (contenuta nel nome) o usa il jolly `*` (nome intero).
    """
    puliti = [n.lower() for n in nomi if isinstance(n, str) and n]
    for schema in schemi:
        s = schema.lower()
        for nome in puliti:
            if ("*" in s and fnmatch.fnmatchcase(nome, s)) or ("*" not in s and s in nome):
                return schema
    return None


def azione_piu_forte(azioni) -> str:
    return max(azioni, key=lambda a: _GRAVITA.get(a, 0), default=AZIONE_NIENTE)


def pulisci_schema(schema: str) -> str:
    """Schema salvato: spazi tolti ai lati, minuscole, al massimo MAX_SCHEMA caratteri."""
    return (schema or "").strip().lower()[:MAX_SCHEMA]


# ---------------------------------------------------- ultimi ingressi del server
@dataclass(frozen=True)
class Ingresso:
    member_id: int
    nome: str
    creato: datetime
    entrato: datetime
    sospetto: bool = False


MAX_INGRESSI_PER_SERVER = 200

_ingressi: BoundedCache[int, deque] = BoundedCache(max_size=2000)


def registra_ingresso(guild_id: int, ingresso: Ingresso) -> None:
    coda = _ingressi.get(guild_id)
    if coda is None:
        coda = deque(maxlen=MAX_INGRESSI_PER_SERVER)
        _ingressi.set(guild_id, coda)
    coda.append(ingresso)


def ultimi_ingressi(guild_id: int, dal: datetime | None = None) -> list[Ingresso]:
    """Gli ingressi tenuti in memoria (dal più vecchio), solo da `dal` in poi se dato."""
    coda = _ingressi.get(guild_id) or ()
    return [i for i in coda if dal is None or i.entrato >= dal]


def azzera_ingressi() -> None:
    """Per i test: svuota il registro in memoria."""
    _ingressi.clear()
    _rete.clear()


def account_vicini(recenti, creato: datetime, margine_secondi: int) -> int:
    """Quanti ingressi recenti hanno un account creato entro il margine da questo (SIC-030), lui compreso."""
    return sum(1 for i in recenti if abs((i.creato - creato).total_seconds()) <= margine_secondi)


SOGLIA_NOMI_SIMILI = 0.8


def nomi_simili(recenti, nome: str) -> int:
    """Quanti ingressi recenti hanno un nome simile a questo (SIC-031), lui compreso."""
    base = normalizza_nome(nome)
    if len(base) < 3:
        return 0
    radice = base.rstrip("0123456789")
    totale = 0
    for i in recenti:
        altro = normalizza_nome(i.nome)
        if not altro:
            continue
        if altro.rstrip("0123456789") == radice and len(radice) >= 3:
            totale += 1
        elif SequenceMatcher(None, base, altro).ratio() >= SOGLIA_NOMI_SIMILI:
            totale += 1
    return totale


def elenco_testo(righe) -> str:
    """Elenco degli account per il file allegato (SIC-035): una riga per account."""
    return "\n".join(righe) + ("\n" if righe else "")


def riga_elenco(member_id: int, nome: str, creato: datetime, entrato: datetime) -> str:
    return f"{member_id}\t{nome}\tcreato {creato:%Y-%m-%d %H:%M}\tentrato {entrato:%Y-%m-%d %H:%M:%S} UTC"


# --------------------------------------------------------- segnale di rete (SIC-037)
FINESTRA_RETE_SECONDI = 10 * 60
SERVER_RETE_MINIMI = 4
_rete: BoundedCache[int, deque] = BoundedCache(max_size=20000)


def ingresso_in_rete(user_id: int, guild_id: int, adesso: datetime) -> int:
    """
    Segna l'ingresso dell'utente e restituisce in quanti server diversi è
    entrato negli ultimi FINESTRA_RETE_SECONDI; 0 se in questo server era già
    entrato nella finestra (un rientro non vale un nuovo avviso). Nessuna
    configurazione: vale per tutti i server con l'anti-raid attivo.
    """
    coda = _rete.get(user_id)
    if coda is None:
        coda = deque(maxlen=50)
        _rete.set(user_id, coda)
    prima = {g for g, t in coda if (adesso - t).total_seconds() <= FINESTRA_RETE_SECONDI}
    coda.append((guild_id, adesso))
    return 0 if guild_id in prima else len(prima) + 1

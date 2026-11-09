"""
core/moderation_motivi.py
=========================
Motivi pronti di moderazione: il server ne tiene fino a 25 (nome fino a 32 caratteri, testo fino a 512) e li
richiama dal completamento del campo «motivo». Il valore scelto è `#m<id>`; il testo vero si legge dal database.
Una piccola cache per server (3 secondi) evita una query a ogni tasto premuto.
D68: ogni motivo ha una severità (lieve, media, grave, gravissima) e una sanzione di base con durata; alla prima
lettura il server riceve un elenco preimpostato, che poi può cambiare, togliere o ampliare.
Funzioni coperte: SPEC §5.9 (MOD-113, MOD-116), D68
"""

from __future__ import annotations

import re
import time
from typing import NamedTuple

from core.repositories.moderation_repo import moderation_repo

MAX_MOTIVI = 25
MAX_NOME = 32
MIN_TESTO = 3
MAX_TESTO = 512
SECONDI_CACHE = 3
_VALORE = re.compile(r"^#m([1-9][0-9]{0,17})$")

SEVERITA = ("lieve", "media", "grave", "gravissima")
AZIONI = ("warn", "timeout", "kick", "ban")
MAX_TIMEOUT_S = 28 * 86400
_ORA, _GIORNO = 3600, 86400


def _p(nome: str, testo: str, severita: str, azione: str, durata_s: int | None = None) -> dict:
    return {"nome": nome, "testo": testo, "severita": severita, "azione": azione, "durata_s": durata_s}


# Elenco di base, uguale per tutti i server (D68). Il server lo cambia dopo la prima lettura.
PREIMPOSTATI: tuple[dict, ...] = (
    _p("Spam", "Spam: messaggi ripetuti o senza senso", "lieve", "warn"),
    _p("Flood", "Flood: troppi messaggi, emoji o menzioni in poco tempo", "lieve", "warn"),
    _p("Provocazioni", "Provocazioni e litigi che disturbano la chat", "lieve", "warn"),
    _p("Pubblicità", "Pubblicità o inviti ad altri server non autorizzati", "media", "timeout", _ORA),
    _p("Insulti", "Insulti o linguaggio offensivo verso altri membri", "media", "timeout", _ORA),
    _p("Contenuti NSFW", "Contenuti NSFW fuori dai canali dedicati", "media", "timeout", _ORA),
    _p("Molestie", "Molestie o persecuzione di altri membri", "grave", "timeout", _GIORNO),
    _p("Discriminazione", "Discriminazione o incitamento all'odio", "grave", "timeout", _GIORNO),
    _p("Dati personali", "Condivisione di dati personali di altri senza permesso", "grave", "timeout", _GIORNO),
    _p("Evasione sanzione", "Tentativo di aggirare una sanzione già data", "grave", "kick"),
    _p("Raid", "Partecipazione a un raid contro il server", "gravissima", "ban"),
    _p("Truffa o phishing", "Truffa, phishing o link malevoli", "gravissima", "ban"),
    _p("Minacce", "Minacce gravi verso altri membri o lo staff", "gravissima", "ban"),
    _p("Contenuti illegali", "Condivisione di contenuti illegali", "gravissima", "ban"),
)


class Proposta(NamedTuple):
    """La sanzione di base di un motivo pronto: lo staff può cambiarla prima di confermare."""

    severita: str | None
    azione: str
    durata_s: int | None


_cache: dict[int, tuple[float, list[dict]]] = {}
_seminati: set[int] = set()  # server il cui elenco di base è già stato dato (segnato solo dopo la scrittura riuscita)


def id_da_valore(valore: str) -> int | None:
    """L'id di un motivo pronto da un valore `#m<id>`; None se il testo è un motivo scritto a mano."""
    trovato = _VALORE.match(valore.strip()) if valore else None
    return int(trovato.group(1)) if trovato else None


def durata_breve(secondi: int) -> str:
    """1h, 24h, 7d, 30m: la durata in forma corta per le etichette."""
    for unita, valore in (("d", _GIORNO), ("h", _ORA), ("m", 60)):
        if secondi % valore == 0:
            return f"{secondi // valore}{unita}"
    return f"{secondi}s"


def sanzione_breve(motivo: dict) -> str:
    """«media, timeout 1h»: severità e sanzione di base; vuoto se il motivo non le ha."""
    parti = []
    if motivo.get("severita"):
        parti.append(motivo["severita"])
    if motivo.get("azione"):
        parti.append(motivo["azione"] + (f" {durata_breve(motivo['durata_s'])}" if motivo.get("durata_s") else ""))
    return ", ".join(parti)


def etichetta(motivo: dict) -> str:
    """Nome, sanzione di base e inizio del testo, al massimo 100 caratteri (limite del completamento di Discord)."""
    sanzione = sanzione_breve(motivo)
    return (f"{motivo['nome']} [{sanzione}]: {motivo['testo']}" if sanzione else f"{motivo['nome']}: {motivo['testo']}")[:100]


def suggerimenti(elenco: list[dict], scritto: str) -> list[tuple[str, str]]:
    """(nome, valore) dei motivi che contengono `scritto` nel nome o nel testo; al massimo 25."""
    cerca = scritto.strip().casefold()
    righe = [m for m in elenco if not cerca or cerca in m["nome"].casefold() or cerca in m["testo"].casefold()]
    return [(etichetta(m), f"#m{m['id']}") for m in righe[:MAX_MOTIVI]]


async def elenco(guild_id: int) -> list[dict]:
    if guild_id not in _seminati:
        await moderation_repo.semina_motivi(guild_id, PREIMPOSTATI, MAX_MOTIVI)
        _seminati.add(guild_id)
        _cache.pop(guild_id, None)
    adesso = time.monotonic()
    voce = _cache.get(guild_id)
    if voce is not None and adesso - voce[0] < SECONDI_CACHE:
        return voce[1]
    righe = await moderation_repo.list_motivi(guild_id)
    _cache[guild_id] = (adesso, righe)
    return righe


def _controlla_sanzione(severita: str | None, azione: str | None, durata_s: int | None) -> None:
    """ValueError (codice «severita», «azione» o «durata») se la sanzione di base non è valida."""
    if severita is not None and severita not in SEVERITA:
        raise ValueError("severita")
    if azione is not None and azione not in AZIONI:
        raise ValueError("azione")
    if durata_s is not None and (azione != "timeout" or not 0 < durata_s <= MAX_TIMEOUT_S):
        raise ValueError("durata")


async def aggiungi(
    guild_id: int,
    nome: str,
    testo: str,
    autore_id: int,
    severita: str | None = None,
    azione: str | None = None,
    durata_s: int | None = None,
) -> int:
    """Aggiunge un motivo pronto e ne dà l'id. ValueError (codice) se qualcosa non va."""
    nome, testo = nome.strip(), testo.strip()
    if not 1 <= len(nome) <= MAX_NOME:
        raise ValueError("nome")
    if not MIN_TESTO <= len(testo) <= MAX_TESTO:
        raise ValueError("testo")
    _controlla_sanzione(severita, azione, durata_s)
    if await moderation_repo.count_motivi(guild_id) >= MAX_MOTIVI:
        raise ValueError("tetto")
    nuovo = await moderation_repo.add_motivo(guild_id, nome, testo, autore_id, severita, azione, durata_s)
    if nuovo is None:
        raise ValueError("doppio")
    _cache.pop(guild_id, None)
    return nuovo


async def modifica(
    guild_id: int,
    nome: str,
    testo: str | None = None,
    severita: str | None = None,
    azione: str | None = None,
    durata_s: int | None = None,
) -> bool:
    """Cambia i campi passati di un motivo; False se non c'è. Con un'azione diversa da timeout la durata si toglie."""
    if testo is not None:
        testo = testo.strip()
        if not MIN_TESTO <= len(testo) <= MAX_TESTO:
            raise ValueError("testo")
    attuale = await moderation_repo.get_motivo(guild_id, nome.strip())
    if attuale is None:
        return False
    nuova_azione = azione if azione is not None else attuale["azione"]
    nuova_durata = durata_s if durata_s is not None else (attuale["durata_s"] if nuova_azione == "timeout" else None)
    _controlla_sanzione(severita, nuova_azione, nuova_durata)
    campi = {"testo": testo, "severita": severita, "azione": nuova_azione, "durata_s": nuova_durata}
    scelti = {k: v for k, v in campi.items() if v is not None or k == "durata_s"}
    fatto = await moderation_repo.update_motivo(guild_id, nome.strip(), scelti)
    _cache.pop(guild_id, None)
    return fatto


async def proposta(guild_id: int, valore: str) -> Proposta | None:
    """La sanzione di base del motivo pronto `#m<id>`; None per un testo scritto a mano o un motivo senza sanzione."""
    motivo_id = id_da_valore(valore)
    if motivo_id is None:
        return None
    for m in await elenco(guild_id):
        if m["id"] == motivo_id:
            return Proposta(m["severita"], m["azione"], m["durata_s"]) if m["azione"] else None
    return None


async def togli(guild_id: int, nome: str) -> bool:
    tolto = await moderation_repo.delete_motivo(guild_id, nome.strip())
    _cache.pop(guild_id, None)
    return tolto


async def espandi(guild_id: int, valore: str) -> str:
    """Se `valore` è un motivo pronto (`#m<id>`) dà il suo testo, altrimenti lo stesso valore."""
    motivo_id = id_da_valore(valore)
    if motivo_id is None:
        return valore
    for m in await elenco(guild_id):
        if m["id"] == motivo_id:
            return m["testo"]
    return valore

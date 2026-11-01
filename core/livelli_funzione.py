"""
core/livelli_funzione.py
========================
Il livello di abbonamento di ogni funzione (gratuito, premium, VIP 5, VIP 20): un solo
punto che lo legge e lo scrive (D16), usato da `/premium`, `/vip`, dal controllo all'avvio
di ogni comando e dal futuro pannello. Di default tutto è gratuito. I livelli stanno nella
tabella `livelli_funzione`; chi li cambia passa da `imposta_livello`: gli ascoltatori
(il cog dei comandi) registrano o tolgono i gruppi `/premium` e `/vip` senza riavvio.
I comandi premium restano nel loro gruppo: si controlla il livello quando partono.
L'elenco è paginato: il numero di funzioni non tocca mai i limiti dell'albero.
Funzioni coperte: D57
Dipende da: core/migrations/0486_livelli_funzione.sql, core/database.py
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

GRATUITO = "gratuito"
PREMIUM = "premium"
VIP5 = "vip5"
VIP20 = "vip20"
LIVELLI = (GRATUITO, PREMIUM, VIP5, VIP20)
ETICHETTE = {GRATUITO: "gratuito", PREMIUM: "Premium", VIP5: "VIP 5", VIP20: "VIP 20"}

# chiave: (nome leggibile, percorsi dei comandi della funzione)
FUNZIONI: dict[str, tuple[str, tuple[str, ...]]] = {
    "ai_immagini": ("Immagini AI", ("assistente immagina", "assistente ingrandisci", "assistente pacchetto")),
    "ai_testo": ("Testo AI", ("assistente riassumi", "assistente spiega", "assistente traduci", "assistente stile")),
    "ai_personaggi": ("Personaggi AI", ("assistente crea-personaggio", "assistente personaggio", "assistente mistero")),
    "ai_voce": ("Voce AI", ("assistente parla",)),
}

_livelli: dict[str, str] = {}
_ascoltatori: list[Callable[[], None]] = []


class LivelloNonValido(ValueError):
    """Funzione o livello sconosciuti."""


def livello_di(chiave: str, funzioni: dict | None = None) -> str:
    """Il livello della funzione (default: gratuito)."""
    return _livelli.get(chiave, GRATUITO)


def applica_livello(chiave: str, livello: str, funzioni: dict | None = None) -> bool:
    """
    Cambia il livello in memoria e avvisa gli ascoltatori se è cambiato (senza scrivere nel
    database: lo fanno `imposta_livello` e `carica_livelli`). Restituisce True se è cambiato.
    LivelloNonValido se chiave o livello non esistono.
    """
    elenco = FUNZIONI if funzioni is None else funzioni
    if chiave not in elenco:
        raise LivelloNonValido(f"funzione sconosciuta: {chiave}")
    if livello not in LIVELLI:
        raise LivelloNonValido(f"livello sconosciuto: {livello}")
    if livello_di(chiave) == livello:
        return False
    if livello == GRATUITO:
        _livelli.pop(chiave, None)
    else:
        _livelli[chiave] = livello
    for ascoltatore in list(_ascoltatori):
        try:
            ascoltatore()
        except Exception:
            logger.exception("Ascoltatore dei livelli fallito")
    return True


imposta_livello_in_memoria = applica_livello


async def imposta_livello(chiave: str, livello: str, funzioni: dict | None = None) -> bool:
    """Il punto unico di scrittura (D16): controlla, salva nel database, poi applica. True se è cambiato."""
    elenco = FUNZIONI if funzioni is None else funzioni
    if chiave not in elenco:
        raise LivelloNonValido(f"funzione sconosciuta: {chiave}")
    if livello not in LIVELLI:
        raise LivelloNonValido(f"livello sconosciuto: {livello}")
    from core.database import db

    if livello == GRATUITO:
        await db.pool.execute("DELETE FROM livelli_funzione WHERE funzione = $1", chiave)
    else:
        await db.pool.execute(
            """
            INSERT INTO livelli_funzione (funzione, livello) VALUES ($1, $2)
            ON CONFLICT (funzione) DO UPDATE SET livello = EXCLUDED.livello, aggiornato_il = now()
            """,
            chiave,
            livello,
        )
    return applica_livello(chiave, livello, funzioni)


async def carica_livelli(funzioni: dict | None = None) -> None:
    """Rilegge tutti i livelli dal database (all'avvio). Le righe di funzioni sparite si ignorano."""
    from core.database import db

    elenco = FUNZIONI if funzioni is None else funzioni
    righe = await db.pool.fetch("SELECT funzione, livello FROM livelli_funzione")
    nuovi = {r["funzione"]: r["livello"] for r in righe if r["funzione"] in elenco and r["livello"] in LIVELLI}
    for chiave in set(_livelli) - set(nuovi):
        applica_livello(chiave, GRATUITO, elenco)
    for chiave, livello in nuovi.items():
        applica_livello(chiave, livello, elenco)


def azzera_livelli() -> None:
    """Tutto gratuito (per i test)."""
    _livelli.clear()


def aggiungi_ascoltatore(funzione: Callable[[], None]) -> None:
    if funzione not in _ascoltatori:
        _ascoltatori.append(funzione)


def togli_ascoltatore(funzione: Callable[[], None]) -> None:
    if funzione in _ascoltatori:
        _ascoltatori.remove(funzione)


def funzioni_per_livello(livelli: tuple[str, ...], funzioni: dict | None = None) -> list[tuple[str, str, tuple[str, ...]]]:
    """[(livello, nome, percorsi)] delle funzioni che stanno in uno dei `livelli`, in ordine di livello."""
    elenco = FUNZIONI if funzioni is None else funzioni
    righe = []
    for livello in livelli:
        for chiave, (nome, percorsi) in elenco.items():
            if livello_di(chiave) == livello:
                righe.append((livello, nome, percorsi))
    return righe


def serve_premium(funzioni: dict | None = None) -> bool:
    """True se almeno una funzione è premium: allora esiste `/premium`."""
    return bool(funzioni_per_livello((PREMIUM,), funzioni))


def serve_vip(funzioni: dict | None = None) -> bool:
    """True se almeno una funzione è VIP 5 o VIP 20: allora esiste `/vip`."""
    return bool(funzioni_per_livello((VIP5, VIP20), funzioni))


def testo_elenco(livelli: tuple[str, ...], funzioni: dict | None = None) -> str:
    """Il messaggio di `/premium` e `/vip`: i comandi per livello, o una frase chiara se non ce ne sono."""
    righe = funzioni_per_livello(livelli, funzioni)
    if not righe:
        return "Al momento tutte le funzioni del bot sono gratuite per tutti."
    testo: list[str] = []
    for livello in livelli:
        scelte = [r for r in righe if r[0] == livello]
        if not scelte:
            continue
        testo.append(f"**{ETICHETTE[livello]}**")
        for _, nome, percorsi in scelte:
            testo.append(f"- {nome}: " + ", ".join(f"`/{p}`" for p in percorsi))
    return "\n".join(testo)


# ----------------------------------------------------------------------
# Elenco paginato (per /premium elenco e /vip elenco)
# ----------------------------------------------------------------------
PER_PAGINA = 10  # voci per pagina: il menu ne mostra al massimo 25, l'embed resta sotto i 4.096 caratteri
MAX_SUGGERIMENTI = 25
_MAX_RIGA = 300


def righe_per_area(livelli_scelti: tuple[str, ...], area: str | None = None, funzioni: dict | None = None):
    """Le funzioni dei livelli scelti; con `area` solo quelle con almeno un comando in quel gruppo."""
    righe = funzioni_per_livello(livelli_scelti, funzioni)
    if area:
        righe = [r for r in righe if any(p.split()[0] == area for p in r[2])]
    return righe


def aree_disponibili(livelli_scelti: tuple[str, ...], filtro: str = "", funzioni: dict | None = None) -> list[str]:
    """I gruppi che hanno funzioni dei livelli scelti, filtrati da `filtro`, al massimo 25 (completamento)."""
    aree = sorted({p.split()[0] for _, _, percorsi in funzioni_per_livello(livelli_scelti, funzioni) for p in percorsi})
    filtro = filtro.strip().lower().lstrip("/")
    return [a for a in aree if filtro in a][:MAX_SUGGERIMENTI]


def numero_pagine(righe: list, per_pagina: int = PER_PAGINA) -> int:
    return max(1, -(-len(righe) // per_pagina))


def voci_pagina(righe: list, pagina: int, per_pagina: int = PER_PAGINA) -> list:
    """Le voci della pagina (0 = prima); una pagina fuori misura si riporta nei limiti."""
    pagina = min(max(pagina, 0), numero_pagine(righe, per_pagina) - 1)
    return righe[pagina * per_pagina : (pagina + 1) * per_pagina]


def riga_voce(livello: str, nome: str, percorsi: tuple[str, ...]) -> str:
    riga = f"**{nome}** ({ETICHETTE[livello]}): " + ", ".join(f"`/{p}`" for p in percorsi)
    return riga if len(riga) <= _MAX_RIGA else riga[: _MAX_RIGA - 1] + "…"


def testo_pagina(righe: list, pagina: int, per_pagina: int = PER_PAGINA) -> str:
    """La descrizione dell'embed di una pagina (sempre sotto i 4.096 caratteri)."""
    voci = voci_pagina(righe, pagina, per_pagina)
    if not voci:
        return "Al momento tutte le funzioni del bot sono gratuite per tutti."
    return "\n".join(riga_voce(*v) for v in voci)[:4000]


def funzione_del_comando(percorso: str, funzioni: dict | None = None) -> str | None:
    """La chiave della funzione a cui appartiene il comando (percorso senza barra), o None."""
    elenco = FUNZIONI if funzioni is None else funzioni
    for chiave, (_, percorsi) in elenco.items():
        if percorso in percorsi:
            return chiave
    return None


async def ha_livello(interaction, livello: str) -> bool:
    """
    Il server o l'utente ha il livello? Oggi non c'è ancora una fonte di abbonamenti: passa solo
    l'owner del bot. Il collegamento ai pagamenti si farà col pannello (D57).
    """
    from core.config import config

    return interaction.user.id == config.OWNER_ID


async def motivo_negato(interaction, funzioni: dict | None = None) -> str | None:
    """
    Controllo di livello quando parte un comando (un solo punto, D16). None se può partire,
    altrimenti il messaggio da mostrare. Con tutto gratuito non nega mai.
    """
    comando = getattr(interaction, "command", None)
    if comando is None:
        return None
    chiave = funzione_del_comando(comando.qualified_name, funzioni)
    if chiave is None:
        return None
    livello = livello_di(chiave)
    if livello == GRATUITO or await ha_livello(interaction, livello):
        return None
    return f"Questa funzione è del livello {ETICHETTE[livello]}. Guarda /{'vip' if livello != PREMIUM else 'premium'} elenco."

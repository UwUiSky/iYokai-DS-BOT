"""
core/telefono_logic.py
======================
Il telefono tra server (#131, B12): regole di una chiamata, pulizia dei messaggi che passano da un server
all'altro e il centralino in memoria (chi squilla, chi parla, durata massima e silenzio). Niente Discord qui:
il cog legge gli eventi e chiama queste funzioni.
Funzioni coperte: SPEC §16 (FUN-079, FUN-080)
Dipende da: core/fun_extra_logic.py (stili di testo)
"""

from __future__ import annotations

import asyncio
import random
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from core.fun_extra_logic import trasforma_testo

DURATA_MAX_SECONDI = 3600
SILENZIO_MAX_SECONDI = 600
ATTESA_RISPOSTA_SECONDI = 60
PAUSA_UTENTE_SECONDI = 2.0
PAUSA_INVIO_SECONDI = 0.5  # 5 messaggi ogni 2 secondi per webhook, con margine
CODA_MAX = 30
ERRORI_MAX = 5
MAX_TESTO = 1900
MAX_NOME = 80
MAX_UTENTI_NELLA_PAUSA = 500
EFFETTI = ("nessuno", "capovolto", "mescolato", "owo", "emoji")
NOME_WEBHOOK = "iYokai Telefono"
_NOMI_VIETATI = re.compile(r"discord|clyde", re.IGNORECASE)
_LINK = re.compile(
    r"(?:https?://|www\.)\S+|(?:discord\.gg|discord(?:app)?\.com/invite)/\S+", re.IGNORECASE
)
_SPAZI = re.compile(r"\s+")

# Fine di una chiamata: il codice si salva nel registro.
FINE_RIAGGANCIATA = "riagganciata"
FINE_DURATA = "durata"
FINE_SILENZIO = "silenzio"
FINE_ERRORE = "errore"
FINE_RIAVVIO = "riavvio"

_CAPOVOLTO = dict(zip(
    "abcdefghijklmnopqrstuvwxyz",
    "ɐqɔpǝɟƃɥᴉɾʞlɯuodbɹsʇnʌʍxʎz",
))
_CAPOVOLTO.update({"?": "¿", "!": "¡", ".": "˙", ",": "'", "'": ",", "(": ")", ")": "(", "_": "‾"})


def pulisci_nome(nome: str, ripiego: str = "Utente") -> str:
    """Nome per il webhook: senza «discord» né «clyde» (Discord li rifiuta), da 1 a 80 caratteri."""
    pulito = _SPAZI.sub(" ", _NOMI_VIETATI.sub("", nome or "")).strip()
    return (pulito or ripiego)[:MAX_NOME].strip() or ripiego


def nome_mittente(autore: str, server: str) -> str:
    """«Autore · Server» entro 80 caratteri, ognuno già pulito."""
    a, s = pulisci_nome(autore), pulisci_nome(server, "Server")
    return pulisci_nome(f"{a[:50]} · {s[:26]}")


def togli_link(testo: str) -> str:
    return _LINK.sub("🔗", testo)


def applica_effetto(effetto: str, testo: str, rng: random.Random | None = None) -> str:
    if effetto == "capovolto":
        return "".join(_CAPOVOLTO.get(c.lower(), c) for c in reversed(testo))
    if effetto == "mescolato":
        generatore = rng or random
        parole = []
        for parola in testo.split(" "):
            if len(parola) > 3:
                mezzo = list(parola[1:-1])
                generatore.shuffle(mezzo)
                parola = parola[0] + "".join(mezzo) + parola[-1]
            parole.append(parola)
        return " ".join(parole)
    if effetto in ("owo", "emoji"):
        return trasforma_testo(effetto, testo)
    return testo


def prepara_testo(testo: str, allegati: list[str], effetto: str = "nessuno", rng: random.Random | None = None) -> str | None:
    """Il testo da mandare all'altro server, o None se non c'è niente da dire.
    Link e inviti tolti, effetto applicato, allegati come soli indirizzi, al massimo 1900 caratteri."""
    corpo = _SPAZI.sub(" ", togli_link(testo or "")).strip()
    if corpo:
        corpo = applica_effetto(effetto, corpo, rng)
    righe = [f"📎 {url}" for url in allegati if url.startswith("https://")]
    completo = "\n".join(([corpo] if corpo else []) + righe)
    if not completo.strip():
        return None
    return completo[:MAX_TESTO]


def adulti_bloccato(origine_per_adulti: bool, destinazione_per_adulti: bool) -> bool:
    """Un canale con limite d'età non passa mai a un canale senza limite."""
    return origine_per_adulti and not destinazione_per_adulti


class PausaUtenti:
    """Un messaggio ogni 2 secondi per persona, con la memoria a tetto."""

    def __init__(self, ora: Callable[[], float] = time.monotonic) -> None:
        self._ora = ora
        self._ultimo: dict[int, float] = {}

    def passa(self, utente_id: int) -> bool:
        adesso = self._ora()
        if adesso - self._ultimo.get(utente_id, -1e9) < PAUSA_UTENTE_SECONDI:
            return False
        if len(self._ultimo) >= MAX_UTENTI_NELLA_PAUSA:
            self._ultimo = {u: t for u, t in self._ultimo.items() if adesso - t < PAUSA_UTENTE_SECONDI}
        self._ultimo[utente_id] = adesso
        return True


Invio = Callable[[str, str, str], Awaitable[None]]  # testo, nome, indirizzo avatar


@dataclass
class Chiamata:
    a: int
    b: int
    canali: dict[int, int]
    effetti: dict[int, str]
    chi_chiama: int
    inizio: float
    ultimo: float
    iniziata_il: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    segnalata: bool = False
    pronta: bool = False
    invii: dict[int, Invio] = field(default_factory=dict)
    code: dict[int, asyncio.Queue] = field(default_factory=dict)
    lavoratori: list[asyncio.Task] = field(default_factory=list)
    errori: int = 0

    def altro(self, guild_id: int) -> int:
        return self.b if guild_id == self.a else self.a


@dataclass
class Squillo:
    chiamante: int
    chiamato: int
    canali: dict[int, int]
    effetto: str
    chi_chiama: int


class Centralino:
    """Chi squilla e chi parla, tutto in memoria. Ogni cambio passa dal lock."""

    def __init__(self, ora: Callable[[], float] = time.monotonic, rng: random.Random | None = None) -> None:
        self._ora = ora
        self._rng = rng or random.Random()
        self._lock = asyncio.Lock()
        self._chiamate: dict[int, Chiamata] = {}
        self._squilli: dict[int, Squillo] = {}  # per server chiamante

    def occupato(self, guild_id: int) -> bool:
        return guild_id in self._chiamate or guild_id in self._squilli or any(
            s.chiamato == guild_id for s in self._squilli.values()
        )

    def chiamata_di(self, guild_id: int) -> Chiamata | None:
        return self._chiamate.get(guild_id)

    def squillo_di(self, guild_id: int) -> Squillo | None:
        return self._squilli.get(guild_id)

    def chiamate(self) -> list[Chiamata]:
        visti: dict[int, Chiamata] = {c.a: c for c in self._chiamate.values()}
        return list(visti.values())

    async def suona(self, chiamante: int, candidati: list[int], canali: dict[int, int], effetto: str, chi_chiama: int) -> Squillo | None:
        """Sceglie a caso un server libero fra i candidati e lo fa squillare. None se non c'è nessuno."""
        async with self._lock:
            if self.occupato(chiamante):
                return None
            liberi = [g for g in candidati if g != chiamante and not self.occupato(g) and g in canali]
            if not liberi or chiamante not in canali:
                return None
            scelto = self._rng.choice(liberi)
            squillo = Squillo(chiamante, scelto, {chiamante: canali[chiamante], scelto: canali[scelto]}, effetto, chi_chiama)
            self._squilli[chiamante] = squillo
            return squillo

    async def annulla_squillo(self, chiamante: int) -> Squillo | None:
        async with self._lock:
            return self._squilli.pop(chiamante, None)

    async def risposto(self, chiamante: int) -> Chiamata | None:
        """Chi è chiamato ha accettato: lo squillo diventa chiamata (non ancora «pronta»). None se non c'è più."""
        async with self._lock:
            squillo = self._squilli.pop(chiamante, None)
            if squillo is None:
                return None
            adesso = self._ora()
            chiamata = Chiamata(
                a=squillo.chiamante, b=squillo.chiamato, canali=squillo.canali,
                effetti={squillo.chiamante: squillo.effetto, squillo.chiamato: "nessuno"},
                chi_chiama=squillo.chi_chiama, inizio=adesso, ultimo=adesso,
            )
            self._chiamate[chiamata.a] = chiamata
            self._chiamate[chiamata.b] = chiamata
            return chiamata

    async def termina(self, guild_id: int) -> Chiamata | None:
        async with self._lock:
            chiamata = self._chiamate.get(guild_id)
            if chiamata is None:
                return None
            self._chiamate.pop(chiamata.a, None)
            self._chiamate.pop(chiamata.b, None)
            return chiamata

    def tocca(self, chiamata: Chiamata) -> None:
        chiamata.ultimo = self._ora()

    def motivo_scadenza(self, chiamata: Chiamata) -> str | None:
        adesso = self._ora()
        if adesso - chiamata.inizio >= DURATA_MAX_SECONDI:
            return FINE_DURATA
        if adesso - chiamata.ultimo >= SILENZIO_MAX_SECONDI:
            return FINE_SILENZIO
        return None

    def scadute(self) -> list[tuple[Chiamata, str]]:
        return [(c, m) for c in self.chiamate() if (m := self.motivo_scadenza(c))]

    async def svuota(self) -> tuple[list[Chiamata], list[Squillo]]:
        """Al riavvio: tutte le chiamate e gli squilli finiscono."""
        async with self._lock:
            chiamate = self.chiamate()
            squilli = list(self._squilli.values())
            self._chiamate.clear()
            self._squilli.clear()
            return chiamate, squilli


centralino = Centralino()

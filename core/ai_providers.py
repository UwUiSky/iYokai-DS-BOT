"""
core/ai_providers.py
====================
Elenco dei fornitori AI letto dal `.env` e chiamata HTTP verso di loro.
Ogni fornitore parla il formato "compatibile OpenAI" (chat, immagini,
elenco dei modelli): lo usano quasi tutti i servizi, anche quelli locali.
Funzioni coperte: SPEC §25.1, §25.13, §25.94 (NF-24; AI-R-001, AI-R-008, AI-R-101)

Variabili (una serie per fornitore, NOME in maiuscolo):
- `AI_FORNITORI`: nomi separati da virgola, nell'ordine di preferenza.
- `AI_KEY_<NOME>`: la chiave (vuota solo per un servizio sulla stessa macchina).
- `AI_URL_<NOME>`: indirizzo base, es. `https://servizio.example/v1`.
- `AI_MODELLO_<NOME>`, `AI_MODELLO_IMMAGINI_<NOME>`: nomi dei modelli.
- `AI_TIPI_<NOME>`: lavori che sa fare (vedi `TIPI`).
- `AI_FASCIA_<NOME>`: `bassa`, `media` o `alta`.
- `AI_ADDESTRA_<NOME>`: deve valere `no` (il servizio dichiara di non
  addestrare su ciò che riceve). Altrimenti il fornitore non si usa (D19).
- `AI_LIMITI_<NOME>`: `rpm=30,rpg=1000,tpm=6000,tpg=500000` (richieste al
  minuto e al giorno, token al minuto e al giorno). Vuoto: nessun tetto noto.
- `AI_PAGAMENTO_<NOME>`: `si` per una chiave a pagamento; si usa solo con
  `AI_USA_CHIAVI_PAGAMENTO=si`.
- `AI_COSTO_<NOME>`: centesimi per milione di token (0 per i livelli gratuiti).
"""

from __future__ import annotations

import base64
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Mapping

import aiohttp

logger = logging.getLogger("iyokai.ai_providers")

TIPI = ("chat", "testo", "giudizio", "codice", "traduzione", "confronto", "immagine", "audio", "musica", "video")
FASCE = ("bassa", "media", "alta")
_NOME_VALIDO = re.compile(r"^[a-z0-9_]{1,24}$")
_HOST_LOCALI = ("localhost", "127.0.0.1", "[::1]")
TIMEOUT_SECONDI = 25
MAX_BYTES_IMMAGINE = 10 * 1024 * 1024


@dataclass(frozen=True)
class LimitiFornitore:
    rpm: int | None = None  # richieste al minuto
    rpg: int | None = None  # richieste al giorno
    tpm: int | None = None  # token al minuto
    tpg: int | None = None  # token al giorno


@dataclass(frozen=True)
class Fornitore:
    nome: str
    url: str
    chiave: str = field(repr=False, default="")
    modello: str = ""
    modello_immagini: str = ""
    tipi: frozenset[str] = frozenset()
    fascia: str = "bassa"
    a_pagamento: bool = False
    costo_cent_milione: int = 0
    limiti: LimitiFornitore = LimitiFornitore()

    @property
    def livello(self) -> int:
        return FASCE.index(self.fascia)


class ErroreFornitore(Exception):
    """Il servizio ha risposto male. `stato` è il codice HTTP (0 = rete o tempo scaduto)."""

    def __init__(self, stato: int, retry_after: float | None = None) -> None:
        super().__init__(f"Fornitore AI: errore {stato}")
        self.stato = stato
        self.retry_after = retry_after


@dataclass(frozen=True)
class EsitoChiamata:
    testo: str = ""
    immagine: bytes | None = None
    token_in: int = 0
    token_out: int = 0
    intestazioni: Mapping[str, str] = field(default_factory=dict)


def _si(valore: str | None) -> bool:
    return (valore or "").strip().lower() in ("si", "sì", "yes", "true", "1")


def leggi_limiti(testo: str | None) -> LimitiFornitore:
    """`rpm=30,rpg=1000` → LimitiFornitore. Le voci sbagliate si ignorano."""
    valori: dict[str, int] = {}
    for pezzo in (testo or "").split(","):
        chiave, _, numero = pezzo.partition("=")
        chiave = chiave.strip().lower()
        if chiave in ("rpm", "rpg", "tpm", "tpg") and numero.strip().isdigit() and int(numero) > 0:
            valori[chiave] = int(numero)
    return LimitiFornitore(**valori)


def _e_locale(url: str) -> bool:
    host = re.sub(r"^https?://", "", url).split("/")[0].split(":")[0]
    return host in _HOST_LOCALI or url.startswith(("http://[::1]",))


def leggi_fornitori(env: Mapping[str, str] | None = None) -> tuple[list[Fornitore], list[str]]:
    """
    I fornitori validi e, a parte, i motivi per cui gli altri sono stati scartati
    (senza mai riportare la chiave).
    """
    env = os.environ if env is None else env
    fornitori: list[Fornitore] = []
    scarti: list[str] = []
    for grezzo in (env.get("AI_FORNITORI") or "").split(","):
        nome = grezzo.strip().lower()
        if not nome:
            continue
        if not _NOME_VALIDO.match(nome):
            scarti.append(f"{nome[:24]}: nome non valido")
            continue
        su = nome.upper()
        url = (env.get(f"AI_URL_{su}") or "").strip().rstrip("/")
        chiave = (env.get(f"AI_KEY_{su}") or "").strip()
        if not url.startswith(("https://", "http://")):
            scarti.append(f"{nome}: manca AI_URL_{su}")
            continue
        if url.startswith("http://") and not _e_locale(url):
            scarti.append(f"{nome}: indirizzo senza https")
            continue
        if not chiave and not _e_locale(url):
            scarti.append(f"{nome}: manca AI_KEY_{su}")
            continue
        if (env.get(f"AI_ADDESTRA_{su}") or "").strip().lower() != "no":
            scarti.append(f"{nome}: AI_ADDESTRA_{su} deve valere 'no' (D19)")
            continue
        tipi = frozenset(t.strip().lower() for t in (env.get(f"AI_TIPI_{su}") or "chat,testo").split(",")) & set(TIPI)
        fascia = (env.get(f"AI_FASCIA_{su}") or "bassa").strip().lower()
        if fascia not in FASCE:
            fascia = "bassa"
        costo = (env.get(f"AI_COSTO_{su}") or "0").strip()
        fornitori.append(
            Fornitore(
                nome=nome, url=url, chiave=chiave,
                modello=(env.get(f"AI_MODELLO_{su}") or "").strip(),
                modello_immagini=(env.get(f"AI_MODELLO_IMMAGINI_{su}") or "").strip(),
                tipi=tipi, fascia=fascia,
                a_pagamento=_si(env.get(f"AI_PAGAMENTO_{su}")),
                costo_cent_milione=int(costo) if costo.isdigit() else 0,
                limiti=leggi_limiti(env.get(f"AI_LIMITI_{su}")),
            )
        )
    return fornitori, scarti


def usa_chiavi_a_pagamento(env: Mapping[str, str] | None = None) -> bool:
    """Interruttore globale delle chiavi a pagamento (AI-R-008): spento se non c'è."""
    env = os.environ if env is None else env
    return _si(env.get("AI_USA_CHIAVI_PAGAMENTO"))


def _retry_after(intestazioni: Mapping[str, str]) -> float | None:
    valore = intestazioni.get("Retry-After") or intestazioni.get("retry-after")
    try:
        return max(0.0, float(valore)) if valore else None
    except ValueError:
        return None


class TrasportoHTTP:
    """La sola parte che parla in rete. Nei test si usa un trasporto finto con gli stessi metodi."""

    def __init__(self) -> None:
        self._sessione: aiohttp.ClientSession | None = None

    async def _http(self) -> aiohttp.ClientSession:
        if self._sessione is None or self._sessione.closed:
            self._sessione = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDI))
        return self._sessione

    async def chiudi(self) -> None:
        if self._sessione is not None and not self._sessione.closed:
            await self._sessione.close()

    def _intestazioni(self, f: Fornitore) -> dict[str, str]:
        return {"Authorization": f"Bearer {f.chiave}"} if f.chiave else {}

    async def _post(self, f: Fornitore, percorso: str, corpo: dict) -> tuple[dict, Mapping[str, str]]:
        sessione = await self._http()
        try:
            async with sessione.post(f"{f.url}{percorso}", json=corpo, headers=self._intestazioni(f)) as r:
                if r.status >= 400:
                    raise ErroreFornitore(r.status, _retry_after(r.headers))
                dati = await r.json(content_type=None)
                if not isinstance(dati, dict):
                    raise ErroreFornitore(502)
                return dati, dict(r.headers)
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise ErroreFornitore(0) from exc
        except ValueError as exc:  # corpo che non è JSON
            raise ErroreFornitore(502) from exc

    async def completa(self, f: Fornitore, messaggi: list[dict], max_token: int) -> EsitoChiamata:
        dati, intestazioni = await self._post(
            f, "/chat/completions", {"model": f.modello, "messages": messaggi, "max_tokens": max_token}
        )
        try:
            testo = str(dati["choices"][0]["message"]["content"] or "")
            uso = dati.get("usage") or {}
            token_in, token_out = int(uso.get("prompt_tokens") or 0), int(uso.get("completion_tokens") or 0)
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
            raise ErroreFornitore(502) from exc
        return EsitoChiamata(testo=testo, token_in=token_in, token_out=token_out, intestazioni=intestazioni)

    async def immagine(self, f: Fornitore, prompt: str) -> EsitoChiamata:
        dati, intestazioni = await self._post(
            f, "/images/generations",
            {"model": f.modello_immagini or f.modello, "prompt": prompt, "n": 1, "response_format": "b64_json"},
        )
        try:
            grezzo = base64.b64decode(dati["data"][0]["b64_json"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ErroreFornitore(502) from exc
        if len(grezzo) > MAX_BYTES_IMMAGINE:
            raise ErroreFornitore(413)
        return EsitoChiamata(immagine=grezzo, intestazioni=intestazioni)

    async def controlla(self, f: Fornitore) -> bool:
        """Chiave valida? Chiede l'elenco dei modelli: non consuma token."""
        sessione = await self._http()
        try:
            async with sessione.get("/".join((f.url, "models")), headers=self._intestazioni(f)) as r:
                return r.status < 400
        except (aiohttp.ClientError, TimeoutError):
            return False

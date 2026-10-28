"""
core/trascrizione.py
====================
Riconoscimento vocale dei vocali delle persone (AI-R-111): un servizio compatibile con `/audio/transcriptions`,
indirizzo e chiave da `.env`. Si accende solo se il servizio dichiara di non addestrarsi sui messaggi (D19:
`VOCE_TRASCRIZIONE_ADDESTRA=no`); altrimenti resta spento.
Funzioni coperte: SPEC §25.104 (AI-R-111)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Mapping

import aiohttp

logger = logging.getLogger("iyokai.trascrizione")

MAX_SECONDI = 120
MAX_BYTE = 8 * 1024 * 1024
TIMEOUT_SECONDI = 60


@dataclass(frozen=True)
class ConfigTrascrizione:
    url: str
    chiave: str
    modello: str


def leggi_config(env: Mapping[str, str] | None = None) -> ConfigTrascrizione | None:
    env = os.environ if env is None else env
    url = (env.get("VOCE_TRASCRIZIONE_URL") or "").strip().rstrip("/")
    if not url.startswith("https://") or (env.get("VOCE_TRASCRIZIONE_ADDESTRA") or "").strip().lower() != "no":
        return None
    chiave = (env.get("VOCE_TRASCRIZIONE_CHIAVE") or "").strip()
    return ConfigTrascrizione(url, chiave, (env.get("VOCE_TRASCRIZIONE_MODELLO") or "whisper-1").strip())


def vocale_accettabile(durata: float | None, byte: int) -> str | None:
    """None se va bene, altrimenti il motivo (detto alla persona)."""
    if durata is not None and durata > MAX_SECONDI:
        return f"Il vocale è troppo lungo: al massimo {MAX_SECONDI} secondi."
    if byte > MAX_BYTE:
        return "Il vocale pesa troppo."
    return None


class Trascrittore:
    def __init__(self, config: ConfigTrascrizione | None, trasporto=None) -> None:
        self.config = config
        self._trasporto = trasporto or self._http

    @property
    def attivo(self) -> bool:
        return self.config is not None

    async def _http(self, config: ConfigTrascrizione, audio: bytes, nome: str) -> dict:
        form = aiohttp.FormData()
        form.add_field("model", config.modello)
        form.add_field("file", audio, filename=nome, content_type="audio/ogg")
        intestazioni = {"Authorization": f"Bearer {config.chiave}"} if config.chiave else {}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDI)) as sessione:
            async with sessione.post(f"{config.url}/audio/transcriptions", data=form, headers=intestazioni) as r:
                if r.status >= 400:
                    raise RuntimeError(f"trascrizione: stato {r.status}")
                return await r.json(content_type=None)

    async def trascrivi(self, audio: bytes, nome: str = "vocale.ogg") -> str | None:
        """Il testo del vocale, o None se il servizio è spento o sbaglia."""
        if self.config is None:
            return None
        try:
            dati = await self._trasporto(self.config, audio, nome)
        except Exception:  # noqa: BLE001
            logger.warning("Trascrizione non riuscita.", exc_info=True)
            return None
        testo = dati.get("text") if isinstance(dati, dict) else None
        return " ".join(testo.split())[:2000] if isinstance(testo, str) and testo.strip() else None


_trascrittore: Trascrittore | None = None


def trascrittore() -> Trascrittore:
    global _trascrittore
    if _trascrittore is None:
        _trascrittore = Trascrittore(leggi_config())
    return _trascrittore


def imposta_trascrittore(t: Trascrittore | None) -> None:
    """Per i test."""
    global _trascrittore
    _trascrittore = t

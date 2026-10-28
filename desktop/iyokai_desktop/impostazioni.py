"""
desktop/iyokai_desktop/impostazioni.py
======================================
Le impostazioni sul PC: indirizzo del servizio iYokai, ID dell'applicazione della rich presence, lingua, ultimo
avviso visto. Il codice personale sta in un file a parte, leggibile solo dalla persona. Nessun segreto nel programma.
Funzioni coperte: SPEC D.1
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

NOME_CARTELLA = "iyokai-desktop"
_ID = re.compile(r"^\d{15,25}$")
LINGUE = ("it", "en")


class ErroreImpostazioni(Exception):
    def __init__(self, codice: str) -> None:
        super().__init__(codice)
        self.codice = codice


def cartella_config(ambiente: dict | None = None, piattaforma: str | None = None) -> Path:
    ambiente = os.environ if ambiente is None else ambiente
    piattaforma = piattaforma or sys.platform
    casa = Path(ambiente.get("HOME") or ambiente.get("USERPROFILE") or ".")
    if piattaforma.startswith("win"):
        return Path(ambiente.get("APPDATA") or casa / "AppData" / "Roaming") / NOME_CARTELLA
    if piattaforma == "darwin":
        return casa / "Library" / "Application Support" / NOME_CARTELLA
    return Path(ambiente.get("XDG_CONFIG_HOME") or casa / ".config") / NOME_CARTELLA


def indirizzo_valido(url: str) -> str:
    """Il servizio si raggiunge solo in https (http solo sul proprio PC, per le prove)."""
    parti = urlsplit((url or "").strip())
    locale = parti.hostname in ("localhost", "127.0.0.1")
    if not parti.netloc or parti.username or parti.password or parti.query or parti.fragment:
        raise ErroreImpostazioni("indirizzo_non_valido")
    if parti.scheme != "https" and not (parti.scheme == "http" and locale):
        raise ErroreImpostazioni("indirizzo_non_sicuro")
    return f"{parti.scheme}://{parti.netloc}{parti.path.rstrip('/')}"


class Impostazioni:
    def __init__(self, cartella: Path) -> None:
        self.cartella = Path(cartella)
        self._file = self.cartella / "impostazioni.json"
        self._file_token = self.cartella / "codice.txt"

    def _dati(self) -> dict:
        try:
            dati = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return dati if isinstance(dati, dict) else {}

    def _salva(self, dati: dict) -> None:
        self.cartella.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps(dati, indent=2), encoding="utf-8")

    def leggi(self, chiave: str, predefinito=None):
        return self._dati().get(chiave, predefinito)

    def imposta_servizio(self, url: str) -> None:
        self._salva({**self._dati(), "servizio": indirizzo_valido(url)})

    def imposta_app_id(self, app_id: str) -> None:
        if not _ID.match(app_id or ""):
            raise ErroreImpostazioni("app_id_non_valido")
        self._salva({**self._dati(), "app_id": app_id})

    def imposta_lingua(self, lingua: str) -> None:
        if lingua not in LINGUE:
            raise ErroreImpostazioni("lingua_non_valida")
        self._salva({**self._dati(), "lingua": lingua})

    def ultimo_evento(self) -> int:
        valore = self._dati().get("ultimo_evento", 0)
        return valore if isinstance(valore, int) and valore >= 0 else 0

    def imposta_ultimo_evento(self, numero: int) -> None:
        self._salva({**self._dati(), "ultimo_evento": int(numero)})

    # ------------------------------------------------ il codice personale
    def salva_codice(self, codice: str) -> None:
        self.cartella.mkdir(parents=True, exist_ok=True)
        descrittore = os.open(self._file_token, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descrittore, "w", encoding="utf-8") as f:
            f.write(codice.strip())
        try:
            os.chmod(self._file_token, 0o600)
        except OSError:
            pass  # Windows: i permessi del file seguono la cartella dell'utente

    def codice(self) -> str | None:
        try:
            return self._file_token.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None

    def dimentica_codice(self) -> bool:
        try:
            self._file_token.unlink()
            return True
        except OSError:
            return False

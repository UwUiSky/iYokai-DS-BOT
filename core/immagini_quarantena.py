"""
core/immagini_quarantena.py
===========================
Cartella di quarantena dei byte delle immagini (D61, D62): fuori dal sito, mai aperti dal
processo del bot. Nome casuale di 32 cifre esadecimali creato con `O_CREAT|O_EXCL`, file `0640`,
registro nella tabella `quarantena_file` per la cancellazione a scadenza e per `/privacy`.
Funzioni coperte: SPEC §6 (D61, D62)
Dipende da: core/migrations/0504_quarantena_file.sql
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from core.database import db

logger = logging.getLogger("iyokai.immagini.quarantena")

VARIABILE_CARTELLA = "IYOKAI_QUARANTENA_DIR"
CARTELLA_PREDEFINITA = "/var/lib/iyokai/quarantena"
ORE_SOSPETTA = 72
ORE_PULITA = 1  # una pulita si cancella subito: l'ora e' solo la rete di sicurezza
NOME_VALIDO = re.compile(r"^[0-9a-f]{32}$")
_TENTATIVI = 8


@dataclass(frozen=True)
class VoceQuarantena:
    nome: str
    percorso: Path


def cartella() -> Path:
    """La cartella (creata se manca). Se quella di sistema non si puo' usare, una temporanea: lo dice il log."""
    scelta = Path(os.environ.get(VARIABILE_CARTELLA) or CARTELLA_PREDEFINITA)
    try:
        scelta.mkdir(mode=0o2750, parents=True, exist_ok=True)
        if not os.access(scelta, os.W_OK):
            raise PermissionError(str(scelta))
        return scelta
    except OSError:
        ripiego = Path(tempfile.gettempdir()) / "iyokai-quarantena"
        ripiego.mkdir(mode=0o750, parents=True, exist_ok=True)
        logger.warning("Quarantena: %s non utilizzabile, uso la cartella temporanea", scelta)
        return ripiego


def percorso_di(nome: str) -> Path:
    """Il percorso di un file in quarantena. ValueError se il nome non e' di 32 cifre esadecimali."""
    if not isinstance(nome, str) or not NOME_VALIDO.fullmatch(nome):
        raise ValueError("nome di quarantena non valido")
    return cartella() / nome


def _scrivi(dati: bytes) -> VoceQuarantena:
    base = cartella()
    for _ in range(_TENTATIVI):
        nome = secrets.token_hex(16)
        try:
            fd = os.open(base / nome, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        except FileExistsError:
            continue
        with os.fdopen(fd, "wb") as fh:
            fh.write(dati)
        os.chmod(base / nome, 0o640)
        return VoceQuarantena(nome, base / nome)
    raise OSError("nome di quarantena non trovato")


async def salva(dati: bytes, guild_id: int, sha256: str, ore: int = ORE_SOSPETTA) -> VoceQuarantena:
    """Scrive i byte cosi' come sono e li registra. Se la registrazione fallisce il file si toglie."""
    voce = await asyncio.to_thread(_scrivi, dati)
    try:
        await db.pool.execute(
            "INSERT INTO quarantena_file (sha256, nome, guild_id, scade_il) VALUES ($1, $2, $3, now() + make_interval(hours => $4))",
            sha256, voce.nome, guild_id, ore,
        )
    except Exception:
        voce.percorso.unlink(missing_ok=True)
        raise
    return voce


async def prolunga(nome: str, ore: int = ORE_SOSPETTA) -> None:
    """Un file che l'analisi ha trovato sospetto resta per il tempo delle sospette."""
    percorso_di(nome)
    await db.pool.execute("UPDATE quarantena_file SET scade_il = now() + make_interval(hours => $2) WHERE nome = $1", nome, ore)


async def cancella(nome: str) -> None:
    """Toglie file e riga. Si puo' chiamare piu' volte."""
    percorso = percorso_di(nome)
    await asyncio.to_thread(percorso.unlink, True)
    await db.pool.execute("DELETE FROM quarantena_file WHERE nome = $1", nome)


async def pulisci() -> int:
    """Cancella i file scaduti e quelli senza riga piu' vecchi di un'ora. Ritorna quanti ne ha tolti."""
    righe = await db.pool.fetch("DELETE FROM quarantena_file WHERE scade_il < now() RETURNING nome")
    base = cartella()
    tolti = 0
    for r in righe:
        if await asyncio.to_thread(_togli, base / r["nome"]):
            tolti += 1
    noti = {r["nome"] for r in await db.pool.fetch("SELECT nome FROM quarantena_file")}
    limite = time.time() - ORE_PULITA * 3600
    for p in await asyncio.to_thread(lambda: [x for x in base.iterdir() if x.is_file()]):
        if NOME_VALIDO.fullmatch(p.name) and p.name not in noti and p.stat().st_mtime < limite:
            if await asyncio.to_thread(_togli, p):
                tolti += 1
    return tolti


def _togli(p: Path) -> bool:
    try:
        p.unlink()
        return True
    except FileNotFoundError:
        return False

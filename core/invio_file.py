"""
core/invio_file.py
==================
Un solo modo per mandare un file su Discord (M 14.7, LIM-55).

discord.py crede a 10 MiB per allegato, ma il limite vero cambia con il
livello del server. Qui la soglia è un po' più bassa (FILE_MAX_BYTE): un
file più grande si divide in parti (a fine riga se è testo) oppure, con
`dividi=False`, si rifiuta con `FileTroppoGrande`.
Funzioni coperte: SPEC §14 (M 14.7)
"""

from __future__ import annotations

import io
from pathlib import PurePosixPath
from typing import Awaitable, Callable

import discord

FILE_MAX_BYTE = 8 * 1024 * 1024
PARTI_MAX = 10  # un messaggio porta al massimo 10 allegati; qui uno per messaggio, ma basta così


class FileTroppoGrande(ValueError):
    """Il file supera il limite e non si può (o non si vuole) dividere."""


def _nome_parte(nome: str, numero: int) -> str:
    percorso = PurePosixPath(nome)
    return f"{percorso.stem}.part{numero}{percorso.suffix}"


def dividi_in_parti(
    dati: bytes, nome: str, limite: int = FILE_MAX_BYTE
) -> list[tuple[str, bytes]]:
    """
    Divide `dati` in parti di al massimo `limite` byte. Il testo si taglia a fine
    riga quando c'è un a-capo nella parte; altrimenti si taglia sul limite.
    Un file che sta nel limite torna intero, con il suo nome.
    """
    if limite < 1:
        raise ValueError("Il limite deve essere almeno 1 byte.")
    if len(dati) <= limite:
        return [(nome, dati)]

    pezzi: list[bytes] = []
    inizio = 0
    while inizio < len(dati):
        fine = min(inizio + limite, len(dati))
        if fine < len(dati):
            a_capo = dati.rfind(b"\n", inizio, fine)
            if a_capo > inizio:
                fine = a_capo + 1
        pezzi.append(dati[inizio:fine])
        inizio = fine
    return [(_nome_parte(nome, n), pezzo) for n, pezzo in enumerate(pezzi, start=1)]


async def invia_file(
    invia: Callable[..., Awaitable],
    dati: bytes,
    nome: str,
    *,
    contenuto: str | None = None,
    limite: int = FILE_MAX_BYTE,
    dividi: bool = True,
    max_parti: int = PARTI_MAX,
    **kwargs,
) -> int:
    """
    Manda `dati` chiamando `invia(contenuto, file=..., **kwargs)` (ad esempio
    `interaction.followup.send` o `channel.send`). Il testo accompagna solo la
    prima parte. Restituisce quante parti ha mandato.

    Solleva `FileTroppoGrande` PRIMA di mandare qualunque cosa se il file supera
    il limite con `dividi=False`, o se servirebbero più di `max_parti` parti.
    """
    if not dividi and len(dati) > limite:
        raise FileTroppoGrande(
            f"Il file {nome} pesa {len(dati)} byte, oltre il limite di {limite}."
        )
    parti = dividi_in_parti(dati, nome, limite)
    if len(parti) > max_parti:
        raise FileTroppoGrande(
            f"Il file {nome} servirebbe in {len(parti)} parti, oltre le {max_parti} consentite."
        )
    for numero, (nome_parte, pezzo) in enumerate(parti):
        file = discord.File(io.BytesIO(pezzo), filename=nome_parte)
        await invia(contenuto if numero == 0 else None, file=file, **kwargs)
    return len(parti)

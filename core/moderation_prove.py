"""
core/moderation_prove.py
========================
Prove allegate a un caso o a una nota (MOD-038): quali file si accettano, controlli, e cosa si conserva.
Immagini: passano dal percorso unico (D61, D62) e si tiene solo la copia ricodificata. PDF e TXT: file
grezzo conservato cosi' com'e', mai aperto, tolto dopo 180 giorni. Niente Discord qui.
Funzioni coperte: SPEC §5.2 (MOD-038)
Dipende da: core/immagini_pipeline.py, core/repositories/moderation_repo.py
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from core import immagini_pipeline
from core.immagini_byte_logic import PULITA
from core.repositories.moderation_repo import moderation_repo

MAX_PROVE = 5
MAX_BYTE = 10 * 1024 * 1024  # LIM-55
GIORNI_FILE = 180
TIPO_IMMAGINE = "immagine"
TIPO_FILE = "file"
_IMMAGINI = (".png", ".jpg", ".jpeg", ".gif", ".webp")
_FILE = (".pdf", ".txt")


@dataclass(frozen=True)
class EsitoProva:
    id: int | None = None
    errore: str | None = None  # chiave del testo da mostrare
    tipo: str | None = None


def tipo_di(nome_file: str) -> str | None:
    """Il tipo di prova dal nome del file, o None se non si accetta."""
    nome = nome_file.lower()
    if nome.endswith(_IMMAGINI):
        return TIPO_IMMAGINE
    if nome.endswith(_FILE):
        return TIPO_FILE
    return None


def nome_sicuro(nome_file: str) -> str:
    """Solo il nome del file, corto e senza caratteri di controllo (finisce in un elenco)."""
    pulito = "".join(c for c in nome_file.replace("\\", "/").split("/")[-1] if c.isprintable())
    return pulito[:80] or "file"


async def aggiungi_prova(
    guild_id: int, user_id: int, autore_id: int, *, nome_file: str, dimensione: int, leggi,
    content_type: str | None = None, case_number: int | None = None, nota_id: int | None = None,
) -> EsitoProva:
    """
    Controlla e conserva un allegato. `leggi` e' una funzione async che da' i byte (si chiama solo dopo i
    controlli sul peso). Errori: prove_tipo, prove_grande, prove_troppe, prove_immagine.
    """
    tipo = tipo_di(nome_file)
    if tipo is None:
        return EsitoProva(errore="prove_tipo")
    if dimensione > MAX_BYTE:
        return EsitoProva(errore="prove_grande")
    if await moderation_repo.conta_prove(guild_id, case_number=case_number, nota_id=nota_id) >= MAX_PROVE:
        return EsitoProva(errore="prove_troppe")
    dati = await leggi()
    if len(dati) > MAX_BYTE:
        return EsitoProva(errore="prove_grande")
    if tipo == TIPO_IMMAGINE:
        esito = await immagini_pipeline.analizza_immagine(dati, nome_file, content_type, guild_id)
        if esito.verdetto != PULITA or esito.non_analizzata or not esito.png:
            return EsitoProva(errore="prove_immagine")  # mai l'originale: o la copia ricodificata, o niente
        dati = esito.png
    sha = hashlib.sha256(dati).hexdigest()
    id_prova = await moderation_repo.add_prova(
        guild_id, user_id, autore_id, case_number=case_number, nota_id=nota_id,
        nome_file=nome_sicuro(nome_file), tipo=tipo, sha256=sha, dati=dati,
    )
    return EsitoProva(id=id_prova, tipo=tipo)

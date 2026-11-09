"""
core/giveaway_immagine.py
=========================
Immagine dell'annuncio di un giveaway: l'allegato passa dalla pipeline delle immagini (D61, D62) e si
conserva solo la copia ricodificata. L'URL dell'allegato scade sul CDN di Discord, quindi il messaggio
la ri-allega ogni volta che serve.
Funzioni coperte: SPEC §15.5 (NF-28), UTL-126
Dipende da: core/immagini_pipeline.py, core/repositories/giveaway_repo.py
"""

from __future__ import annotations

import hashlib
import io
import logging

import discord

from core.giveaway_logic import NOME_FILE_IMMAGINE
from core.immagini_byte_logic import PULITA
from core.immagini_pipeline import analizza_immagine
from core.repositories.giveaway_repo import giveaway_repo

logger = logging.getLogger("iyokai.giveaway_immagine")

ERRORE_IMMAGINE = "giveaway_immagine_non_valida"


async def conserva_allegato(allegato: discord.Attachment, guild_id: int) -> tuple[int | None, str | None]:
    """Ritorna (id della copia conservata, None) oppure (None, chiave del testo d'errore). Mai l'originale."""
    try:
        dati = await allegato.read()
    except discord.HTTPException:
        logger.warning("Immagine del giveaway non scaricata", exc_info=True)
        return None, ERRORE_IMMAGINE
    esito = await analizza_immagine(dati, allegato.filename, allegato.content_type, guild_id)
    if esito.verdetto != PULITA or esito.non_analizzata or not esito.png:
        return None, ERRORE_IMMAGINE
    return await giveaway_repo.salva_immagine(guild_id, hashlib.sha256(esito.png).hexdigest(), esito.png), None


async def file_annuncio(immagine_id: int | None) -> discord.File | None:
    """Il file da ri-allegare al messaggio dell'annuncio, o None se il giveaway non ha immagine (o la copia manca)."""
    dati = await giveaway_repo.get_immagine(immagine_id)
    if dati is None:
        return None
    return discord.File(io.BytesIO(dati), filename=NOME_FILE_IMMAGINE)

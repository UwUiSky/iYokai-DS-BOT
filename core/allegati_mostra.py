"""
core/allegati_mostra.py
=======================
Gli allegati di un utente che il bot mostra o inoltra (D74): mai il link all'originale. Un'immagine vera e pulita
torna come copia PNG rifatta dalla sandbox; ogni altro file diventa una riga di scheda (nome pulito, tipo vero,
peso) o di avviso. Un file troppo grande non si scarica: scheda dal nome.
Funzioni coperte: SPEC §8.16 (D74, #160)
Dipende da: core/immagini_pipeline.py (decisione unica e sandbox)
"""

from __future__ import annotations

import logging

import discord

from core import allegati_tipo_logic as tipo
from core.immagini_pipeline import esamina_allegato

logger = logging.getLogger(__name__)

MAX_BYTE = 8 * 1024 * 1024  # stesso tetto di core/allegati_sicuri
MAX_MOSTRATI = 5


def riga_per(d: tipo.Decisione, modello_scheda: str = tipo.MODELLO_SCHEDA, modello_avviso: str = tipo.MODELLO_AVVISO) -> str:
    """La riga di scheda (file valido ma non rimandato) o di avviso (travestito, eseguibile, sconosciuto)."""
    if d.azione == tipo.RIFIUTA:
        return tipo.riga_avviso(d, modello_avviso)
    return tipo.riga_scheda(d, modello_scheda)


async def prepara(
    allegati, guild_id: int, *, massimo: int = MAX_MOSTRATI, modello_scheda: str = tipo.MODELLO_SCHEDA,
    modello_avviso: str = tipo.MODELLO_AVVISO, modello_altri: str = "… e altri {n} allegati",
) -> tuple[list[tuple[str, bytes]], list[str]]:
    """(copie rifatte come (nome, PNG), righe per tutto il resto). Non solleva per colpa di un file."""
    copie: list[tuple[str, bytes]] = []
    righe: list[str] = []
    for i, a in enumerate(allegati):
        if i >= massimo:
            righe.append(modello_altri.format(n=len(allegati) - massimo))
            break
        nome, ct, peso = a.filename, getattr(a, "content_type", None), int(getattr(a, "size", 0) or 0)
        dati = None
        if peso <= MAX_BYTE:
            try:
                dati = await a.read()
            except (discord.HTTPException, OSError):
                dati = None  # link scaduto o file sparito: resta la scheda dal nome
        if dati is None:
            righe.append(riga_per(tipo.decidi_senza_byte(nome, ct, peso), modello_scheda, modello_avviso))
            continue
        copia, d = await esamina_allegato(dati, nome, ct, guild_id)
        if copia is not None and len(copia[1]) <= MAX_BYTE:
            copie.append(copia)
            continue
        if d.azione == tipo.RIFIUTA:
            logger.info("Allegato %s non mostrato: %s", d.nome, ", ".join(d.motivi))
        righe.append(riga_per(d, modello_scheda, modello_avviso))
    return copie, righe

"""
core/allegati_mostra.py
=======================
Gli allegati di un utente che il bot mostra o inoltra (D74): mai il link all'originale. Un'immagine vera e pulita
torna come copia PNG rifatta dalla sandbox; PDF, audio, testo (e video, dove il chiamante lo chiede) tornano come
copia convertita nel processo a parte; ogni altro file diventa una riga di scheda (nome pulito, tipo vero, peso) o di
avviso. Le copie di un messaggio non superano 9,5 MiB in tutto. Un file troppo grande non si scarica: scheda dal nome.
Funzioni coperte: SPEC §8.16 (D74, #160)
Dipende da: core/immagini_pipeline.py (decisione unica e sandbox)
"""

from __future__ import annotations

import logging

import discord

from core import allegati_tipo_logic as tipo
from core.immagini_pipeline import esamina_allegato

logger = logging.getLogger(__name__)

MAX_BYTE = 20 * 1024 * 1024  # tetto in entrata: come i PDF, audio e video di core/allegati_copia
MAX_TOTALE_COPIE = int(9.5 * 1024 * 1024)  # peso delle copie in un solo messaggio Discord
MAX_MOSTRATI = 5


def file_da(copie: list[tuple[str, bytes]], prefisso: str = "allegato") -> tuple[list[discord.File], str | None]:
    """
    I file Discord delle copie. I PNG si chiamano `<prefisso><n>.png` (cosi' un embed li puo' mostrare), gli altri
    tengono il nome della copia. Torna anche il nome del primo PNG, se c'e'.
    """
    import io

    file, primo = [], None
    for i, (nome, dati) in enumerate(copie):
        if nome.lower().endswith(".png"):
            nome = f"{prefisso}{i}.png"
            primo = primo or nome
        file.append(discord.File(io.BytesIO(dati), filename=nome))
    return file, primo


def riga_per(d: tipo.Decisione, modello_scheda: str = tipo.MODELLO_SCHEDA, modello_avviso: str = tipo.MODELLO_AVVISO) -> str:
    """La riga di scheda (file valido ma non rimandato) o di avviso (travestito, eseguibile, sconosciuto)."""
    if d.azione == tipo.RIFIUTA:
        return tipo.riga_avviso(d, modello_avviso)
    return tipo.riga_scheda(d, modello_scheda)


async def prepara(
    allegati, guild_id: int, *, massimo: int = MAX_MOSTRATI, modello_scheda: str = tipo.MODELLO_SCHEDA,
    modello_avviso: str = tipo.MODELLO_AVVISO, modello_altri: str = "… e altri {n} allegati", con_video: bool = False,
) -> tuple[list[tuple[str, bytes]], list[str]]:
    """(copie rifatte come (nome, byte), righe per tutto il resto). Non solleva per colpa di un file."""
    copie: list[tuple[str, bytes]] = []
    totale = 0
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
        copia, d = await esamina_allegato(dati, nome, ct, guild_id, con_video=con_video)
        if copia is not None and totale + len(copia[1]) <= MAX_TOTALE_COPIE:
            totale += len(copia[1])
            copie.append(copia)
            continue
        if d.azione == tipo.RIFIUTA:
            logger.info("Allegato %s non mostrato: %s", d.nome, ", ".join(d.motivi))
        righe.append(riga_per(d, modello_scheda, modello_avviso))
    return copie, righe

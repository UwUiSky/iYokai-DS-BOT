"""
core/safe_image.py
==================
Il bot NON apre mai i byte di un utente (blocco B): `apri_in_sandbox` li manda al servizio `iyokai-sandbox`, che li
decodifica in un processo a parte (`core/immagini_decodifica.py`, mai importato dal bot) e rende i soli pixel grezzi;
qui si rifa' l'immagine con `Image.frombytes`, senza nessun decoder. Senza servizio il lavoro si rifiuta con
`SandboxNonDisponibile`: niente ripiego. Qui stanno anche i limiti (byte, formati, pixel, lato) e la corsia dei lavori
Pillow fuori dall'event loop, con un numero limitato di lavori insieme.
Funzioni coperte: REVIEW.md SEC-11, SEC-20; SPEC §6 (D62)
Dipende da: core/immagini_sandbox.py, core/immagini_servizio.py
"""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
import time
from typing import Callable, TypeVar

from PIL import Image, UnidentifiedImageError

from core import immagini_sandbox as sandbox

logger = logging.getLogger("iyokai.immagini.safe")

# Oltre questa dimensione un allegato non viene scaricato.
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB

# Oltre questo numero di pixel dichiarati, un'immagine viene rifiutata
# prima di essere decodificata. 16 milioni di pixel (es. 4000x4000)
# bastano per qualunque foto o avatar e tengono la decodifica sotto i
# 64 MB (4 byte per pixel).
MAX_PIXELS = 16_000_000

# Gli unici formati che apriamo: sono quelli che Discord usa per avatar
# e anteprime, e di ognuno è stato misurato quanto costa decodificarlo.
FORMATI_AMMESSI = ("PNG", "JPEG", "GIF", "WEBP", "BMP")

# Solo la sandbox degli allegati (D74) apre anche questi: vengono sempre ricodificati in PNG e mai conservati.
FORMATI_SANDBOX = FORMATI_AMMESSI + ("TIFF", "ICO", "AVIF", "HEIF")

# WebP e JPEG progressivi, per essere decodificati, usano da 3 a 4
# volte la memoria degli altri formati (12-16 byte per pixel invece di
# 4, misurato con Pillow 12): il loro limite di pixel è un quarto,
# così il tetto di memoria resta lo stesso.
DIVISORE_PIXEL_DECODIFICA_PESANTE = 4

# Lato più lungo dell'immagine restituita da apri_in_sandbox.
MAX_SIDE = 2048

# Seconda linea di difesa: Pillow stesso avvisa/rifiuta oltre questo
# limite nei punti che non passano da apri_in_sandbox.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

# Al massimo 2 lavori immagine dei comandi /fun insieme, in tutto il
# processo: il limite reale è la RAM del processo intero.
_SEMAFORO_FUN = asyncio.Semaphore(2)

# SEC-20: le miniature dello spam-trap hanno una corsia loro (un lavoro
# alla volta), così un'ondata di /fun non ritarda i ban.
_SEMAFORO_SPAM_TRAP = asyncio.Semaphore(1)

T = TypeVar("T")


class ImmagineTroppoGrande(Exception):
    """Le dimensioni dichiarate dall'immagine superano il limite consentito."""


async def run_image_task(func: Callable[..., T], *args) -> T:
    """
    Esegue una funzione Pillow CPU-bound in un thread separato, senza
    mai più di due esecuzioni insieme in tutto il processo. Per i
    comandi immagine di /fun.
    """
    async with _SEMAFORO_FUN:
        return await asyncio.to_thread(func, *args)


async def run_spam_trap_image_task(func: Callable[..., T], *args) -> T:
    """
    Come run_image_task, ma sulla corsia riservata allo spam-trap: non
    aspetta mai dietro i lavori dei comandi /fun.
    """
    async with _SEMAFORO_SPAM_TRAP:
        return await asyncio.to_thread(func, *args)


class SandboxNonDisponibile(Exception):
    """La sandbox manca, e' ferma, e' piena o non e' isolata: il lavoro sull'immagine si rifiuta (nessun ripiego)."""


# Al massimo tre richieste di pixel insieme dal bot (il servizio ne tiene tre): le altre aspettano un poco, poi si rifiutano.
_POSTI_SANDBOX = threading.BoundedSemaphore(3)
ATTESA_POSTO = 20.0
_BYTE_PER_PIXEL = {"RGB": 3, "RGBA": 4}


def _chiedi_pixel(nome: str, lato: int, insieme: str) -> sandbox.RisultatoSandbox:
    """Una richiesta `pixel` al servizio, con socket bloccante e tempi stretti. Solleva SandboxNonDisponibile."""
    limiti = sandbox.LIMITE_PIXEL
    percorso = sandbox.socket_servizio()
    scadenza = time.monotonic() + limiti.reale + 5.0
    cliente = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        cliente.settimeout(2.0)
        cliente.connect(percorso)
        cliente.sendall(sandbox.richiesta_al_servizio(nome, pixel=(lato, insieme)) + b"\n")
        pezzi, totale = [], 0
        while True:
            cliente.settimeout(max(0.1, scadenza - time.monotonic()))
            blocco = cliente.recv(65536)
            if not blocco:
                break
            totale += len(blocco)
            if totale > limiti.uscita + 65536 or time.monotonic() > scadenza:
                raise SandboxNonDisponibile("risposta troppo grande o troppo lenta")
            pezzi.append(blocco)
    except (OSError, socket.timeout) as errore:
        logger.error("Sandbox: servizio non raggiungibile o muto (%s)", type(errore).__name__)
        raise SandboxNonDisponibile("servizio non raggiungibile") from errore
    finally:
        cliente.close()
    try:
        info, grezzo = sandbox.leggi_uscita(b"".join(pezzi))
    except ValueError as errore:
        raise SandboxNonDisponibile("risposta illeggibile") from errore
    return sandbox.RisultatoSandbox(str(info.get("stato", "errore")), info.get("info") or {}, grezzo, sandbox.MODO_SERVIZIO)


def apri_in_sandbox(image_bytes: bytes, max_side: int = MAX_SIDE, formati: tuple[str, ...] = FORMATI_AMMESSI) -> Image.Image:
    """
    Rende un'immagine (RGB o RGBA, lato piu' lungo al massimo `max_side`) fatta dai soli pixel che la sandbox ha
    decodificato. Va chiamata in un thread (`run_image_task`), mai nell'event loop: aspetta il servizio.
    Solleva ImmagineTroppoGrande (troppi pixel), UnidentifiedImageError (formato o file non valido) oppure
    SandboxNonDisponibile (servizio assente, fermo, pieno o non isolato).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("apri_in_sandbox blocca: va chiamata in un thread (run_image_task), non nell'event loop")
    if not isinstance(image_bytes, (bytes, bytearray)) or len(image_bytes) > MAX_IMAGE_BYTES:
        raise ImmagineTroppoGrande("file oltre il limite di byte")
    insieme = {tuple(FORMATI_AMMESSI): "std", ("PNG",): "png"}.get(tuple(formati))
    if insieme is None:
        raise ValueError("insieme di formati non ammesso")
    lato = max(sandbox.LATO_PIXEL_MIN, min(int(max_side), sandbox.LATO_PIXEL_MAX))
    if not _POSTI_SANDBOX.acquire(timeout=ATTESA_POSTO):
        logger.error("Sandbox: nessun posto libero entro %s s, immagine rifiutata", ATTESA_POSTO)
        raise SandboxNonDisponibile("sandbox occupata")
    try:
        from core import immagini_quarantena as quarantena  # solo qui: il worker importa questo modulo e non ha il database

        voce = quarantena.scrivi_file(bytes(image_bytes))
        try:
            risultato = _chiedi_pixel(voce.nome, lato, insieme)
        finally:
            voce.percorso.unlink(missing_ok=True)
    except OSError as errore:
        logger.error("Sandbox: quarantena non scrivibile (%s)", type(errore).__name__)
        raise SandboxNonDisponibile("quarantena non scrivibile") from errore
    finally:
        _POSTI_SANDBOX.release()
    return _immagine_da(risultato)


def _immagine_da(r: sandbox.RisultatoSandbox) -> Image.Image:
    if r.esito == "errore":
        motivo = r.info.get("motivo")
        if motivo == "troppo_grande":
            raise ImmagineTroppoGrande("immagine oltre i limiti di pixel")
        raise UnidentifiedImageError(f"immagine non valida ({motivo})")
    if r.esito != "ok":
        logger.error("Sandbox: esito %s, immagine rifiutata", r.esito)
        raise SandboxNonDisponibile(r.esito)
    modo, l, h = r.info.get("modo"), r.info.get("larghezza"), r.info.get("altezza")
    if modo not in _BYTE_PER_PIXEL or not all(isinstance(v, int) and 0 < v <= sandbox.LATO_PIXEL_MAX for v in (l, h)):
        raise SandboxNonDisponibile("risposta incoerente")
    if len(r.png) != l * h * _BYTE_PER_PIXEL[modo]:
        raise SandboxNonDisponibile("pixel incompleti")
    img = Image.frombytes(modo, (l, h), r.png)
    img.format = r.info.get("formato")
    return img

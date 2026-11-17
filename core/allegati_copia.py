"""
core/allegati_copia.py
======================
«Copia sicura» di un allegato che non e' un'immagine (D74, #160): data la decisione di `allegati_tipo_logic`, PDF,
audio, video e testo si convertono nel processo a parte (`core/conversioni_worker.py`, via `immagini_sandbox.converti`)
e tornano come (nome, byte): PDF rifatto, `.ogg` (Opus), `.mp4` (H.264 + AAC), `.txt`. Il bot non apre mai il file.
Niente copia (None) se il tipo non si converte, il file e' troppo grande, la copia supera 9,5 MiB, il server ha finito
il tempo-sandbox del giorno, la coda e' piena o la conversione fallisce: resta la scheda. Il video solo dove lo
chiede il chiamante (ticket, ModMail, backup).
Funzioni coperte: SPEC §8.16 (D74, #160)
Dipende da: core/allegati_tipo_logic.py, core/immagini_sandbox.py, core/immagini_quarantena.py, core/immagini_coda.py
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from core import allegati_tipo_logic as tipo
from core import immagini_quarantena as quarantena
from core import immagini_sandbox as sandbox
from core.immagini_coda import CodaPiena, coda_immagini

logger = logging.getLogger("iyokai.allegati.copia")

MAX_USCITA = int(9.5 * 1024 * 1024)
MAX_ENTRATA = {"pdf": 20 * 1024 * 1024, "audio": 20 * 1024 * 1024, "video": 20 * 1024 * 1024, "testo": 1024 * 1024}
ESTENSIONE = {"pdf": "pdf", "audio": "ogg", "video": "mp4", "testo": "txt"}
SETTING_SECONDI_GIORNO = "sandbox_secondi_giorno"
SECONDI_GIORNO_PREDEFINITI = 600
MAX_SECONDI_GIORNO = 3600
MAX_GIORNI_IN_MEMORIA = 2

# Tempo-sandbox usato oggi per server: {(guild_id, giorno UTC): secondi}. Si azzera al riavvio del bot (vedi D74).
_usati: dict[tuple[int, str], float] = {}


def _giorno() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def secondi_usati(guild_id: int) -> float:
    return _usati.get((guild_id, _giorno()), 0.0)


def _addebita(guild_id: int, secondi: float) -> None:
    oggi = _giorno()
    for chiave in [k for k in _usati if k[1] != oggi]:
        del _usati[chiave]
    _usati[(guild_id, oggi)] = _usati.get((guild_id, oggi), 0.0) + max(0.0, secondi)


def azzera_tempo() -> None:
    _usati.clear()


async def tetto_secondi(guild_id: int, archivio=None) -> int:
    """Il tetto del server (impostazione `sandbox_secondi_giorno`); un valore storto vale il predefinito."""
    if archivio is None:
        from core.database import db as archivio
    valore = await archivio.get_guild_setting(guild_id, SETTING_SECONDI_GIORNO, SECONDI_GIORNO_PREDEFINITI)
    if isinstance(valore, int) and not isinstance(valore, bool) and 0 <= valore <= MAX_SECONDI_GIORNO:
        return valore
    return SECONDI_GIORNO_PREDEFINITI


def estensioni_convertibili(con_video: bool) -> tuple[str, ...]:
    return tuple(t for t in ESTENSIONE if con_video or t != "video")


def nome_della_copia(nome: str, categoria: str, tagliato: bool) -> str:
    """Il nome pulito senza estensione, piu' `-tagliato` se la copia e' solo l'inizio, piu' l'estensione nuova."""
    radice = nome.rsplit(".", 1)[0] if "." in nome else nome
    return f"{(radice or 'file')[:70]}{'-tagliato' if tagliato else ''}.{ESTENSIONE[categoria]}"


async def copia_sicura(
    dati: bytes, d: tipo.Decisione, guild_id: int, *, con_video: bool = False, archivio=None,
) -> tuple[str, bytes] | None:
    """(nome, byte convertiti) o None. Non solleva mai: un file storto non ferma nessuno."""
    categoria = d.tipo.categoria
    if d.azione != tipo.SCHEDA or categoria not in estensioni_convertibili(con_video) or not dati:
        return None
    if len(dati) > MAX_ENTRATA[categoria]:
        return None
    try:
        if secondi_usati(guild_id) >= await tetto_secondi(guild_id, archivio):
            logger.info("Tempo-sandbox del giorno finito per il server %s: solo scheda", guild_id)
            return None
        voce = await quarantena.salva(dati, guild_id, d.sha256, ore=quarantena.ORE_PULITA)
    except Exception:  # noqa: BLE001 - senza quarantena o senza impostazione resta la scheda
        logger.warning("Copia sicura non avviata", exc_info=True)
        return None
    try:
        return await _converti(categoria, voce.nome, d.nome, guild_id)
    except CodaPiena:
        return None
    except Exception:  # noqa: BLE001
        logger.warning("Copia sicura non riuscita", exc_info=True)
        return None
    finally:
        try:
            await quarantena.cancella(voce.nome)
        except Exception:  # noqa: BLE001
            logger.warning("Quarantena: file non cancellato", exc_info=True)


async def _converti(categoria: str, nome_quarantena: str, nome: str, guild_id: int) -> tuple[str, bytes] | None:
    async def lavoro() -> sandbox.RisultatoSandbox:
        inizio = time.monotonic()
        try:
            return await sandbox.converti(categoria, nome_quarantena)
        finally:
            _addebita(guild_id, time.monotonic() - inizio)

    r = await coda_immagini.esegui(guild_id, lavoro)
    if not r.riuscita or not r.png or len(r.png) > MAX_USCITA:
        logger.info("Copia sicura %s: nessuna copia (%s %s)", categoria, r.esito, r.info.get("motivo", ""))
        return None
    return nome_della_copia(nome, categoria, bool(r.info.get("tagliato"))), r.png

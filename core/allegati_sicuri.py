"""
core/allegati_sicuri.py
=======================
Copia sicura degli allegati nei log dei messaggi (D61, D62, D74, #152, #160). Il tipo si decide dai primi byte
(`allegati_tipo_logic`): delle immagini vere (PNG, JPEG, GIF, WEBP) si salva solo la copia PNG rifatta dalla sandbox,
mai l'originale (nome casuale, SHA-256 dell'originale, tetto di peso); ogni altro file resta una scheda (nome pulito, tipo, peso,
impronta) o un avviso se e' travestito, eseguibile o sconosciuto: mai un file. Cartella fuori dalla radice del sito. L'anteprima
e' solo la copia PNG ricodificata nel processo a parte (`immagini_pipeline`); un'immagine sospetta non si
conserva (resta in quarantena). Conservazione a tempo, `/privacy` dal registro dei dati, link di download
firmati e a scadenza (serviti dal pannello con `attachment`, `nosniff`, CSP `sandbox`).
Funzioni coperte: SPEC §8.16 (D61, D74, #152, #160)
Dipende da: core/allegati_tipo_logic.py, core/immagini_pipeline.py, core/immagini_byte_logic.py, core/migrations/0304_allegati_copie.sql
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import re
import secrets
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from urllib.parse import quote

from core import allegati_tipo_logic, immagini_pipeline
from core.database import db
from core.immagini_byte_logic import PULITA, riconosci_tipo

logger = logging.getLogger("iyokai.allegati")

VARIABILE_CARTELLA = "IYOKAI_ALLEGATI_DIR"
CARTELLA_PREDEFINITA = "/var/lib/iyokai/allegati"
GIORNI_CONSERVAZIONE = 30
MAX_BYTE = 8 * 1024 * 1024
MAX_PER_MESSAGGIO = 5
SECONDI_LINK = 7 * 24 * 3600
NOME_VALIDO = re.compile(r"^[0-9a-f]{32}$")
GENERICO = "generico"
TIPI_MIME = {"png": "image/png", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}
STATO_SALVATA = "salvata"
STATO_BLOCCATA = "bloccata"  # immagine sospetta o malevola: nessun file, solo il registro
STATO_SCHEDA = "scheda"  # file non immagine (D74): solo nome, tipo, peso e impronta
STATO_RIFIUTATA = "rifiutata"  # travestito, eseguibile o sconosciuto (D74): solo l'avviso
_TENTATIVI = 8


@dataclass(frozen=True)
class Copia:
    id: int
    nome_file: str
    tipo: str
    dimensione: int
    stato: str
    anteprima: str | None
    con_file: bool
    sha256: str = ""


def tipo_dai_byte(dati: bytes) -> str:
    """Il tipo vero dai primi byte, solo dall'elenco chiuso; tutto il resto e' «generico»."""
    return riconosci_tipo(dati) or GENERICO


def cartella() -> Path:
    """La cartella dei byte, mai dentro la radice del sito (creata se manca)."""
    from core.web_panel_server import CARTELLA as radice_sito

    scelta = Path(os.environ.get(VARIABILE_CARTELLA) or CARTELLA_PREDEFINITA)
    try:
        scelta.mkdir(mode=0o750, parents=True, exist_ok=True)
        if not os.access(scelta, os.W_OK):
            raise PermissionError(str(scelta))
    except OSError:
        scelta = Path(tempfile.gettempdir()) / "iyokai-allegati"
        scelta.mkdir(mode=0o750, parents=True, exist_ok=True)
        logger.warning("Allegati: cartella di sistema non utilizzabile, uso quella temporanea")
    if scelta.resolve().is_relative_to(radice_sito.resolve()):
        raise RuntimeError("La cartella degli allegati non puo' stare dentro la radice del sito.")
    return scelta


def _percorso(nome: str) -> Path:
    if not isinstance(nome, str) or not NOME_VALIDO.fullmatch(nome):
        raise ValueError("nome non valido")
    return cartella() / nome


def _scrivi(dati: bytes) -> str:
    base = cartella()
    for _ in range(_TENTATIVI):
        nome = secrets.token_hex(16)
        try:
            fd = os.open(base / nome, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        except FileExistsError:
            continue
        with os.fdopen(fd, "wb") as fh:
            fh.write(dati)
        return nome
    raise OSError("nome non trovato")


async def _togli(nome: str | None) -> None:
    if nome:
        await asyncio.to_thread(lambda: _percorso(nome).unlink(True))


async def _registra(
    guild_id: int, channel_id: int, message_id: int, user_id: int, origine: str, d: allegati_tipo_logic.Decisione,
    stato: str, nome: str | None, anteprima: str | None,
) -> Copia:
    tipo = d.tipo.formato if d.azione == allegati_tipo_logic.IMMAGINE else d.tipo.categoria
    try:
        riga = await db.pool.fetchrow(
            """
            INSERT INTO allegati_copie (guild_id, channel_id, message_id, user_id, origine, nome_file, tipo, sha256,
                dimensione, nome, anteprima, stato, scade_il)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12, now() + make_interval(days => $13)) RETURNING id
            """,
            guild_id, channel_id, message_id, user_id, origine, d.nome, tipo, d.sha256, d.dimensione, nome, anteprima,
            stato, GIORNI_CONSERVAZIONE,
        )
    except Exception:
        await _togli(nome)
        await _togli(anteprima)
        raise
    return Copia(riga["id"], d.nome, tipo, d.dimensione, stato, anteprima, nome is not None, d.sha256)


async def salva(
    guild_id: int, channel_id: int, message_id: int, user_id: int, origine: str, nome_file: str, dati: bytes,
    *, content_type: str | None = None,
) -> Copia | None:
    """
    Registra un allegato dopo la decisione unica (D74). Torna None se e' troppo grande. Immagine vera: percorso
    D62 (pulita -> solo la copia PNG rifatta dalla sandbox, mai l'originale; sospetta o non analizzata -> solo il
    registro). Ogni altro file:
    mai conservato; `scheda` (nome, tipo vero, peso, SHA-256) o `rifiutata` (travestito, eseguibile, sconosciuto).
    Non solleva per colpa del file.
    """
    if len(dati) > MAX_BYTE:
        return None
    d = allegati_tipo_logic.decidi(dati, nome_file, content_type)
    if d.azione != allegati_tipo_logic.IMMAGINE:
        stato = STATO_SCHEDA if d.azione == allegati_tipo_logic.SCHEDA else STATO_RIFIUTATA
        return await _registra(guild_id, channel_id, message_id, user_id, origine, d, stato, None, None)
    try:
        esito = await immagini_pipeline.analizza_immagine(dati, nome_file, content_type, guild_id, con_png=True)
    except Exception:  # noqa: BLE001 - un'analisi che cade non ferma il log
        logger.warning("Allegato non analizzato", exc_info=True)
        esito = None
    if esito is not None and esito.verdetto != PULITA:
        return await _registra(guild_id, channel_id, message_id, user_id, origine, d, STATO_BLOCCATA, None, None)
    png = esito.png if esito is not None and esito.non_analizzata is None else b""
    if not png:  # sandbox caduta o immagine non analizzata: senza la copia rifatta non si conserva niente
        return await _registra(guild_id, channel_id, message_id, user_id, origine, d, STATO_SCHEDA, None, None)
    # D74: l'originale non tocca mai il disco. L'unico file è il PNG rifatto dalla sandbox.
    nome = await asyncio.to_thread(_scrivi, png)
    return await _registra(guild_id, channel_id, message_id, user_id, origine, d, STATO_SALVATA, nome, nome)


async def salva_senza_byte(
    guild_id: int, channel_id: int, message_id: int, user_id: int, origine: str, nome_file: str,
    content_type: str | None, dimensione: int,
) -> Copia:
    """File troppo grande da scaricare (D74): solo scheda senza impronta, o rifiuto se il nome e' pericoloso."""
    d = allegati_tipo_logic.decidi_senza_byte(nome_file, content_type, dimensione)
    stato = STATO_SCHEDA if d.azione == allegati_tipo_logic.SCHEDA else STATO_RIFIUTATA
    return await _registra(guild_id, channel_id, message_id, user_id, origine, d, stato, None, None)


async def del_messaggio(guild_id: int, message_id: int) -> list[Copia]:
    righe = await db.pool.fetch(
        "SELECT * FROM allegati_copie WHERE guild_id = $1 AND message_id = $2 AND scade_il > now() ORDER BY id",
        guild_id, message_id,
    )
    return [Copia(r["id"], r["nome_file"], r["tipo"], r["dimensione"], r["stato"], r["anteprima"], r["nome"] is not None,
                  r["sha256"]) for r in righe]


async def leggi(copia_id: int, *, anteprima: bool = False) -> tuple[str, bytes] | None:
    """(nome del file, byte) di una copia non scaduta, o None."""
    r = await db.pool.fetchrow("SELECT * FROM allegati_copie WHERE id = $1 AND scade_il > now()", copia_id)
    if r is None:
        return None
    nome = r["anteprima"] if anteprima else r["nome"]
    if not nome:
        return None
    try:
        dati = await asyncio.to_thread(lambda: _percorso(nome).read_bytes())
    except OSError:
        return None
    # Il file conservato è sempre un PNG rifatto: il nome scaricato lo dice, qualunque fosse l'estensione di partenza.
    radice = (r["nome_file"] or "immagine").rsplit(".", 1)[0] or "immagine"
    return (f"anteprima-{r['id']}.png" if anteprima else f"{radice}.png"), dati


async def pulisci() -> int:
    """Toglie le copie scadute e i file senza riga (anche dopo `/privacy`). Torna quanti file ha tolto."""
    righe = await db.pool.fetch("DELETE FROM allegati_copie WHERE scade_il < now() RETURNING nome, anteprima")
    tolti = 0
    for r in righe:
        for n in {r["nome"], r["anteprima"]} - {None}:  # di solito lo stesso file: si conta una volta
            await _togli(n)
            tolti += 1
    noti = set()
    for r in await db.pool.fetch("SELECT nome, anteprima FROM allegati_copie"):
        noti.update(x for x in (r["nome"], r["anteprima"]) if x)
    limite = time.time() - 3600
    base = cartella()
    for p in await asyncio.to_thread(lambda: [x for x in base.iterdir() if x.is_file()]):
        if NOME_VALIDO.fullmatch(p.name) and p.name not in noti and p.stat().st_mtime < limite:
            await asyncio.to_thread(p.unlink, True)
            tolti += 1
    return tolti


# ------------------------------------------------------------------ link di download firmati
def _firma(chiave: str, testo: str) -> str:
    return hmac.new(chiave.encode(), testo.encode(), hashlib.sha256).hexdigest()


def crea_token(chiave: str, copia_id: int, *, anteprima: bool = False, adesso: float | None = None) -> str:
    if not chiave:
        raise ValueError("chiave dei link vuota")
    scade = int((adesso if adesso is not None else time.time()) + SECONDI_LINK)
    corpo = f"{copia_id}.{'a' if anteprima else 'o'}.{scade}"
    return f"{corpo}.{_firma(chiave, 'allegato:' + corpo)}"


def leggi_token(chiave: str, token: str, *, adesso: float | None = None) -> tuple[int, bool] | None:
    """(id, anteprima) se la firma e' buona e il link non e' scaduto."""
    parti = token.split(".") if isinstance(token, str) and len(token) <= 120 else []
    if not chiave or len(parti) != 4 or not parti[0].isdigit() or parti[1] not in ("a", "o") or not parti[2].isdigit():
        return None
    if not parti[3].isascii():
        return None
    corpo = ".".join(parti[:3])
    if not hmac.compare_digest(_firma(chiave, "allegato:" + corpo), parti[3]):
        return None
    if int(parti[2]) < (adesso if adesso is not None else time.time()):
        return None
    return int(parti[0]), parti[1] == "a"


def _disposizione(nome: str) -> str:
    """Un'intestazione HTTP porta solo ASCII: nome di riserva in ASCII, nome vero in `filename*` (RFC 5987)."""
    ascii_ = "".join(c if c.isascii() and c.isalnum() or c in "._- " else "_" for c in nome) or "file"
    return f"attachment; filename=\"{ascii_}\"; filename*=UTF-8''{quote(nome, safe='')}"


def intestazioni_download(nome_file: str) -> dict[str, str]:
    """Mai in linea: scarica, non indovinare il tipo, niente script (D61)."""
    return {
        "Content-Disposition": _disposizione(allegati_tipo_logic.nome_pulito(nome_file)),
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox",
        "Cache-Control": "no-store",
        "Cross-Origin-Resource-Policy": "same-site",
    }


def url_download(base: str, chiave: str, copia_id: int, *, anteprima: bool = False) -> str | None:
    """Il link da mostrare allo staff, o None se il sotto-dominio non e' configurato."""
    if not base or not chiave:
        return None
    return f"{base.rstrip('/')}/allegato/{crea_token(chiave, copia_id, anteprima=anteprima)}"


"""
core/immagini_pipeline.py
=========================
Percorso unico di un'immagine scaricata dal bot (D61, D62): controlli sui byte (nessun decoder) ->
libreria delle impronte -> quarantena -> coda -> sandbox -> esito {pulita, sospetta, malevola} con la
copia ricodificata. Il verdetto di una stessa immagine si ricorda per SHA-256 (24 ore): in un raid
si analizza una volta sola. La libreria per SHA-256 si guarda sempre prima, e un cambio della libreria
(owner, nuova condivisa) rende vecchia la cache. Coda piena o sandbox ferma: i controlli sui byte e la libreria girano
comunque, il resto e' «non analizzata». Niente Discord qui: lo fa il cog.
Funzioni coperte: SPEC §6 (D61, D62)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, replace

from core import immagini_qr_logic as qr_logic
from core import immagini_quarantena as quarantena
from core import immagini_sandbox as sandbox
from core.bounded_cache import BoundedCache
from core.immagini_byte_logic import MALEVOLA, PULITA, SOSPETTA, controlla_byte
from core.immagini_coda import CodaPiena, coda_immagini
from core.immagini_trappola_logic import verdetto_di
from core.immagini_trappola_service import libreria_immagini

logger = logging.getLogger("iyokai.immagini.pipeline")

SECONDI_CACHE = 24 * 3600
MAX_VERDETTI_IN_CACHE = 50_000
MOTIVI_SANDBOX_MALEVOLI = ("ucciso", "ucciso_tempo", "uscita_enorme")

NON_ANALIZZATA_GRANDE = "troppo_grande"
NON_ANALIZZATA_CODA = "coda_piena"
NON_ANALIZZATA_SANDBOX = "sandbox_ferma"


@dataclass(frozen=True)
class EsitoImmagine:
    verdetto: str = PULITA
    sha256: str = ""
    motivi: tuple[str, ...] = ()
    dhash: int | None = None
    qr: tuple[str, ...] = ()
    png: bytes = b""
    non_analizzata: str | None = None
    modo_sandbox: str | None = None
    da_libreria: bool = False
    solo_avviso: bool = False  # «simile» a una trappola: si avvisa lo staff, non si agisce
    note: tuple[str, ...] = field(default=())

    @property
    def da_segnalare(self) -> bool:
        """Solo le malevole nuove vanno in libreria: una sospetta condivisa da 3 server diventerebbe malevola ovunque."""
        return self.verdetto == MALEVOLA and not self.da_libreria and not self.solo_avviso and self.non_analizzata is None


_cache: BoundedCache[tuple[int, str], tuple[float, int, EsitoImmagine]] = BoundedCache(MAX_VERDETTI_IN_CACHE)
_modo_dichiarato = False


def svuota_cache() -> None:
    _cache._data.clear()


def _dalla_cache(guild_id: int, sha: str) -> EsitoImmagine | None:
    voce = _cache.get((guild_id, sha))
    if voce and time.monotonic() < voce[0] and voce[1] == libreria_immagini.versione:
        return voce[2]
    return None


def _ricorda(guild_id: int, esito: EsitoImmagine) -> EsitoImmagine:
    # Il PNG non si tiene in memoria: la cache serve a non rifare l'analisi, non a conservare immagini.
    voce = (time.monotonic() + SECONDI_CACHE, libreria_immagini.versione, replace(esito, png=b""))
    _cache.set((guild_id, esito.sha256), voce)
    return esito


def _peggiore(a: str, b: str) -> str:
    ordine = {PULITA: 0, SOSPETTA: 1, MALEVOLA: 2}
    return a if ordine[a] >= ordine[b] else b


async def _libreria_per_sha(sha: str, guild_id: int) -> EsitoImmagine | None:
    voce = await libreria_immagini.cerca_sha(sha, guild_id)
    if voce is None:
        return None
    verdetto = verdetto_di(voce.stato)
    if verdetto is None:
        return None
    return EsitoImmagine(verdetto, sha, (f"libreria_{voce.stato}",), voce.dhash, da_libreria=True)


async def analizza_immagine(dati: bytes, nome_file: str, content_type: str | None, guild_id: int) -> EsitoImmagine:
    """Giudica un allegato. Non solleva mai: ogni imprevisto e' «non analizzata» o «sospetta»."""
    byte = controlla_byte(dati, nome_file, content_type)
    if byte.troppo_grande:
        return EsitoImmagine(PULITA, byte.sha256, non_analizzata=NON_ANALIZZATA_GRANDE)
    trovata = await _libreria_per_sha(byte.sha256, guild_id)
    if trovata is not None:
        return trovata
    nota = _dalla_cache(guild_id, byte.sha256)
    if nota is not None:
        return nota
    motivi = tuple(m.codice for m in byte.motivi)
    if byte.verdetto != PULITA:
        # Un file gia' strano dai byte non si decodifica: il decoder e' proprio cio' che l'attacco cerca.
        await _conserva(dati, guild_id, byte.sha256)
        return _ricorda(guild_id, EsitoImmagine(byte.verdetto, byte.sha256, motivi, note=byte.note))
    return await _con_sandbox(dati, byte, guild_id)


async def _conserva(dati: bytes, guild_id: int, sha: str) -> None:
    """L'originale sospetto resta in quarantena 72 ore (D62); se non si puo', pazienza."""
    try:
        await quarantena.salva(dati, guild_id, sha)
    except Exception:
        logger.warning("Quarantena non scritta", exc_info=True)


async def _con_sandbox(dati: bytes, byte, guild_id: int) -> EsitoImmagine:
    global _modo_dichiarato
    try:
        voce = await quarantena.salva(dati, guild_id, byte.sha256, ore=quarantena.ORE_PULITA)
    except Exception:
        logger.warning("Quarantena non scritta", exc_info=True)
        return EsitoImmagine(PULITA, byte.sha256, non_analizzata=NON_ANALIZZATA_SANDBOX)
    tenere = False
    try:
        try:
            risultato = await coda_immagini.esegui(guild_id, lambda: sandbox.analizza(voce.nome))
        except CodaPiena:
            return EsitoImmagine(PULITA, byte.sha256, non_analizzata=NON_ANALIZZATA_CODA)
        except Exception:
            logger.exception("Sandbox: errore imprevisto")
            return EsitoImmagine(PULITA, byte.sha256, non_analizzata=NON_ANALIZZATA_SANDBOX)
        if risultato.esito == "non_disponibile":
            return EsitoImmagine(PULITA, byte.sha256, non_analizzata=NON_ANALIZZATA_SANDBOX)
        if risultato.modo == sandbox.MODO_RIDOTTA and not _modo_dichiarato:
            _modo_dichiarato = True
            logger.warning("Filtro immagini: sandbox ridotta (servizio iyokai-sandbox non raggiungibile)")
        esito = await _esito_da_sandbox(risultato, byte.sha256, guild_id)
        tenere = esito.verdetto != PULITA
        return _ricorda(guild_id, esito)
    finally:
        if not tenere:
            try:
                await quarantena.cancella(voce.nome)
            except Exception:
                logger.warning("Quarantena: file non cancellato", exc_info=True)


async def _esito_da_sandbox(r: sandbox.RisultatoSandbox, sha: str, guild_id: int) -> EsitoImmagine:
    if r.esito in MOTIVI_SANDBOX_MALEVOLI:
        return EsitoImmagine(MALEVOLA, sha, (f"sandbox_{r.esito}",), modo_sandbox=r.modo)
    if not r.riuscita:
        return EsitoImmagine(SOSPETTA, sha, (f"sandbox_{r.info.get('motivo', 'errore')}",), modo_sandbox=r.modo)
    motivi = [str(m) for m in r.info.get("motivi", [])]
    verdetto = SOSPETTA if motivi else PULITA
    qr = tuple(str(t) for t in r.info.get("qr", []))
    motivo_qr = qr_logic.giudica_qr_lista(list(qr))
    if motivo_qr:
        motivi.append(motivo_qr)
        verdetto = MALEVOLA
    dhash = int(r.info["dhash"], 16) if r.info.get("dhash") else None
    solo_avviso = False
    if dhash is not None:
        trovata = await libreria_immagini.cerca_impronta(dhash, guild_id)
        if trovata is not None:
            v = verdetto_di(trovata.voce.stato)
            if trovata.tipo == "uguale" and v:
                motivi.append(f"libreria_{trovata.voce.stato}_impronta")
                verdetto = _peggiore(verdetto, v)
            elif trovata.tipo == "simile":
                motivi.append("libreria_simile")
                solo_avviso = verdetto == PULITA
                verdetto = _peggiore(verdetto, SOSPETTA)
    return EsitoImmagine(
        verdetto, sha, tuple(motivi), dhash, qr, r.png if verdetto == PULITA else b"", modo_sandbox=r.modo,
        da_libreria=any(m.startswith("libreria_") for m in motivi) and not motivo_qr, solo_avviso=solo_avviso,
    )


async def impronte(dati: bytes) -> tuple[str, int | None]:
    """SHA-256 e dHash di un'immagine (per le aggiunte dell'owner). dHash None se la sandbox non risponde."""
    byte = controlla_byte(dati)
    if byte.troppo_grande or byte.tipo is None:
        return byte.sha256, None
    try:
        voce = await quarantena.salva(dati, 0, byte.sha256, ore=quarantena.ORE_PULITA)
    except Exception:
        return byte.sha256, None
    try:
        r = await coda_immagini.esegui(0, lambda: sandbox.analizza(voce.nome))
        return byte.sha256, (int(r.info["dhash"], 16) if r.riuscita and r.info.get("dhash") else None)
    except Exception:
        return byte.sha256, None
    finally:
        await quarantena.cancella(voce.nome)

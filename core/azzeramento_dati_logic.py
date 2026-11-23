"""
core/azzeramento_dati_logic.py
==============================
Azzerare tutti i dati del bot per un server, con 30 giorni di ritardo (UTL-228, D111). Solo il proprietario del server
la chiede (scrivendo il nome del server); i dati restano per 30 giorni e la richiesta si può annullare (proprietario del
server o proprietario del bot). Avviso all'inizio e 3 giorni prima. Se il proprietario del server cambia, la richiesta si
sospende e il nuovo proprietario deve confermarla (account rubato). Allo scadere si cancella tutto con il registro dei
dati (`core/data_registry.py`, cancellazione per server). Un solo punto per il comando e per il futuro pannello (D16).
Funzioni coperte: SPEC §19 (NF-04), catalogo #128 (UTL-228)
Dipende da: core/data_registry.py, core/repositories/azzeramento_repo.py, core/scheduler.py
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from core.data_registry import REGISTRO
from core.forget_user_service import righe_toccate, tabelle_esistenti
from core.repositories.azzeramento_repo import Richiesta, azzeramento_repo

logger = logging.getLogger("iyokai.azzeramento")

GIORNI_RITARDO = 30
GIORNI_PREAVVISO = 3
STATO_ATTIVA = "attiva"
STATO_SOSPESA = "sospesa"
AZIONE_PREAVVISO = "azzera_dati_preavviso"
AZIONE_ESEGUI = "azzera_dati_esegui"

ESEGUITA = "eseguita"
SOSPESA = "sospesa"
NON_PRONTA = "non_pronta"
NESSUNA = "nessuna"


class ServerNonPronto(RuntimeError):
    """Il server non è in memoria: senza sapere chi lo possiede non si cancella niente. Lo scheduler riprova."""


def nome_confermato(scritto: str | None, nome_server: str) -> bool:
    """Il nome del server scritto a mano: uguale, lettera per lettera (spazi ai lati esclusi)."""
    return bool(scritto) and bool(nome_server) and scritto.strip() == nome_server


def puo_chiedere(user_id: int, proprietario_server: int | None) -> bool:
    """Solo il proprietario del server. Mai un admin."""
    return proprietario_server is not None and user_id == proprietario_server


def puo_annullare(user_id: int, proprietario_server: int | None, proprietario_bot: int | None) -> bool:
    """Il proprietario del server o il proprietario del bot."""
    return user_id in {i for i in (proprietario_server, proprietario_bot) if i is not None}


def _scheduler():
    from core.scheduler import scheduler

    return scheduler


async def _pianifica(richiesta: Richiesta) -> None:
    """Mette in coda il preavviso (3 giorni prima) e l'esecuzione. I due numeri restano nella richiesta."""
    sched = _scheduler()
    payload = {"guild_id": richiesta.guild_id}
    preavviso = richiesta.esegui_il - timedelta(days=GIORNI_PREAVVISO)
    id_preavviso = await sched.schedule(
        richiesta.guild_id, richiesta.proprietario_id, AZIONE_PREAVVISO, preavviso, payload
    )
    id_esegui = await sched.schedule(
        richiesta.guild_id, richiesta.proprietario_id, AZIONE_ESEGUI, richiesta.esegui_il, payload
    )
    await azzeramento_repo.imposta_azioni(richiesta.guild_id, id_preavviso, id_esegui)


async def _togli_dalla_coda(richiesta: Richiesta) -> None:
    sched = _scheduler()
    for azione in (richiesta.azione_preavviso_id, richiesta.azione_esegui_id):
        if azione is not None:
            await sched.cancel(azione)


async def chiedi(guild_id: int, user_id: int, proprietario_server: int | None, adesso: datetime | None = None) -> Richiesta | None:
    """
    Registra la richiesta (dati intatti per 30 giorni). Solleva PermissionError se `user_id` non possiede il server.
    None se per il server c'è già una richiesta.
    """
    if not puo_chiedere(user_id, proprietario_server):
        raise PermissionError("Solo il proprietario del server può chiedere l'azzeramento dei dati.")
    adesso = adesso or datetime.now(timezone.utc)
    richiesta = await azzeramento_repo.crea(guild_id, user_id, user_id, adesso + timedelta(days=GIORNI_RITARDO))
    if richiesta is None:
        return None
    await _pianifica(richiesta)
    return await azzeramento_repo.get(guild_id)


async def annulla(guild_id: int, user_id: int, proprietario_server: int | None, proprietario_bot: int | None) -> Richiesta | None:
    """Annulla la richiesta (attiva o sospesa). PermissionError se non è il proprietario del server o del bot."""
    if not puo_annullare(user_id, proprietario_server, proprietario_bot):
        raise PermissionError("Solo il proprietario del server o del bot può annullare la richiesta.")
    richiesta = await azzeramento_repo.elimina(guild_id)
    if richiesta is not None:
        await _togli_dalla_coda(richiesta)
    return richiesta


async def sospendi_se_cambiato(guild_id: int, proprietario_attuale: int) -> Richiesta | None:
    """Il proprietario del server è cambiato: la richiesta attiva si sospende e si toglie dalla coda."""
    richiesta = await azzeramento_repo.get(guild_id)
    if richiesta is None or richiesta.stato != STATO_ATTIVA or richiesta.proprietario_id == proprietario_attuale:
        return None
    sospesa = await azzeramento_repo.sospendi(guild_id, proprietario_attuale)
    if sospesa is not None:
        await _togli_dalla_coda(richiesta)
    return sospesa


async def riprendi(guild_id: int, user_id: int, proprietario_server: int | None, adesso: datetime | None = None) -> Richiesta | None:
    """
    Il nuovo proprietario conferma una richiesta sospesa: i 30 giorni ripartono da adesso.
    PermissionError se non possiede il server. None se non c'è una richiesta sospesa.
    """
    if not puo_chiedere(user_id, proprietario_server):
        raise PermissionError("Solo il proprietario del server può confermare la richiesta.")
    adesso = adesso or datetime.now(timezone.utc)
    richiesta = await azzeramento_repo.riprendi(guild_id, user_id, adesso + timedelta(days=GIORNI_RITARDO))
    if richiesta is None:
        return None
    await _pianifica(richiesta)
    return await azzeramento_repo.get(guild_id)


async def _cancella_dati(conn, guild_id: int) -> dict[str, int]:
    """Ogni tabella del registro con la sua regola di cancellazione per server (ban e kick di sicurezza restano)."""
    cancellate: dict[str, int] = {}
    esistenti = await tabelle_esistenti(conn)
    for t in REGISTRO:
        sql = t.sql_cancella_server()
        if sql is None or t.nome not in esistenti:
            continue
        n = righe_toccate(await conn.execute(sql, guild_id))
        if n:
            cancellate[t.nome] = n
    for t in REGISTRO:  # ciò che deve sopravvivere alla cancellazione (contatore dei casi)
        if t.dopo_purga_server and t.nome in esistenti:
            await conn.execute(t.dopo_purga_server, guild_id)
    return cancellate


async def esegui(
    pool, guild_id: int, proprietario_attuale: int | None, adesso: datetime | None = None
) -> tuple[str, dict[str, int]]:
    """
    Cancella i dati solo se la richiesta è attiva, scaduta (30 giorni) e il proprietario del server è ancora quello
    che l'ha confermata. Altrimenti niente: proprietario cambiato = sospesa. Una transazione sola, con la riga bloccata.
    Solleva ServerNonPronto se non si conosce il proprietario (lo scheduler riprova).
    """
    adesso = adesso or datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        async with conn.transaction():
            r = await conn.fetchrow("SELECT * FROM richieste_azzeramento WHERE guild_id = $1 FOR UPDATE", guild_id)
            if r is None or r["stato"] != STATO_ATTIVA:
                return NESSUNA, {}
            if r["esegui_il"] > adesso:
                return NON_PRONTA, {}
            if proprietario_attuale is None:
                raise ServerNonPronto(f"Server {guild_id} non in memoria.")
            if proprietario_attuale != r["proprietario_id"]:
                await conn.execute(
                    "UPDATE richieste_azzeramento SET stato = 'sospesa', proprietario_id = $2 WHERE guild_id = $1",
                    guild_id, proprietario_attuale,
                )
                return SOSPESA, {}
            cancellate = await _cancella_dati(conn, guild_id)
            await conn.execute("DELETE FROM richieste_azzeramento WHERE guild_id = $1", guild_id)
    from core.database import db
    from core.premium_cache import invalida_cache_premium

    db.dimentica_server(guild_id)
    invalida_cache_premium(guild_id)
    logger.info("Dati del server %s azzerati (%d tabelle).", guild_id, len(cancellate))
    return ESEGUITA, cancellate

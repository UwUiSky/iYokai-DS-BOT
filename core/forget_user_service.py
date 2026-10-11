"""
core/forget_user_service.py
===========================
Cancella, rende anonimi o esporta i dati di un utente, seguendo il registro in
core/data_registry.py. Una sola transazione: o tutto o niente.
Funzioni coperte: SPEC §19 (NF-04, GDPR-2, #37)

Che cosa NON si cancella (e si dice all'utente): ban e kick (`retain_for_security`),
registri di sicurezza e ban globali, azioni ancora in coda, il titolare di un clan.
Il resto sì.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import asyncpg

from core.data_registry import REGISTRO, TabellaDati, tabelle_esportabili

logger = logging.getLogger("iyokai.privacy")

RIGHE_MAX_PER_TABELLA = 5000
ESPORTAZIONE_MAX_BYTE = 8 * 1024 * 1024  # sotto i 10 MiB di Discord (LIM-55)

# La richiesta stessa resta come prova: non fa parte di ciò che si "conserva" per sicurezza.
FUORI_DAL_RAPPORTO = frozenset({"data_deletion_requests"})


async def tabelle_esistenti(conn) -> set[str]:
    righe = await conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )
    return {r["table_name"] for r in righe}


def _conta(esito: str) -> int:
    try:
        return int(esito.rsplit(" ", 1)[-1])
    except ValueError:
        return 0


async def _dimentica_in(conn, user_id: int) -> dict[str, dict[str, int]]:
    esistenti = await tabelle_esistenti(conn)
    rapporto: dict[str, dict[str, int]] = {}
    for t in REGISTRO:
        if t.nome not in esistenti or t.nome in FUORI_DAL_RAPPORTO or not (
            t.colonne_utente or t.colonne_attore
        ):
            continue
        voce = {"cancellate": 0, "anonimizzate": 0, "conservate": 0}
        if t.colonne_utente:
            if t.utente == "cancella":
                voce["cancellate"] = _conta(await conn.execute(t.sql_cancella_utente(), user_id))
            elif t.utente == "anonimizza":
                voce["anonimizzate"] = _conta(await conn.execute(t.sql_anonimizza_utente(), user_id))
            if t.utente == "conserva" or t.conserva_se or t.conserva_utente_se:
                voce["conservate"] = await conn.fetchval(t.sql_conta_conservate(), user_id)
        for colonna in t.attori_da_azzerare():
            voce["anonimizzate"] += _conta(await conn.execute(t.sql_azzera_attore(colonna), user_id))
        if any(voce.values()):
            rapporto[t.nome] = voce
    return rapporto


async def dimentica_utente(pool: asyncpg.Pool, user_id: int, conn=None) -> dict[str, dict[str, int]]:
    """
    Cancella o anonimizza i dati di `user_id` in tutte le tabelle del registro.
    Restituisce {tabella: {cancellate, anonimizzate, conservate}} solo per le
    tabelle dove è successo qualcosa. Con `conn` entra nella transazione di chi chiama.
    """
    if conn is not None:
        return await _dimentica_in(conn, user_id)
    async with pool.acquire() as propria:
        async with propria.transaction():
            return await _dimentica_in(propria, user_id)


def riepilogo(rapporto: dict[str, dict[str, int]]) -> dict[str, int]:
    """Totali del rapporto: quante righe cancellate, anonimizzate, conservate."""
    totali = {"cancellate": 0, "anonimizzate": 0, "conservate": 0}
    for voce in rapporto.values():
        for chiave in totali:
            totali[chiave] += voce[chiave]
    return totali


def testo_rapporto(rapporto: dict[str, dict[str, int]]) -> str:
    """Il messaggio per l'utente: cosa è stato fatto e cosa è rimasto, e perché."""
    t = riepilogo(rapporto)
    righe = [
        f"Righe cancellate: {t['cancellate']}.",
        f"Righe rese anonime: {t['anonimizzate']}.",
    ]
    if t["conservate"]:
        righe.append(
            f"Righe conservate: {t['conservate']}. Restano per sicurezza dei server: "
            "ban, kick, registri di sicurezza e azioni ancora in coda."
        )
    return "\n".join(righe)


# ----------------------------------------------------------------------
# Esportazione (art. 15)
# ----------------------------------------------------------------------
def _valore(v):
    if isinstance(v, (bytes, bytearray, memoryview)):
        return None
    if isinstance(v, str):
        try:  # le colonne JSONB arrivano come testo
            if v[:1] in ("{", "["):
                return json.loads(v)
        except ValueError:
            pass
    return v


async def esporta_utente(
    pool: asyncpg.Pool, user_id: int, righe_max: int = RIGHE_MAX_PER_TABELLA
) -> dict:
    """Le righe dove compare `user_id`, tabella per tabella, senza i token."""
    async with pool.acquire() as conn:
        esistenti = await tabelle_esistenti(conn)
        tabelle: dict[str, dict] = {}
        for t in tabelle_esportabili():
            if t.nome not in esistenti:
                continue
            righe = await conn.fetch(t.sql_esporta(righe_max), user_id)
            if not righe:
                continue
            tabelle[t.nome] = {
                "descrizione": t.descrizione,
                "righe": [
                    {k: _valore(v) for k, v in dict(r).items() if k not in t.escludi_dall_esportazione}
                    for r in righe
                ],
            }
    return {
        "generato_il": datetime.now(timezone.utc).isoformat(),
        "utente": user_id,
        "nota": (
            "Copia dei dati che iYokai conserva su di te. I token di accesso non sono inclusi. "
            "Le note private dello staff e i registri di sicurezza possono comparire solo in parte."
        ),
        "tabelle": tabelle,
    }


def serializza_esportazione(dati: dict, limite_byte: int = ESPORTAZIONE_MAX_BYTE) -> tuple[bytes, list[str]]:
    """
    JSON leggibile. Se supera `limite_byte` toglie righe dalle tabelle più grandi
    (dimezzandole) finché ci sta, e dice quali ha accorciato.
    """
    accorciate: list[str] = []
    while True:
        testo = json.dumps(dati, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        if len(testo) <= limite_byte or not dati["tabelle"]:
            break
        nome, voce = max(dati["tabelle"].items(), key=lambda kv: len(kv[1]["righe"]))
        if len(voce["righe"]) <= 1:
            del dati["tabelle"][nome]
        else:
            voce["righe"] = voce["righe"][: len(voce["righe"]) // 2]
        if nome not in accorciate:
            accorciate.append(nome)
    if accorciate:
        dati["accorciate"] = accorciate
        testo = json.dumps(dati, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    return testo, accorciate


# ----------------------------------------------------------------------
# Richieste di cancellazione: eseguire o rifiutare
# ----------------------------------------------------------------------
async def esegui_richiesta(pool: asyncpg.Pool, richiesta_id: int, deciso_da: int) -> dict | None:
    """
    Approva una richiesta: cancella e chiude la richiesta nella STESSA transazione.
    Restituisce {"user_id", "rapporto"} oppure None se la richiesta non c'è o è già chiusa.
    """
    from core.repositories.data_deletion_request_repo import STATO_ESEGUITA, data_deletion_request_repo

    async with pool.acquire() as conn:
        async with conn.transaction():
            riga = await conn.fetchrow(
                "SELECT user_id FROM data_deletion_requests WHERE id = $1 AND stato = 'in_attesa' FOR UPDATE",
                richiesta_id,
            )
            if riga is None:
                return None
            user_id = riga["user_id"]
            rapporto = await dimentica_utente(pool, user_id, conn=conn)
            chiusa = await data_deletion_request_repo.chiudi(
                richiesta_id, STATO_ESEGUITA, deciso_da, {"tabelle": rapporto, "totali": riepilogo(rapporto)}, conn=conn
            )
            if not chiusa:  # non dovrebbe succedere: la riga è bloccata
                raise RuntimeError("Richiesta di cancellazione non chiudibile.")
    logger.info("Richiesta di cancellazione %s eseguita da %s.", richiesta_id, deciso_da)
    return {"user_id": user_id, "rapporto": rapporto}

"""
core/forget_user_service.py
===========================
Cancella, rende anonimi o esporta i dati di un utente, seguendo il registro in
core/data_registry.py. Una sola transazione: o tutto o niente.
Funzioni coperte: SPEC §19 (NF-04, GDPR-2, #37)

Che cosa NON si cancella (e si dice all'utente): ban e kick (`retain_for_security`),
registri di sicurezza e ban globali, sban programmati. Il titolare di un clan
non resta: il clan passa al co-titolare (o al membro più anziano), da solo si scioglie.
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


def righe_toccate(esito: str) -> int:
    try:
        return int(esito.rsplit(" ", 1)[-1])
    except ValueError:
        return 0


async def _clan_del_titolare(conn, user_id: int) -> dict[str, int]:
    """
    Prima di togliere l'utente da `clan_members`: ogni clan di cui è titolare passa al
    co-titolare, o al membro più anziano; senza altri membri il clan si scioglie (le
    righe figlie vanno via con ON DELETE CASCADE, l'attività vocale a mano). Dove è
    co-titolare il posto resta vuoto. Così `clans.owner_id` non punta mai a un assente.
    """
    esito = {"trasferiti": 0, "sciolti": 0, "co_titolare": 0}
    clan = await conn.fetch("SELECT id, co_owner_id FROM clans WHERE owner_id = $1 ORDER BY id FOR UPDATE", user_id)
    for riga in clan:
        erede = await conn.fetchval(
            """
            SELECT user_id FROM clan_members
            WHERE clan_id = $1 AND user_id <> $2
            ORDER BY (user_id = $3) DESC, joined_at, user_id
            LIMIT 1
            """,
            riga["id"], user_id, riga["co_owner_id"],
        )
        if erede is None:
            await conn.execute("DELETE FROM clan_voice_activity WHERE clan_id = $1", riga["id"])
            await conn.execute("DELETE FROM clans WHERE id = $1", riga["id"])
            esito["sciolti"] += 1
            continue
        await conn.execute(
            "UPDATE clans SET owner_id = $2, co_owner_id = CASE WHEN co_owner_id = $2 THEN NULL ELSE co_owner_id END "
            "WHERE id = $1",
            riga["id"], erede,
        )
        await conn.execute("UPDATE clan_members SET role = 'owner' WHERE clan_id = $1 AND user_id = $2", riga["id"], erede)
        esito["trasferiti"] += 1
    esito["co_titolare"] = righe_toccate(
        await conn.execute("UPDATE clans SET co_owner_id = NULL WHERE co_owner_id = $1", user_id)
    )
    return esito


async def _dimentica_in(conn, user_id: int) -> dict[str, dict[str, int]]:
    esistenti = await tabelle_esistenti(conn)
    rapporto: dict[str, dict[str, int]] = {}
    if {"clans", "clan_members"} <= esistenti:
        clan = await _clan_del_titolare(conn, user_id)
        if clan["sciolti"] or clan["trasferiti"] or clan["co_titolare"]:
            rapporto["clans"] = {
                "cancellate": clan["sciolti"],
                "anonimizzate": clan["trasferiti"] + clan["co_titolare"],
                "conservate": 0,
            }
    for t in REGISTRO:
        if t.nome not in esistenti or t.nome in FUORI_DAL_RAPPORTO or not (
            t.colonne_utente or t.colonne_attore
        ):
            continue
        voce = {"cancellate": 0, "anonimizzate": 0, "conservate": 0}
        if t.colonne_utente:
            if t.utente == "cancella":
                voce["cancellate"] = righe_toccate(await conn.execute(t.sql_cancella_utente(), user_id))
            elif t.utente == "anonimizza":
                voce["anonimizzate"] = righe_toccate(await conn.execute(t.sql_anonimizza_utente(), user_id))
            if t.utente == "conserva" or t.conserva_se or t.conserva_utente_se:
                voce["conservate"] = await conn.fetchval(t.sql_conta_conservate(), user_id)
        for colonna in t.attori_da_azzerare():
            voce["anonimizzate"] += righe_toccate(await conn.execute(t.sql_azzera_attore(colonna), user_id))
        if any(voce.values()):
            if t.nome in rapporto:  # il clan già descritto sopra: si sommano
                for chiave, valore in voce.items():
                    rapporto[t.nome][chiave] += valore
            else:
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
            "ban, kick, registri di sicurezza e sban programmati."
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


async def _chiavi_primarie(conn, nomi: list[str]) -> dict[str, tuple[str, ...]]:
    """{tabella: colonne della chiave primaria}, per ordinare l'esportazione in modo ripetibile."""
    righe = await conn.fetch(
        """
        SELECT c.relname AS tabella, a.attname AS colonna
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
        JOIN LATERAL unnest(i.indkey::int2[]) WITH ORDINALITY AS k(attnum, pos) ON TRUE
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum
        WHERE i.indisprimary AND c.relname = ANY($1::text[])
        ORDER BY c.relname, k.pos
        """,
        nomi,
    )
    chiavi: dict[str, list[str]] = {}
    for r in righe:
        chiavi.setdefault(r["tabella"], []).append(r["colonna"])
    return {t: tuple(c) for t, c in chiavi.items()}


def _riga_esportata(t: TabellaDati, riga, user_id: int) -> dict:
    """La riga senza i campi riservati e senza gli id di altre persone (staff, titolari)."""
    fuori = set(t.escludi_dall_esportazione)
    altri = set(t.colonne_attore) - set(t.colonne_utente)
    uscita = {}
    for k, v in dict(riga).items():
        if k in fuori:
            continue
        uscita[k] = None if (k in altri and v != user_id) else _valore(v)
    return uscita


async def esporta_utente(
    pool: asyncpg.Pool, user_id: int, righe_max: int = RIGHE_MAX_PER_TABELLA
) -> dict:
    """
    Le righe dove `user_id` è il SOGGETTO, tabella per tabella, senza i token: non quelle
    dove ha solo agito su altri (note, casi, ticket presi in carico). In ordine di chiave
    primaria; se una tabella supera `righe_max` il taglio è dichiarato in `troncate`.
    """
    troncate: list[str] = []
    async with pool.acquire() as conn:
        esistenti = await tabelle_esistenti(conn)
        esportabili = [t for t in tabelle_esportabili() if t.nome in esistenti]
        chiavi = await _chiavi_primarie(conn, [t.nome for t in esportabili])
        tabelle: dict[str, dict] = {}
        for t in esportabili:
            righe = await conn.fetch(t.sql_esporta(righe_max + 1, chiavi.get(t.nome, ())), user_id)
            if not righe:
                continue
            if len(righe) > righe_max:
                righe = righe[:righe_max]
                troncate.append(t.nome)
            tabelle[t.nome] = {
                "descrizione": t.descrizione,
                "righe": [_riga_esportata(t, r, user_id) for r in righe],
            }
            if t.nome in troncate:
                tabelle[t.nome]["troncata"] = f"Solo le prime {righe_max} righe su più."
    dati = {
        "generato_il": datetime.now(timezone.utc).isoformat(),
        "utente": user_id,
        "nota": (
            "Copia dei dati che iYokai conserva su di te. I token di accesso non sono inclusi. "
            "Le note private dello staff e i registri di sicurezza possono comparire solo in parte; "
            "gli id dello staff non compaiono."
        ),
        "tabelle": tabelle,
    }
    if troncate:
        dati["troncate"] = troncate
    return dati


def serializza_esportazione(dati: dict, limite_byte: int = ESPORTAZIONE_MAX_BYTE) -> tuple[bytes, list[str]]:
    """
    JSON leggibile. Se supera `limite_byte` toglie righe dalle tabelle più grandi
    (dimezzandole) finché ci sta, e dice quali ha accorciato. Ogni riga si serializza
    UNA volta sola (la misura); il documento intero una volta, più una per ogni
    correzione se la stima era corta.
    """

    def _testo(d: dict) -> bytes:
        return json.dumps(d, ensure_ascii=False, indent=2, default=str).encode("utf-8")

    accorciate: list[str] = []
    testo = _testo(dati)
    if len(testo) <= limite_byte or not dati["tabelle"]:
        return testo, accorciate

    misure = {
        nome: [len(json.dumps(r, ensure_ascii=False, indent=2, default=str).encode("utf-8")) + 6 for r in voce["righe"]]
        for nome, voce in dati["tabelle"].items()
    }
    eccesso = len(testo) - limite_byte + 256  # margine per la chiave "accorciate" e gli arrotondamenti
    while eccesso > 0 and dati["tabelle"]:
        nome, voce = max(dati["tabelle"].items(), key=lambda kv: sum(misure[kv[0]]))
        righe = voce["righe"]
        if len(righe) <= 1:
            eccesso -= sum(misure[nome]) + 80
            del dati["tabelle"][nome], misure[nome]
        else:
            tieni = len(righe) // 2
            eccesso -= sum(misure[nome][tieni:])
            voce["righe"], misure[nome] = righe[:tieni], misure[nome][:tieni]
        if nome not in accorciate:
            accorciate.append(nome)
    dati["accorciate"] = accorciate
    testo = _testo(dati)
    while len(testo) > limite_byte and dati["tabelle"]:  # la stima era corta: si toglie ancora
        nome, voce = max(dati["tabelle"].items(), key=lambda kv: len(kv[1]["righe"]))
        if len(voce["righe"]) <= 1:
            del dati["tabelle"][nome]
        else:
            voce["righe"] = voce["righe"][: len(voce["righe"]) // 2]
        if nome not in accorciate:
            accorciate.append(nome)
        testo = _testo(dati)
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

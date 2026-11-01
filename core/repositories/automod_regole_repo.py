"""
core/repositories/automod_regole_repo.py
========================================
Righe della tabella `automod_regole` (filtri e regole personali dei server). Solo lettura e scrittura:
i controlli e la cache stanno in core/automod_regole_service.py. La tabella nasce nella migrazione 0500.
Funzioni coperte: SPEC §6 (AMD-029..061), D63
"""

from __future__ import annotations

import json

from core.automod_regole_logic import Regola, regola_a_json, regola_da_json


def _json(valore):
    return json.loads(valore) if isinstance(valore, str) else valore


def _regola(riga) -> Regola:
    return regola_da_json({
        "id": riga["id"], "guild_id": riga["guild_id"], "chiave": riga["chiave"], "tipo": riga["tipo"],
        "nome": riga["nome"], "evento": riga["evento"], "attiva": riga["attiva"], "gruppo": riga["gruppo"],
        "innesco": _json(riga["innesco"]), "condizioni": _json(riga["condizioni"]),
        "azioni": _json(riga["azioni"]), "contatore": _json(riga["contatore"]), "calore": riga["calore"],
    })


class AutomodRegoleRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self):
        return self._pool_provider()

    async def elenca(self, guild_id: int) -> list[Regola]:
        righe = await self._pool.fetch("SELECT * FROM automod_regole WHERE guild_id = $1 ORDER BY id", guild_id)
        return [_regola(r) for r in righe]

    async def conta_personali(self, guild_id: int) -> int:
        return await self._pool.fetchval(
            "SELECT count(*) FROM automod_regole WHERE guild_id = $1 AND tipo = 'personale'", guild_id)

    async def prossimo_id(self) -> int:
        return await self._pool.fetchval("SELECT nextval(pg_get_serial_sequence('automod_regole', 'id'))")

    async def salva(self, guild_id: int, regola: Regola, autore_id: int | None, regola_id: int | None = None) -> None:
        j = regola_a_json(regola)
        await self._pool.execute(
            """
            INSERT INTO automod_regole (id, guild_id, chiave, tipo, nome, evento, attiva, gruppo, innesco, condizioni,
                                        azioni, contatore, calore, aggiornata_da)
            VALUES (COALESCE($14::bigint, nextval(pg_get_serial_sequence('automod_regole', 'id'))),
                    $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10::jsonb, $11::jsonb, $12, $13)
            ON CONFLICT (guild_id, chiave) DO UPDATE SET
                nome = EXCLUDED.nome, evento = EXCLUDED.evento, attiva = EXCLUDED.attiva, gruppo = EXCLUDED.gruppo,
                innesco = EXCLUDED.innesco, condizioni = EXCLUDED.condizioni, azioni = EXCLUDED.azioni,
                contatore = EXCLUDED.contatore, calore = EXCLUDED.calore,
                aggiornata_da = EXCLUDED.aggiornata_da, aggiornata_il = now()
            """,
            guild_id, regola.chiave, regola.tipo, regola.nome, regola.evento, regola.attiva, regola.gruppo,
            json.dumps(j["innesco"]), json.dumps(j["condizioni"]), json.dumps(j["azioni"]),
            None if j["contatore"] is None else json.dumps(j["contatore"]), regola.calore, autore_id, regola_id,
        )

    async def elimina(self, guild_id: int, chiave: str) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM automod_regole WHERE guild_id = $1 AND chiave = $2 AND tipo = 'personale'", guild_id, chiave)
        return esito.endswith(" 1")

    async def imposta_gruppo(self, guild_id: int, gruppo: str, attiva: bool) -> int:
        esito = await self._pool.execute(
            "UPDATE automod_regole SET attiva = $3, aggiornata_il = now() WHERE guild_id = $1 AND gruppo = $2 AND attiva <> $3",
            guild_id, gruppo, attiva)
        return int(esito.split()[-1])

    async def cambia_timeout(self, guild_id: int, vecchio: int, nuovo: int) -> None:
        """Nelle righe dei filtri sposta i timeout uguali a `vecchio` al valore `nuovo` (le personalizzate restano)."""
        await self._pool.execute(
            """
            UPDATE automod_regole SET aggiornata_il = now(), azioni = (
                SELECT jsonb_agg(CASE WHEN e->>'t' = 'timeout' AND (e->>'secondi')::bigint = $2
                                      THEN jsonb_set(e, '{secondi}', to_jsonb($3::bigint)) ELSE e END ORDER BY o)
                FROM jsonb_array_elements(azioni) WITH ORDINALITY AS x(e, o))
            WHERE guild_id = $1 AND tipo = 'filtro' AND jsonb_array_length(azioni) > 0
            """,
            guild_id, vecchio, nuovo)


def _get_pool():
    from core.database import db
    return db.pool


automod_regole_repo = AutomodRegoleRepository(pool_provider=_get_pool)

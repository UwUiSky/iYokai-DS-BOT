"""
core/repositories/rete_repo.py
==============================
Accesso al database della rete di protezione tra server (VER-025): impostazioni, segnalazioni e consegne, server
bloccati dal proprietario del bot, timeout messi per account compromessi, proposte della rete dei ban.
Tabelle: migrazione 0820, dichiarate in core/data_registry.py. Valori sempre come parametri.
Funzioni coperte: SPEC §6.22 (VER-025)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

CAMPI_IMPOSTAZIONI = {
    "ricezione": bool, "canale_id": (int, type(None)), "mostra_origine": bool, "timeout_ore": int,
    "ban_aderisce": bool, "ban_modo": str,
}
STATI_PROPOSTA = ("proposta", "applicato", "rifiutato", "annullato", "fallito")


@dataclass(frozen=True)
class ImpostazioniRete:
    guild_id: int
    ricezione: bool = True
    canale_id: int | None = None
    mostra_origine: bool = False
    timeout_ore: int = 24
    ban_aderisce: bool = False
    ban_modo: str = "proposta"


class ReteRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # --- impostazioni -------------------------------------------------
    async def impostazioni(self, guild_id: int) -> ImpostazioniRete:
        r = await self._pool.fetchrow(
            "SELECT ricezione, canale_id, mostra_origine, timeout_ore, ban_aderisce, ban_modo FROM rete_impostazioni WHERE guild_id = $1",
            guild_id,
        )
        return ImpostazioniRete(guild_id, **dict(r)) if r else ImpostazioniRete(guild_id)

    async def imposta(self, guild_id: int, **campi) -> None:
        """Cambia solo i campi dati. Un nome o un tipo fuori dall'elenco fisso è un errore (mai SQL costruito da fuori)."""
        if not campi:
            return
        for nome, valore in campi.items():
            if nome not in CAMPI_IMPOSTAZIONI or not isinstance(valore, CAMPI_IMPOSTAZIONI[nome]):
                raise ValueError(f"impostazione non valida: {nome}")
        if "ban_modo" in campi and campi["ban_modo"] not in ("proposta", "automatico"):
            raise ValueError("ban_modo")
        nomi = list(campi)
        colonne = ", ".join(nomi)
        segnaposto = ", ".join(f"${i + 2}" for i in range(len(nomi)))
        aggiorna = ", ".join(f"{n} = EXCLUDED.{n}" for n in nomi)
        aderito = ", aderito_il = CASE WHEN EXCLUDED.ban_aderisce THEN COALESCE(rete_impostazioni.aderito_il, now()) ELSE NULL END" if "ban_aderisce" in nomi else ""
        await self._pool.execute(
            f"INSERT INTO rete_impostazioni (guild_id, {colonne}) VALUES ($1, {segnaposto}) "
            f"ON CONFLICT (guild_id) DO UPDATE SET {aggiorna}{aderito}",
            guild_id, *campi.values(),
        )
        if "ban_aderisce" in nomi and campi["ban_aderisce"]:
            await self._pool.execute("UPDATE rete_impostazioni SET aderito_il = COALESCE(aderito_il, now()) WHERE guild_id = $1", guild_id)

    async def aderenti_ban(self) -> dict[int, str]:
        righe = await self._pool.fetch("SELECT guild_id, ban_modo FROM rete_impostazioni WHERE ban_aderisce")
        return {r["guild_id"]: r["ban_modo"] for r in righe}

    # --- segnalazioni e consegne ---------------------------------------
    async def segnalazioni_origine_oggi(self, guild_id: int) -> int:
        return await self._pool.fetchval(
            "SELECT count(*) FROM rete_segnalazioni WHERE guild_origine = $1 AND creata_il > now() - interval '1 day'", guild_id
        )

    async def gia_segnalato(self, user_id: int, categoria: str, ore: int) -> bool:
        return bool(await self._pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM rete_segnalazioni WHERE user_id = $1 AND categoria = $2 "
            "AND creata_il > now() - make_interval(hours => $3))", user_id, categoria, ore,
        ))

    async def registra_segnalazione(self, user_id: int, guild_origine: int, categoria: str, gravita: str) -> int:
        return await self._pool.fetchval(
            "INSERT INTO rete_segnalazioni (user_id, guild_origine, categoria, gravita) VALUES ($1, $2, $3, $4) RETURNING id",
            user_id, guild_origine, categoria, gravita,
        )

    async def consegne_oggi(self, guild_id: int) -> int:
        return await self._pool.fetchval(
            "SELECT count(*) FROM rete_consegne WHERE guild_id = $1 AND consegnata_il > now() - interval '1 day'", guild_id
        )

    async def registra_consegna(self, segnalazione_id: int, guild_id: int) -> None:
        await self._pool.execute("INSERT INTO rete_consegne (segnalazione_id, guild_id) VALUES ($1, $2)", segnalazione_id, guild_id)

    # --- server bloccati -----------------------------------------------
    async def e_bloccato(self, guild_id: int) -> bool:
        return bool(await self._pool.fetchval("SELECT EXISTS (SELECT 1 FROM rete_server_bloccati WHERE guild_id = $1)", guild_id))

    async def blocca(self, guild_id: int, bloccato_da: int, motivo: str | None) -> None:
        await self._pool.execute(
            "INSERT INTO rete_server_bloccati (guild_id, bloccato_da, motivo) VALUES ($1, $2, $3) "
            "ON CONFLICT (guild_id) DO UPDATE SET bloccato_da = EXCLUDED.bloccato_da, motivo = EXCLUDED.motivo, bloccato_il = now()",
            guild_id, bloccato_da, (motivo or "")[:200] or None,
        )

    async def sblocca(self, guild_id: int) -> bool:
        return (await self._pool.execute("DELETE FROM rete_server_bloccati WHERE guild_id = $1", guild_id)) != "DELETE 0"

    async def elenco_bloccati(self, limite: int = 25) -> list[asyncpg.Record]:
        return await self._pool.fetch("SELECT guild_id, motivo, bloccato_il FROM rete_server_bloccati ORDER BY bloccato_il DESC LIMIT $1", limite)

    # --- timeout per account compromessi --------------------------------
    async def registra_timeout(self, guild_id: int, user_id: int, origine_guild: int, fino_a: datetime, case_number: int | None) -> None:
        await self._pool.execute(
            "INSERT INTO rete_timeout (guild_id, user_id, origine_guild, fino_a, case_number) VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (guild_id, user_id) DO UPDATE SET origine_guild = EXCLUDED.origine_guild, fino_a = EXCLUDED.fino_a, "
            "case_number = EXCLUDED.case_number, creato_il = now(), annullato_da = NULL, annullato_il = NULL",
            guild_id, user_id, origine_guild, fino_a, case_number,
        )

    async def timeout_attivo(self, guild_id: int, user_id: int) -> bool:
        return bool(await self._pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM rete_timeout WHERE guild_id = $1 AND user_id = $2 AND fino_a > now() AND annullato_il IS NULL)",
            guild_id, user_id,
        ))

    async def annulla_timeout(self, guild_id: int, user_id: int, da: int) -> bool:
        """True se c'era un timeout della rete ancora attivo e ora è segnato come tolto."""
        r = await self._pool.execute(
            "UPDATE rete_timeout SET annullato_da = $3, annullato_il = now() "
            "WHERE guild_id = $1 AND user_id = $2 AND annullato_il IS NULL AND fino_a > now()", guild_id, user_id, da,
        )
        return r != "UPDATE 0"

    # --- rete dei ban --------------------------------------------------
    async def crea_proposta(self, user_id: int, guild_origine: int, guild_dest: int, categoria: str) -> int | None:
        """Id della proposta nuova, None se per quella terna esiste già (niente doppioni, niente catene)."""
        return await self._pool.fetchval(
            "INSERT INTO rete_ban_proposte (user_id, guild_origine, guild_dest, categoria) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (user_id, guild_origine, guild_dest) DO NOTHING RETURNING id",
            user_id, guild_origine, guild_dest, categoria,
        )

    async def proposta(self, proposta_id: int) -> asyncpg.Record | None:
        return await self._pool.fetchrow("SELECT * FROM rete_ban_proposte WHERE id = $1", proposta_id)

    async def decidi(self, proposta_id: int, da_stato: str, a_stato: str, deciso_da: int | None, case_number: int | None = None) -> bool:
        """Passa la proposta da uno stato all'altro UNA volta sola (due click insieme: vince uno)."""
        if a_stato not in STATI_PROPOSTA or da_stato not in STATI_PROPOSTA:
            raise ValueError("stato")
        r = await self._pool.execute(
            "UPDATE rete_ban_proposte SET stato = $3, deciso_da = $4, deciso_il = now(), case_number = COALESCE($5, case_number) "
            "WHERE id = $1 AND stato = $2", proposta_id, da_stato, a_stato, deciso_da, case_number,
        )
        return r != "UPDATE 0"

    async def ultima_applicata(self, user_id: int, guild_dest: int) -> asyncpg.Record | None:
        return await self._pool.fetchrow(
            "SELECT * FROM rete_ban_proposte WHERE user_id = $1 AND guild_dest = $2 AND stato = 'applicato' ORDER BY id DESC LIMIT 1",
            user_id, guild_dest,
        )



def _get_pool():
    from core.database import db

    return db.pool


rete_repo = ReteRepository(pool_provider=_get_pool)

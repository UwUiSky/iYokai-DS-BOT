"""
core/repositories/custom_command_repo.py
========================================
Comandi personalizzati del server (NF-09) e prefisso per usarli
(guild_config.prefix, M 10.15). Tabella: core/migrations/0082_custom_commands.sql.
Funzioni coperte: SPEC §22 (NF-09)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.repositories.tetto_server import tetto_per_server

from core.custom_command_logic import MAX_TAG


@dataclass(frozen=True)
class CustomCommand:
    guild_id: int
    name: str
    response: str
    use_embed: bool
    role_id: int | None
    role_action: str
    cooldown_seconds: int
    ping_ruoli: bool
    uses: int
    permesso: str | None = None
    bersaglio: bool = False
    cancella_innesco: bool = False
    invio: str = "canale"
    canale_id: int | None = None
    reazioni: tuple = ()
    si_cancella_dopo: int | None = None
    cancella_messaggi: int | None = None
    solo_nsfw: bool = False
    anche_modificati: bool = False
    gruppo: str | None = None
    created_by: int | None = None


_COLONNE = (
    "guild_id, name, response, use_embed, role_id, role_action, cooldown_seconds, ping_ruoli, uses, permesso, bersaglio, "
    "cancella_innesco, invio, canale_id, reazioni, si_cancella_dopo, cancella_messaggi, solo_nsfw, anche_modificati, gruppo, created_by"
)
_MODIFICABILI = {
    "response", "use_embed", "role_id", "role_action", "cooldown_seconds", "ping_ruoli", "permesso", "bersaglio", "cancella_innesco",
    "invio", "canale_id", "reazioni", "si_cancella_dopo", "cancella_messaggi", "solo_nsfw", "anche_modificati", "gruppo", "created_by",
}


class CustomCommandRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def create_tag(
        self,
        guild_id: int,
        name: str,
        *,
        response: str,
        use_embed: bool,
        role_id: int | None,
        role_action: str,
        cooldown_seconds: int,
        ping_ruoli: bool,
        created_by: int,
    ) -> str:
        """"ok", "esiste" (nome già preso) o "pieno" (tetto per server). Controllo e scrittura in una query."""
        async with tetto_per_server(self._pool, "custom_commands", guild_id) as conn:
            riga = await conn.fetchrow(
                """
                INSERT INTO custom_commands
                    (guild_id, name, response, use_embed, role_id, role_action, cooldown_seconds, ping_ruoli, created_by)
                SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9
                WHERE (SELECT count(*) FROM custom_commands WHERE guild_id = $1) < $10
                ON CONFLICT (guild_id, name) DO NOTHING
                RETURNING name
                """,
                guild_id, name, response, use_embed, role_id, role_action, cooldown_seconds, ping_ruoli,
                created_by, MAX_TAG,
            )
            if riga is not None:
                return "ok"
            esiste = await conn.fetchval(
                "SELECT 1 FROM custom_commands WHERE guild_id = $1 AND name = $2", guild_id, name
            )
            return "esiste" if esiste else "pieno"

    async def get_tag(self, guild_id: int, name: str) -> CustomCommand | None:
        r = await self._pool.fetchrow(
            f"SELECT {_COLONNE} FROM custom_commands WHERE guild_id = $1 AND name = $2", guild_id, name
        )
        return None if r is None else CustomCommand(**dict(r))

    async def list_tags(self, guild_id: int) -> list[CustomCommand]:
        righe = await self._pool.fetch(
            f"SELECT {_COLONNE} FROM custom_commands WHERE guild_id = $1 ORDER BY name", guild_id
        )
        return [CustomCommand(**dict(r)) for r in righe]

    async def search_names(self, guild_id: int, parte: str, limite: int = 25) -> list[str]:
        """Per il completamento automatico: al massimo `limite` nomi che contengono `parte`."""
        pulita = parte.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        righe = await self._pool.fetch(
            "SELECT name FROM custom_commands WHERE guild_id = $1 AND name LIKE $2 ORDER BY name LIMIT $3",
            guild_id, f"%{pulita}%", limite,
        )
        return [r["name"] for r in righe]

    async def update_tag(self, guild_id: int, name: str, **campi) -> bool:
        """Cambia solo i campi dati (nomi presi da un elenco fisso, valori sempre come parametri)."""
        if not campi or not set(campi) <= _MODIFICABILI:
            raise ValueError(f"Campi non modificabili: {sorted(set(campi) - _MODIFICABILI)}")
        impostazioni = ", ".join(f"{col} = ${i}" for i, col in enumerate(campi, start=3))
        esito = await self._pool.execute(
            f"UPDATE custom_commands SET {impostazioni} WHERE guild_id = $1 AND name = $2",
            guild_id, name, *campi.values(),
        )
        return esito.endswith(" 1")

    async def get_risposte(self, guild_id: int, name: str) -> list[tuple[int, str]]:
        """Le risposte con peso del tag (vuoto: vale il testo del tag)."""
        righe = await self._pool.fetch(
            "SELECT peso, testo FROM custom_command_risposte WHERE guild_id = $1 AND name = $2 ORDER BY pos", guild_id, name)
        return [(r["peso"], r["testo"]) for r in righe]

    async def set_risposte(self, guild_id: int, name: str, risposte: list[tuple[int, str]]) -> bool:
        """Sostituisce le risposte (al massimo 5). False se il tag non esiste. Vuoto: le toglie."""
        async with self._pool.acquire() as con, con.transaction():
            if not await con.fetchval("SELECT 1 FROM custom_commands WHERE guild_id = $1 AND name = $2 FOR UPDATE", guild_id, name):
                return False
            await con.execute("DELETE FROM custom_command_risposte WHERE guild_id = $1 AND name = $2", guild_id, name)
            for i, (peso, testo) in enumerate(risposte[:5], start=1):
                await con.execute(
                    "INSERT INTO custom_command_risposte (guild_id, name, pos, peso, testo) VALUES ($1,$2,$3,$4,$5)",
                    guild_id, name, i, peso, testo)
            return True

    async def sostituisci(self, guild_id: int, da: str, a: str, applica: bool) -> int:
        """Quanti tag cambiano se si scrive `a` al posto di `da` nel testo (maiuscole contano). Con `applica` li cambia. Un tag che
        andrebbe oltre i 4.000 caratteri non si tocca."""
        condizione = "guild_id = $1 AND position($2 in response) > 0 AND char_length(replace(response, $2, $3)) <= 4000"
        if not applica:
            return await self._pool.fetchval(f"SELECT count(*) FROM custom_commands WHERE {condizione}", guild_id, da, a)
        esito = await self._pool.execute(
            f"UPDATE custom_commands SET response = replace(response, $2, $3) WHERE {condizione}", guild_id, da, a)
        return int(esito.split()[-1])

    async def tutti_con_risposte(self, guild_id: int):
        tags = await self.list_tags(guild_id)
        righe = await self._pool.fetch(
            "SELECT name, peso, testo FROM custom_command_risposte WHERE guild_id = $1 ORDER BY name, pos", guild_id)
        risposte: dict[str, list] = {}
        for r in righe:
            risposte.setdefault(r["name"], []).append((r["peso"], r["testo"]))
        return tags, risposte

    async def importa(self, guild_id: int, voci: list[dict], creato_da: int) -> tuple[int, int]:
        """(aggiunti, saltati): salta i nomi già presi e quelli oltre il tetto di 50 per server."""
        aggiunti = 0
        for v in voci:
            esito = await self.create_tag(
                guild_id, v["nome"], response=v["testo"], use_embed=v["use_embed"], role_id=None, role_action="nessuna",
                cooldown_seconds=v["pausa"], ping_ruoli=False, created_by=creato_da)
            if esito != "ok":
                continue
            await self.update_tag(
                guild_id, v["nome"], permesso=v["permesso"], bersaglio=v["bersaglio"], cancella_innesco=v["cancella_innesco"],
                invio=v["invio"], reazioni=v["reazioni"], si_cancella_dopo=v["si_cancella_dopo"],
                cancella_messaggi=v["cancella_messaggi"], solo_nsfw=v["solo_nsfw"], anche_modificati=v["anche_modificati"], gruppo=v["gruppo"])
            if v["risposte"]:
                await self.set_risposte(guild_id, v["nome"], v["risposte"])
            aggiunti += 1
        return aggiunti, len(voci) - aggiunti

    async def crea_pacchetto(self, guild_id: int, dati: dict, creato_da: int, codice: str) -> None:
        import json
        await self._pool.execute("DELETE FROM tag_pacchetti WHERE scade_il < now()")
        await self._pool.execute(
            "INSERT INTO tag_pacchetti (codice, guild_id, dati, creato_da, scade_il) VALUES ($1,$2,$3::jsonb,$4, now() + interval '7 days')",
            codice, guild_id, json.dumps(dati), creato_da)

    async def leggi_pacchetto(self, codice: str):
        """Il contenuto del pacchetto se il codice c'è e non è scaduto."""
        import json
        grezzo = await self._pool.fetchval("SELECT dati FROM tag_pacchetti WHERE codice = $1 AND scade_il > now()", codice.strip())
        return None if grezzo is None else json.loads(grezzo)

    async def gruppo(self, guild_id: int, gruppo: str):
        return await self._pool.fetchrow("SELECT canale_id, ruolo_id FROM tag_gruppi WHERE guild_id = $1 AND gruppo = $2", guild_id, gruppo)

    async def imposta_gruppo(self, guild_id: int, gruppo: str, canale_id: int | None, ruolo_id: int | None) -> None:
        await self._pool.execute(
            "INSERT INTO tag_gruppi (guild_id, gruppo, canale_id, ruolo_id) VALUES ($1,$2,$3,$4) "
            "ON CONFLICT (guild_id, gruppo) DO UPDATE SET canale_id = $3, ruolo_id = $4", guild_id, gruppo, canale_id, ruolo_id)

    async def togli_gruppo(self, guild_id: int, gruppo: str) -> bool:
        await self._pool.execute("UPDATE custom_commands SET gruppo = NULL WHERE guild_id = $1 AND gruppo = $2", guild_id, gruppo)
        return (await self._pool.execute("DELETE FROM tag_gruppi WHERE guild_id = $1 AND gruppo = $2", guild_id, gruppo)).endswith(" 1")

    async def elenco_gruppi(self, guild_id: int):
        return await self._pool.fetch(
            "SELECT g.gruppo, g.canale_id, g.ruolo_id, (SELECT count(*) FROM custom_commands c WHERE c.guild_id = g.guild_id AND c.gruppo = g.gruppo) AS tag "
            "FROM tag_gruppi g WHERE g.guild_id = $1 ORDER BY g.gruppo LIMIT 25", guild_id)

    async def nomi_di(self, guild_id: int, user_id: int, parte: str, limite: int = 25) -> list[str]:
        """Per il completamento: i tag creati da `user_id` che contengono `parte`."""
        pulita = parte.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        righe = await self._pool.fetch(
            "SELECT name FROM custom_commands WHERE guild_id = $1 AND created_by = $2 AND name LIKE $3 ORDER BY name LIMIT $4",
            guild_id, user_id, f"%{pulita}%", limite)
        return [r["name"] for r in righe]

    async def conta_di(self, guild_id: int, user_id: int) -> int:
        return await self._pool.fetchval("SELECT count(*) FROM custom_commands WHERE guild_id = $1 AND created_by = $2", guild_id, user_id)

    async def delete_tag_di(self, guild_id: int, name: str, user_id: int) -> bool:
        return (await self._pool.execute(
            "DELETE FROM custom_commands WHERE guild_id = $1 AND name = $2 AND created_by = $3", guild_id, name, user_id)).endswith(" 1")

    async def prendi(self, guild_id: int, name: str, nuovo: int, ex_autore_presente) -> str:
        """«ok» se il tag passa a `nuovo`; «non_esiste», «tuo» o «autore_presente». `ex_autore_presente(user_id) -> bool`."""
        tag = await self.get_tag(guild_id, name)
        if tag is None:
            return "non_esiste"
        if tag.created_by == nuovo:
            return "tuo"
        if tag.created_by is not None and ex_autore_presente(tag.created_by):
            return "autore_presente"
        await self._pool.execute(
            "UPDATE custom_commands SET created_by = $3 WHERE guild_id = $1 AND name = $2 AND created_by IS NOT DISTINCT FROM $4",
            guild_id, name, nuovo, tag.created_by)
        return "ok"

    async def canale_cancellato(self, guild_id: int, channel_id: int) -> None:
        """Un canale è stato cancellato: i tag che rispondevano lì tornano a rispondere nel canale dove si usano."""
        await self._pool.execute(
            "UPDATE custom_commands SET invio = 'canale', canale_id = NULL WHERE guild_id = $1 AND canale_id = $2", guild_id, channel_id)
        await self._pool.execute("UPDATE tag_gruppi SET canale_id = NULL WHERE guild_id = $1 AND canale_id = $2", guild_id, channel_id)

    async def delete_tag(self, guild_id: int, name: str) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM custom_commands WHERE guild_id = $1 AND name = $2", guild_id, name
        )
        return esito.endswith(" 1")

    async def add_use(self, guild_id: int, name: str) -> None:
        await self._pool.execute(
            "UPDATE custom_commands SET uses = uses + 1 WHERE guild_id = $1 AND name = $2", guild_id, name
        )

    async def get_prefix(self, guild_id: int) -> str | None:
        return await self._pool.fetchval("SELECT prefix FROM guild_config WHERE guild_id = $1", guild_id)

    async def set_prefix(self, guild_id: int, prefix: str | None) -> None:
        await self._pool.execute(
            """
            INSERT INTO guild_config (guild_id, prefix) VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET prefix = EXCLUDED.prefix, updated_at = now()
            """,
            guild_id, prefix,
        )


def _get_pool():
    from core.database import db
    return db.pool


custom_command_repo = CustomCommandRepository(pool_provider=_get_pool)

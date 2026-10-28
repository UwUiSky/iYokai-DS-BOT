"""
core/repositories/ai_gioco_repo.py
==================================
Tabelle dei giochi con l'AI (migrazione 0421): World Boss (config, eventi, colpi, boss di rete e totali),
mostri e storie della libreria comune, dungeon di gruppo, misteri, spiriti e frammenti di lore.
Funzioni coperte: SPEC §25.49–§25.59, §25.64, §25.70–§25.72, §25.99 (NF-24)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from datetime import date, datetime, timedelta, timezone

import asyncpg

from core.boss_logic import FERITA_SECONDI, RITMO_CONTRATTACCO, Mostro
from core.dungeon_logic import Nodo, Scelta, Storia


@dataclass(frozen=True)
class BossConfig:
    guild_id: int
    attivo: bool = False
    canale_id: int | None = None
    giorni: tuple[int, ...] = ()
    ora: int = 21
    fuso: str = "Europe/Rome"
    rete: bool = False
    ruolo_premio_id: int | None = None
    ruolo_premio_ore: int = 24
    ultimo_giorno: date | None = None


_CAMPI_BOSS = {f.name for f in fields(BossConfig)} - {"guild_id", "ultimo_giorno"}


@dataclass(frozen=True)
class BossEvento:
    id: int
    guild_id: int
    channel_id: int
    message_id: int | None
    nome: str
    aspetto: str
    frasi: tuple[str, ...]
    vita_max: int
    vita: int
    azioni: int
    stato: str
    rete_id: int | None
    creato_il: datetime
    scade_il: datetime


@dataclass(frozen=True)
class EsitoAzione:
    """Cosa è successo a un'azione sul boss. `stato`: ok, chiuso, attesa, ferito."""

    stato: str
    vita: int = 0
    danno: int = 0
    sconfitto: bool = False
    contrattacco: int = 0  # quante persone ha ferito
    secondi: int = 0  # attesa o ferita rimasta


@dataclass(frozen=True)
class Partita:
    id: int
    guild_id: int
    channel_id: int
    message_id: int | None
    storia_id: int
    nodo: str
    stato: str
    scade_il: datetime
    cronologia: tuple[str, ...]
    esito: str | None


@dataclass(frozen=True)
class Mistero:
    id: int
    guild_id: int
    titolo: str
    indizio: str
    premio: str
    premio_valore: int
    durata_ore: int
    stato: str
    risolto_da: int | None


def _evento(r) -> BossEvento:
    v = {f.name: r[f.name] for f in fields(BossEvento)}
    v["frasi"] = tuple(v["frasi"] or ())
    return BossEvento(**v)


def _partita(r) -> Partita:
    v = {f.name: r[f.name] for f in fields(Partita)}
    v["cronologia"] = tuple(v["cronologia"] or ())
    return Partita(**v)


def _mistero(r) -> Mistero:
    return Mistero(**{f.name: r[f.name] for f in fields(Mistero)})


def _nodo(r) -> Nodo:
    scelte = r["scelte"]
    scelte = json.loads(scelte) if isinstance(scelte, str) else scelte
    return Nodo(r["nodo"], r["testo"], r["finale"], r["esito"], tuple(Scelta(**s) for s in scelte))


def _scelte_json(n: Nodo) -> str:
    return json.dumps([s.__dict__ for s in n.scelte])


class AiGiocoRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ============================================================ World Boss: scelte del server
    async def boss_config(self, guild_id: int) -> BossConfig:
        r = await self._pool.fetchrow("SELECT * FROM ai_boss_config WHERE guild_id = $1", guild_id)
        if r is None:
            return BossConfig(guild_id=guild_id)
        v = {f.name: r[f.name] for f in fields(BossConfig)}
        v["giorni"] = tuple(v["giorni"] or ())
        return BossConfig(**v)

    async def boss_imposta(self, guild_id: int, **campi) -> BossConfig:
        """Il solo punto che cambia le scelte del World Boss (comandi e pannello, D16)."""
        sconosciuti = set(campi) - _CAMPI_BOSS
        if sconosciuti or not campi:
            raise ValueError(f"Campi del boss non validi: {sorted(sconosciuti)}")
        nomi = list(campi)
        valori = [list(v) if k == "giorni" else v for k, v in campi.items()]
        colonne = ", ".join(nomi)
        segnaposto = ", ".join(f"${i + 2}" for i in range(len(nomi)))
        aggiorna = ", ".join(f"{n} = EXCLUDED.{n}" for n in nomi)
        await self._pool.execute(
            f"INSERT INTO ai_boss_config (guild_id, {colonne}) VALUES ($1, {segnaposto}) "
            f"ON CONFLICT (guild_id) DO UPDATE SET {aggiorna}",
            guild_id, *valori,
        )
        return await self.boss_config(guild_id)

    async def boss_programmati(self) -> list[BossConfig]:
        righe = await self._pool.fetch("SELECT guild_id FROM ai_boss_config WHERE attivo AND canale_id IS NOT NULL AND cardinality(giorni) > 0")
        return [await self.boss_config(r["guild_id"]) for r in righe]

    async def boss_segna_comparso(self, guild_id: int, giorno: date) -> None:
        await self._pool.execute("UPDATE ai_boss_config SET ultimo_giorno = $2 WHERE guild_id = $1", guild_id, giorno)

    # ============================================================ World Boss: eventi
    async def boss_crea(
        self, guild_id: int, channel_id: int, mostro: Mostro, vita_max: int, scade_il: datetime, rete_id: int | None = None
    ) -> int | None:
        """Crea l'evento; None se nel canale ce n'è già uno attivo (uno per canale)."""
        try:
            return await self._pool.fetchval(
                "INSERT INTO ai_boss_eventi (guild_id, channel_id, nome, aspetto, frasi, vita_max, vita, scade_il, rete_id) "
                "VALUES ($1, $2, $3, $4, $5, $6, $6, $7, $8) RETURNING id",
                guild_id, channel_id, mostro.nome, mostro.aspetto, list(mostro.frasi), vita_max, scade_il, rete_id,
            )
        except asyncpg.UniqueViolationError:
            return None

    async def boss_imposta_messaggio(self, evento_id: int, message_id: int) -> None:
        await self._pool.execute("UPDATE ai_boss_eventi SET message_id = $2 WHERE id = $1", evento_id, message_id)

    async def boss_evento(self, evento_id: int) -> BossEvento | None:
        r = await self._pool.fetchrow("SELECT * FROM ai_boss_eventi WHERE id = $1", evento_id)
        return _evento(r) if r else None

    async def boss_per_messaggio(self, message_id: int) -> BossEvento | None:
        r = await self._pool.fetchrow("SELECT * FROM ai_boss_eventi WHERE message_id = $1", message_id)
        return _evento(r) if r else None

    async def boss_attivi(self, guild_id: int | None = None) -> list[BossEvento]:
        righe = await self._pool.fetch(
            "SELECT * FROM ai_boss_eventi WHERE stato = 'attivo' AND ($1::bigint IS NULL OR guild_id = $1) ORDER BY id LIMIT 500",
            guild_id,
        )
        return [_evento(r) for r in righe]

    async def boss_agisci(
        self, evento_id: int, user_id: int, azione: str, danno: int, attesa_secondi: int, adesso: datetime | None = None
    ) -> EsitoAzione:
        """
        Un'azione sul boss in una sola transazione (riga bloccata): attesa tra due azioni, ferita, danno,
        guardia, cura, contrattacco ogni 10 azioni, sconfitta (AI-R-054, AI-R-057).
        """
        adesso = adesso or datetime.now(timezone.utc)
        async with self._pool.acquire() as conn, conn.transaction():
            ev = await conn.fetchrow("SELECT vita, azioni, stato, scade_il FROM ai_boss_eventi WHERE id = $1 FOR UPDATE", evento_id)
            if ev is None or ev["stato"] != "attivo" or ev["scade_il"] <= adesso:
                return EsitoAzione("chiuso")
            colpo = await conn.fetchrow(
                "SELECT ultima_azione, ferito_fino FROM ai_boss_colpi WHERE evento_id = $1 AND user_id = $2 FOR UPDATE",
                evento_id, user_id,
            )
            if colpo and colpo["ultima_azione"] and (adesso - colpo["ultima_azione"]).total_seconds() < attesa_secondi:
                resto = attesa_secondi - (adesso - colpo["ultima_azione"]).total_seconds()
                return EsitoAzione("attesa", vita=ev["vita"], secondi=max(1, int(resto + 0.99)))
            ferito = bool(colpo and colpo["ferito_fino"] and colpo["ferito_fino"] > adesso)
            if ferito and azione != "cura":
                return EsitoAzione("ferito", vita=ev["vita"], secondi=int((colpo["ferito_fino"] - adesso).total_seconds()) + 1)
            infliggi = min(danno, ev["vita"]) if azione in ("attacco", "magia") else 0
            await conn.execute(
                "INSERT INTO ai_boss_colpi (evento_id, user_id, danno, azioni, guardia, ultima_azione) VALUES ($1, $2, $3, 1, $4, $5) "
                "ON CONFLICT (evento_id, user_id) DO UPDATE SET danno = ai_boss_colpi.danno + $3, azioni = ai_boss_colpi.azioni + 1, "
                "guardia = CASE WHEN $6 THEN TRUE ELSE ai_boss_colpi.guardia END, "
                "ferito_fino = CASE WHEN $7 THEN NULL ELSE ai_boss_colpi.ferito_fino END, ultima_azione = $5",
                evento_id, user_id, infliggi, azione == "difesa", adesso, azione == "difesa", azione == "cura",
            )
            vita = ev["vita"] - infliggi
            azioni = ev["azioni"] + 1
            sconfitto = vita <= 0
            await conn.execute(
                "UPDATE ai_boss_eventi SET vita = $2, azioni = $3, stato = CASE WHEN $4 THEN 'sconfitto' ELSE stato END, "
                "chiuso_il = CASE WHEN $4 THEN $5 ELSE chiuso_il END WHERE id = $1",
                evento_id, vita, azioni, sconfitto, adesso,
            )
            feriti = 0
            if not sconfitto and azioni % RITMO_CONTRATTACCO == 0:
                esito = await conn.execute(
                    "UPDATE ai_boss_colpi SET ferito_fino = $2, guardia = FALSE WHERE evento_id = $1 AND NOT guardia "
                    "AND ultima_azione > $3",
                    evento_id, adesso + timedelta(seconds=FERITA_SECONDI), adesso - timedelta(minutes=5),
                )
                feriti = int(esito.split()[-1])
                await conn.execute("UPDATE ai_boss_colpi SET guardia = FALSE WHERE evento_id = $1", evento_id)
        return EsitoAzione("ok", vita=max(0, vita), danno=infliggi, sconfitto=sconfitto, contrattacco=feriti)

    async def boss_chiudi(self, evento_id: int, stato: str) -> bool:
        """Chiude un evento ancora attivo (fuggito alla scadenza). False se era già chiuso."""
        esito = await self._pool.execute(
            "UPDATE ai_boss_eventi SET stato = $2, chiuso_il = now() WHERE id = $1 AND stato = 'attivo'", evento_id, stato
        )
        return esito.endswith(" 1")

    async def boss_scaduti(self, adesso: datetime | None = None) -> list[BossEvento]:
        righe = await self._pool.fetch(
            "SELECT * FROM ai_boss_eventi WHERE stato = 'attivo' AND scade_il <= $1", adesso or datetime.now(timezone.utc)
        )
        return [_evento(r) for r in righe]

    async def boss_partecipanti(self, evento_id: int, limite: int = 500) -> list[tuple[int, int]]:
        righe = await self._pool.fetch(
            "SELECT user_id, danno FROM ai_boss_colpi WHERE evento_id = $1 ORDER BY danno DESC, user_id LIMIT $2", evento_id, limite
        )
        return [(r["user_id"], r["danno"]) for r in righe]

    # ============================================================ boss di rete (solo totali)
    async def rete_crea(self, creato_da: int, mostro: Mostro, vita_extra: int) -> int:
        return await self._pool.fetchval(
            "INSERT INTO ai_boss_rete (nome, aspetto, frasi, vita_extra, creato_da) VALUES ($1, $2, $3, $4, $5) RETURNING id",
            mostro.nome, mostro.aspetto, list(mostro.frasi), vita_extra, creato_da,
        )

    async def rete_attiva(self) -> tuple[int, Mostro, int] | None:
        """Il boss di rete in corso: (id, mostro, vita extra), o None."""
        r = await self._pool.fetchrow("SELECT * FROM ai_boss_rete WHERE attivo ORDER BY id DESC LIMIT 1")
        return None if r is None else (r["id"], Mostro(r["nome"], r["aspetto"], tuple(r["frasi"] or ())), r["vita_extra"])

    async def rete_chiudi(self) -> int:
        esito = await self._pool.execute("UPDATE ai_boss_rete SET attivo = FALSE WHERE attivo")
        return int(esito.split()[-1])

    async def rete_aggiungi_totali(self, rete_id: int, guild_id: int, danno: int, partecipanti: int, sconfitto: bool) -> None:
        await self._pool.execute(
            "INSERT INTO ai_boss_rete_totali (rete_id, guild_id, danno_totale, partecipanti, sconfitto) VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (rete_id, guild_id) DO UPDATE SET danno_totale = EXCLUDED.danno_totale, "
            "partecipanti = EXCLUDED.partecipanti, sconfitto = EXCLUDED.sconfitto",
            rete_id, guild_id, danno, partecipanti, sconfitto,
        )

    async def rete_totali(self, rete_id: int) -> tuple[int, int, int, int]:
        """(danno totale, server che hanno combattuto, persone, server che l'hanno sconfitto)."""
        r = await self._pool.fetchrow(
            "SELECT COALESCE(SUM(danno_totale), 0) AS d, COUNT(*) AS s, COALESCE(SUM(partecipanti), 0) AS p, "
            "COUNT(*) FILTER (WHERE sconfitto) AS v FROM ai_boss_rete_totali WHERE rete_id = $1",
            rete_id,
        )
        return int(r["d"]), r["s"], int(r["p"]), r["v"]

    # ============================================================ libreria: mostri e storie (testi dell'AI)
    async def mostro_libreria(self, tema: str) -> Mostro | None:
        r = await self._pool.fetchrow("SELECT nome, aspetto, frasi FROM ai_mostri WHERE tema = $1 ORDER BY random() LIMIT 1", tema)
        return None if r is None else Mostro(r["nome"], r["aspetto"], tuple(r["frasi"] or ()))

    async def mostro_salva(self, tema: str, m: Mostro) -> None:
        await self._pool.execute(
            "INSERT INTO ai_mostri (tema, nome, aspetto, frasi) VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING",
            tema, m.nome, m.aspetto, list(m.frasi),
        )

    async def storia_trova(self, tema: str, escludi: tuple[int, ...] = ()) -> int | None:
        """Una storia del tema già pronta (libreria comune), a caso, non tra quelle escluse."""
        return await self._pool.fetchval(
            "SELECT id FROM ai_storie WHERE tema = $1 AND NOT (id = ANY($2::int[])) ORDER BY random() LIMIT 1", tema, list(escludi)
        )

    async def storia_salva(self, tema: str, s: Storia) -> int | None:
        async with self._pool.acquire() as conn, conn.transaction():
            storia_id = await conn.fetchval(
                "INSERT INTO ai_storie (tema, titolo, inizio) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING RETURNING id",
                tema, s.titolo, s.inizio,
            )
            if storia_id is None:
                return None
            for n in s.nodi:
                await conn.execute(
                    "INSERT INTO ai_storie_nodi (storia_id, nodo, testo, finale, esito, scelte) VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
                    storia_id, n.id, n.testo, n.finale, n.esito, _scelte_json(n),
                )
        return storia_id

    async def storia_carica(self, storia_id: int) -> Storia | None:
        s = await self._pool.fetchrow("SELECT titolo, inizio FROM ai_storie WHERE id = $1", storia_id)
        if s is None:
            return None
        righe = await self._pool.fetch("SELECT * FROM ai_storie_nodi WHERE storia_id = $1 ORDER BY nodo", storia_id)
        return Storia(s["titolo"], s["inizio"], tuple(_nodo(r) for r in righe))

    async def storia_nodo_salva(self, storia_id: int, n: Nodo) -> None:
        """Un ramo scritto dopo: resta nella libreria, la volta dopo c'è già."""
        await self._pool.execute(
            "INSERT INTO ai_storie_nodi (storia_id, nodo, testo, finale, esito, scelte) VALUES ($1, $2, $3, $4, $5, $6::jsonb) "
            "ON CONFLICT DO NOTHING",
            storia_id, n.id, n.testo, n.finale, n.esito, _scelte_json(n),
        )

    async def storie_conta(self, tema: str) -> int:
        return await self._pool.fetchval("SELECT COUNT(*) FROM ai_storie WHERE tema = $1", tema)

    # ============================================================ dungeon
    async def partita_crea(self, guild_id: int, channel_id: int, storia_id: int, nodo: str, scade_il: datetime) -> int | None:
        """None se nel canale c'è già una partita non finita (una per canale)."""
        try:
            return await self._pool.fetchval(
                "INSERT INTO ai_dungeon_partite (guild_id, channel_id, storia_id, nodo, scade_il) VALUES ($1, $2, $3, $4, $5) RETURNING id",
                guild_id, channel_id, storia_id, nodo, scade_il,
            )
        except asyncpg.UniqueViolationError:
            return None

    async def partita(self, partita_id: int) -> Partita | None:
        r = await self._pool.fetchrow("SELECT * FROM ai_dungeon_partite WHERE id = $1", partita_id)
        return _partita(r) if r else None

    async def partita_per_messaggio(self, message_id: int) -> Partita | None:
        r = await self._pool.fetchrow("SELECT * FROM ai_dungeon_partite WHERE message_id = $1", message_id)
        return _partita(r) if r else None

    async def partita_imposta_messaggio(self, partita_id: int, message_id: int) -> None:
        await self._pool.execute("UPDATE ai_dungeon_partite SET message_id = $2 WHERE id = $1", partita_id, message_id)

    async def partite_attive(self, guild_id: int | None = None) -> list[Partita]:
        righe = await self._pool.fetch(
            "SELECT * FROM ai_dungeon_partite WHERE stato <> 'finita' AND ($1::bigint IS NULL OR guild_id = $1) ORDER BY id LIMIT 500", guild_id
        )
        return [_partita(r) for r in righe]

    async def partite_scadute(self, adesso: datetime | None = None) -> list[Partita]:
        righe = await self._pool.fetch(
            "SELECT * FROM ai_dungeon_partite WHERE stato <> 'finita' AND scade_il <= $1 ORDER BY id LIMIT 100",
            adesso or datetime.now(timezone.utc),
        )
        return [_partita(r) for r in righe]

    async def partita_giocatore(self, partita_id: int, user_id: int, classe: str) -> None:
        await self._pool.execute(
            "INSERT INTO ai_dungeon_giocatori (partita_id, user_id, classe) VALUES ($1, $2, $3) "
            "ON CONFLICT (partita_id, user_id) DO UPDATE SET classe = EXCLUDED.classe",
            partita_id, user_id, classe,
        )

    async def partita_voto(self, partita_id: int, user_id: int, voto: int) -> bool:
        """Il voto di chi sta nella partita; False se non ha scelto la classe."""
        esito = await self._pool.execute(
            "UPDATE ai_dungeon_giocatori SET voto = $3 WHERE partita_id = $1 AND user_id = $2", partita_id, user_id, voto
        )
        return esito.endswith(" 1")

    async def partita_giocatori(self, partita_id: int) -> list[tuple[int, str, int | None]]:
        righe = await self._pool.fetch(
            "SELECT user_id, classe, voto FROM ai_dungeon_giocatori WHERE partita_id = $1 ORDER BY user_id LIMIT 500", partita_id
        )
        return [(r["user_id"], r["classe"], r["voto"]) for r in righe]

    async def partita_avanza(self, partita_id: int, nodo: str, scade_il: datetime, scelta: str | None) -> None:
        """Nuova stanza: il cammino si allunga, i voti si azzerano, la partita è in corso."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "UPDATE ai_dungeon_partite SET nodo = $2, scade_il = $3, stato = 'in_corso', "
                "cronologia = CASE WHEN $4::text IS NULL THEN cronologia ELSE array_append(cronologia, $4) END WHERE id = $1",
                partita_id, nodo, scade_il, scelta,
            )
            await conn.execute("UPDATE ai_dungeon_giocatori SET voto = NULL WHERE partita_id = $1", partita_id)

    async def partita_chiudi(self, partita_id: int, esito: str) -> bool:
        r = await self._pool.execute(
            "UPDATE ai_dungeon_partite SET stato = 'finita', esito = $2 WHERE id = $1 AND stato <> 'finita'", partita_id, esito
        )
        return r.endswith(" 1")

    async def storie_giocate(self, guild_id: int, ultime: int = 5) -> tuple[int, ...]:
        righe = await self._pool.fetch(
            "SELECT DISTINCT storia_id FROM (SELECT storia_id FROM ai_dungeon_partite WHERE guild_id = $1 ORDER BY id DESC LIMIT $2) t",
            guild_id, ultime,
        )
        return tuple(r["storia_id"] for r in righe)

    # ============================================================ misteri
    async def mistero_crea(
        self, guild_id: int, titolo: str, indizio: str, codice_hash: str, premio: str, premio_valore: int, durata_ore: int, creato_da: int
    ) -> int:
        return await self._pool.fetchval(
            "INSERT INTO ai_misteri (guild_id, titolo, indizio, codice_hash, premio, premio_valore, durata_ore, creato_da) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id",
            guild_id, titolo, indizio, codice_hash, premio, premio_valore, durata_ore, creato_da,
        )

    async def misteri(self, guild_id: int, *, solo_aperti: bool = False) -> list[Mistero]:
        righe = await self._pool.fetch(
            "SELECT * FROM ai_misteri WHERE guild_id = $1 AND (stato = 'aperto' OR NOT $2) ORDER BY id LIMIT 25", guild_id, solo_aperti
        )
        return [_mistero(r) for r in righe]

    async def mistero_togli(self, guild_id: int, mistero_id: int) -> bool:
        esito = await self._pool.execute("DELETE FROM ai_misteri WHERE guild_id = $1 AND id = $2", guild_id, mistero_id)
        return esito.endswith(" 1")

    async def mistero_risolvi(self, guild_id: int, codice_hash: str, user_id: int) -> Mistero | None:
        """Il mistero aperto con questo codice, chiuso a nome di chi l'ha risolto per primo (una volta sola)."""
        r = await self._pool.fetchrow(
            "UPDATE ai_misteri SET stato = 'risolto', risolto_da = $3, risolto_il = now() "
            "WHERE id = (SELECT id FROM ai_misteri WHERE guild_id = $1 AND codice_hash = $2 AND stato = 'aperto' ORDER BY id LIMIT 1 FOR UPDATE) "
            "AND stato = 'aperto' RETURNING *",
            guild_id, codice_hash, user_id,
        )
        return _mistero(r) if r else None

    # ============================================================ spiriti e frammenti
    async def spirito_scelto(self, guild_id: int, user_id: int) -> str | None:
        return await self._pool.fetchval("SELECT scelto FROM ai_spiriti WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)

    async def spirito_imposta(self, guild_id: int, user_id: int, scelto: str | None) -> None:
        await self._pool.execute(
            "INSERT INTO ai_spiriti (guild_id, user_id, scelto) VALUES ($1, $2, $3) "
            "ON CONFLICT (guild_id, user_id) DO UPDATE SET scelto = EXCLUDED.scelto",
            guild_id, user_id, scelto,
        )

    async def frammenti(self, guild_id: int, user_id: int) -> list[str]:
        righe = await self._pool.fetch(
            "SELECT codice FROM ai_frammenti WHERE guild_id = $1 AND user_id = $2 ORDER BY sbloccato_il", guild_id, user_id
        )
        return [r["codice"] for r in righe]

    async def frammento_sblocca(self, guild_id: int, user_id: int, codice: str) -> bool:
        esito = await self._pool.execute(
            "INSERT INTO ai_frammenti (guild_id, user_id, codice) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING", guild_id, user_id, codice
        )
        return esito.endswith(" 1")

    # ============================================================ per «cosa posso fare qui?»
    async def eventi_in_corso(self, guild_id: int) -> list[str]:
        righe: list[str] = []
        for e in await self.boss_attivi(guild_id):
            righe.append(f"World Boss «{e.nome}» in <#{e.channel_id}>: {e.vita}/{e.vita_max} di vita")
        for p in await self.partite_attive(guild_id):
            righe.append(f"Dungeon di gruppo in <#{p.channel_id}>")
        aperti = await self.misteri(guild_id, solo_aperti=True)
        if aperti:
            righe.append(f"{len(aperti)} misteri aperti: cerca gli indizi e rispondi con il comando dei misteri")
        return righe


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


ai_gioco_repo = AiGiocoRepository(pool_provider=_get_pool)

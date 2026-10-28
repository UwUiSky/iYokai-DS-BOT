"""
core/repositories/ai_repo.py
============================
Tabelle del motore AI (migrazione 0140): scelte del server (`ai_config`,
un solo punto per comandi e pannello), conti dell'uso (`ai_uso`, solo
numeri), cache e libreria comune (`ai_cache`), base di conoscenza,
personaggi, canali tradotti, immagini comprate.
Funzioni coperte: SPEC §25 (NF-24)
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime

import asyncpg

from core.ai_cost_logic import Quote, Uso, quota_superata, tetto_raggiunto, usa_credito_immagine


@dataclass(frozen=True)
class ConfigAI:
    guild_id: int
    attivo: bool = False
    consenso_da: int | None = None
    canali_spenti: tuple[int, ...] = ()
    tetto_mensile_cent: int = 0
    quota_utente_giorno: int = 20
    quota_utente_30g: int = 300
    quota_funzione_giorno: int = 500
    quota_immagini_settimana: int = 5
    prezzo_pacchetto_immagini: int = 0
    privacy: str = "completa"
    lunghezza: str = "media"
    conservazione_minuti: int = 30
    lore_tema: str | None = None
    lore_testo: str | None = None
    nome_punti: str | None = None
    prefisso_titolo: str | None = None
    parole_vietate: tuple[str, ...] = ()
    menzione: bool = False
    bandiere: bool = False
    moderazione_canali: tuple[int, ...] = ()
    prova_inizio: datetime | None = None

    def quote(self) -> Quote:
        return Quote(
            tetto_mensile_cent=self.tetto_mensile_cent, utente_giorno=self.quota_utente_giorno,
            utente_30_giorni=self.quota_utente_30g, funzione_giorno=self.quota_funzione_giorno,
            immagini_settimana=self.quota_immagini_settimana,
        )


_CAMPI = {f.name for f in fields(ConfigAI)} - {"guild_id", "consenso_da"}
_TUPLE = {"canali_spenti", "parole_vietate", "moderazione_canali"}


@dataclass(frozen=True)
class Prenotazione:
    """Un posto nei conti preso prima della chiamata (`motivo`: perché non si può partire)."""

    id: int
    guild_id: int
    user_id: int
    solo_gratuiti: bool = True
    credito: bool = False
    motivo: str | None = None


@dataclass(frozen=True)
class Personaggio:
    id: int
    guild_id: int
    autore_id: int
    nome: str
    biografia: str
    tratti: str
    gusti: str
    fatti: str
    installato: bool


def _config(r) -> ConfigAI:
    valori = {k: (tuple(r[k]) if k in _TUPLE else r[k]) for k in _CAMPI}
    return ConfigAI(guild_id=r["guild_id"], consenso_da=r["consenso_da"], **valori)


def _personaggio(r) -> Personaggio:
    return Personaggio(**{f.name: r[f.name] for f in fields(Personaggio)})


class AiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ------------------------------------------------------------ scelte del server
    async def get_config(self, guild_id: int) -> ConfigAI:
        r = await self._pool.fetchrow("SELECT * FROM ai_config WHERE guild_id = $1", guild_id)
        return ConfigAI(guild_id=guild_id) if r is None else _config(r)

    async def imposta(self, guild_id: int, **campi) -> ConfigAI:
        """Il solo punto che cambia le scelte AI di un server (comandi e pannello web, D16)."""
        sconosciuti = set(campi) - _CAMPI
        if sconosciuti or not campi:
            raise ValueError(f"Campi AI non validi: {sorted(sconosciuti)}")
        nomi = list(campi)
        valori = [list(v) if k in _TUPLE else v for k, v in campi.items()]
        colonne = ", ".join(nomi)
        segnaposto = ", ".join(f"${i + 2}" for i in range(len(nomi)))
        aggiorna = ", ".join(f"{n} = EXCLUDED.{n}" for n in nomi)
        r = await self._pool.fetchrow(
            f"INSERT INTO ai_config (guild_id, {colonne}) VALUES ($1, {segnaposto}) "
            f"ON CONFLICT (guild_id) DO UPDATE SET {aggiorna}, aggiornato_il = now() RETURNING *",
            guild_id, *valori,
        )
        return _config(r)

    async def avvia_prova(self, guild_id: int) -> ConfigAI:
        """
        Fa partire il periodo di prova dell'AI, una volta sola per server (AI-R-023). L'inizio
        resta in `ai_prove` anche dopo la cancellazione dei dati del server: vale il più vecchio.
        """
        r = await self._pool.fetchrow(
            "WITH p AS (INSERT INTO ai_prove (guild_id) VALUES ($1) "
            "ON CONFLICT (guild_id) DO UPDATE SET guild_id = EXCLUDED.guild_id RETURNING inizio) "
            "INSERT INTO ai_config (guild_id, prova_inizio) SELECT $1, inizio FROM p "
            "ON CONFLICT (guild_id) DO UPDATE SET prova_inizio = "
            "LEAST(COALESCE(ai_config.prova_inizio, EXCLUDED.prova_inizio), EXCLUDED.prova_inizio) RETURNING *",
            guild_id,
        )
        return _config(r)

    # ------------------------------------------------------------ interruttori dell'owner
    async def manutenzione(self) -> str | None:
        """Il messaggio di manutenzione globale, o None se l'AI è in servizio (AI-R-020)."""
        return await self._pool.fetchval("SELECT valore FROM ai_globale WHERE chiave = 'manutenzione'")

    async def imposta_manutenzione(self, acceso: bool, messaggio: str, user_id: int | None) -> None:
        if not acceso:
            await self._pool.execute("DELETE FROM ai_globale WHERE chiave = 'manutenzione'")
            return
        await self._pool.execute(
            "INSERT INTO ai_globale (chiave, valore, aggiornato_da) VALUES ('manutenzione', $1, $2) "
            "ON CONFLICT (chiave) DO UPDATE SET valore = $1, aggiornato_da = $2, aggiornato_il = now()",
            messaggio, user_id,
        )

    async def registra_consenso(self, guild_id: int, user_id: int, attivo: bool) -> ConfigAI:
        """Accende o spegne l'AI; all'accensione ricorda chi ha dato il consenso e quando."""
        r = await self._pool.fetchrow(
            "INSERT INTO ai_config (guild_id, attivo, consenso_da, consenso_il) "
            "VALUES ($1, $2, CASE WHEN $2 THEN $3::bigint END, CASE WHEN $2 THEN now() END) "
            "ON CONFLICT (guild_id) DO UPDATE SET attivo = $2, "
            "consenso_da = CASE WHEN $2 THEN $3::bigint ELSE ai_config.consenso_da END, "
            "consenso_il = CASE WHEN $2 THEN now() ELSE ai_config.consenso_il END, aggiornato_il = now() "
            "RETURNING *",
            guild_id, attivo, user_id,
        )
        return _config(r)

    # ------------------------------------------------------------ uso (solo numeri)
    async def _uso(self, conn, guild_id: int, user_id: int, funzione: str) -> Uso:
        r = await conn.fetchrow(
            """
            SELECT
              COALESCE(SUM(costo_millesimi) FILTER (WHERE creato_il >= date_trunc('month', now())), 0) AS spesa,
              COUNT(*) FILTER (WHERE user_id = $2 AND creato_il >= date_trunc('day', now())) AS utente_oggi,
              COUNT(*) FILTER (WHERE user_id = $2 AND creato_il >= now() - interval '30 days') AS utente_30,
              COUNT(*) FILTER (WHERE funzione = $3 AND creato_il >= date_trunc('day', now())) AS funzione_oggi,
              COUNT(*) FILTER (WHERE user_id = $2 AND immagine AND creato_il >= now() - interval '7 days') AS immagini
            FROM ai_uso WHERE guild_id = $1 AND creato_il >= LEAST(date_trunc('month', now()), now() - interval '30 days')
            """,
            guild_id, user_id, funzione,
        )
        extra = await conn.fetchval(
            "SELECT immagini_extra FROM ai_crediti WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )
        return Uso(
            spesa_mese_millesimi=int(r["spesa"]), utente_oggi=r["utente_oggi"], utente_30_giorni=r["utente_30"],
            funzione_oggi=r["funzione_oggi"], immagini_settimana=r["immagini"], immagini_extra=extra or 0,
        )

    async def uso(self, guild_id: int, user_id: int, funzione: str) -> Uso:
        async with self._pool.acquire() as conn:
            return await self._uso(conn, guild_id, user_id, funzione)

    async def prenota(
        self, guild_id: int, user_id: int, funzione: str, *, quote: Quote | None, immagine: bool, costo_stimato: int,
    ) -> Prenotazione:
        """
        Controllo delle quote e posto nei conti in un colpo solo, sotto un blocco del server
        nel database: due richieste insieme (anche di persone o processi diversi) non passano
        entrambe l'ultimo posto, il credito si consuma qui, e la spesa prevista conta subito
        sul tetto. `quote` None: nessun controllo (messaggi privati), solo fornitori gratuiti.
        """
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('ai_uso:' || $1::bigint::text, 0))", guild_id)
            solo_gratuiti, credito = True, False
            if quote is not None:
                uso = await self._uso(conn, guild_id, user_id, funzione)
                motivo = quota_superata(quote, uso, immagine=immagine)
                if motivo:
                    return Prenotazione(0, guild_id, user_id, motivo=motivo)
                solo_gratuiti = tetto_raggiunto(quote, uso)
                credito = immagine and usa_credito_immagine(quote, uso)
            if credito:
                await conn.execute(
                    "UPDATE ai_crediti SET immagini_extra = immagini_extra - 1 "
                    "WHERE guild_id = $1 AND user_id = $2 AND immagini_extra > 0",
                    guild_id, user_id,
                )
            id_riga = await conn.fetchval(
                "INSERT INTO ai_uso (guild_id, user_id, funzione, fornitore, immagine, costo_millesimi) "
                "VALUES ($1, $2, $3, '', $4, $5) RETURNING id",
                guild_id, user_id, funzione, immagine, 0 if solo_gratuiti else max(0, costo_stimato),
            )
        return Prenotazione(id_riga, guild_id, user_id, solo_gratuiti=solo_gratuiti, credito=credito)

    async def conferma(
        self, p: Prenotazione, fornitore: str, *, token_in: int, token_out: int, costo_millesimi: int,
    ) -> None:
        """La chiamata è andata: i conti prendono fornitore, token e costo veri."""
        await self._pool.execute(
            "UPDATE ai_uso SET fornitore = $3, token_in = $4, token_out = $5, costo_millesimi = $6 "
            "WHERE id = $1 AND guild_id = $2",
            p.id, p.guild_id, fornitore[:40] or "?", token_in, token_out, costo_millesimi,
        )

    async def annulla(self, p: Prenotazione) -> None:
        """La chiamata non è andata: il posto si libera e il credito torna."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("DELETE FROM ai_uso WHERE id = $1 AND guild_id = $2", p.id, p.guild_id)
            if p.credito:
                await conn.execute(
                    "UPDATE ai_crediti SET immagini_extra = immagini_extra + 1 WHERE guild_id = $1 AND user_id = $2",
                    p.guild_id, p.user_id,
                )

    async def riepilogo_mese(self, guild_id: int | None = None) -> list[asyncpg.Record]:
        """Richieste, token e spesa del mese per fornitore: di un server, o di tutti (owner)."""
        return await self._pool.fetch(
            "SELECT fornitore, COUNT(*) AS richieste, SUM(token_in + token_out) AS token, "
            "SUM(costo_millesimi) AS spesa FROM ai_uso "
            "WHERE creato_il >= date_trunc('month', now()) AND fornitore <> '' AND ($1::bigint IS NULL OR guild_id = $1) "
            "GROUP BY fornitore ORDER BY richieste DESC LIMIT 25",
            guild_id,
        )

    # ------------------------------------------------------------ cache e libreria comune
    async def cache_trova(self, guild_id: int, chiave: str) -> str | None:
        return await self._pool.fetchval(
            "UPDATE ai_cache SET usi = usi + 1 WHERE guild_id = $1 AND chiave = $2 RETURNING risposta", guild_id, chiave
        )

    async def cache_metti(self, guild_id: int, chiave: str, tipo: str, risposta: str) -> None:
        await self._pool.execute(
            "INSERT INTO ai_cache (guild_id, chiave, tipo, risposta) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (guild_id, chiave) DO UPDATE SET risposta = EXCLUDED.risposta",
            guild_id, chiave, tipo, risposta,
        )

    # ------------------------------------------------------------ base di conoscenza
    async def conoscenza_aggiungi(self, guild_id: int, titolo: str, testo: str, autore_id: int) -> int:
        return await self._pool.fetchval(
            "INSERT INTO ai_conoscenza (guild_id, titolo, testo, creato_da) VALUES ($1, $2, $3, $4) RETURNING id",
            guild_id, titolo, testo, autore_id,
        )

    async def conoscenza_elenco(self, guild_id: int) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT id, titolo, testo FROM ai_conoscenza WHERE guild_id = $1 ORDER BY id LIMIT 50", guild_id
        )

    async def conoscenza_togli(self, guild_id: int, voce_id: int) -> bool:
        esito = await self._pool.execute("DELETE FROM ai_conoscenza WHERE guild_id = $1 AND id = $2", guild_id, voce_id)
        return esito.endswith(" 1")

    async def conoscenza_conta(self, guild_id: int) -> int:
        return await self._pool.fetchval("SELECT COUNT(*) FROM ai_conoscenza WHERE guild_id = $1", guild_id)

    # ------------------------------------------------------------ personaggi
    async def personaggio_crea(self, guild_id: int, autore_id: int, nome: str, **testi: str) -> Personaggio | None:
        r = await self._pool.fetchrow(
            "INSERT INTO ai_personaggi (guild_id, autore_id, nome, biografia, tratti, gusti, fatti) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT (guild_id, nome) DO NOTHING RETURNING *",
            guild_id, autore_id, nome, testi.get("biografia", ""), testi.get("tratti", ""),
            testi.get("gusti", ""), testi.get("fatti", ""),
        )
        return _personaggio(r) if r else None

    async def personaggi(self, guild_id: int, *, solo_installati: bool = False) -> list[Personaggio]:
        righe = await self._pool.fetch(
            "SELECT * FROM ai_personaggi WHERE guild_id = $1 AND (installato OR NOT $2) ORDER BY nome LIMIT 25",
            guild_id, solo_installati,
        )
        return [_personaggio(r) for r in righe]

    async def personaggio(self, guild_id: int, nome: str) -> Personaggio | None:
        r = await self._pool.fetchrow(
            "SELECT * FROM ai_personaggi WHERE guild_id = $1 AND lower(nome) = lower($2)", guild_id, nome
        )
        return _personaggio(r) if r else None

    async def personaggio_installa(self, guild_id: int, nome: str, installato: bool) -> bool:
        esito = await self._pool.execute(
            "UPDATE ai_personaggi SET installato = $3 WHERE guild_id = $1 AND lower(nome) = lower($2)",
            guild_id, nome, installato,
        )
        return esito.endswith(" 1")

    async def personaggio_togli(self, guild_id: int, nome: str, autore_id: int | None = None) -> bool:
        """Cancella il personaggio; con `autore_id` solo se l'ha creato quella persona."""
        esito = await self._pool.execute(
            "DELETE FROM ai_personaggi WHERE guild_id = $1 AND lower(nome) = lower($2) "
            "AND ($3::bigint IS NULL OR autore_id = $3)",
            guild_id, nome, autore_id,
        )
        return esito.endswith(" 1")

    # ------------------------------------------------------------ canali tradotti
    async def traduzione_imposta(self, guild_id: int, channel_id: int, lingua: str | None) -> None:
        if lingua is None:
            await self._pool.execute("DELETE FROM ai_traduzione_canali WHERE channel_id = $1", channel_id)
            return
        await self._pool.execute(
            "INSERT INTO ai_traduzione_canali (channel_id, guild_id, lingua) VALUES ($1, $2, $3) "
            "ON CONFLICT (channel_id) DO UPDATE SET lingua = EXCLUDED.lingua",
            channel_id, guild_id, lingua,
        )

    async def traduzione_canali(self) -> dict[int, str]:
        """Tutti i canali con traduzione automatica (letti all'avvio, poi tenuti in memoria)."""
        righe = await self._pool.fetch("SELECT channel_id, lingua FROM ai_traduzione_canali")
        return {r["channel_id"]: r["lingua"] for r in righe}

    # ------------------------------------------------------------ preferenza personale e traguardi
    async def assistente_acceso(self, user_id: int) -> bool:
        """La persona vuole le risposte dell'AI? Senza riga: sì (AI-R-094)."""
        valore = await self._pool.fetchval("SELECT assistente FROM ai_utenti WHERE user_id = $1", user_id)
        return True if valore is None else bool(valore)

    async def imposta_assistente(self, user_id: int, acceso: bool) -> None:
        await self._pool.execute(
            "INSERT INTO ai_utenti (user_id, assistente) VALUES ($1, $2) "
            "ON CONFLICT (user_id) DO UPDATE SET assistente = $2, aggiornato_il = now()",
            user_id, acceso,
        )

    async def traguardo_assegna(self, user_id: int, codice: str) -> bool:
        """True se il traguardo è nuovo per la persona (AI-R-080)."""
        esito = await self._pool.execute(
            "INSERT INTO ai_traguardi (user_id, codice) VALUES ($1, $2) ON CONFLICT DO NOTHING", user_id, codice
        )
        return esito.endswith(" 1")

    async def traguardi(self, user_id: int) -> list[str]:
        righe = await self._pool.fetch(
            "SELECT codice FROM ai_traguardi WHERE user_id = $1 ORDER BY ottenuto_il LIMIT 25", user_id
        )
        return [r["codice"] for r in righe]

    # ------------------------------------------------------------ immagini comprate
    async def crediti_aggiungi(self, guild_id: int, user_id: int, quante: int) -> int:
        return await self._pool.fetchval(
            "INSERT INTO ai_crediti (guild_id, user_id, immagini_extra) VALUES ($1, $2, $3) "
            "ON CONFLICT (guild_id, user_id) DO UPDATE SET immagini_extra = ai_crediti.immagini_extra + $3 "
            "RETURNING immagini_extra",
            guild_id, user_id, quante,
        )


def _get_pool() -> asyncpg.Pool:
    from core.database import db
    return db.pool


ai_repo = AiRepository(pool_provider=_get_pool)

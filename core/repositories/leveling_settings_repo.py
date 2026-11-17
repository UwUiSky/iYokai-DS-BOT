"""
core/repositories/leveling_settings_repo.py
===========================================
Impostazioni dei livelli per server: numeri di XP e monete, dove
annunciare il level-up, modalità dei ruoli premio, canali e ruoli
esclusi, moltiplicatori. Le impostazioni passano da qui sia per i comandi
sia per il futuro pannello web (D16).
Funzioni coperte: SPEC §22.14 (NF-15)
"""

from __future__ import annotations

import time
from dataclasses import fields

import asyncpg

from core.bounded_cache import BoundedCache
from core.leveling_logic import (
    FATTORE_MASSIMO,
    FATTORE_MINIMO,
    LIMITI_IMPOSTAZIONI,
    MAX_REGOLE_PER_TIPO,
    MAX_TESTO_ANNUNCIO,
    FORMULE,
    MAX_PREFISSI,
    MODI_ANNUNCIO,
    MODI_CANALI,
    MODI_XP_MESSAGGIO,
    level_for_xp,
    prefisso_valido,
    MODI_AZZERA_SU,
    MODI_MOLTIPLICATORI,
    MODI_PREMI,
    TIPI_REGOLA,
    TIPI_REGOLA_CON_FATTORE,
    ConfigLivelli,
    LevelingSettings,
    nome_moneta_valido,
)

# Quanto resta in memoria una configurazione letta: il listener dei
# messaggi la chiede a ogni messaggio.
SECONDI_DI_CACHE = 60

_CAMPI_NOTI = {f.name for f in fields(LevelingSettings)}
_MODI = {
    "levelup_mode": MODI_ANNUNCIO,
    "reward_mode": MODI_PREMI,
    "azzera_su": MODI_AZZERA_SU,
    "multiplier_mode": MODI_MOLTIPLICATORI,
    "formula": FORMULE,
    "xp_modo": MODI_XP_MESSAGGIO,
    "canali_modo": MODI_CANALI,
}


def _campi_da_riga(riga) -> dict:
    campi = {k: riga[k] for k in _CAMPI_NOTI}
    campi["prefissi_ignorati"] = tuple(campi["prefissi_ignorati"] or ())
    return campi


class RegolaPiena(Exception):
    """Il server ha già 25 regole di questo tipo."""


class LevelingSettingsRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider
        self._cache: BoundedCache[int, tuple[float, ConfigLivelli]] = BoundedCache(max_size=5_000)
        # Sale a ogni modifica: una lettura partita prima di un salvataggio
        # non rimette in cache il valore vecchio.
        self._versione: dict[int, int] = {}

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get_config(self, guild_id: int, fresco: bool = False) -> ConfigLivelli:
        """`fresco`: salta la cache (per i controlli che non devono vedere un valore vecchio)."""
        voce = None if fresco else self._cache.get(guild_id)
        if voce is not None and time.monotonic() - voce[0] < SECONDI_DI_CACHE:
            return voce[1]

        versione = self._versione.get(guild_id, 0)
        riga = await self._pool.fetchrow(
            "SELECT * FROM leveling_settings WHERE guild_id = $1", guild_id
        )
        regole = await self._pool.fetch(
            "SELECT kind, target_id, factor FROM leveling_xp_rules WHERE guild_id = $1", guild_id
        )
        impostazioni = LevelingSettings(**_campi_da_riga(riga)) if riga else LevelingSettings()
        config = ConfigLivelli(
            impostazioni=impostazioni,
            canali_esclusi=frozenset(r["target_id"] for r in regole if r["kind"] == "canale_escluso"),
            ruoli_esclusi=frozenset(r["target_id"] for r in regole if r["kind"] == "ruolo_escluso"),
            mult_canali={r["target_id"]: float(r["factor"]) for r in regole if r["kind"] == "mult_canale"},
            mult_ruoli={r["target_id"]: float(r["factor"]) for r in regole if r["kind"] == "mult_ruolo"},
        )
        if self._versione.get(guild_id, 0) == versione:
            self._cache.set(guild_id, (time.monotonic(), config))
        return config

    def _invalida(self, guild_id: int) -> None:
        self._versione[guild_id] = self._versione.get(guild_id, 0) + 1
        self._cache.delete(guild_id)

    async def get_immagine_moneta(self, guild_id: int) -> bytes | None:
        """D38: l'immagine della moneta del server (PNG pronto), o None = moneta di iYokai."""
        return await self._pool.fetchval(
            "SELECT immagine FROM guild_coin_images WHERE guild_id = $1", guild_id
        )

    async def set_immagine_moneta(self, guild_id: int, immagine: bytes | None) -> None:
        """Salva l'immagine preparata da core.moneta_server.prepara_moneta; None la toglie."""
        if immagine is None:
            await self._pool.execute("DELETE FROM guild_coin_images WHERE guild_id = $1", guild_id)
            return
        await self._pool.execute(
            """
            INSERT INTO guild_coin_images (guild_id, immagine) VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET immagine = $2, aggiornato_at = now()
            """,
            guild_id,
            immagine,
        )

    async def set_options(self, guild_id: int, **campi) -> LevelingSettings:
        """
        Cambia solo i campi dati; gli altri restano come sono. Valori
        fuori dai limiti o modi sconosciuti sollevano ValueError.
        """
        for nome, valore in campi.items():
            if nome not in _CAMPI_NOTI:
                raise ValueError(f"Impostazione sconosciuta: {nome}")
            if nome in LIMITI_IMPOSTAZIONI:
                minimo, massimo = LIMITI_IMPOSTAZIONI[nome]
                if not minimo <= valore <= massimo:
                    raise ValueError(f"{nome} deve stare tra {minimo} e {massimo}.")
            if nome in _MODI and valore not in _MODI[nome]:
                raise ValueError(f"Valore non valido per {nome}: {valore}")
            if nome == "levelup_testo" and (not isinstance(valore, str) or len(valore) > MAX_TESTO_ANNUNCIO):
                raise ValueError(f"Il testo dell'annuncio può avere al massimo {MAX_TESTO_ANNUNCIO} caratteri.")
            if nome == "prefissi_ignorati":
                raise ValueError("I prefissi si cambiano con aggiungi_prefisso e togli_prefisso.")
            if nome == "currency_name":
                campi[nome] = nome_moneta_valido(valore)

        if "work_min" in campi or "work_max" in campi:
            attuale = (await self.get_config(guild_id)).impostazioni
            minimo = campi.get("work_min", attuale.work_min)
            massimo = campi.get("work_max", attuale.work_max)
            if minimo > massimo:
                raise ValueError("Il minimo del lavoro non può superare il massimo.")

        if "pay_min" in campi or "pay_max" in campi:
            attuale = (await self.get_config(guild_id)).impostazioni
            minimo = campi.get("pay_min", attuale.pay_min)
            massimo = campi.get("pay_max", attuale.pay_max)
            if minimo and massimo and minimo > massimo:
                raise ValueError("Il minimo di /monete pay non può superare il massimo.")

        if campi.get("levelup_mode") == "canale_scelto" and not campi.get("levelup_channel_id"):
            attuale = (await self.get_config(guild_id)).impostazioni.levelup_channel_id
            if attuale is None:
                raise ValueError("Per annunciare in un canale scelto serve il canale.")
            campi["levelup_channel_id"] = attuale

        if campi:
            nomi = list(campi)
            segnaposto = ", ".join(f"${i + 2}" for i in range(len(nomi)))
            aggiornamenti = ", ".join(f"{n} = EXCLUDED.{n}" for n in nomi)
            try:
                await self._pool.execute(
                    f"INSERT INTO leveling_settings (guild_id, {', '.join(nomi)}) "
                    f"VALUES ($1, {segnaposto}) "
                    f"ON CONFLICT (guild_id) DO UPDATE SET {aggiornamenti}",
                    guild_id,
                    *campi.values(),
                )
            except asyncpg.CheckViolationError as errore:
                # Ultima parola al database: due modifiche insieme non rompono min <= max.
                if "work_ordine" in str(errore):
                    raise ValueError("Il minimo del lavoro non può superare il massimo.") from errore
                raise
            self._invalida(guild_id)
        return (await self.get_config(guild_id)).impostazioni

    async def aggiungi_prefisso(self, guild_id: int, prefisso: str) -> str:
        """
        LIV-018: aggiunge un prefisso in una sola scrittura (al massimo 10).
        Restituisce "aggiunto", "presente", "pieno" o "non_valido".
        """
        pulito = prefisso_valido(prefisso)
        if pulito is None:
            return "non_valido"
        riga = await self._pool.fetchrow(
            """
            INSERT INTO leveling_settings (guild_id, prefissi_ignorati) VALUES ($1, ARRAY[$2]::text[])
            ON CONFLICT (guild_id) DO UPDATE
                SET prefissi_ignorati = array_append(leveling_settings.prefissi_ignorati, $2)
                WHERE NOT ($2 = ANY(leveling_settings.prefissi_ignorati))
                  AND cardinality(leveling_settings.prefissi_ignorati) < $3
            RETURNING 1
            """,
            guild_id, pulito, MAX_PREFISSI,
        )
        self._invalida(guild_id)
        if riga is not None:
            return "aggiunto"
        presenti = await self._pool.fetchval(
            "SELECT prefissi_ignorati FROM leveling_settings WHERE guild_id = $1", guild_id
        )
        return "presente" if pulito in (presenti or []) else "pieno"

    async def togli_prefisso(self, guild_id: int, prefisso: str | None) -> int:
        """LIV-018: toglie un prefisso (o tutti, con None). Restituisce quanti ne restano."""
        if prefisso is None:
            nuovi = await self._pool.fetchval(
                "UPDATE leveling_settings SET prefissi_ignorati = '{}' WHERE guild_id = $1 "
                "RETURNING cardinality(prefissi_ignorati)", guild_id,
            )
        else:
            nuovi = await self._pool.fetchval(
                "UPDATE leveling_settings SET prefissi_ignorati = array_remove(prefissi_ignorati, $2) "
                "WHERE guild_id = $1 RETURNING cardinality(prefissi_ignorati)", guild_id, prefisso.strip(),
            )
        self._invalida(guild_id)
        return nuovi or 0

    async def cambia_formula(self, guild_id: int, formula: str) -> int:
        """
        LIV-004: cambia la formula e ricalcola il livello di tutti dall'XP totale, in una
        transazione (due cambi insieme si mettono in fila). Restituisce quante righe sono cambiate.
        """
        if formula not in FORMULE:
            raise ValueError(f"Formula sconosciuta: {formula}")
        cambiate = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1, hashtext('formula'))", guild_id % 2**31)
                await conn.execute(
                    "INSERT INTO leveling_settings (guild_id, formula) VALUES ($1, $2) "
                    "ON CONFLICT (guild_id) DO UPDATE SET formula = EXCLUDED.formula",
                    guild_id, formula,
                )
                tetto = await conn.fetchval("SELECT max_level FROM leveling_settings WHERE guild_id = $1", guild_id)
                ultimo = 0
                while True:
                    righe = await conn.fetch(
                        "SELECT user_id, xp_total, level FROM leveling_totals "
                        "WHERE guild_id = $1 AND user_id > $2 ORDER BY user_id LIMIT 2000 FOR UPDATE",
                        guild_id, ultimo,
                    )
                    if not righe:
                        break
                    nuovi = [
                        (r["user_id"], level_for_xp(r["xp_total"], tetto or 0, formula))
                        for r in righe
                    ]
                    da_scrivere = [
                        (u, lv) for (u, lv), r in zip(nuovi, righe) if lv != r["level"]
                    ]
                    if da_scrivere:
                        await conn.executemany(
                            "UPDATE leveling_totals SET level = $2 WHERE user_id = $1 AND guild_id = $3",
                            [(u, lv, guild_id) for u, lv in da_scrivere],
                        )
                        cambiate += len(da_scrivere)
                    ultimo = righe[-1]["user_id"]
        self._invalida(guild_id)
        return cambiate

    async def set_rule(
        self, guild_id: int, kind: str, target_id: int, factor: float | None = None
    ) -> None:
        """
        Aggiunge o aggiorna una regola. Al massimo 25 per tipo e per
        server (RegolaPiena); aggiornare una già presente è sempre
        possibile.
        """
        if kind not in TIPI_REGOLA:
            raise ValueError(f"Tipo di regola sconosciuto: {kind}")
        if kind in TIPI_REGOLA_CON_FATTORE:
            if factor is None or not FATTORE_MINIMO <= factor <= FATTORE_MASSIMO:
                raise ValueError(f"Il fattore deve stare tra {FATTORE_MINIMO} e {FATTORE_MASSIMO}.")
        elif factor is not None:
            raise ValueError("Questo tipo di regola non ha un fattore.")

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Blocca la riga del server: due aggiunte insieme non superano il tetto.
                await conn.execute(
                    "SELECT pg_advisory_xact_lock($1, hashtext($2))", guild_id % 2**31, kind
                )
                esiste = await conn.fetchval(
                    "SELECT 1 FROM leveling_xp_rules WHERE guild_id=$1 AND kind=$2 AND target_id=$3",
                    guild_id, kind, target_id,
                )
                if not esiste:
                    quante = await conn.fetchval(
                        "SELECT count(*) FROM leveling_xp_rules WHERE guild_id=$1 AND kind=$2",
                        guild_id, kind,
                    )
                    if quante >= MAX_REGOLE_PER_TIPO:
                        raise RegolaPiena(kind)
                await conn.execute(
                    """
                    INSERT INTO leveling_xp_rules (guild_id, kind, target_id, factor)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (guild_id, kind, target_id) DO UPDATE SET factor = EXCLUDED.factor
                    """,
                    guild_id, kind, target_id, factor,
                )
        self._invalida(guild_id)

    async def remove_rule(self, guild_id: int, kind: str, target_id: int) -> bool:
        risultato = await self._pool.execute(
            "DELETE FROM leveling_xp_rules WHERE guild_id=$1 AND kind=$2 AND target_id=$3",
            guild_id, kind, target_id,
        )
        self._invalida(guild_id)
        return risultato.endswith(" 1")


def _get_pool():
    from core.database import db

    return db.pool


leveling_settings_repo = LevelingSettingsRepository(pool_provider=_get_pool)

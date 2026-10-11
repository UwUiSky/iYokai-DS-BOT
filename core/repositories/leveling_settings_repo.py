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
    MODI_ANNUNCIO,
    MODI_MOLTIPLICATORI,
    MODI_PREMI,
    TIPI_REGOLA,
    TIPI_REGOLA_CON_FATTORE,
    ConfigLivelli,
    LevelingSettings,
)

# Quanto resta in memoria una configurazione letta: il listener dei
# messaggi la chiede a ogni messaggio.
SECONDI_DI_CACHE = 60

_CAMPI_NOTI = {f.name for f in fields(LevelingSettings)}
_MODI = {
    "levelup_mode": MODI_ANNUNCIO,
    "reward_mode": MODI_PREMI,
    "multiplier_mode": MODI_MOLTIPLICATORI,
}


class RegolaPiena(Exception):
    """Il server ha già 25 regole di questo tipo."""


class LevelingSettingsRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider
        self._cache: BoundedCache[int, tuple[float, ConfigLivelli]] = BoundedCache(max_size=5_000)

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get_config(self, guild_id: int) -> ConfigLivelli:
        voce = self._cache.get(guild_id)
        if voce is not None and time.monotonic() - voce[0] < SECONDI_DI_CACHE:
            return voce[1]

        riga = await self._pool.fetchrow(
            "SELECT * FROM leveling_settings WHERE guild_id = $1", guild_id
        )
        regole = await self._pool.fetch(
            "SELECT kind, target_id, factor FROM leveling_xp_rules WHERE guild_id = $1", guild_id
        )
        impostazioni = (
            LevelingSettings(**{k: riga[k] for k in _CAMPI_NOTI}) if riga else LevelingSettings()
        )
        config = ConfigLivelli(
            impostazioni=impostazioni,
            canali_esclusi=frozenset(r["target_id"] for r in regole if r["kind"] == "canale_escluso"),
            ruoli_esclusi=frozenset(r["target_id"] for r in regole if r["kind"] == "ruolo_escluso"),
            mult_canali={r["target_id"]: float(r["factor"]) for r in regole if r["kind"] == "mult_canale"},
            mult_ruoli={r["target_id"]: float(r["factor"]) for r in regole if r["kind"] == "mult_ruolo"},
        )
        self._cache.set(guild_id, (time.monotonic(), config))
        return config

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

        if campi.get("levelup_mode") == "canale_scelto" and not campi.get("levelup_channel_id"):
            attuale = (await self.get_config(guild_id)).impostazioni.levelup_channel_id
            if attuale is None:
                raise ValueError("Per annunciare in un canale scelto serve il canale.")
            campi["levelup_channel_id"] = attuale

        if campi:
            nomi = list(campi)
            segnaposto = ", ".join(f"${i + 2}" for i in range(len(nomi)))
            aggiornamenti = ", ".join(f"{n} = EXCLUDED.{n}" for n in nomi)
            await self._pool.execute(
                f"INSERT INTO leveling_settings (guild_id, {', '.join(nomi)}) "
                f"VALUES ($1, {segnaposto}) "
                f"ON CONFLICT (guild_id) DO UPDATE SET {aggiornamenti}",
                guild_id,
                *campi.values(),
            )
            self._cache.delete(guild_id)
        return (await self.get_config(guild_id)).impostazioni

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
        self._cache.delete(guild_id)

    async def remove_rule(self, guild_id: int, kind: str, target_id: int) -> bool:
        risultato = await self._pool.execute(
            "DELETE FROM leveling_xp_rules WHERE guild_id=$1 AND kind=$2 AND target_id=$3",
            guild_id, kind, target_id,
        )
        self._cache.delete(guild_id)
        return risultato.endswith(" 1")


def _get_pool():
    from core.database import db

    return db.pool


leveling_settings_repo = LevelingSettingsRepository(pool_provider=_get_pool)

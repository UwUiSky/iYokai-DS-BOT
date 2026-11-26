"""
core/salute.py
==============
Lo stato di salute del bot, per chi lo sorveglia (systemd, un monitor): l'endpoint di salute e le
metriche nei log ogni 5 minuti. Dice se il bot è pronto, se il database risponde entro 2 secondi,
quali giri periodici sono vivi, di quanto rallenta il ciclo asyncio (i server web e i bot girano
tutti nello stesso ciclo) e se la musica ha un Lavalink. Risponde 200 se il bot è pronto e il
database risponde, 503 altrimenti. In ascolto solo su WEB_BIND_HOST (di base 127.0.0.1) e senza
nessun segreto nella risposta.
Funzioni coperte: consiglio 25/11/2026, critico 11 e seri di stabilità (blocco C)
Dipende da: core/giro_periodico.py, core/pool_db.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from typing import Any

from aiohttp import web

from core.giro_periodico import giri_in_difficolta, giro_periodico, stato_giri

logger = logging.getLogger("iyokai.salute")

PERCORSO = "/" + "salute"  # l'indirizzo web del controllo (non è un comando di Discord)

TIMEOUT_DATABASE_SECONDI = 2.0
RITARDO_CICLO_AVVISO_SECONDI = 1.0
FINESTRA_RITARDO_SECONDI = 300.0


class MisuraCiclo:
    """Quanto in ritardo arriva un giro da 1 secondo: se il ciclo asyncio è bloccato, il ritardo sale."""

    def __init__(self) -> None:
        self.ultimo_ms = 0.0
        self._finestra: deque[tuple[float, float]] = deque(maxlen=400)
        self._prima: float | None = None

    def registra(self, adesso: float, intervallo: float = 1.0) -> float:
        """Registra un giro arrivato a `adesso`. Restituisce il ritardo in secondi."""
        ritardo = 0.0
        if self._prima is not None:
            ritardo = max(0.0, adesso - self._prima - intervallo)
        self._prima = adesso
        self.ultimo_ms = ritardo * 1000
        self._finestra.append((adesso, ritardo * 1000))
        return ritardo

    def massimo_ms(self, adesso: float, secondi: float = FINESTRA_RITARDO_SECONDI) -> float:
        return max((ms for t, ms in self._finestra if adesso - t <= secondi), default=0.0)


misura_ciclo = MisuraCiclo()


async def _misura_database(pool: Any) -> dict[str, Any]:
    inizio = time.monotonic()
    try:
        await asyncio.wait_for(pool.fetchval("SELECT 1"), timeout=TIMEOUT_DATABASE_SECONDI)
    except Exception:
        return {"ok": False, "ms": round((time.monotonic() - inizio) * 1000)}
    return {"ok": True, "ms": round((time.monotonic() - inizio) * 1000)}


def _musica(bot: Any) -> dict[str, Any]:
    gestore = getattr(bot, "music_nodes", None)
    flotta = getattr(bot, "music_fleet", None)
    pronti = sum(1 for w in getattr(flotta, "worker_bots", []) if w.is_ready())
    return {
        "lavalink": gestore.stato_per_servizio() if gestore is not None else {},
        "worker_pronti": pronti,
    }


async def rapporto(bot: Any, pool: Any, adesso: float | None = None) -> dict[str, Any]:
    """Il rapporto di salute completo. `stato`: ok, degradato (giri in difficoltà) o giu (non pronto o senza database)."""
    adesso = time.monotonic() if adesso is None else adesso
    pronto = bool(bot.is_ready())
    database = await _misura_database(pool) if pool is not None else {"ok": False, "ms": 0}
    giri = stato_giri()
    in_difficolta = giri_in_difficolta()
    if not pronto or not database["ok"]:
        stato = "giu"
    elif in_difficolta:
        stato = "degradato"
    else:
        stato = "ok"
    return {
        "stato": stato,
        "pronto": pronto,
        "database": database,
        "giri": {
            "totale": len(giri),
            "vivi": sum(1 for g in giri if g["vivo"]),
            "in_difficolta": in_difficolta,
        },
        "ritardo_ciclo_ms": {
            "ultimo": round(misura_ciclo.ultimo_ms),
            "massimo_5_minuti": round(misura_ciclo.massimo_ms(adesso)),
        },
        "musica": _musica(bot),
    }


def build_app(bot: Any, pool_provider) -> web.Application:
    """`pool_provider()` dà il pool del database, o None se non è aperto."""

    async def salute(request: web.Request) -> web.Response:
        try:
            dati = await rapporto(bot, pool_provider())
        except Exception:
            logger.exception("Rapporto di salute non calcolabile.")
            dati = {"stato": "giu", "pronto": False}
        stato_http = 200 if dati["stato"] in ("ok", "degradato") else 503
        return web.Response(
            status=stato_http, text=json.dumps(dati, ensure_ascii=False), content_type="application/json"
        )

    app = web.Application()
    app.router.add_get(PERCORSO, salute)
    return app


async def start_server(app: web.Application, host: str, port: int) -> web.AppRunner:
    runner = web.AppRunner(app, access_log=None)  # un controllo ogni pochi secondi non va nel log
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    logger.info("Controllo di salute in ascolto su %s:%d%s", host, port, PERCORSO)
    return runner


def avvia_misure(bot: Any, pool_provider):
    """Fa partire la misura del ritardo del ciclo (ogni secondo) e le metriche nei log (ogni 5 minuti)."""

    @giro_periodico(seconds=1, subito=True, silenzioso=True)
    async def _misura_ritardo_ciclo() -> None:
        ritardo = misura_ciclo.registra(time.monotonic())
        if ritardo >= RITARDO_CICLO_AVVISO_SECONDI:
            logger.warning("Il ciclo asyncio è in ritardo di %.1f s: qualcosa lo sta bloccando.", ritardo)

    @giro_periodico(minutes=5, subito=True, silenzioso=True)
    async def _metriche_nei_log() -> None:
        dati = await rapporto(bot, pool_provider())
        pool = pool_provider()
        occupate = (pool.get_size() - pool.get_idle_size(), pool.get_size()) if pool is not None else (0, 0)
        try:
            import psutil

            rss_mb = psutil.Process().memory_info().rss // (1024 * 1024)
        except Exception:
            rss_mb = -1
        logger.info(
            "Salute: stato=%s db=%sms giri=%d/%d in_difficolta=%d ritardo_max5m=%dms pool=%d/%d rss=%dMB task=%d",
            dati["stato"], dati["database"]["ms"], dati["giri"]["vivi"], dati["giri"]["totale"],
            len(dati["giri"]["in_difficolta"]), dati["ritardo_ciclo_ms"]["massimo_5_minuti"],
            occupate[0], occupate[1], rss_mb, len(asyncio.all_tasks()),
        )

    _misura_ritardo_ciclo.start()
    _metriche_nei_log.start()
    return [_misura_ritardo_ciclo, _metriche_nei_log]

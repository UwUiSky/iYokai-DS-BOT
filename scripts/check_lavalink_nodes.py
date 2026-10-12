"""
scripts/check_lavalink_nodes.py
===================================
Controlla i nodi Lavalink del .env (LAVALINK_NODES + nodo locale): legge
`/v4/info` di ciascuno e scrive un WARNING se non risponde, se la password
e' sbagliata o se la versione e' sotto la 4.2.0 (issue #48, M 8.11).

Uso:
    python3 scripts/check_lavalink_nodes.py            # solo avvisi
    python3 scripts/check_lavalink_nodes.py --strict   # exit 1 se c'e' un nodo non valido

Non scrive mai le password: nei log compare solo l'indirizzo.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

import aiohttp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.music_logic import LavalinkNodeConfig, is_supported_lavalink, parse_lavalink_nodes

logger = logging.getLogger("iyokai.check_lavalink")
TIMEOUT_S = 8


async def controlla_nodo(sessione: aiohttp.ClientSession, nodo: LavalinkNodeConfig) -> tuple[bool, str]:
    """(ok, descrizione). Mai la password nel testo."""
    url = f"{nodo.uri.rstrip('/')}/v4/info"
    try:
        async with sessione.get(
            url,
            headers={"Authorization": nodo.password},
            timeout=aiohttp.ClientTimeout(total=TIMEOUT_S),
        ) as risposta:
            if risposta.status == 401:
                return False, "password rifiutata"
            if risposta.status != 200:
                return False, f"risposta HTTP {risposta.status}"
            dati = await risposta.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as errore:
        return False, f"non risponde ({type(errore).__name__})"

    versione = (dati.get("version") or {}).get("semver")
    if not is_supported_lavalink(versione):
        return False, f"versione {versione} sotto la 4.2.0"
    sorgenti = ",".join(dati.get("sourceManagers") or [])
    return True, f"versione {versione}, sorgenti: {sorgenti}"


async def controlla_tutti(nodi: list[LavalinkNodeConfig]) -> list[tuple[LavalinkNodeConfig, bool, str]]:
    async with aiohttp.ClientSession() as sessione:
        esiti = await asyncio.gather(*(controlla_nodo(sessione, n) for n in nodi))
    return [(n, ok, testo) for n, (ok, testo) in zip(nodi, esiti)]


def nodi_dal_ambiente() -> list[LavalinkNodeConfig]:
    nodi = parse_lavalink_nodes(os.getenv("LAVALINK_NODES", ""))
    host = os.getenv("LAVALINK_HOST", "127.0.0.1")
    porta = os.getenv("LAVALINK_PORT", "2333")
    nodi.append(LavalinkNodeConfig(f"http://{host}:{porta}", os.getenv("LAVALINK_PASSWORD", "")))
    return nodi


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    risultati = asyncio.run(controlla_tutti(nodi_dal_ambiente()))
    cattivi = 0
    for nodo, ok, testo in risultati:
        if ok:
            logger.info("OK      %s: %s", nodo.uri, testo)
        else:
            cattivi += 1
            logger.warning("NODO NON VALIDO %s: %s", nodo.uri, testo)
    return 1 if (args.strict and cattivi) else 0


if __name__ == "__main__":
    sys.exit(main())

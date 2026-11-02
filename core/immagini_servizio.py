"""
core/immagini_servizio.py
=========================
Servizio di sistema `iyokai-sandbox` (D62, modo A): ascolta su un socket Unix, riceve il nome di un
file di quarantena (una riga) e risponde con l'esito dell'analisi, avviando per ogni lavoro un
processo figlio nuovo con i limiti di core/immagini_sandbox.py. Gira con un utente senza permessi,
senza rete e con la quarantena in sola lettura (deploy/systemd/iyokai-sandbox.service).
Si avvia con `python3 -I core/immagini_servizio.py`. Il bot parla con lui da `sandbox.analizza`.
Funzioni coperte: SPEC §6 (D62)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
import sys
from pathlib import Path

RADICE = str(Path(__file__).resolve().parent.parent)
if RADICE not in sys.path:
    sys.path.insert(0, RADICE)

from core import immagini_sandbox as sb  # noqa: E402

logger = logging.getLogger("iyokai.immagini.servizio")
ATTESA_RIGA = 5.0


def impacchetta(r: sb.RisultatoSandbox) -> bytes:
    corpo = json.dumps({"stato": r.esito, "info": r.info}, separators=(",", ":")).encode()
    return struct.pack(">I", len(corpo)) + corpo + struct.pack(">I", len(r.png)) + r.png


async def gestisci(lettore: asyncio.StreamReader, scrittore: asyncio.StreamWriter) -> None:
    try:
        riga = await asyncio.wait_for(lettore.readline(), ATTESA_RIGA)
        nome = riga.decode("ascii", "ignore").strip()
        if not sb.NOME.fullmatch(nome):
            risposta = impacchetta(sb.RisultatoSandbox("errore", {"motivo": "nome"}))
        else:
            # Il servizio ha gia' PrivateNetwork: niente `unshare` qui.
            risposta = impacchetta(await sb.esegui_locale(nome, isola_rete=False))
        scrittore.write(risposta)
        await scrittore.drain()
    except (asyncio.TimeoutError, ConnectionError):
        pass
    except Exception:
        logger.exception("Servizio sandbox: errore imprevisto")
    finally:
        scrittore.close()


async def serve(percorso: str) -> asyncio.AbstractServer:
    Path(percorso).parent.mkdir(parents=True, exist_ok=True)
    try:
        os.unlink(percorso)
    except FileNotFoundError:
        pass
    server = await asyncio.start_unix_server(gestisci, path=percorso)
    os.chmod(percorso, 0o660)
    _dai_al_gruppo_del_bot(percorso)
    return server


def _dai_al_gruppo_del_bot(percorso: str) -> None:
    """
    Di base il socket resta al gruppo del servizio (`iyokai-sbx`) e il bot entra in quel gruppo: il servizio
    non riceve mai il gruppo del bot, cosi' un worker compromesso non legge i suoi file. Solo se
    `IYOKAI_SANDBOX_GRUPPO` e' impostata si assegna quel gruppo (il servizio deve esserne membro).
    """
    nome = os.environ.get("IYOKAI_SANDBOX_GRUPPO")
    if not nome:
        return
    try:
        import grp

        gid = grp.getgrnam(nome).gr_gid
        os.chown(percorso, -1, gid)
        os.chown(os.path.dirname(percorso), -1, gid)
    except (KeyError, PermissionError, OSError, ImportError):
        logger.warning("Servizio sandbox: gruppo %s non assegnato al socket", nome)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    server = await serve(sb.socket_servizio())
    logger.info("Servizio sandbox in ascolto su %s", sb.socket_servizio())
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())

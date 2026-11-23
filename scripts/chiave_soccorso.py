"""
scripts/chiave_soccorso.py
==========================
Verifica a mano della chiave di soccorso dell'owner (SIC-021). Si lancia sul server del bot, con `DATABASE_URL` nel
`.env`: chiede il codice senza mostrarlo e dice se è giusto. Non cambia `OWNER_ID`: se il codice è giusto, la modifica
del `.env` la fa chi ha accesso al server.
Funzioni coperte: SIC-021
Uso: python scripts/chiave_soccorso.py verifica
"""

from __future__ import annotations

import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def _verifica() -> int:
    from core import chiave_soccorso
    from core.config import config
    from core.database import db

    await db.connect()
    try:
        st = await chiave_soccorso.stato()
        if not st.presente:
            print("Nessuna chiave di soccorso: non si può verificare.")
            return 2
        if st.bloccata:
            print("La chiave è bloccata (troppi errori). Serve un owner che ne crei una nuova.")
            return 3
        if await chiave_soccorso.verifica(getpass.getpass("Codice di soccorso: ")):
            print("Codice giusto. Ora cambia OWNER_ID nel .env con il nuovo account e riavvia il bot.")
            return 0
        print("Codice sbagliato.")
        return 1
    finally:
        await db.close()


def main() -> int:
    if sys.argv[1:] != ["verifica"]:
        print(__doc__)
        return 64
    return asyncio.run(_verifica())


if __name__ == "__main__":
    sys.exit(main())

"""
scripts/genera_wiki.py
======================
Genera la wiki dei comandi come sito statico (issue #147) dall'albero VERO del bot, come
`generate_command_list.py`. Da servire dalla radice di un dominio.

Uso (con le variabili d'ambiente di `generate_command_list.py`):
    python3 scripts/genera_wiki.py [cartella_di_uscita]      # di base: wiki_generata/
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main(uscita: pathlib.Path) -> int:
    from core.command_search_logic import raccogli_comandi
    from core.command_translator import carica_traduzioni
    from core.database import db
    from core.wiki_statica import genera
    from tests.support.full_tree import build_full_bot, close_full_bot

    await db.connect()
    try:
        await db.run_migrations()
        carica_traduzioni(forza=True)
        bot, falliti = await build_full_bot()
        try:
            for modulo, errore in falliti:
                print(f"ATTENZIONE: {modulo} non caricato: {errore}", file=sys.stderr)
            comandi = sorted(raccogli_comandi(bot.tree.get_commands()), key=lambda c: c.percorso)
            return genera(comandi, uscita)
        finally:
            await close_full_bot(bot)
    finally:
        await db.close()


if __name__ == "__main__":
    cartella = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "wiki_generata")
    print(f"Pagine di comando scritte: {asyncio.run(main(cartella))} in {cartella}/")

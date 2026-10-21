"""
scripts/generate_command_list.py
====================================
Genera COMMAND_LIST.md interrogando l'albero comandi VERO del bot
(bot.tree, dopo aver caricato ogni cog reale) — non un elenco scritto
a mano che rischierebbe di disallinearsi dal codice a ogni nuova
feature. Va rilanciato ogni volta che si aggiunge/rimuove un comando,
dopo commit e push (vedi PROGRESS.md).

Uso:
    export YOKAI_BOT_TOKEN=test YOKAI_CREATOR_TOKEN=test
    export MUSIC_TOKEN_1=test MUSIC_TOKEN_2=test MUSIC_TOKEN_3=test MUSIC_TOKEN_4=test MUSIC_TOKEN_5=test
    export NSFW_TOKEN=test OWNER_ID=123 MAIN_GUILD_ID=456 ENVIRONMENT=development
    export DATABASE_URL=postgresql://utente:password@host:5432/nome_db
    python3 scripts/generate_command_list.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord
from discord import app_commands
from discord.ext import commands

from core.command_tree_utils import walk_commands


async def main() -> None:
    from core.database import db
    from core.cog_manager import discover_cog_modules
    from core.blacklist_tree import BlacklistAwareCommandTree

    await db.connect()
    try:
        await db.run_migrations()

        bot = commands.Bot(
            command_prefix="!",
            intents=discord.Intents.default(),
            tree_cls=BlacklistAwareCommandTree,
        )

        moduli = discover_cog_modules()
        per_categoria: dict[str, list[tuple[str, str]]] = defaultdict(list)

        for modulo_path in sorted(moduli):
            try:
                await bot.load_extension(modulo_path)
            except Exception as exc:
                print(f"ATTENZIONE: {modulo_path} non caricato: {type(exc).__name__}: {exc}",
                      file=sys.stderr)
                continue

        # I comandi vanno letti DOPO che tutti i cog sono caricati,
        # non uno alla volta: alcuni gruppi (es. /owner) ricevono
        # sottocomandi da più metodi nello stesso file, serve
        # l'albero completo.
        from core.command_groups import GRUPPI
        from core.command_translator import carica_traduzioni

        carica_traduzioni(forza=True)
        # `/owner` vive solo nel server dell'owner: non è nell'albero globale ma va nell'elenco.
        comandi_top_level = list(bot.tree.get_commands())
        if GRUPPI["owner"].commands:
            comandi_top_level.append(GRUPPI["owner"])

        # La categoria è il gruppo di primo livello (D24); i comandi
        # singoli di primo livello (-cerca-comando, -chiedi) vanno in "aiuto".
        per_lingua = {"it": defaultdict(list), "en": defaultdict(list)}
        for cmd in comandi_top_level:
            categoria = cmd.name if isinstance(cmd, app_commands.Group) else "aiuto"
            for lingua in ("it", "en"):
                per_lingua[lingua][categoria].extend(_foglie(cmd, lingua))

        _scrivi_markdown(per_lingua["it"], "COMMAND_LIST.md", "it")
        _scrivi_markdown(per_lingua["it"], "COMMAND_LIST_ITA.md", "it")
        _scrivi_markdown(per_lingua["en"], "COMMAND_LIST_ENG.md", "en")
        print(f"Scritti COMMAND_LIST.md, _ITA e _ENG con {sum(len(v) for v in per_lingua['it'].values())} comandi "
              f"in {len(per_lingua['it'])} categorie.")
    finally:
        await db.close()


def _foglie(nodo, lingua: str, prefisso: str = "") -> list[tuple[str, str]]:
    """(percorso, descrizione) di ogni comando sotto `nodo`, in italiano (base) o in inglese (traduzione di Discord)."""
    from core.command_translator import descrizione_inglese, nome_inglese

    nome = (nome_inglese(nodo.name) or nodo.name) if lingua == "en" else nodo.name
    mostrato = f"{prefisso} {nome}".strip() if prefisso else nome
    if isinstance(nodo, app_commands.Group):
        figli: list[tuple[str, str]] = []
        for c in nodo.commands:
            figli.extend(_foglie(c, lingua, mostrato))
        return figli
    # `percorso` per la traduzione è sempre quello italiano (chiave del file); qui lo ricostruiamo
    # dal nodo vero.
    descrizione = nodo.description or "(nessuna descrizione)"
    if lingua == "en":
        descrizione = descrizione_inglese(nodo.qualified_name) or descrizione
    return [(mostrato, descrizione)]


def _scrivi_markdown(per_categoria: dict[str, list[tuple[str, str]]], file_nome: str = "COMMAND_LIST.md", lingua: str = "it") -> None:
    etichette_categoria = {
        "aiuto": "Aiuto (primo livello)",
        "admin": "Admin",
        "automod": "AutoMod",
        "clan": "Clan",
        "fun": "Divertimento",
        "gestione": "Gestione",
        "level": "Livelli",
        "log": "Log",
        "mod": "Moderazione",
        "modban": "Ban (modban)",
        "moduli": "Moduli",
        "music": "Musica",
        "owner": "Owner",
        "security": "Sicurezza",
        "ticket": "Ticket",
        "utility": "Utility",
        "voice": "Vocali",
    }

    if lingua == "en":
        etichette_categoria = {
            "aiuto": "Help (top level)", "admin": "Admin", "automod": "AutoMod", "clan": "Clan",
            "fun": "Fun", "gestione": "Management", "level": "Levels", "log": "Log",
            "mod": "Moderation", "modban": "Bans (modban)", "moduli": "Modules", "music": "Music",
            "owner": "Owner", "security": "Security", "ticket": "Tickets", "utility": "Utility",
            "voice": "Voice", "economia": "Economy", "ruoli": "Roles",
        }
    etichette_categoria.setdefault("economia", "Economia")
    righe = [
        "# Command list (English) — iYokai" if lingua == "en" else "# Elenco comandi — iYokai",
        "",
        (
            f"Generated automatically by `scripts/generate_command_list.py` on "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from the REAL command tree. "
            f"English names and descriptions are the ones Discord shows to users with the client in English "
            f"(`locales/comandi.en.json`); the base names in the code are Italian. Regenerate after every "
            f"commit that adds, removes or renames a command."
            if lingua == "en"
            else f"Generato automaticamente da `scripts/generate_command_list.py` il "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}, "
            f"interrogando l'albero comandi VERO del bot dopo aver caricato ogni "
            f"cog — non un elenco scritto a mano. Da rigenerare dopo ogni commit "
            f"che aggiunge, rimuove o rinomina un comando."
        ),
        "",
        f"**{'Total' if lingua == 'en' else 'Totale'}: {sum(len(v) for v in per_categoria.values())} "
        f"{'commands' if lingua == 'en' else 'comandi'} in "
        f"{len(per_categoria)} {'categories' if lingua == 'en' else 'categorie'}.**",
        "",
    ]

    for categoria in sorted(per_categoria.keys()):
        etichetta = etichette_categoria.get(categoria, categoria.capitalize())
        comandi = sorted(per_categoria[categoria])
        righe.append(f"## {etichetta}")
        righe.append("")
        for nome, descrizione in comandi:
            righe.append(f"- **`/{nome}`** — {descrizione}")
        righe.append("")

    percorso = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), file_nome
    )
    with open(percorso, "w", encoding="utf-8") as f:
        f.write("\n".join(righe))


if __name__ == "__main__":
    asyncio.run(main())

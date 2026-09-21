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
        comandi_top_level = bot.tree.get_commands()

        # Per assegnare ogni comando alla categoria giusta, guardiamo
        # a quale cog appartiene il comando (o il primo sottocomando
        # per i gruppi), non al modulo che lo ha CARICATO per ultimo.
        for cmd in comandi_top_level:
            if isinstance(cmd, app_commands.Group):
                sotto = walk_commands(cmd.commands, prefix=cmd.name)
                riferimento = cmd.commands[0] if cmd.commands else None
            else:
                sotto = [(cmd.name, cmd.description or "(nessuna descrizione)")]
                riferimento = cmd

            cog_nome = None
            if riferimento is not None and riferimento.binding is not None:
                cog_nome = type(riferimento.binding).__module__

            categoria = cog_nome.split(".")[1] if cog_nome else "altro"
            per_categoria[categoria].extend(sotto)

        _scrivi_markdown(per_categoria)
        print(f"Scritto COMMAND_LIST.md con {sum(len(v) for v in per_categoria.values())} comandi "
              f"in {len(per_categoria)} categorie.")
    finally:
        await db.close()


def _scrivi_markdown(per_categoria: dict[str, list[tuple[str, str]]]) -> None:
    etichette_categoria = {
        "moderation": "Moderazione",
        "security": "Sicurezza",
        "utility": "Utility",
        "automod": "AutoMod",
        "logging": "Logging",
        "levels": "Livelli",
        "tickets": "Ticket",
        "voice_temp": "Canali Vocali Temporanei",
        "altro": "Altro",
    }

    righe = [
        "# Elenco comandi — iYokai",
        "",
        f"Generato automaticamente da `scripts/generate_command_list.py` il "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}, "
        f"interrogando l'albero comandi VERO del bot dopo aver caricato ogni "
        f"cog — non un elenco scritto a mano. Da rigenerare dopo ogni commit "
        f"che aggiunge, rimuove o rinomina un comando.",
        "",
        f"**Totale: {sum(len(v) for v in per_categoria.values())} comandi in "
        f"{len(per_categoria)} categorie.**",
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
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "COMMAND_LIST.md"
    )
    with open(percorso, "w", encoding="utf-8") as f:
        f.write("\n".join(righe))


if __name__ == "__main__":
    asyncio.run(main())

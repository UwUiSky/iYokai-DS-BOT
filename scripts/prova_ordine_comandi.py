"""
scripts/prova_ordine_comandi.py
===============================
Prova a mano: in che ordine Discord mostra i comandi quando si scrive "/".
Registra 8 comandi di prova SOLO nel server di prova (non globali) con nomi
che iniziano con simboli, numeri e lettere; poi li rimuove.

Uso (dal tuo computer o dal server, con il tuo .env):
    python3 scripts/prova_ordine_comandi.py registra
    ... scrivi "/" nel server di prova e annota l'ordine in cui compaiono ...
    python3 scripts/prova_ordine_comandi.py rimuovi

Variabili lette dall'ambiente (o da .env, se python-dotenv è installato):
    YOKAI_BOT_TOKEN   token del bot (non viene mai stampato)
    PROVA_GUILD_ID    ID del server di prova

Nota: i comandi per-server compaiono subito. `rimuovi` cancella solo i comandi
che hanno questi nomi: gli altri comandi del bot non vengono toccati.
Non usa `sync`, quindi non sovrascrive i comandi che il bot ha già nel server.
"""

from __future__ import annotations

import asyncio
import os
import sys

import discord

# Nomi ammessi da Discord: lettere minuscole, numeri, "-", "_" e "ʼ".
NOMI = ["_prova", "-prova", "ʼprova", "0prova", "1prova", "aprova", "mprova", "zprova"]


def _leggi_ambiente() -> tuple[str, int]:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    token = os.environ.get("YOKAI_BOT_TOKEN", "")
    guild = os.environ.get("PROVA_GUILD_ID", "")
    if not token or not guild.isdigit():
        sys.exit("Servono YOKAI_BOT_TOKEN e PROVA_GUILD_ID (numero) nell'ambiente.")
    return token, int(guild)


async def _esegui(modo: str) -> None:
    token, guild_id = _leggi_ambiente()
    client = discord.Client(intents=discord.Intents.none())
    async with client:
        await client.login(token)
        app_id = (await client.application_info()).id
        if modo == "registra":
            for nome in NOMI:
                # Un comando alla volta, senza sync: i comandi veri del bot
                # nel server di prova non vengono toccati.
                await client.http.upsert_guild_command(
                    app_id,
                    guild_id,
                    {"name": nome, "description": "Prova dell'ordine dei comandi", "type": 1},
                )
            print(f"Registrati {len(NOMI)} comandi di prova nel server {guild_id}.")
            return
        esistenti = await client.http.get_guild_commands(app_id, guild_id)
        tolti = 0
        for comando in esistenti:
            if comando["name"] in NOMI:
                await client.http.delete_guild_command(app_id, guild_id, int(comando["id"]))
                tolti += 1
        print(f"Rimossi {tolti} comandi di prova dal server {guild_id}.")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("registra", "rimuovi"):
        sys.exit(__doc__)
    asyncio.run(_esegui(sys.argv[1]))


if __name__ == "__main__":
    main()

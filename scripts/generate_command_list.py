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
from core.comandi_diretti import ComandoDiretto, percorso_vero


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
        if GRUPPI["owner-radio"].commands:
            comandi_top_level.append(GRUPPI["owner-radio"])
        # Le applicazioni separate (istanza NSFW, iYokai App) hanno un albero proprio: categorie a parte.
        from tests.support.full_tree import build_separate_trees

        per_app: dict[int, str] = {}  # per oggetto: `/ai` esiste in due app diverse
        for altro in await build_separate_trees():
            for c in altro.tree.get_commands():
                comandi_top_level.append(c)
                per_app[id(c)] = f"app:{altro.istanza}"
            await altro.close()

        # La categoria è il gruppo di primo livello (D24); i comandi
        # singoli di primo livello (/help) e i comandi diretti vanno nelle loro categorie.
        per_lingua = {"it": defaultdict(list), "en": defaultdict(list)}
        for cmd in comandi_top_level:
            categoria = per_app.get(id(cmd)) or (
                cmd.name if isinstance(cmd, app_commands.Group) else "diretti" if isinstance(cmd, ComandoDiretto) else "help"
            )
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
    from core.command_translator import descrizione_inglese, menu_inglese, nome_inglese

    nome = (nome_inglese(nodo.name) or nodo.name) if lingua == "en" else nodo.name
    mostrato = f"{prefisso} {nome}".strip() if prefisso else nome
    if isinstance(nodo, app_commands.ContextMenu):
        mostrato = (menu_inglese(nodo.name) or nodo.name) if lingua == "en" else nodo.name
        return [(mostrato, "Menu «App» (tasto destro)" if lingua != "en" else "“Apps” menu (right click)")]
    if isinstance(nodo, app_commands.Group):
        figli: list[tuple[str, str]] = []
        for c in nodo.commands:
            figli.extend(_foglie(c, lingua, mostrato))
        return figli
    # `percorso` per la traduzione è sempre quello italiano (chiave del file); qui lo ricostruiamo
    # dal nodo vero.
    descrizione = nodo.description or "(nessuna descrizione)"
    if lingua == "en":
        descrizione = descrizione_inglese(percorso_vero(nodo)) or descrizione
    return [(mostrato, descrizione)]


# Etichette dei gruppi nati dal riordino (D137), in italiano e in inglese.
_ETICHETTE_RIORDINO = {
    "it": {
        "help": "Aiuto", "diretti": "Comandi diretti (stessa funzione del comando lungo)", "owner-radio": "Owner: radio",
        "ai": "Assistente AI", "vocali": "Vocali", "monete-clan": "Clan",
        "music-playlist": "Playlist", "giochi-sala": "Sala giochi", "giochi-mondo": "Il tuo mondo",
        "giochi-animali": "Animali e pesca", "utility-web": "Cerca sul web", "utility-server": "Il tuo server",
        "admin-automod-filtri": "Admin: filtri", "admin-sicurezza-antinuke": "Admin: anti-nuke",
        "admin-sicurezza-antiraid": "Admin: anti-raid", "admin-sicurezza-verifica": "Admin: verifica",
        "admin-ruoli-menu": "Admin: menu dei ruoli", "admin-economia-negozio": "Admin: negozio avanzato",
        "admin-messaggi-tag": "Admin: tag", "admin-bot-config": "Admin: configurazione",
        "admin-ticket-pannelli": "Admin: pannelli dei ticket", "admin-livelli-guadagno": "Admin: guadagno XP",
        "admin-livelli-rep": "Admin: reputazione",
    },
    "en": {
        "help": "Help", "diretti": "Direct commands (same function as the long command)", "owner-radio": "Owner: radio",
        "ai": "AI assistant", "vocali": "Voice", "monete-clan": "Clan",
        "music-playlist": "Playlists", "giochi-sala": "Game room", "giochi-mondo": "Your world",
        "giochi-animali": "Pets and fishing", "utility-web": "Web search", "utility-server": "Your server",
        "admin-automod-filtri": "Admin: filters", "admin-sicurezza-antinuke": "Admin: anti-nuke",
        "admin-sicurezza-antiraid": "Admin: anti-raid", "admin-sicurezza-verifica": "Admin: verification",
        "admin-ruoli-menu": "Admin: role menus", "admin-economia-negozio": "Admin: advanced shop",
        "admin-messaggi-tag": "Admin: tags", "admin-bot-config": "Admin: configuration",
        "admin-ticket-pannelli": "Admin: ticket panels", "admin-livelli-guadagno": "Admin: XP gain",
        "admin-livelli-rep": "Admin: reputation",
    },
}


def _scrivi_markdown(per_categoria: dict[str, list[tuple[str, str]]], file_nome: str = "COMMAND_LIST.md", lingua: str = "it") -> None:
    etichette_categoria = {
        "aiuto": "Aiuto (primo livello)",
        "fun": "Divertimento",
        "level": "Livelli",
        "music": "Musica",
        "owner": "Owner",
        "ticket": "Ticket",
        "utility": "Utility",
                "admin-bot": "Admin: impianto del bot",
        "admin-musica": "Admin: musica",
        "admin-ai": "Admin: AI",
        "admin-automod": "Admin: AutoMod",
        "admin-sicurezza": "Admin: sicurezza",
        "admin-moduli": "Admin: moduli",
        "admin-economia": "Admin: economia",
        "admin-livelli": "Admin: livelli e XP",
        "admin-ruoli": "Admin: ruoli",
        "admin-log": "Admin: log",
        "admin-messaggi": "Admin: messaggi",
        "admin-inviti": "Admin: inviti",
        "admin-giochi": "Admin: giochi",
        "admin-automazioni": "Admin: automazioni",
        "admin-giveaway": "Admin: giveaway",
        "admin-alert": "Admin: avvisi social",
        "admin-ticket": "Admin: ticket",
        "admin-ticket-opzioni": "Admin: opzioni dei ticket",
        "admin-backup": "Admin: backup",
        "admin-benvenuto": "Admin: benvenuto",
        "admin-vocali": "Admin: vocali temporanei",
        "mod-sanzioni": "Mod: sanzioni",
        "mod-casi": "Mod: casi e note",
        "mod-canali": "Mod: canali",
        "mod-ban": "Mod: ban",
        "founder": "Founder (proprietario del server)",
        "immagini": "Immagini", "giochi": "Giochi", "monete": "Monete",
        "premium": "Premium", "vip": "VIP",
        "app:nsfw": "iYokai NSFW (app separata, solo canali vietati ai minori)",
        "app:app": "iYokai App (app separata, installata sull'utente)",
    }

    if lingua == "en":
        etichette_categoria = {
            "aiuto": "Help (top level)", "clan": "Clan", "fun": "Fun", "level": "Levels",
            "music": "Music", "owner": "Owner", "ticket": "Tickets", "utility": "Utility",
            "admin-bot": "Admin: bot setup",
            "admin-musica": "Admin: music",
            "admin-ai": "Admin: AI",
            "admin-automod": "Admin: AutoMod",
            "admin-sicurezza": "Admin: security",
            "admin-moduli": "Admin: modules",
            "admin-economia": "Admin: economy",
            "admin-livelli": "Admin: levels and XP",
            "admin-ruoli": "Admin: roles",
            "admin-log": "Admin: log",
            "admin-messaggi": "Admin: messages",
            "admin-inviti": "Admin: invites",
            "admin-giochi": "Admin: games",
            "admin-automazioni": "Admin: automations",
            "admin-giveaway": "Admin: giveaways",
            "admin-alert": "Admin: social alerts",
            "admin-ticket": "Admin: tickets",
            "admin-ticket-opzioni": "Admin: ticket options",
            "admin-backup": "Admin: backup",
            "admin-benvenuto": "Admin: welcome",
            "admin-vocali": "Admin: temporary voice",
            "mod-sanzioni": "Mod: sanctions",
            "mod-casi": "Mod: cases and notes",
            "mod-canali": "Mod: channels",
            "mod-ban": "Mod: bans",
            "founder": "Founder (server owner)",
            "immagini": "Images", "giochi": "Games", "monete": "Coins",
            "premium": "Premium", "vip": "VIP",
            "app:nsfw": "iYokai NSFW (separate app, age-restricted channels only)",
            "app:app": "iYokai App (separate app, installed on the user)",
        }
    etichette_categoria.setdefault("economia", "Economia")
    etichette_categoria.update(_ETICHETTE_RIORDINO["en" if lingua == "en" else "it"])
    righe = [
        "# Command list (English) — iYokai" if lingua == "en" else "# Elenco comandi — iYokai",
        "",
        (
            f"Generated automatically by `scripts/generate_command_list.py` on "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from the REAL command tree. "
            f"English names and descriptions are the ones Discord shows to users with the client in English "
            f"(`locales/en-US/comandi.json`); the base names in the code are Italian. Regenerate after every "
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

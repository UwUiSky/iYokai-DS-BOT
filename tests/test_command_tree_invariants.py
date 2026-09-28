"""
tests/test_command_tree_invariants.py
=========================================
Verifica sui limiti REALI dell'API Discord applicati all'albero
comandi del bot vero (costruito con tests/support/full_tree.py, non
un albero finto): ogni gruppo entro 25 sotto-comandi, al massimo 1
livello di sotto-gruppi, e i componenti Select costruiti con dati
reali entro 25 opzioni.
Funzioni coperte: RT-2 di PIANO_FIX.md.
"""

from __future__ import annotations

import discord
from discord import app_commands

from tests.support.full_tree import build_full_bot, close_full_bot, connect_db_if_needed

MAX_SUBCOMMANDS_PER_GROUP = 25
MAX_SUBGROUP_DEPTH = 1

# Cricchetto: nomi di Select che OGGI superano il limite di 25 opzioni
# con dati reali. Il test fallisce se compare un nome nuovo qui sopra
# o se uno di questi viene sistemato ma non tolto dall'insieme.
# /setup: ModuleSelect costruita con tutti i PremiumModule registrati
# (oggi 32) — limite Discord 25, fix previsto in R5 (paginazione).
KNOWN_OVERSIZED_SELECTS = {"setup"}


def _sottogruppi_e_comandi(gruppo: app_commands.Group) -> tuple[list, list]:
    sottogruppi = [c for c in gruppo.commands if isinstance(c, app_commands.Group)]
    comandi = [c for c in gruppo.commands if not isinstance(c, app_commands.Group)]
    return sottogruppi, comandi


async def test_ogni_gruppo_ha_al_massimo_25_sottocomandi_e_1_livello():
    creato_qui = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti, f"Cog falliti nel caricamento: {falliti}"

        gruppi_top_level = [
            c for c in bot.tree.get_commands() if isinstance(c, app_commands.Group)
        ]
        assert gruppi_top_level, "Nessun gruppo top-level trovato: l'albero è vuoto?"

        for gruppo in gruppi_top_level:
            sottogruppi, comandi_diretti = _sottogruppi_e_comandi(gruppo)

            assert len(gruppo.commands) <= MAX_SUBCOMMANDS_PER_GROUP, (
                f"Il gruppo '{gruppo.name}' ha {len(gruppo.commands)} elementi "
                f"diretti (comandi + sotto-gruppi): il limite Discord per "
                f"gruppo è {MAX_SUBCOMMANDS_PER_GROUP}."
            )

            for sottogruppo in sottogruppi:
                nipoti_sottogruppi, _ = _sottogruppi_e_comandi(sottogruppo)
                assert not nipoti_sottogruppi, (
                    f"'{gruppo.name} {sottogruppo.name}' ha un ulteriore "
                    f"livello di sotto-gruppi: Discord permette al massimo "
                    f"{MAX_SUBGROUP_DEPTH} livello di annidamento sotto un "
                    f"gruppo top-level."
                )
                assert len(sottogruppo.commands) <= MAX_SUBCOMMANDS_PER_GROUP, (
                    f"'{gruppo.name} {sottogruppo.name}' ha "
                    f"{len(sottogruppo.commands)} sotto-comandi: il limite "
                    f"Discord è {MAX_SUBCOMMANDS_PER_GROUP}."
                )
    finally:
        await close_full_bot(bot)
        if creato_qui:
            from core.database import db as db_singleton

            await db_singleton.close()


async def test_select_moduli_setup_supera_25_opzioni_cricchetto_noto():
    """
    Cricchetto: costruisce il vero ModuleSelect con tutti i moduli
    REALMENTE registrati (non un elenco finto) e conferma che oggi
    supera il limite di 25 opzioni di Discord — bug reale (#4/#38/#43),
    fix previsto in R5. Se un giorno passa sotto 25, questo test
    fallisce apposta: è il segnale per togliere "setup" dal cricchetto.
    """
    creato_qui = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti, f"Cog falliti nel caricamento: {falliti}"

        from core.premium import registry
        from cogs.utility.setup import ModuleSelect, MAX_SELECT_OPTIONS

        moduli = registry.all_modules()
        modules_with_state = [(m, False) for m in moduli]
        select = ModuleSelect(modules_with_state)

        supera_il_limite = len(select.options) > MAX_SELECT_OPTIONS

        if "setup" in KNOWN_OVERSIZED_SELECTS:
            assert supera_il_limite, (
                "'setup' è nel cricchetto KNOWN_OVERSIZED_SELECTS ma il "
                f"Select ora ha {len(select.options)} opzioni, entro il "
                f"limite di {MAX_SELECT_OPTIONS}: il bug è stato sistemato "
                "— togli 'setup' dal cricchetto in questo file."
            )
        else:
            assert not supera_il_limite, (
                f"Il Select di /setup ha {len(select.options)} opzioni, "
                f"oltre il limite di {MAX_SELECT_OPTIONS}, ma 'setup' non "
                "è (più) nel cricchetto: nuovo problema, o va rimesso lì."
            )
    finally:
        await close_full_bot(bot)
        if creato_qui:
            from core.database import db as db_singleton

            await db_singleton.close()

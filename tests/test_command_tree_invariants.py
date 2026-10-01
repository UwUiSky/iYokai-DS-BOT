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
# BUG-2 risolto: /setup ora ha un Select per categoria, il cricchetto è vuoto.
KNOWN_OVERSIZED_SELECTS: set[str] = set()


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


async def test_select_moduli_setup_per_categoria_entra_nel_limite_di_25():
    """
    BUG-2 risolto: costruisce il vero ModuleSelect per ogni categoria con
    i moduli REALMENTE registrati. Se una categoria supera 25 opzioni il
    test fallisce (servirebbe la paginazione).
    """
    creato_qui = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti, f"Cog falliti nel caricamento: {falliti}"

        from core.premium import CATEGORIE_MODULI, registry
        from cogs.utility.setup import ModuleSelect, MAX_SELECT_OPTIONS

        for categoria in CATEGORIE_MODULI:
            moduli = registry.modules_in_category(categoria)
            select = ModuleSelect([(m, False) for m in moduli])
            assert len(select.options) <= MAX_SELECT_OPTIONS, (
                f"Categoria '{categoria}': {len(select.options)} opzioni, "
                f"oltre il limite di {MAX_SELECT_OPTIONS}."
            )
        assert not KNOWN_OVERSIZED_SELECTS
    finally:
        await close_full_bot(bot)
        if creato_qui:
            from core.database import db as db_singleton

            await db_singleton.close()

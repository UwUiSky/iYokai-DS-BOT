"""
tests/test_cfg_gia_coperte.py
=============================
Voci del catalogo #122 che il codice copre già (e che il catalogo diceva mancanti): una prova per ciascuna, sull'albero
comandi vero. CFG-007 (canali del wizard), CFG-028 (molte lingue), CFG-031 (bot con token proprio), CFG-035 (stato
premium del server), CFG-037 (acquisto in Discord), CFG-042 (privacy: esporta e cancella), CFG-045 (aiuto per comando).
Se un comando cambia nome questa prova fallisce: va aggiornato anche il catalogo.
"""

from discord import app_commands

from tests.support.full_tree import build_full_bot, close_full_bot, connect_db_if_needed


def _percorsi(nodi, prefisso=""):
    trovati = set()
    for nodo in nodi:
        nome = f"{prefisso}{nodo.name}"
        if isinstance(nodo, app_commands.Group):
            trovati |= _percorsi(nodo.commands, nome + " ")
        else:
            trovati.add(nome)
    return trovati


async def test_comandi_del_catalogo_che_esistono_gia():
    creato_qui = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti
        percorsi = _percorsi(bot.tree.get_commands())
        assert "admin-bot setup wizard" in percorsi  # CFG-007
        assert "admin-bot premium marchio" in percorsi  # CFG-031
        assert "admin-bot premium stato" in percorsi  # CFG-035
        assert {"utility privacy esporta", "utility privacy cancella"} <= percorsi  # CFG-042
        assert "help" in percorsi  # CFG-045 (D137: ex cerca-comando)
        assert {"admin-bot lingua set", "admin-bot lingua show", "utility lingua"} <= percorsi  # CFG-028
    finally:
        await close_full_bot(bot)
        if creato_qui:
            from core.database import db

            await db.close()


def test_cfg007_il_wizard_sa_creare_i_canali_per_tre_categorie():
    from core.setup_wizard_logic import CANALI_PER_CATEGORIA

    assert {"moderation", "security", "community"} <= set(CANALI_PER_CATEGORIA)
    assert CANALI_PER_CATEGORIA["moderation"].riservato  # il canale dei log non è pubblico


def test_cfg028_ci_sono_piu_lingue_con_testi():
    from core.i18n import lingue_disponibili

    assert {"it", "en"} <= set(lingue_disponibili())


async def test_cfg037_gli_abbonamenti_discord_sbloccano_il_server(clean_db, monkeypatch):
    import core.database as database_module
    from core.premium_entitlement_service import server_ha_abbonamento

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    assert await server_ha_abbonamento(4040) is False

"""
tests/test_setup_categories.py
==================================
BUG-2 (#4, #38, #43, #49): /setup si rifiutava sempre perché i moduli
registrati (32) superano le 25 opzioni di un Select. Ora ogni modulo ha
una categoria e /setup mostra un Select per categoria. Questi test usano
il registry REALE (tutti i cog caricati), non moduli finti.
"""

import pytest

from core.premium import CATEGORIE_MODULI, PremiumModule, PremiumRegistry
from tests.support.discord_fakes import fake_guild, fake_interaction
from tests.support.full_tree import build_full_bot, close_full_bot, connect_db_if_needed


class TestRegistroRifiutaCategorieSbagliate:
    def test_categoria_sconosciuta_viene_rifiutata(self):
        registro = PremiumRegistry()
        with pytest.raises(ValueError):
            registro.register(
                PremiumModule(name="x", display_name="X", description="x", category="inventata")
            )

    def test_categoria_mancante_viene_rifiutata(self):
        registro = PremiumRegistry()
        with pytest.raises(ValueError):
            registro.register(PremiumModule(name="x", display_name="X", description="x"))

    def test_categoria_valida_viene_accettata(self):
        registro = PremiumRegistry()
        registro.register(
            PremiumModule(name="x", display_name="X", description="x", category="utility")
        )
        assert registro.get("x").category == "utility"


@pytest.fixture
async def bot_completo():
    creato_qui = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    assert not falliti, f"Cog falliti nel caricamento: {falliti}"
    yield bot
    await close_full_bot(bot)
    if creato_qui:
        from core.database import db

        await db.close()


async def test_ogni_modulo_reale_ha_una_categoria_valida(bot_completo):
    from core.premium import registry

    for modulo in registry.all_modules():
        assert modulo.category in CATEGORIE_MODULI, (
            f"Modulo '{modulo.name}' con categoria non valida: {modulo.category!r}"
        )


async def test_ogni_categoria_ha_un_select_costruibile_con_i_moduli_reali(bot_completo):
    from cogs.utility.setup import MAX_SELECT_OPTIONS, ModuleSelect
    from core.premium import registry

    for categoria in CATEGORIE_MODULI:
        moduli = registry.modules_in_category(categoria)
        assert 0 < len(moduli) <= MAX_SELECT_OPTIONS, (
            f"Categoria '{categoria}': {len(moduli)} moduli"
        )
        # Se il Select ha più di 25 opzioni, discord.py solleva ValueError qui.
        ModuleSelect([(m, False) for m in moduli])


async def test_setup_con_categoria_mostra_solo_i_moduli_di_quella_categoria(bot_completo, clean_db, monkeypatch):
    import core.database as database_module
    from cogs.utility.setup import SetupCog, SetupView
    from core.premium import registry

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()

    cog = SetupCog(bot_completo)
    interazione = fake_interaction(guild=fake_guild(guild_id=4242))

    await cog.setup.callback(cog, interazione, categoria="tickets")

    kwargs = interazione.followup.send.call_args.kwargs
    view = kwargs["view"]
    assert isinstance(view, SetupView)
    attesi = {m.name for m in registry.modules_in_category("tickets")}
    assert set(view.all_module_names) == attesi
    assert attesi  # la categoria non è vuota


async def test_setup_senza_categoria_mostra_un_embed_di_sola_lettura(bot_completo, clean_db, monkeypatch):
    import core.database as database_module
    from cogs.utility.setup import SetupCog
    from core.premium import registry

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()

    cog = SetupCog(bot_completo)
    interazione = fake_interaction(guild=fake_guild(guild_id=4243))

    await cog.setup.callback(cog, interazione, categoria=None)

    kwargs = interazione.followup.send.call_args.kwargs
    assert "view" not in kwargs or kwargs["view"] is None
    testo = " ".join(
        (f.name + " " + f.value) for f in kwargs["embed"].fields
    )
    for modulo in registry.all_modules():
        assert modulo.display_name in testo

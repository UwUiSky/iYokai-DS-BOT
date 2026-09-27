"""
tests/test_setup_wizard.py
==============================
Test di SetupWizardView (SPEC.md §2.2) — stesso schema di
tests/test_setup_cog.py: simulazione dei click sui bottoni con
un'Interaction finta, verifica del salvataggio reale sul database.
"""

import discord

from core.database import Database
from core.premium import PremiumModule
from cogs.utility.setup import SetupWizardView


class _FakeResponse:
    def __init__(self) -> None:
        self.edited_embed = "non toccato"
        self.edited_view = "non toccato"
        self.edited_content: str | None = None

    async def edit_message(self, content: str | None = None, embed=None, view=None) -> None:
        self.edited_content = content
        self.edited_embed = embed
        self.edited_view = view


class _FakeUser:
    id = 999


class _FakeInteraction:
    def __init__(self) -> None:
        self.response = _FakeResponse()
        self.user = _FakeUser()


def _modules_with_state() -> list[tuple[PremiumModule, bool]]:
    a = PremiumModule(name="wiz_a", display_name="A", description="Modulo A")
    b = PremiumModule(name="wiz_b", display_name="B", description="Modulo B")
    return [(a, True), (b, False)]


class TestNavigazione:
    def test_step_iniziale_e_zero(self):
        view = SetupWizardView(guild_id=1, modules_with_state=_modules_with_state())
        assert view.step == 0
        assert view.previous_button.disabled is True
        assert view.next_button.label == "Avanti"

    async def test_avanti_passa_al_secondo_step(self):
        view = SetupWizardView(guild_id=1, modules_with_state=_modules_with_state())
        await view.next_button.callback(_FakeInteraction())
        assert view.step == 1
        # Ultimo step: "Avanti" diventa "Salva".
        assert view.next_button.label == "Salva"
        assert view.previous_button.disabled is False

    async def test_indietro_torna_al_primo_step(self):
        view = SetupWizardView(guild_id=1, modules_with_state=_modules_with_state())
        await view.next_button.callback(_FakeInteraction())
        await view.previous_button.callback(_FakeInteraction())
        assert view.step == 0
        assert view.previous_button.disabled is True

    async def test_toggle_inverte_lo_stato_dello_step_corrente(self):
        view = SetupWizardView(guild_id=1, modules_with_state=_modules_with_state())
        modulo_a_name = _modules_with_state()[0][0].name
        assert view.selected[modulo_a_name] is True

        await view.toggle_button.callback(_FakeInteraction())

        assert view.selected[modulo_a_name] is False
        assert view.toggle_button.label == "Attiva"


async def test_salvataggio_persiste_solo_i_moduli_effettivamente_cambiati():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 555555560
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = $1", guild_id
        )
        await database.ensure_guild_exists(guild_id)
        await database.set_module_active_for_guild(guild_id, "wiz_a", True)
        await database.set_module_active_for_guild(guild_id, "wiz_b", False)

        import cogs.utility.setup as setup_module
        original_db = setup_module.db
        setup_module.db = database
        try:
            view = SetupWizardView(guild_id, _modules_with_state())
            # Step 0 ("wiz_a"): disattiva. Poi avanti, step 1 ("wiz_b"): attiva. Poi Salva.
            await view.toggle_button.callback(_FakeInteraction())
            await view.next_button.callback(_FakeInteraction())
            await view.toggle_button.callback(_FakeInteraction())
            await view.next_button.callback(_FakeInteraction())  # ultimo step -> salva

            assert await database.is_module_active_for_guild(guild_id, "wiz_a") is False
            assert await database.is_module_active_for_guild(guild_id, "wiz_b") is True
        finally:
            setup_module.db = original_db
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 555555560")
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = 555555560"
        )
        await database.close()

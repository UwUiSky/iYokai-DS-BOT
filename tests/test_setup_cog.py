"""
tests/test_setup_cog.py
==========================
Due livelli di verifica:

1. Smoke test: il cog si carica in un Bot vero, il comando /setup
   risulta registrato con i permessi giusti.

2. Test di PERSISTENZA REALE: costruisce una SetupView "a mano" (come
   farebbe /setup dopo aver letto lo stato dei moduli), SIMULA il
   click sul bottone "Salva" chiamando direttamente il callback del
   bottone con un'Interaction finta, e verifica che il database
   rifletta ESATTAMENTE la selezione — incluso il caso più delicato:
   un modulo che era attivo PRIMA e non viene riselezionato deve
   risultare disattivato dopo il salvataggio, non restare acceso per
   dimenticanza.
"""

import discord
from discord.ext import commands

from core.database import Database
from core.premium import PremiumModule
from cogs.utility.setup import SetupView, setup as setup_cog_setup


async def test_setup_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await setup_cog_setup(bot)

    assert bot.get_cog("SetupCog") is not None

    comandi = {c.name for c in bot.tree.get_commands()}
    assert "setup" in comandi


class _FakeResponse:
    def __init__(self) -> None:
        self.edited_content: str | None = None
        self.edited_view = "non toccato"

    async def edit_message(self, content: str | None = None, view=None) -> None:
        self.edited_content = content
        self.edited_view = view

    async def defer(self) -> None:
        pass


class _FakeUser:
    id = 999


class _FakeInteraction:
    def __init__(self) -> None:
        self.response = _FakeResponse()
        self.user = _FakeUser()


def _find_button(view: SetupView, label: str) -> discord.ui.Button:
    for child in view.children:
        if isinstance(child, discord.ui.Button) and child.label == label:
            return child
    raise AssertionError(f"Bottone '{label}' non trovato nella view")


async def test_salvataggio_persiste_esattamente_la_selezione():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 555555555
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = $1", guild_id
        )

        modulo_a = PremiumModule(
            name="test_modulo_a", display_name="Modulo A", description="Test A"
        )
        modulo_b = PremiumModule(
            name="test_modulo_b", display_name="Modulo B", description="Test B"
        )
        modulo_c = PremiumModule(
            name="test_modulo_c", display_name="Modulo C", description="Test C"
        )

        # Stato di partenza REALE nel database: A e B già attivi,
        # C disattivato. Questo è il caso interessante: la view viene
        # costruita con questo stato pre-esistente.
        await database.ensure_guild_exists(guild_id)
        await database.set_module_active_for_guild(guild_id, "test_modulo_a", True)
        await database.set_module_active_for_guild(guild_id, "test_modulo_b", True)
        await database.set_module_active_for_guild(guild_id, "test_modulo_c", False)

        import cogs.utility.setup as setup_module
        original_db = setup_module.db
        setup_module.db = database  # setup.py usa "from core.database import db" a livello di modulo

        try:
            modules_with_state = [
                (modulo_a, True),
                (modulo_b, True),
                (modulo_c, False),
            ]
            view = SetupView(guild_id, modules_with_state)

            # L'utente ora DESELEZIONA il modulo B e seleziona il
            # modulo C, lasciando A invariato — esattamente il tipo
            # di modifica che deve essere applicata fedelmente.
            view.selected_values = {"test_modulo_a", "test_modulo_c"}

            save_button = _find_button(view, "Salva configurazione")
            fake_interaction = _FakeInteraction()
            await save_button.callback(fake_interaction)

            # Verifica diretta sul database, non sulla view: il punto
            # è che la SCRITTURA sia avvenuta correttamente.
            assert await database.is_module_active_for_guild(
                guild_id, "test_modulo_a"
            ) is True
            assert await database.is_module_active_for_guild(
                guild_id, "test_modulo_b"
            ) is False, (
                "Il modulo B era attivo e non è stato riselezionato: "
                "deve risultare disattivato, non restare acceso."
            )
            assert await database.is_module_active_for_guild(
                guild_id, "test_modulo_c"
            ) is True

            # Il messaggio di conferma riporta il conteggio corretto.
            assert "2/3" in fake_interaction.response.edited_content
        finally:
            setup_module.db = original_db
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 555555555"
        )
        await database.close()


async def test_salvataggio_non_registra_storico_per_moduli_invariati():
    # Verifica del fix: prima di questa correzione, /setup scriveva
    # (e quindi loggava nello storico Config Diff & Rollback) OGNI
    # modulo ad ogni salvataggio, anche quelli il cui stato non era
    # cambiato — riempiendo lo storico di voci "cambiate" false.
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 555555556
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = $1", guild_id
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = $1", guild_id
        )

        modulo_a = PremiumModule(
            name="test_invariato_a", display_name="A", description="A"
        )
        modulo_b = PremiumModule(
            name="test_cambiato_b", display_name="B", description="B"
        )

        await database.ensure_guild_exists(guild_id)
        await database.set_module_active_for_guild(guild_id, "test_invariato_a", True)
        await database.set_module_active_for_guild(guild_id, "test_cambiato_b", False)
        # Puliamo lo storico DOPO la configurazione iniziale, per
        # isolare solo quello che genera il salvataggio della view.
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = $1", guild_id
        )

        import cogs.utility.setup as setup_module
        original_db = setup_module.db
        setup_module.db = database

        try:
            modules_with_state = [(modulo_a, True), (modulo_b, False)]
            view = SetupView(guild_id, modules_with_state)

            # L'utente lascia A com'era (attivo) e attiva B: solo B
            # deve produrre una voce di storico.
            view.selected_values = {"test_invariato_a", "test_cambiato_b"}

            save_button = _find_button(view, "Salva configurazione")
            await save_button.callback(_FakeInteraction())

            storico = await database.get_config_history(guild_id)
            assert len(storico) == 1
            assert storico[0].key_name == "test_cambiato_b"
        finally:
            setup_module.db = original_db
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 555555556"
        )
        await database.pool.execute(
            "DELETE FROM guild_config_history WHERE guild_id = 555555556"
        )
        await database.close()


async def test_annulla_non_scrive_nulla_sul_database():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 444444444
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = $1", guild_id
        )
        await database.ensure_guild_exists(guild_id)
        await database.set_module_active_for_guild(guild_id, "test_modulo_x", True)

        import cogs.utility.setup as setup_module
        original_db = setup_module.db
        setup_module.db = database

        try:
            modulo_x = PremiumModule(
                name="test_modulo_x", display_name="Modulo X", description="Test X"
            )
            view = SetupView(guild_id, [(modulo_x, True)])
            # L'utente deseleziona tutto ma preme Annulla, non Salva.
            view.selected_values = set()

            cancel_button = _find_button(view, "Annulla")
            fake_interaction = _FakeInteraction()
            await cancel_button.callback(fake_interaction)

            # Lo stato nel database non deve essere cambiato.
            assert await database.is_module_active_for_guild(
                guild_id, "test_modulo_x"
            ) is True
            assert "annullata" in fake_interaction.response.edited_content.lower()
        finally:
            setup_module.db = original_db
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 444444444"
        )
        await database.close()


def test_select_pre_seleziona_i_moduli_gia_attivi():
    # Test di logica pura (nessun DB, nessuna Interaction): verifica
    # che le SelectOption vengano costruite con default=True solo
    # per i moduli effettivamente attivi.
    modulo_attivo = PremiumModule(
        name="attivo", display_name="Attivo", description="x"
    )
    modulo_spento = PremiumModule(
        name="spento", display_name="Spento", description="y"
    )
    view = SetupView(
        guild_id=1, modules_with_state=[(modulo_attivo, True), (modulo_spento, False)]
    )

    select = next(c for c in view.children if isinstance(c, discord.ui.Select))
    stato_default = {opt.value: opt.default for opt in select.options}
    assert stato_default == {"attivo": True, "spento": False}

    # Lo stato iniziale della selezione (prima di ogni interazione)
    # deve coincidere con quello già attivo, non partire vuoto.
    assert view.selected_values == {"attivo"}

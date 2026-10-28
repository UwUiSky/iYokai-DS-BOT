"""
tests/test_setup_wizard.py
==========================
Il wizard di `/admin setup wizard` (SPEC §2.2, M 10.14, #148): un passo per i ruoli del bot,
un passo per ogni categoria di moduli, i ruoli salvati subito, i moduli alla fine.
Click simulati con un'Interaction finta fedele; salvataggio vero sul database.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

import core.config_schema as config_schema_module
from cogs.utility._setup_wizard_views import SelezioneModuli, SelezioneRuolo
from cogs.utility.setup import ETICHETTE_CATEGORIE, SetupWizardView
from core.command_access import RuoloAdminNegato, TipoRuolo
from core.database import Database
from core.premium import CATEGORIE_MODULI, PremiumModule
from core.setup_wizard_logic import costruisci_passi
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role


@pytest.fixture(autouse=True)
def _moduli_registrati(reset_premium_registry):
    """`imposta_modulo` (D16) accetta solo moduli registrati: qui quelli finti del test."""
    from core.premium import registry

    for nome in ("wiz_a", "wiz_b", "wiz_c"):
        registry.register(PremiumModule(category="utility", name=nome, display_name=nome, description=nome))
    registry.register(PremiumModule(category="logging", name="wiz_log", display_name="L", description="log"))


def _vista(guild_id=555555560, ruoli=None):
    moduli = {
        "wiz_a": PremiumModule(category="utility", name="wiz_a", display_name="A", description="Modulo A"),
        "wiz_b": PremiumModule(category="utility", name="wiz_b", display_name="B", description="Modulo B"),
        "wiz_log": PremiumModule(category="logging", name="wiz_log", display_name="L", description="log"),
    }
    passi = costruisci_passi(
        {"utility": ["wiz_a", "wiz_b"], "logging": ["wiz_log"]}, tuple(ETICHETTE_CATEGORIE)
    )
    stato = {"wiz_a": True, "wiz_b": False, "wiz_log": False}
    return SetupWizardView(guild_id, passi, moduli, stato, ruoli or {}, ETICHETTE_CATEGORIE)


def _clic():
    interazione = fake_interaction(guild=fake_guild(555555560), user=fake_member(user_id=999))
    interazione.client = MagicMock()
    return interazione


def _bottone(vista, etichetta):
    return next(c for c in vista.children if getattr(c, "label", None) == etichetta)


def test_le_etichette_coprono_tutte_le_categorie_dei_moduli():
    assert set(ETICHETTE_CATEGORIE) == set(CATEGORIE_MODULI)


def test_il_primo_passo_sono_i_ruoli_con_tre_menu_e_i_bottoni():
    vista = _vista()
    assert vista.passo.tipo == "ruoli"
    menu = [c for c in vista.children if isinstance(c, SelezioneRuolo)]
    assert {m.tipo for m in menu} == set(TipoRuolo)
    assert _bottone(vista, "Indietro").disabled is True
    assert "Passo 1/3" in vista.embed().title


async def test_avanti_e_indietro_cambiano_passo_e_bottoni():
    vista = _vista()
    interazione = _clic()
    await vista._avanti(interazione)
    assert vista.step == 1 and "Log" in vista.embed().title
    assert any(isinstance(c, SelezioneModuli) for c in vista.children)
    assert _bottone(vista, "Avanti").label == "Avanti"
    await vista._avanti(interazione)  # passo di Utility: ultimo
    assert _bottone(vista, "Salva")
    await vista._indietro(interazione)
    assert vista.step == 1


async def test_la_scelta_nel_menu_resta_nella_vista_fino_a_salva():
    vista = _vista()
    vista.step = 2  # passo di Utility
    vista.ricostruisci()
    menu = next(c for c in vista.children if isinstance(c, SelezioneModuli))
    menu._values = ["wiz_b"]  # A deselezionato, B scelto
    await menu.callback(_clic())
    assert vista.scelti == {"wiz_a": False, "wiz_b": True, "wiz_log": False}
    assert vista.iniziale["wiz_a"] is True


async def test_il_ruolo_scelto_si_salva_subito_con_il_punto_unico():
    ruolo = fake_role(4242)
    guild = fake_guild(555555560)
    guild.get_role = MagicMock(return_value=ruolo)
    vista = _vista()
    menu = next(c for c in vista.children if isinstance(c, SelezioneRuolo) and c.tipo is TipoRuolo.MOD)
    menu._values = [ruolo]
    interazione = fake_interaction(guild=guild, user=fake_member(user_id=999))
    with patch("cogs.utility._setup_wizard_views.imposta_ruolo", AsyncMock()) as salva:
        await menu.callback(interazione)
    args = salva.await_args
    assert args.args[:3] == (guild, TipoRuolo.MOD, ruolo) and args.args[3] == 999
    assert vista.ruoli[TipoRuolo.MOD] is ruolo
    interazione.response.edit_message.assert_awaited_once()


async def test_ruolo_admin_negato_non_si_salva_e_lo_dice():
    ruolo = fake_role(4243)
    guild = fake_guild(555555560)
    guild.get_role = MagicMock(return_value=ruolo)
    vista = _vista()
    menu = next(c for c in vista.children if isinstance(c, SelezioneRuolo) and c.tipo is TipoRuolo.ADMIN)
    menu._values = [ruolo]
    interazione = fake_interaction(guild=guild, user=fake_member(user_id=999))
    with patch("cogs.utility._setup_wizard_views.imposta_ruolo", AsyncMock(side_effect=RuoloAdminNegato())):
        await menu.callback(interazione)
    assert vista.ruoli.get(TipoRuolo.ADMIN) is None
    assert "Amministratore" in interazione.followup.send.await_args.args[0]


async def test_il_passo_dei_log_offre_di_creare_i_canali_con_lo_stesso_comando():
    vista = _vista()
    vista.step = 1  # passo «Log»
    vista.ricostruisci()
    interazione = _clic()
    cog = MagicMock()
    cog.crea_canali.callback = AsyncMock()
    interazione.client.get_cog = MagicMock(return_value=cog)
    await _bottone(vista, "Crea i canali dei log").callback(interazione)
    cog.crea_canali.callback.assert_awaited_once_with(cog, interazione)


async def test_senza_il_cog_dei_log_il_bottone_manda_al_comando():
    vista = _vista()
    vista.step = 1
    vista.ricostruisci()
    interazione = _clic()
    interazione.client.get_cog = MagicMock(return_value=None)
    await _bottone(vista, "Crea i canali dei log").callback(interazione)
    assert "/log crea-canali" in interazione.response.send_message.await_args.args[0]


async def test_gli_altri_passi_non_hanno_il_bottone_dei_canali():
    vista = _vista()
    vista.step = 2
    vista.ricostruisci()
    assert not any(getattr(c, "label", "") == "Crea i canali dei log" for c in vista.children)


async def test_annulla_non_scrive_i_moduli():
    vista = _vista()
    vista.scelti["wiz_b"] = True
    with patch("cogs.utility._setup_wizard_views.imposta_modulo", AsyncMock()) as scrive:
        await _bottone(vista, "Annulla").callback(_clic())
    scrive.assert_not_awaited()


async def test_salvataggio_persiste_solo_i_moduli_effettivamente_cambiati():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 555555560
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
        await database.pool.execute("DELETE FROM guild_config_history WHERE guild_id = $1", guild_id)
        await database.ensure_guild_exists(guild_id)
        await database.set_module_active_for_guild(guild_id, "wiz_a", True)
        await database.set_module_active_for_guild(guild_id, "wiz_b", False)
        original_db = config_schema_module.db
        config_schema_module.db = database
        try:
            vista = _vista(guild_id)
            vista.scelti["wiz_a"] = False
            vista.scelti["wiz_b"] = True
            vista.step = len(vista.passi) - 1
            vista.ricostruisci()
            await _bottone(vista, "Salva").callback(_clic())
            assert await database.is_module_active_for_guild(guild_id, "wiz_a") is False
            assert await database.is_module_active_for_guild(guild_id, "wiz_b") is True
            chiavi = await database.pool.fetch(
                "SELECT DISTINCT key_name FROM guild_config_history WHERE guild_id = $1 AND changed_by = 999",
                guild_id,
            )
            assert {r["key_name"] for r in chiavi} == {"wiz_a", "wiz_b"}  # non wiz_log: non è cambiato
        finally:
            config_schema_module.db = original_db
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 555555560")
        await database.pool.execute("DELETE FROM guild_config_history WHERE guild_id = 555555560")
        await database.close()


async def test_il_comando_wizard_apre_ruoli_e_una_categoria_per_passo():
    import cogs.utility.setup as setup_module
    import core.command_access as command_access
    from core.premium import registry

    # Solo i moduli finti del test: i cog importati da altri test ne registrano di veri
    # (il fixture `reset_premium_registry` rimette tutto a posto dopo).
    registry._modules = {nome: m for nome, m in registry._modules.items() if nome.startswith("wiz_")}

    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 555555561
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
        vecchi = (setup_module.db, command_access.db)
        setup_module.db = command_access.db = database
        try:
            ruolo = fake_role(777)
            guild = fake_guild(guild_id)
            guild.get_role = MagicMock(return_value=ruolo)
            await database.ensure_guild_exists(guild_id)
            await database.set_guild_setting(guild_id, "mod_role_id", 777, 1)
            interazione = fake_interaction(guild=guild, user=fake_member(user_id=999))
            interazione.original_response = AsyncMock(return_value=MagicMock())
            cog = setup_module.SetupCog(MagicMock())
            with patch.object(setup_module, "lingua_interazione", AsyncMock(return_value="en")):
                await cog.setup_wizard.callback(cog, interazione)
            vista = interazione.response.send_message.await_args.kwargs["view"]
            # menu e bottoni nella lingua di chi usa il comando, non solo l'embed
            assert vista.children[0].placeholder == "Bot admin role"
            assert "Next" in [getattr(c, "label", None) for c in vista.children]
            categorie = [p.categoria for p in vista.passi if p.tipo == "moduli"]
            assert categorie == ["logging", "utility"]  # solo le categorie con moduli registrati
            assert vista.ruoli[TipoRuolo.MOD] is ruolo and vista.ruoli[TipoRuolo.ADMIN] is None
            assert vista.iniziale == {"wiz_a": False, "wiz_b": False, "wiz_c": False, "wiz_log": False}
        finally:
            setup_module.db, command_access.db = vecchi
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 555555561")
        await database.close()


# ---- 22.16: un canale per categoria, creato e collegato ----
def _vista_con(categoria, nomi=("wiz_a",)):
    moduli = {n: PremiumModule(category=categoria, name=n, display_name=n, description=n) for n in nomi}
    passi = costruisci_passi({categoria: list(nomi)}, tuple(ETICHETTE_CATEGORIE))
    vista = SetupWizardView(555555560, passi, moduli, {n: False for n in nomi}, {}, ETICHETTE_CATEGORIE)
    vista.step = 1
    vista.ricostruisci()
    return vista


@pytest.mark.parametrize(
    "categoria, etichetta",
    [("moderation", "Crea il canale mod-log"), ("security", "Crea il canale allarmi-sicurezza"),
     ("community", "Crea il canale benvenuto")],
)
def test_le_categorie_con_un_canale_hanno_il_bottone(categoria, etichetta):
    assert _bottone(_vista_con(categoria), etichetta)


def test_le_altre_categorie_non_hanno_il_bottone_del_canale():
    vista = _vista_con("fun")
    assert not any(str(getattr(c, "label", "")).startswith("Crea il canale") for c in vista.children)


def _server_per_canali(guild_id):
    server = fake_guild(guild_id)
    server.me.guild_permissions = discord.Permissions(manage_channels=True, view_channel=True, send_messages=True)
    server.channels = []
    nuovo = MagicMock()
    nuovo.id = 7777
    nuovo.mention = "<#7777>"
    server.create_text_channel = AsyncMock(return_value=nuovo)
    return server


async def test_il_canale_modlog_si_crea_riservato_e_si_collega(clean_db, monkeypatch):
    from core.database import db

    monkeypatch.setattr(db, "_pool", clean_db)
    server = _server_per_canali(555555561)
    interazione = _clic()
    interazione.guild = server
    await _bottone(_vista_con("moderation"), "Crea il canale mod-log").callback(interazione)

    kw = server.create_text_channel.await_args
    assert kw.args[0] == "mod-log" and kw.kwargs["overwrites"]  # riservato: ci sono regole
    assert await db.get_guild_setting(555555561, "mod_log_channel_id") == 7777
    assert "<#7777>" in interazione.followup.send.await_args.args[0]


async def test_il_canale_degli_allarmi_va_nel_router(clean_db, monkeypatch):
    from core.database import db
    from core.repositories.output_channel_repo import output_channel_repo

    monkeypatch.setattr(db, "_pool", clean_db)
    server = _server_per_canali(555555562)
    interazione = _clic()
    interazione.guild = server
    await _bottone(_vista_con("security"), "Crea il canale allarmi-sicurezza").callback(interazione)
    riga = await output_channel_repo.ottieni(555555562, "allarmi")
    assert riga is not None and riga.channel_id == 7777


async def test_il_canale_benvenuto_e_pubblico_e_non_accende_il_modulo(clean_db, monkeypatch):
    from core.database import db
    from core.repositories.greetings_repo import greetings_repo

    monkeypatch.setattr(db, "_pool", clean_db)
    server = _server_per_canali(555555563)
    interazione = _clic()
    interazione.guild = server
    await _bottone(_vista_con("community"), "Crea il canale benvenuto").callback(interazione)

    assert server.create_text_channel.await_args.kwargs["overwrites"] == {}
    config = await greetings_repo.get_config(555555563)
    assert config.welcome_channel_id == 7777 and config.welcome_enabled is False


async def test_senza_permessi_o_senza_posto_il_canale_non_si_crea():
    server = _server_per_canali(555555564)
    server.me.guild_permissions = discord.Permissions.none()
    interazione = _clic()
    interazione.guild = server
    await _bottone(_vista_con("moderation"), "Crea il canale mod-log").callback(interazione)
    server.create_text_channel.assert_not_awaited()
    assert "manage_channels" in interazione.followup.send.await_args.args[0]

    server2 = _server_per_canali(555555565)
    server2.channels = [MagicMock()] * 500
    interazione2 = _clic()
    interazione2.guild = server2
    await _bottone(_vista_con("moderation"), "Crea il canale mod-log").callback(interazione2)
    server2.create_text_channel.assert_not_awaited()

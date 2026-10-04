"""
tests/test_config_rollback_bug6.py
=====================================
BUG-6: /config rollback riportava "✅" senza ripristinare niente per
reset e import (scriveva una setting spazzatura), non cambiava la lingua,
e trasformava in `null` una setting appena creata. Usa il database reale.
"""

import json

import pytest

from core.database import db

GUILD = 777000601


@pytest.fixture(autouse=True)
def _pool(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    return clean_db


async def _ultima_voce():
    return (await db.get_config_history(GUILD, limit=1))[0]


@pytest.mark.asyncio
async def test_rollback_di_un_reset_ripristina_tutta_la_configurazione():
    await db.set_module_active_for_guild(GUILD, "tickets", True)
    await db.set_guild_setting(GUILD, "report_channel_id", 55)
    await db.set_guild_language(GUILD, "en")

    await db.reset_guild_config(GUILD, changed_by=1)
    assert await db.get_guild_setting(GUILD, "report_channel_id") is None

    assert await db.rollback_config_change((await _ultima_voce()).id, rolled_back_by=1) is True

    completa = await db.get_full_config(GUILD)
    assert completa["modules"] == {"tickets": True}
    assert completa["settings"] == {"report_channel_id": 55}
    assert completa["language"] == "en"
    assert "guild_config" not in completa["settings"]


@pytest.mark.asyncio
async def test_rollback_di_un_import_ripristina_la_configurazione_precedente():
    await db.set_module_active_for_guild(GUILD, "tickets", True)
    await db.import_full_config(
        GUILD, modules={"poll": True}, settings={"x": 1}, language="en", changed_by=1
    )

    assert await db.rollback_config_change((await _ultima_voce()).id, rolled_back_by=1) is True

    completa = await db.get_full_config(GUILD)
    assert completa["modules"] == {"tickets": True}
    assert completa["settings"] == {}
    assert completa["language"] == "it"


@pytest.mark.asyncio
async def test_rollback_della_lingua_cambia_la_colonna_language():
    await db.set_guild_language(GUILD, "en")

    assert await db.rollback_config_change((await _ultima_voce()).id, rolled_back_by=1) is True

    assert await db.get_guild_language(GUILD) == "it"
    assert await db.get_guild_setting(GUILD, "language") is None  # niente setting spazzatura


@pytest.mark.asyncio
async def test_rollback_di_una_setting_nuova_la_rimuove_invece_di_metterla_a_null():
    await db.set_guild_setting(GUILD, "ticket_support_role_id", 99)

    assert await db.rollback_config_change((await _ultima_voce()).id, rolled_back_by=1) is True

    chiavi = await db.pool.fetchval(
        "SELECT settings::text FROM guild_config WHERE guild_id = $1", GUILD
    )
    assert "ticket_support_role_id" not in json.loads(chiavi)


@pytest.mark.asyncio
async def test_rollback_non_ripristinabile_restituisce_false_non_successo():
    await db.ensure_guild_exists(GUILD)
    # Voce di reset con un valore "prima" che non è una configurazione.
    await db._record_config_change(GUILD, 1, "reset", "guild_config", "spazzatura", {})

    assert await db.rollback_config_change((await _ultima_voce()).id, rolled_back_by=1) is False


# ---------------------------------------------------------------------------
# BUG-32: i comandi veri e il bottone di conferma, con il registry reale.
# La conferma di un import superava i 2000 caratteri (il bottone non
# compariva mai) e /config history superava i 4096 dell'embed.
# ---------------------------------------------------------------------------

LIMITE_MESSAGGIO = 2000
LIMITE_DESCRIZIONE_EMBED = 4096
ADMIN_ID = 4242

SETTINGS_PIENE = {
    "log_channel_id": 111111111111111111,
    "mod_log_channel_id": 222222222222222222,
    "ticket_support_role_ids": list(range(10**17, 10**17 + 250)),
    "spam_trap_staff_role_ids": list(range(2 * 10**17, 2 * 10**17 + 250)),
    "backup_restore_mode": "classic_invite",
    "logging_soundboard_watermark": "2026-10-01T12:00:00+00:00",
}


@pytest.fixture
async def cog_con_registry_vero():
    """Il cog vero dentro un bot con TUTTI i cog caricati (32 moduli registrati)."""
    from core.premium import registry
    from tests.support.full_tree import build_full_bot, close_full_bot

    bot, falliti = await build_full_bot()
    assert not falliti
    assert len(registry.all_modules()) >= 32
    yield bot.get_cog("ConfigHistoryCog")
    await close_full_bot(bot)


def _interazione(user_id: int = ADMIN_ID):
    from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

    return fake_interaction(guild=fake_guild(guild_id=GUILD), user=fake_member(user_id=user_id))


async def _configura_tutto() -> dict:
    """Tutti i moduli reali attivi e settings voluminose, scritti dai metodi veri."""
    from core.premium import registry

    for modulo in registry.all_modules():
        await db.set_module_active_for_guild(GUILD, modulo.name, True, changed_by=ADMIN_ID)
    for chiave, valore in SETTINGS_PIENE.items():
        await db.set_guild_setting(GUILD, chiave, valore, changed_by=ADMIN_ID)
    return await db.get_full_config(GUILD)


class _FileFinto:
    def __init__(self, contenuto: bytes) -> None:
        self._contenuto, self.size = contenuto, len(contenuto)

    async def read(self) -> bytes:
        return self._contenuto


async def _importa_configurazione_vuota(cog) -> None:
    """Il comando vero: è lui a scrivere la voce `import` nello storico."""
    interazione = _interazione()
    vuota = json.dumps({"modules": {}, "settings": {}, "language": "en"}).encode()
    await cog.import_config.callback(cog, interazione, _FileFinto(vuota))
    assert "✅" in interazione.response.send_message.call_args.args[0]


async def _chiedi_rollback(cog, entry_id: int, user_id: int = ADMIN_ID):
    interazione = _interazione(user_id)
    await cog.rollback.callback(cog, interazione, entry_id)
    chiamata = interazione.response.send_message.call_args
    return chiamata.args[0], chiamata.kwargs.get("view")


async def test_conferma_del_rollback_di_un_import_sta_nel_limite_e_ha_il_bottone(
    cog_con_registry_vero,
):
    from cogs.utility.config_history import RollbackConfirmView

    cog = cog_con_registry_vero
    prima = await _configura_tutto()
    await _importa_configurazione_vuota(cog)

    testo, view = await _chiedi_rollback(cog, (await _ultima_voce()).id)

    assert len(testo) <= LIMITE_MESSAGGIO
    assert isinstance(view, RollbackConfirmView)
    assert f"{len(prima['modules'])} moduli" in testo  # riassunto, non l'elenco intero
    assert f"{len(SETTINGS_PIENE)} impostazioni" in testo
    view.stop()


async def test_bottone_di_conferma_ripristina_davvero_la_configurazione(cog_con_registry_vero):
    cog = cog_con_registry_vero
    prima = await _configura_tutto()
    await _importa_configurazione_vuota(cog)
    assert (await db.get_full_config(GUILD))["modules"] == {}
    _, view = await _chiedi_rollback(cog, (await _ultima_voce()).id)

    click = _interazione()
    await view.confirm.callback(click)

    assert await db.get_full_config(GUILD) == prima
    risposta = click.response.edit_message.call_args.kwargs
    assert risposta["content"].startswith("✅")
    assert all(bottone.disabled for bottone in view.children)


async def test_bottone_di_conferma_premuto_da_un_altro_utente_non_fa_nulla(
    cog_con_registry_vero,
):
    cog = cog_con_registry_vero
    await _configura_tutto()
    await _importa_configurazione_vuota(cog)
    _, view = await _chiedi_rollback(cog, (await _ultima_voce()).id)

    click = _interazione(user_id=999)
    await view.confirm.callback(click)

    assert (await db.get_full_config(GUILD))["modules"] == {}  # niente rollback
    assert click.response.send_message.call_args.kwargs["ephemeral"] is True
    click.response.edit_message.assert_not_awaited()
    view.stop()


async def test_bottone_di_conferma_su_una_voce_non_ripristinabile_dice_errore(
    cog_con_registry_vero,
):
    cog = cog_con_registry_vero
    await db.ensure_guild_exists(GUILD)
    await db._record_config_change(GUILD, 1, "reset", "guild_config", "spazzatura", {})
    testo, view = await _chiedi_rollback(cog, (await _ultima_voce()).id)
    assert len(testo) <= LIMITE_MESSAGGIO

    click = _interazione()
    await view.confirm.callback(click)

    assert click.response.edit_message.call_args.kwargs["content"].startswith("❌")


async def test_conferma_del_rollback_di_una_setting_enorme_sta_nel_limite(cog_con_registry_vero):
    cog = cog_con_registry_vero
    await _configura_tutto()
    await db.set_guild_setting(GUILD, "ticket_support_role_ids", [], changed_by=ADMIN_ID)

    testo, view = await _chiedi_rollback(cog, (await _ultima_voce()).id)

    assert len(testo) <= LIMITE_MESSAGGIO
    assert "ticket_support_role_ids" in testo
    view.stop()


async def test_history_con_25_voci_voluminose_sta_nel_limite_dell_embed(cog_con_registry_vero):
    cog = cog_con_registry_vero
    await _configura_tutto()
    # 25 voci grandi: import e reset alternati, più due liste da 250 ID.
    for _ in range(11):
        await _importa_configurazione_vuota(cog)
        await db.rollback_config_change((await _ultima_voce()).id, rolled_back_by=ADMIN_ID)
    await db.reset_guild_config(GUILD, changed_by=ADMIN_ID)
    await db.rollback_config_change((await _ultima_voce()).id, rolled_back_by=ADMIN_ID)
    await db.set_guild_setting(GUILD, "ticket_support_role_ids", [], changed_by=ADMIN_ID)

    interazione = _interazione()
    await cog.history.callback(cog, interazione, 25)

    embed = interazione.response.send_message.call_args.kwargs["embed"]
    assert len(embed.description) <= LIMITE_DESCRIZIONE_EMBED
    assert len(embed) <= 6000
    assert f"`#{(await _ultima_voce()).id}`" in embed.description  # la più recente c'è


async def test_history_normale_mostra_tutte_le_voci_richieste(cog_con_registry_vero):
    cog = cog_con_registry_vero
    await db.set_guild_setting(GUILD, "report_channel_id", 55, changed_by=ADMIN_ID)
    await db.set_module_active_for_guild(GUILD, "tickets", True, changed_by=ADMIN_ID)

    interazione = _interazione()
    await cog.history.callback(cog, interazione, 10)

    descrizione = interazione.response.send_message.call_args.kwargs["embed"].description
    assert descrizione.count("\n") == 1  # due voci, due righe
    assert "`report_channel_id`" in descrizione and "`55`" in descrizione
    assert "`tickets`" in descrizione and "`True`" in descrizione

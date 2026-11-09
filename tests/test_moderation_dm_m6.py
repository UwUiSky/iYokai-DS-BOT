"""
tests/test_moderation_dm_m6.py
==============================
M6 (#115): un solo punto per il DM delle sanzioni (core/moderation_dm.py). Moderatore nascosto (MOD-050) e testo
del server per azione con segnaposto (MOD-059); log e casi tengono il nome. Database vero.
"""

from unittest.mock import AsyncMock

import discord
import pytest

from cogs.moderation._shared import MODULE_ACTIONS, MODULE_CASE_SYSTEM, SETTING_MOD_LOG_CHANNEL
from cogs.moderation.actions import ModerationActionsCog
from cogs.moderation.opzioni import ModuloTestoDm, OpzioniModerazioneCog
from core import moderation_dm, moderation_opzioni
from core.database import db
from tests.support.discord_fakes import fake_guild
from tests.test_moderation_ordine_azione import ID_BERSAGLIO, ID_CANALE_LOG, ID_MODERATORE, ID_SERVER, Scena

G = ID_SERVER


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(G, MODULE_ACTIONS, True)
    await db.set_module_active_for_guild(G, MODULE_CASE_SYSTEM, True)
    await db.set_guild_setting(G, SETTING_MOD_LOG_CHANNEL, ID_CANALE_LOG)
    yield
    database_module.db._modules_cache.clear()


def _campi(embed):
    return {c.name: c.value for c in embed.fields}


def _dm_inviato(scena):
    c = scena.bersaglio.send.call_args
    return c.kwargs["embed"]


async def _costruisci(scena, **extra):
    return await moderation_dm.costruisci(
        scena.server, "kick", titolo="Kick", colore=discord.Color.red(), moderatore=scena.moderatore, motivo="Spam", **extra
    )


def test_segnaposto_e_durata_a_parole():
    assert moderation_dm.espandi("{server}: {motivo} ({durata}) da {moderatore} {altro}", {"server": "S", "motivo": "m", "durata": "1 ora", "moderatore": "x"}) == "S: m (1 ora) da x {altro}"
    assert moderation_dm.durata_a_parole(None) == "" and moderation_dm.durata_a_parole(3600) == "1 ora"
    assert moderation_dm.durata_a_parole(7200) == "2 ore" and moderation_dm.durata_a_parole(86400) == "1 giorno"
    assert moderation_dm.durata_a_parole(90 * 60) == "90 minuti" and moderation_dm.durata_a_parole(45) == "45 secondi"


async def test_di_base_il_dm_nomina_il_moderatore():
    scena = Scena()
    c = _campi(await _costruisci(scena, caso=7, durata_s=3600))
    assert scena.moderatore.mention in c["Moderatore"] and c["Caso"] == "#7" and c["Durata"] == "1 ora" and c["Motivo"] == "Spam"


async def test_con_anonimo_il_dm_dice_staff_del_server():
    await moderation_opzioni.imposta_anonimo(G, True, 1)
    scena = Scena()
    e = await _costruisci(scena)
    assert _campi(e)["Moderatore"] == f"Staff di {scena.server.name}"
    assert scena.moderatore.mention not in str(e.to_dict())


async def test_senza_moderatore_e_come_anonimo():
    scena = Scena()
    e = await moderation_dm.costruisci(scena.server, "kick", titolo="K", colore=discord.Color.red(), moderatore=None, motivo="x")
    assert _campi(e)["Moderatore"] == f"Staff di {scena.server.name}"


async def test_il_testo_del_server_prende_i_segnaposto_e_il_tetto():
    await moderation_opzioni.imposta_dm_testo(G, "kick", "Fuori da {server} per {motivo}. Ciao da {moderatore}", 1)
    scena = Scena()
    e = await _costruisci(scena)
    assert e.description == f"Fuori da {scena.server.name} per Spam. Ciao da {scena.moderatore.mention}"
    assert len(e.description) <= 4096
    # un'altra azione non ha il testo
    altro = await moderation_dm.costruisci(scena.server, "ban", titolo="B", colore=discord.Color.red(), moderatore=None, motivo="x")
    assert altro.description is None


async def test_motivo_lungo_sta_nei_limiti_di_discord():
    scena = Scena()
    e = await moderation_dm.costruisci(scena.server, "kick", titolo="K" * 400, colore=discord.Color.red(), moderatore=None, motivo="x" * 3000)
    assert len(e.title) <= 256 and all(len(c.value) <= 1024 for c in e.fields)


async def test_opzioni_testo_vuoto_toglie_e_troppo_lungo_si_rifiuta():
    await moderation_opzioni.imposta_dm_testo(G, "ban", "ciao", 1)
    assert (await moderation_opzioni.leggi(G)).dm_testi == {"ban": "ciao"}
    await moderation_opzioni.imposta_dm_testo(G, "ban", "  ", 1)
    assert (await moderation_opzioni.leggi(G)).dm_testi == {}
    with pytest.raises(ValueError):
        await moderation_opzioni.imposta_dm_testo(G, "ban", "x" * 1501, 1)
    with pytest.raises(ValueError):
        await moderation_opzioni.imposta_dm_testo(G, "boh", "x", 1)


async def test_kick_anonimo_nel_dm_ma_il_log_tiene_il_nome():
    await moderation_opzioni.imposta_anonimo(G, True, 1)
    scena = Scena()
    cog = ModerationActionsCog(bot=None)
    await cog.kick.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto")
    dm = _dm_inviato(scena)
    assert _campi(dm)["Moderatore"].startswith("Staff di")
    risposta = scena.interazione.followup.send.call_args.kwargs["embed"]
    assert scena.moderatore.mention in _campi(risposta)["Moderatore"]


async def test_warn_con_testo_del_server_nel_dm_e_non_nel_log():
    await moderation_opzioni.imposta_dm_testo(G, "warn", "Attenzione: {motivo}", 1)
    scena = Scena()
    cog = ModerationActionsCog(bot=None)
    await cog.warn.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto")
    assert _dm_inviato(scena).description == "Attenzione: Spam ripetuto"
    risposta = scena.interazione.response.send_message.call_args.kwargs["embed"]
    assert risposta.description is None


async def test_timeout_dm_porta_la_durata():
    scena = Scena()
    scena.bersaglio.timeout = AsyncMock()
    cog = ModerationActionsCog(bot=None)
    await cog.timeout.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto", "2h")
    assert _campi(_dm_inviato(scena))["Durata"] == "2 ore"


async def test_comando_imposta_anonimo_e_dm_testo():
    scena = Scena()
    scena.moderatore.guild_permissions.manage_guild = True
    cog = OpzioniModerazioneCog(bot=None)
    await cog.imposta.callback(cog, scena.interazione, anonimo=True)
    assert (await moderation_opzioni.leggi(G)).anonimo is True
    scelta = discord.app_commands.Choice(name="Kick", value="kick")
    scena.interazione.response.send_modal = AsyncMock()
    await cog.dm.callback(cog, scena.interazione, scelta, True, True)
    modulo = scena.interazione.response.send_modal.call_args.args[0]
    assert isinstance(modulo, ModuloTestoDm) and len(modulo.title) <= 45 and len(modulo.testo.label) <= 45
    modulo.testo._value = "Via da {server}"
    scena.interazione.response.send_message.reset_mock()
    await modulo.on_submit(scena.interazione)
    assert (await moderation_opzioni.leggi(G)).dm_testi == {"kick": "Via da {server}"}
    assert "Via da" in scena.interazione.response.send_message.call_args.args[0]


async def test_il_modulo_rifiuta_chi_ha_perso_i_permessi():
    scena = Scena()
    scena.moderatore.guild_permissions.manage_guild = False
    scena.moderatore.guild_permissions.administrator = False
    modulo = ModuloTestoDm("kick", "Kick", None, "t", "c")
    modulo.testo._value = "x"
    await modulo.on_submit(scena.interazione)
    assert (await moderation_opzioni.leggi(G)).dm_testi == {}


async def test_se_le_opzioni_non_si_leggono_il_dm_parte_lo_stesso_senza_nome(monkeypatch):
    async def rotta(guild_id):
        raise RuntimeError("db")

    monkeypatch.setattr(moderation_opzioni, "leggi", rotta)
    scena = Scena()
    e = await _costruisci(scena)
    assert _campi(e)["Moderatore"] == f"Staff di {scena.server.name}" and e.description is None

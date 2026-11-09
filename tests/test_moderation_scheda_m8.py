"""
tests/test_moderation_scheda_m8.py
==================================
M8 (#115): scheda di moderazione (`/mod-casi scheda`, MOD-106), menu col tasto destro «Scheda moderazione» con 5
tasti (MOD-115), «Segnala messaggio» (MOD-105) e `/utility mie-sanzioni` (MOD-114). Database vero.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.moderation.scheda as scheda
from cogs.moderation._shared import MODULE_ACTIONS, MODULE_CASE_SYSTEM, MODULE_REPORT, SETTING_MOD_LOG_CHANNEL
from cogs.moderation.actions import ModerationActionsCog
from cogs.moderation.report import SETTING_REPORT_CHANNEL
from core import moderation_opzioni, moderation_scheda
from core.database import db
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_member, fake_text_channel
from tests.test_moderation_ordine_azione import ID_BERSAGLIO, ID_CANALE_LOG, ID_MODERATORE, ID_SERVER, Scena

G = ID_SERVER
FUORI = 555


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    for modulo in (MODULE_ACTIONS, MODULE_CASE_SYSTEM, MODULE_REPORT):
        await db.set_module_active_for_guild(G, modulo, True)
    await db.set_guild_setting(G, SETTING_MOD_LOG_CHANNEL, ID_CANALE_LOG)
    livelli = AsyncMock(return_value=True)
    monkeypatch.setattr(scheda, "puo_usare", livelli)
    monkeypatch.setattr(scheda, "testo_rischio_membro", AsyncMock(return_value="rischio basso"))
    yield livelli
    database_module.db._modules_cache.clear()


def _membri(scena, bersaglio_presente=True):
    """get_member che conosce il moderatore e (se c'è) il bersaglio."""
    scena.server.get_member.side_effect = lambda i: {scena.moderatore.id: scena.moderatore, scena.bersaglio.id: scena.bersaglio if bersaglio_presente else None}.get(i)


def _cog():
    return scheda.ModerationSchedaCog(bot=MagicMock())


def _utente(user_id, nome="Fuori"):
    u = MagicMock(spec=discord.User)
    u.id = user_id
    u.name = nome
    u.display_name = nome
    u.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return u


# --- dati e riquadro ---

async def test_conteggi_e_ultimi_non_includono_i_casi_nascosti():
    a = await moderation_repo.create_case(G, FUORI, ID_MODERATORE, "warn", "uno")
    await moderation_repo.create_case(G, FUORI, ID_MODERATORE, "warn", "due")
    await moderation_repo.create_case(G, FUORI, ID_MODERATORE, "ban", "tre")
    await moderation_repo.set_case_hidden(G, a, True)
    assert await moderation_repo.count_cases_by_type(G, FUORI) == {"warn": (1, 1), "ban": (1, 1)}
    assert [c.reason for c in await moderation_repo.list_visible_cases_for_user(G, FUORI, 10)] == ["tre", "due"]


async def test_la_scheda_di_chi_e_fuori_dal_server_non_ha_il_rischio():
    await moderation_repo.create_case(G, FUORI, ID_MODERATORE, "kick", "x")
    await moderation_repo.add_note(G, FUORI, ID_MODERATORE, "una nota")
    dati = await moderation_scheda.leggi_scheda(G, _utente(FUORI), None, None)
    assert dati.entrato is None and dati.note == 1 and dati.conteggi == {"kick": (0 + 1, 1)}
    t = {c: c for c in ("titolo", "account", "entrato", "fuori", "attivi", "nessuno", "totali", "ultimi", "note", "rischio")}
    t["titolo"] = "Scheda {nome}"
    embed = moderation_scheda.embed_scheda(dati, t)
    nomi = [c.name for c in embed.fields]
    assert "rischio" not in nomi and "fuori" in [c.value for c in embed.fields]


def test_il_riquadro_resta_nei_limiti_con_dati_enormi():
    caso = lambda n: moderation_scheda.ModerationCase(n, 1, 2, 3, "warn", "m" * 3000, None, True, datetime.now(timezone.utc), None, None)
    dati = moderation_scheda.DatiScheda(2, "n" * 400, datetime.now(timezone.utc), datetime.now(timezone.utc),
                                        {f"tipo{i}": (9, 9) for i in range(40)}, [caso(i) for i in range(5)], 99, "r" * 5000)
    t = {c: c * 3 for c in ("titolo", "account", "entrato", "fuori", "attivi", "nessuno", "totali", "ultimi", "note", "rischio")}
    t["titolo"] = "{nome}"
    e = moderation_scheda.embed_scheda(dati, t)
    assert len(e.fields) <= 25 and len(e) <= 6000 and all(len(f.value) <= 1024 for f in e.fields) and len(e.title) <= 256


async def test_comando_scheda_per_un_id_fuori_dal_server():
    scena = Scena()
    _membri(scena, False)
    cog = _cog()
    await cog.scheda.callback(cog, scena.interazione, _utente(FUORI))
    scena.interazione.response.defer.assert_awaited_once()
    embed = scena.interazione.followup.send.call_args.kwargs["embed"]
    assert len(embed.fields) >= 5


# --- menu e tasti ---

async def test_il_menu_scheda_e_rifiutato_a_chi_non_e_staff(_amb):
    _amb.return_value = False
    scena = Scena()
    cog = _cog()
    await cog.menu_scheda(scena.interazione, scena.bersaglio)
    scena.interazione.response.send_message.assert_awaited_once()
    scena.interazione.response.defer.assert_not_called()


async def _apri_scheda(scena, utente=None, nel_server=True):
    _membri(scena, nel_server)
    cog = _cog()
    await cog.menu_scheda(scena.interazione, utente or scena.bersaglio)
    return scena.interazione.followup.send.call_args.kwargs["view"]


async def test_la_scheda_ha_cinque_tasti_in_una_riga():
    scena = Scena()
    vista = await _apri_scheda(scena)
    assert [b.custom_id.split(":")[1] for b in vista.children] == ["warn", "timeout", "kick", "ban", "nota"]
    assert all(b.row == 0 and len(b.label) <= 45 and len(b.custom_id) < 100 and not b.disabled for b in vista.children)


async def test_senza_livello_modban_kick_e_ban_sono_spenti(_amb):
    _amb.side_effect = lambda inter, livello: livello is not scheda.Livello.MODBAN
    scena = Scena()
    vista = await _apri_scheda(scena)
    spenti = {b.custom_id.split(":")[1] for b in vista.children if b.disabled}
    assert spenti == {"kick", "ban"}


async def test_per_chi_e_fuori_dal_server_resta_solo_la_nota():
    scena = Scena()
    vista = await _apri_scheda(scena, _utente(FUORI), nel_server=False)
    assert {b.custom_id.split(":")[1] for b in vista.children if not b.disabled} == {"nota"}


async def test_altri_non_usano_i_tasti_della_scheda():
    scena = Scena()
    vista = await _apri_scheda(scena)
    altro = MagicMock()
    altro.user.id = 4242
    altro.response.send_message = AsyncMock()
    assert await vista.interaction_check(altro) is False


async def _invia_modulo(scena, azione, motivo, durata=None, utente=None):
    modulo = scheda.ModuloAzione(_cog(), azione, utente or scena.bersaglio, "t", {"motivo": "m", "durata": "d", "nota": "n"})
    modulo.motivo._value = motivo
    if durata is not None:
        modulo.durata._value = durata
    scena.interazione.client.get_cog.return_value = ModerationActionsCog(bot=None)
    scena.interazione.response.send_message.reset_mock()
    await modulo.on_submit(scena.interazione)
    return modulo


async def test_tasto_warn_da_un_warn_vero():
    scena = Scena()
    _membri(scena)
    await _invia_modulo(scena, "warn", "Spam ripetuto")
    casi = await moderation_repo.list_cases_for_user(G, ID_BERSAGLIO)
    assert len(casi) == 1 and casi[0].action_type == "warn" and casi[0].reason == "Spam ripetuto", scena.interazione.response.send_message.call_args_list


async def test_tasto_timeout_usa_la_durata():
    scena = Scena()
    _membri(scena)
    scena.bersaglio.timeout = AsyncMock()
    await _invia_modulo(scena, "timeout", "Spam ripetuto", "2h")
    assert scena.bersaglio.timeout.call_args.args[0].total_seconds() == 7200


async def test_tasto_ban_con_durata_diventa_tempban(monkeypatch):
    scena = Scena()
    _membri(scena)
    cog = ModerationActionsCog(bot=None)
    chiamato = {}

    async def finto(self_, interazione, **kw):
        chiamato.update(kw)

    monkeypatch.setattr(type(cog).tempban, "callback", finto)
    scena.interazione.client.get_cog.return_value = cog
    modulo = scheda.ModuloAzione(_cog(), "ban", scena.bersaglio, "t", {"motivo": "m", "durata": "d", "nota": "n"})
    modulo.motivo._value = "Spam ripetuto"
    modulo.durata._value = "7d"
    await modulo.on_submit(scena.interazione)
    assert chiamato["duration"] == "604800s" and chiamato["member"] is scena.bersaglio


async def test_tasto_nota_salva_la_nota_anche_per_chi_e_fuori():
    scena = Scena()
    await _invia_modulo(scena, "nota", "tiene d'occhio", utente=_utente(FUORI))
    assert await moderation_repo.count_notes_for_user(G, FUORI) == 1


async def test_il_livello_si_ricontrolla_alla_finestra(_amb):
    scena = Scena()
    _membri(scena)
    _amb.return_value = False
    await _invia_modulo(scena, "ban", "Spam ripetuto")
    assert scena.bersaglio.ban.call_count == 0
    assert await moderation_repo.list_cases_for_user(G, ID_BERSAGLIO) == []


async def test_durata_sbagliata_non_fa_niente():
    scena = Scena()
    _membri(scena)
    scena.bersaglio.timeout = AsyncMock()
    await _invia_modulo(scena, "timeout", "Spam ripetuto", "boh")
    scena.bersaglio.timeout.assert_not_called()


# --- segnala messaggio ---

class _Storia:
    def __init__(self, messaggi):
        self._m = messaggi

    def history(self, limit, before):
        async def _gen():
            for m in self._m:
                yield m

        return _gen()


def _messaggio(autore, testo="ciao", prima=()):
    m = MagicMock(spec=discord.Message)
    m.author = autore
    m.content = testo
    m.jump_url = "https://discord.com/channels/1/2/3"
    m.guild = MagicMock(id=G)
    m.channel = _Storia(list(prima))
    return m


async def test_segnala_il_proprio_messaggio_e_rifiutato():
    scena = Scena()
    cog = _cog()
    await cog.menu_segnala(scena.interazione, _messaggio(scena.moderatore))
    scena.interazione.response.send_modal.assert_not_called()


async def test_segnala_messaggio_apre_la_finestra_e_invia_con_contesto():
    scena = Scena()
    canale_report = fake_text_channel(9001, "segnalazioni")
    scena.server.get_channel.side_effect = lambda i: canale_report if i == 9001 else scena.canale_log
    await db.set_guild_setting(G, SETTING_REPORT_CHANNEL, 9001)
    prima = [MagicMock(author=scena.moderatore, content=f"vecchio {i}") for i in range(3)]
    messaggio = _messaggio(scena.bersaglio, "x" * 1500, prima)
    cog = _cog()
    await cog.menu_segnala(scena.interazione, messaggio)
    modulo = scena.interazione.response.send_modal.call_args.args[0]
    assert len(modulo.title) <= 45 and modulo.motivo.max_length <= 500
    modulo.motivo._value = "è spam"
    await modulo.on_submit(scena.interazione)
    inviato = canale_report.send.call_args.kwargs
    nomi = [f.name for f in inviato["embed"].fields]
    assert messaggio.jump_url in [f.value for f in inviato["embed"].fields]
    assert all(len(f.value) <= 1024 for f in inviato["embed"].fields)
    assert inviato["file"].filename == "contesto.txt"
    assert len(nomi) >= 5


async def test_segnala_messaggio_corto_non_manda_il_file():
    scena = Scena()
    canale_report = fake_text_channel(9001, "segnalazioni")
    scena.server.get_channel.side_effect = lambda i: canale_report if i == 9001 else scena.canale_log
    await db.set_guild_setting(G, SETTING_REPORT_CHANNEL, 9001)
    modulo = scheda.ModuloSegnala(_messaggio(scena.bersaglio, "breve"), "t", "c")
    modulo.motivo._value = "è spam"
    await modulo.on_submit(scena.interazione)
    assert "file" not in canale_report.send.call_args.kwargs


# --- mie sanzioni ---

async def test_mie_sanzioni_mostra_solo_i_casi_visibili_e_mai_le_note():
    scena = Scena()
    a = await moderation_repo.create_case(G, ID_MODERATORE, ID_BERSAGLIO, "warn", "visibile")
    n = await moderation_repo.create_case(G, ID_MODERATORE, ID_BERSAGLIO, "ban", "nascosto")
    await moderation_repo.set_case_hidden(G, n, True)
    await moderation_repo.add_note(G, ID_MODERATORE, ID_BERSAGLIO, "SEGRETA")
    cog = _cog()
    await cog.mie_sanzioni.callback(cog, scena.interazione)
    embed = scena.interazione.response.send_message.call_args.kwargs["embed"]
    assert "visibile" in embed.description and "nascosto" not in embed.description and "SEGRETA" not in embed.description
    assert scena.interazione.response.send_message.call_args.kwargs["ephemeral"] is True


async def test_mie_sanzioni_anonimo_non_nomina_il_moderatore():
    scena = Scena()
    _membri(scena)
    await moderation_repo.create_case(G, ID_MODERATORE, ID_BERSAGLIO, "warn", "visibile")
    await moderation_opzioni.imposta_anonimo(G, True, 1)
    cog = _cog()
    await cog.mie_sanzioni.callback(cog, scena.interazione)
    descr = scena.interazione.response.send_message.call_args.kwargs["embed"].description
    assert f"Staff di {scena.server.name}" in descr and str(ID_BERSAGLIO) not in descr


async def test_mie_sanzioni_spente_dal_server():
    scena = Scena()
    await moderation_repo.create_case(G, ID_MODERATORE, ID_BERSAGLIO, "warn", "visibile")
    await moderation_opzioni.imposta_utente_vede_casi(G, False, 1)
    cog = _cog()
    await cog.mie_sanzioni.callback(cog, scena.interazione)
    assert "embed" not in scena.interazione.response.send_message.call_args.kwargs


async def test_mie_sanzioni_senza_casi():
    scena = Scena()
    cog = _cog()
    await cog.mie_sanzioni.callback(cog, scena.interazione)
    assert "embed" not in scena.interazione.response.send_message.call_args.kwargs


# --- registrazione dei menu ---

async def test_i_menu_si_registrano_con_i_limiti():
    from discord.ext import commands

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    cog = scheda.ModerationSchedaCog(bot)
    await cog.cog_load()
    menu = {(c.name, c.type) for c in bot.tree.get_commands() if isinstance(c, discord.app_commands.ContextMenu)}
    assert menu == {("Scheda moderazione", discord.AppCommandType.user), ("Segnala messaggio", discord.AppCommandType.message)}
    scheda_menu = bot.tree.get_command("Scheda moderazione", type=discord.AppCommandType.user)
    assert scheda_menu.default_permissions.moderate_members and scheda_menu.guild_only
    assert all(len(n) <= 32 for n, _ in menu)
    await cog.cog_unload()
    assert not [c for c in bot.tree.get_commands() if isinstance(c, discord.app_commands.ContextMenu)]
    await bot.close()


async def test_segnalazioni_a_raffica_hanno_un_tetto():
    """Una persona non può riempire il canale dello staff: oltre il tetto le segnalazioni sono rifiutate."""
    from cogs.moderation import report

    report._segnalazioni_fatte.clear()
    scena = Scena()
    canale_report = fake_text_channel(9001, "segnalazioni")
    scena.server.get_channel.side_effect = lambda i: canale_report if i == 9001 else scena.canale_log
    await db.set_guild_setting(G, SETTING_REPORT_CHANNEL, 9001)
    for _ in range(report.MAX_SEGNALAZIONI + 3):
        modulo = scheda.ModuloSegnala(_messaggio(scena.bersaglio, "breve"), "t", "c")
        modulo.motivo._value = "è spam"
        await modulo.on_submit(scena.interazione)
    assert canale_report.send.call_count == report.MAX_SEGNALAZIONI
    report._segnalazioni_fatte.clear()


async def test_segnala_messaggio_risponde_prima_di_leggere_la_cronologia():
    """La finestra va chiusa entro 3 secondi: il defer parte prima della lettura dei messaggi precedenti."""
    scena = Scena()
    canale_report = fake_text_channel(9001, "segnalazioni")
    scena.server.get_channel.side_effect = lambda i: canale_report if i == 9001 else scena.canale_log
    await db.set_guild_setting(G, SETTING_REPORT_CHANNEL, 9001)
    messaggio = _messaggio(scena.bersaglio, "breve", [MagicMock(author=scena.moderatore, content="prima")])
    ordine = []
    storia = messaggio.channel.history

    def history(limit, before):
        ordine.append("cronologia")
        return storia(limit, before)

    messaggio.channel.history = history
    scena.interazione.response.defer.side_effect = lambda *a, **k: ordine.append("defer")
    modulo = scheda.ModuloSegnala(messaggio, "t", "c")
    modulo.motivo._value = "è spam"
    await modulo.on_submit(scena.interazione)
    assert ordine == ["defer", "cronologia"]

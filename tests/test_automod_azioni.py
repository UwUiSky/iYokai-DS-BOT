"""
tests/test_automod_azioni.py
============================
Motore delle azioni AutoMod (D63): ordine fisso, scudo dei protetti, DM prima di kick e ban, sospensione di 10
minuti dopo un 403, slowmode e permessi a tempo, ultimi messaggi, avvisi con pausa.
Funzioni coperte: SPEC §6 (AMD-042-046, 048-053, 055, 056)
"""

from __future__ import annotations

import time
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from core import automod_azioni as M
from core.automod_regole_logic import azioni_da_json
from tests.support.discord_fakes import fake_guild, fake_member, fake_message, fake_role, fake_text_channel

G = 666


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    M._sospese._data.clear()
    M._pause._data.clear()
    M._ultimi._data.clear()
    monkeypatch.setattr(M.scheduler, "schedule", AsyncMock(return_value=1))
    monkeypatch.setattr(M.scheduler, "cancel_for_user", AsyncMock())
    yield
    M._sospese._data.clear()  # una sospensione lasciata qui fermerebbe le azioni nei test di altri file (stesso server)
    M._pause._data.clear()
    M._ultimi._data.clear()


def _bers(membro=None, guild=None, **kw):
    guild = guild or fake_guild(guild_id=G)
    membro = membro or fake_member(user_id=42)
    membro.guild = guild
    messaggio = fake_message(author=membro, guild=guild, content="x")
    canale = fake_text_channel(channel_id=10)
    messaggio.channel = canale
    avvisi = AsyncMock()
    b = M.Bersaglio(guild=guild, motivo="Anti-Link", regola_chiave="anti_link", regola_nome="Anti-Link",
                    membro=membro, messaggio=messaggio, canale=canale, avvisa_staff=avvisi, **kw)
    return b, avvisi


def A(*dati):
    return azioni_da_json(list(dati))


async def test_ordine_cancella_dm_sanzione_e_dm_prima_del_ban(monkeypatch):
    ordine = []
    b, _ = _bers()
    monkeypatch.setattr(M.bot_roles, "cancella_messaggio", AsyncMock(side_effect=lambda m: ordine.append("cancella")))
    monkeypatch.setattr(M.bot_roles, "banna", AsyncMock(side_effect=lambda *a, **k: ordine.append("ban")))
    monkeypatch.setattr(M, "_dm_prima_dell_azione", AsyncMock(side_effect=lambda *a: ordine.append("dm")))
    fatte = await M.esegui_azioni(A({"t": "ban"}, {"t": "cancella"}), b)
    assert ordine == ["cancella", "dm", "ban"]
    assert fatte == ("delete", "ban")


async def test_protetto_subisce_solo_le_azioni_leggere(monkeypatch):
    admin = fake_member(user_id=7, guild_permissions=discord.Permissions(administrator=True))
    b, _ = _bers(admin)
    cancella = AsyncMock()
    monkeypatch.setattr(M.bot_roles, "cancella_messaggio", cancella)
    isola, espelli = AsyncMock(), AsyncMock()
    monkeypatch.setattr(M.bot_roles, "isola", isola)
    monkeypatch.setattr(M.bot_roles, "espelli", espelli)
    nick = AsyncMock()
    admin.edit = nick
    fatte = await M.esegui_azioni(A({"t": "cancella"}, {"t": "timeout", "secondi": 60}, {"t": "kick"},
                                    {"t": "nickname", "testo": "x"}, {"t": "ruolo", "ruolo_id": 1}), b)
    assert fatte == ("delete",)
    isola.assert_not_awaited(); espelli.assert_not_awaited(); nick.assert_not_awaited()


async def test_timeout_usa_la_durata_della_regola(monkeypatch):
    b, _ = _bers()
    isola = AsyncMock()
    monkeypatch.setattr(M.bot_roles, "isola", isola)
    assert await M.esegui_azioni(A({"t": "timeout", "secondi": 900}), b) == ("mute",)
    assert isola.await_args.args[1] == timedelta(seconds=900)


async def test_403_sospende_l_azione_10_minuti_e_avvisa_lo_staff_una_volta(monkeypatch):
    b, avvisi = _bers()
    risposta = MagicMock(status=403, reason="x")
    isola = AsyncMock(side_effect=discord.Forbidden(risposta, "no"))
    monkeypatch.setattr(M.bot_roles, "isola", isola)
    assert await M.esegui_azioni(A({"t": "timeout", "secondi": 60}), b) == ()
    assert M.sospesa(G, "timeout")
    await M.esegui_azioni(A({"t": "timeout", "secondi": 60}), b)
    assert isola.await_count == 1  # la seconda volta non ci prova nemmeno
    assert avvisi.await_count == 1
    M._sospese.set((G, "timeout"), time.monotonic() - 1)  # passati i 10 minuti
    await M.esegui_azioni(A({"t": "timeout", "secondi": 60}), b)
    assert isola.await_count == 2


async def test_kick_fallito_cancella_il_dm(monkeypatch):
    b, _ = _bers()
    dm = MagicMock(delete=AsyncMock())
    monkeypatch.setattr(M, "_dm_prima_dell_azione", AsyncMock(return_value=dm))
    monkeypatch.setattr(M.bot_roles, "espelli", AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500, reason="x"), "x")))
    assert await M.esegui_azioni(A({"t": "kick"}), b) == ()
    dm.delete.assert_awaited_once()


async def test_slowmode_non_tocca_un_canale_che_ce_l_ha_gia():
    b, _ = _bers()
    b.canale.slowmode_delay = 5
    b.canale.edit = AsyncMock()
    assert await M.esegui_azioni(A({"t": "slowmode", "secondi": 30}), b) == ()
    b.canale.edit.assert_not_awaited()
    b.canale.slowmode_delay = 0
    assert await M.esegui_azioni(A({"t": "slowmode", "secondi": 30, "durata_s": 120}), b) == ("slowmode",)
    b.canale.edit.assert_awaited_once()
    assert M.scheduler.schedule.await_args.args[2] == M.AZIONE_SLOWMODE_FINE


async def test_fine_dello_slowmode_solo_se_non_cambiato_da_un_admin():
    canale = fake_text_channel(channel_id=10)
    canale.slowmode_delay = 30
    canale.edit = AsyncMock()
    guild = fake_guild(guild_id=G)
    guild.get_channel_or_thread = MagicMock(return_value=canale)
    bot = MagicMock(get_guild=MagicMock(return_value=guild))
    await M.gestisci_slowmode_fine(bot, G, 10, {"canale_id": 10, "valore": 30})
    canale.edit.assert_awaited_once()
    canale.edit.reset_mock()
    canale.slowmode_delay = 99
    await M.gestisci_slowmode_fine(bot, G, 10, {"canale_id": 10, "valore": 30})
    canale.edit.assert_not_awaited()


async def test_permessi_tolgono_la_scrittura_con_ripristino():
    b, _ = _bers()
    regole = discord.PermissionOverwrite()
    b.canale.overwrites_for = MagicMock(return_value=regole)
    b.canale.set_permissions = AsyncMock()
    b.guild.default_role = fake_role(role_id=G, name="@everyone")
    assert await M.esegui_azioni(A({"t": "permessi", "durata_s": 600}), b) == ("permessi",)
    assert regole.send_messages is False
    assert M.scheduler.schedule.await_args.args[2] == M.AZIONE_PERMESSI_FINE
    assert M.scheduler.schedule.await_args.args[4]["prima"] is None
    # già bloccato: non si fa niente (e non si programma un secondo ripristino)
    M.scheduler.schedule.reset_mock()
    assert await M.esegui_azioni(A({"t": "permessi", "durata_s": 600}), b) == ()
    M.scheduler.schedule.assert_not_awaited()


async def test_fine_dei_permessi_rimette_il_valore_di_prima():
    ruolo = fake_role(role_id=5)
    canale = fake_text_channel(channel_id=10)
    regole = discord.PermissionOverwrite(send_messages=False)
    canale.overwrites_for = MagicMock(return_value=regole)
    canale.set_permissions = AsyncMock()
    guild = fake_guild(guild_id=G)
    guild.get_channel = MagicMock(return_value=canale)
    guild.get_role = MagicMock(return_value=ruolo)
    await M.gestisci_permessi_fine(MagicMock(get_guild=MagicMock(return_value=guild)), G, 10,
                                   {"canale_id": 10, "ruolo_id": 5, "prima": None})
    assert canale.set_permissions.await_args.kwargs["overwrite"] is None  # ripulito: non resta un'eccezione vuota


async def test_avviso_nel_canale_uno_ogni_30_secondi_e_senza_menzioni():
    b, _ = _bers()
    b.canale.send = AsyncMock()
    az = A({"t": "avviso_canale", "testo": "{utente}, niente link", "dopo_s": 5})
    assert await M.esegui_azioni(az, b) == ("avviso_canale",)
    assert await M.esegui_azioni(az, b) == ()
    b.canale.send.assert_awaited_once()
    assert b.canale.send.await_args.kwargs["delete_after"] == 5
    assert b.canale.send.await_args.kwargs["allowed_mentions"].roles is False


async def test_ping_al_ruolo_uno_al_minuto():
    b, avvisi = _bers()
    az = A({"t": "log", "ping_ruolo": 99})
    assert await M.esegui_azioni(az, b) == ("log",)
    assert await M.esegui_azioni(az, b) == ()
    assert avvisi.await_args.args[1] == 99


async def test_ruolo_a_tempo_e_gia_cosi(monkeypatch):
    b, _ = _bers()
    ruolo = fake_role(role_id=5)
    b.guild.get_role = MagicMock(return_value=ruolo)
    b.membro.roles = []
    aggiungi = AsyncMock()
    monkeypatch.setattr(M.bot_roles, "aggiungi_ruolo", aggiungi)
    assert await M.esegui_azioni(A({"t": "ruolo", "ruolo_id": 5, "op": "dai", "secondi": 3600}), b) == ("ruolo",)
    assert M.scheduler.schedule.await_args.args[4] == {"ruolo_id": 5, "rimetti": False}  # alla fine lo toglie
    b.membro.roles = [ruolo]
    aggiungi.reset_mock()
    assert await M.esegui_azioni(A({"t": "ruolo", "ruolo_id": 5, "op": "dai"}), b) == ()
    aggiungi.assert_not_awaited()


def test_ultimi_messaggi_per_numero_tempo_ed_eta():
    adesso = 10_000.0
    recente = discord.utils.time_snowflake(discord.utils.utcnow())
    vecchio = discord.utils.time_snowflake(discord.utils.utcnow() - timedelta(days=15))
    for i in range(60):
        M.registra_messaggio(G, 1, 10, recente + i, ora=adesso - 30)
    M.registra_messaggio(G, 1, 11, vecchio, ora=adesso - 20)
    M.registra_messaggio(G, 1, 12, recente + 500, ora=adesso - 3000)  # fuori dai 10 minuti
    scelti = M.ultimi_da_cancellare(G, 1, n=20, minuti=10, adesso=adesso)
    assert list(scelti) == [10]
    assert 11 not in scelti and 12 not in scelti  # il vecchio di 15 giorni e il troppo lontano nel tempo restano
    assert len(M.ultimi_da_cancellare(G, 1, n=50, minuti=10, adesso=adesso)[10]) <= 50
    # i messaggi ricordati per utente sono 50 al massimo
    assert len(M._ultimi.get((G, 1))) == M.ULTIMI_PER_UTENTE


async def test_cancella_ultimi_un_solo_messaggio_non_usa_il_blocco(monkeypatch):
    b, _ = _bers()
    canale = fake_text_channel(channel_id=10)
    canale.get_partial_message = MagicMock(side_effect=lambda i: MagicMock(id=i))
    b.guild.get_channel_or_thread = MagicMock(return_value=canale)
    singolo, blocco = AsyncMock(), AsyncMock()
    monkeypatch.setattr(M.bot_roles, "cancella_messaggio", singolo)
    monkeypatch.setattr(M.bot_roles, "cancella_messaggi", blocco)
    nuovo = discord.utils.time_snowflake(discord.utils.utcnow())
    M.registra_messaggio(G, 42, 10, nuovo)
    assert await M.esegui_azioni(A({"t": "cancella_ultimi", "n": 5, "minuti": 10}), b) == ("cancella_ultimi",)
    singolo.assert_awaited_once(); blocco.assert_not_awaited()
    M.registra_messaggio(G, 42, 10, nuovo + 1)
    M.registra_messaggio(G, 42, 10, nuovo + 2)
    singolo.reset_mock()
    await M.esegui_azioni(A({"t": "cancella_ultimi", "n": 5, "minuti": 10}), b)
    blocco.assert_awaited_once()


async def test_senza_membro_si_applicano_solo_le_azioni_di_canale(monkeypatch):
    b, _ = _bers()
    b.membro = None
    isola = AsyncMock()
    monkeypatch.setattr(M.bot_roles, "isola", isola)
    assert await M.esegui_azioni(A({"t": "timeout", "secondi": 60}, {"t": "warn"}, {"t": "dm"}), b) == ()
    isola.assert_not_awaited()


async def test_mute_col_ruolo_crea_il_caso_lo_stato_e_la_scadenza(monkeypatch):
    import cogs.moderation.softban_mute as sm
    from core.repositories.moderation_repo import moderation_repo

    b, _ = _bers()
    monkeypatch.setattr(sm, "_get_or_create_mute_role", AsyncMock(return_value=fake_role(role_id=8)))
    monkeypatch.setattr(M.bot_roles, "aggiungi_ruolo", AsyncMock())
    monkeypatch.setattr(moderation_repo, "create_case", AsyncMock(return_value=3))
    salva = AsyncMock()
    monkeypatch.setattr(moderation_repo, "save_mute_state", salva)
    assert await M.esegui_azioni(A({"t": "mute_ruolo", "secondi": 3600}), b) == ("mute_ruolo",)
    assert salva.await_args.args[:2] == (G, 42) and salva.await_args.args[4] == 3
    assert moderation_repo.create_case.await_args.kwargs["origine"] == "automod"  # MOD-048: può scadere
    assert M.scheduler.schedule.await_args.args[2] == sm.SCHEDULED_MUTE_EXPIRE
    assert M.scheduler.schedule.await_args.args[4] == {"caso": 3}


async def test_ban_a_tempo_pianifica_lo_sban_e_ha_il_dm_prima(monkeypatch):
    from cogs.moderation.actions import SCHEDULED_TEMPBAN_EXPIRE
    from core.repositories.moderation_repo import moderation_repo

    ordine = []
    b, _ = _bers()
    monkeypatch.setattr(M, "_dm_prima_dell_azione", AsyncMock(side_effect=lambda *a: ordine.append("dm")))
    monkeypatch.setattr(M.bot_roles, "banna", AsyncMock(side_effect=lambda *a, **k: ordine.append("ban")))
    crea = AsyncMock(return_value=9)
    monkeypatch.setattr(moderation_repo, "create_case", crea)
    monkeypatch.setattr(moderation_repo, "cancel_tempban_jobs", AsyncMock())
    assert await M.esegui_azioni(A({"t": "ban_tempo", "giorni": 7}), b) == ("ban_tempo",)
    assert ordine == ["dm", "ban"]
    assert crea.await_args.kwargs["duration_seconds"] == 7 * 86400
    assert crea.await_args.kwargs["origine"] == "automod"
    assert M.scheduler.schedule.await_args.args[2] == SCHEDULED_TEMPBAN_EXPIRE
    assert M.scheduler.schedule.await_args.args[4] == {"case_number": 9, "modo": "fuori"}


async def test_senza_scudo_si_sanziona_anche_lo_staff_ma_un_403_su_un_admin_non_sospende(monkeypatch):
    admin = fake_member(user_id=7, guild_permissions=discord.Permissions(administrator=True))
    b, avvisi = _bers(admin)
    b.senza_scudo = True
    isola = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403, reason="x"), "no"))
    monkeypatch.setattr(M.bot_roles, "isola", isola)
    await M.esegui_azioni(A({"t": "timeout", "secondi": 60}), b)
    isola.assert_awaited_once()  # ci prova (con lo scudo non lo farebbe)
    assert not M.sospesa(G, "timeout") and avvisi.await_count == 0  # Discord rifiuta gli admin: non è colpa dei permessi del bot
    normale, _ = _bers()
    normale.senza_scudo = True
    await M.esegui_azioni(A({"t": "timeout", "secondi": 60}), normale)
    assert M.sospesa(G, "timeout")  # un membro normale che dà 403 è davvero un permesso mancato al bot


async def test_dm_staff_scrive_ai_membri_dello_staff_e_salta_chi_non_c_e():
    b, _ = _bers()
    staff = fake_member(user_id=501)
    b.guild.get_member = MagicMock(side_effect=lambda i: staff if i == 501 else None)
    fatte = await M.esegui_azioni(A({"t": "dm_staff", "utenti": [501, 502]}), b)
    assert fatte == ("dm_staff",)
    staff.send.assert_awaited_once()  # prima: discord.Object senza .send, AttributeError e messaggio non giudicato


def _con_ruoli(posizione_membro: int, posizione_bot: int):
    me = fake_member(user_id=999, roles=[fake_role(role_id=90, position=posizione_bot)], bot=True)
    guild = fake_guild(guild_id=G, me=me)
    membro = fake_member(user_id=42, roles=[fake_role(role_id=91, position=posizione_membro)])
    return _bers(membro, guild)


@pytest.mark.parametrize("senza_scudo", [False, True])
async def test_membro_sopra_il_bot_non_si_tocca_e_non_sospende_l_azione_per_tutto_il_server(monkeypatch, senza_scudo):
    b, avvisi = _con_ruoli(posizione_membro=5, posizione_bot=3)
    b.senza_scudo = senza_scudo
    isola = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403, reason="x"), "no"))
    monkeypatch.setattr(M.bot_roles, "isola", isola)
    assert await M.esegui_azioni(A({"t": "timeout", "secondi": 60}), b) == ()
    isola.assert_not_awaited()  # Discord rifiuterebbe: niente 403 inutili
    assert not M.sospesa(G, "timeout") and avvisi.await_count == 0
    sotto, _ = _con_ruoli(posizione_membro=2, posizione_bot=3)
    sotto.senza_scudo = senza_scudo
    isola.side_effect = None
    assert await M.esegui_azioni(A({"t": "timeout", "secondi": 60}), sotto) == ("mute",)


async def test_l_owner_del_bot_e_protetto(monkeypatch):
    from core.config import config

    b, _ = _bers(fake_member(user_id=config.OWNER_ID))
    isola = AsyncMock()
    monkeypatch.setattr(M.bot_roles, "isola", isola)
    assert await M.esegui_azioni(A({"t": "timeout", "secondi": 60}), b) == ()
    isola.assert_not_awaited()


async def test_il_warn_dell_automod_crea_un_caso_con_origine_automod(monkeypatch):
    import cogs.moderation._shared as condiviso
    from core.repositories.moderation_repo import moderation_repo

    b, _ = _bers()
    crea = AsyncMock(return_value=4)
    monkeypatch.setattr(moderation_repo, "create_case", crea)
    monkeypatch.setattr(condiviso, "try_dm", AsyncMock())
    monkeypatch.setattr(condiviso, "post_to_mod_log", AsyncMock())
    monkeypatch.setattr("core.moderation_dm.costruisci", AsyncMock(return_value=discord.Embed(title="dm")))  # il DM legge le opzioni dal database
    assert await M.esegui_azioni(A({"t": "warn"}), b) == ("warn",)
    assert crea.await_args.kwargs["origine"] == "automod"

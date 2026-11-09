"""
tests/test_programmati_ripetuti.py
==================================
Catalogo #128 B5 (D69): messaggi programmati che si ripetono (ogni N, ora fissa, salto, non ripetere, ping breve).
"""

from datetime import datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands as ext

import cogs.utility.scheduled_messages as sm
from core import programmati_logic as P
from tests.support.discord_fakes import fake_guild, fake_interaction
from tests.support.percorsi import comando_nel_gruppo

UTC = timezone.utc
T0 = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)


def test_ora_valida_e_non():
    assert P.leggi_ora("8:05") == time(8, 5) and P.leggi_ora("23:59") == time(23, 59)
    for brutta in ("24:00", "8", "ab:cd", "12:60"):
        with pytest.raises(ValueError):
            P.leggi_ora(brutta)


def test_regole_della_ripetizione():
    assert P.errore_ripetizione(None, None) is None
    assert P.errore_ripetizione(599, None) and P.errore_ripetizione(600, None) is None
    assert P.errore_ripetizione(3600, time(9, 0))  # con l'ora fissa solo giorni interi
    assert P.errore_ripetizione(86400, time(9, 0)) is None


def test_prossimo_giro_senza_deriva_e_senza_recupero():
    assert P.prossimo_giro(T0, 3600, T0 + timedelta(seconds=5)) == T0 + timedelta(hours=1)
    # spento per 5 ore e mezza: si salta ai giri futuri, non se ne recuperano 5
    assert P.prossimo_giro(T0, 3600, T0 + timedelta(hours=5, minutes=30)) == T0 + timedelta(hours=6)


def test_ora_fissa_resta_la_stessa_col_cambio_dell_ora_legale():
    roma = P.fuso_valido("Europe/Rome")
    prima = P.prima_ora_fissa(datetime(2026, 10, 24, 5, 0, tzinfo=UTC), time(9, 0), roma)  # 09:00 locale, ora legale
    assert prima.hour == 7
    dopo = P.prossimo_giro(datetime(2026, 10, 24, 7, 0, tzinfo=UTC), 7 * 86400, datetime(2026, 10, 25, tzinfo=UTC), time(9, 0), roma)
    assert dopo == datetime(2026, 10, 31, 8, 0, tzinfo=UTC)  # le 9 sul muro anche dopo il cambio: 8 UTC


def test_salta_solo_se_l_ultimo_e_il_nostro():
    assert P.deve_saltare(True, 5, 5)
    assert not P.deve_saltare(True, 6, 5) and not P.deve_saltare(False, 5, 5) and not P.deve_saltare(True, 5, None)


def _cog(monkeypatch, canale=None):
    c = sm.ScheduledMessagesCog(MagicMock())
    c.bot.get_guild.return_value = MagicMock(get_channel=lambda _id: canale)
    pianifica = AsyncMock(return_value=77)
    monkeypatch.setattr(sm.scheduler, "schedule", pianifica)
    return c, pianifica


def _canale(ultimo_id=None):
    canale = MagicMock(spec=discord.TextChannel)
    canale.id = 5
    canale.send = AsyncMock(return_value=MagicMock(id=900))

    async def storia(limit=1):
        if ultimo_id:
            yield MagicMock(id=ultimo_id)

    canale.history = storia
    return canale


@pytest.mark.asyncio
async def test_il_giro_riprogramma_prima_di_inviare_e_manda_il_ping_breve(monkeypatch):
    canale = _canale()
    c, pianifica = _cog(monkeypatch, canale)
    ordine = []
    pianifica.side_effect = lambda **k: ordine.append("pianifica") or 77
    canale.send.side_effect = lambda *a, **k: ordine.append("invia") or MagicMock(id=900)
    payload = {"channel_id": 5, "message": "ciao", "ripeti": 3600, "quando": T0.isoformat(), "ping_ruolo_id": 123}
    await c.handle_scheduled_message_fire(1, 2, payload)
    assert ordine == ["pianifica", "invia", "invia"]
    secondo = canale.send.await_args_list[1]
    assert secondo.args[0] == "<@&123>" and secondo.kwargs["delete_after"] == 10
    assert secondo.kwargs["allowed_mentions"].everyone is False
    assert pianifica.await_args.kwargs["payload"]["ripeti"] == 3600


@pytest.mark.asyncio
async def test_non_ripetere_se_l_ultimo_e_il_nostro_ma_il_giro_dopo_resta(monkeypatch):
    canale = _canale(ultimo_id=900)
    c, pianifica = _cog(monkeypatch, canale)
    payload = {"channel_id": 5, "message": "ciao", "ripeti": 3600, "quando": T0.isoformat(), "salta_se_ultimo": True, "ultimo_id": 900}
    await c.handle_scheduled_message_fire(1, 2, payload)
    canale.send.assert_not_called()
    pianifica.assert_awaited_once()


@pytest.mark.asyncio
async def test_un_messaggio_singolo_non_riprogramma(monkeypatch):
    canale = _canale()
    c, pianifica = _cog(monkeypatch, canale)
    await c.handle_scheduled_message_fire(1, 2, {"channel_id": 5, "message": "ciao"})
    pianifica.assert_not_called()
    canale.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_crea_con_ripeti_ora_e_limiti(monkeypatch):
    c, pianifica = _cog(monkeypatch)
    monkeypatch.setattr(sm.scheduler, "list_pending_for_guild", AsyncMock(return_value=[]))
    monkeypatch.setattr(sm.db, "is_module_active_for_guild", AsyncMock(return_value=True))
    canale = MagicMock(spec=discord.TextChannel)
    canale.id, canale.mention = 5, "#x"
    utente = MagicMock(spec=discord.Member)
    utente.guild_permissions = discord.Permissions(mention_everyone=True)
    it = fake_interaction(user=utente)
    await c.set_scheduled_message.callback(c, it, canale, "1h", "ciao", "5m", None, False, None)  # 5 minuti: troppo poco
    pianifica.assert_not_called()
    await c.set_scheduled_message.callback(c, it, canale, "1h", "ciao", "6h", None, False, None)
    p = pianifica.await_args.kwargs["payload"]
    assert p["ripeti"] == 21600 and "quando" in p
    pianifica.reset_mock()
    await c.set_scheduled_message.callback(c, it, canale, "1h", "ciao", None, "09:30", False, None)  # ora senza ripeti = ogni giorno
    p = pianifica.await_args.kwargs["payload"]
    assert p["ripeti"] == 86400 and p["ora"] == "09:30"
    assert pianifica.await_args.kwargs["execute_at"].astimezone(P.fuso_valido("Europe/Rome")).strftime("%H:%M") == "09:30"
    pianifica.reset_mock()
    await c.set_scheduled_message.callback(c, it, canale, "1h", "ciao", None, None, True, None)  # salta_se_ultimo senza ripeti
    pianifica.assert_not_called()


@pytest.mark.asyncio
async def test_ping_ruolo_solo_con_il_permesso(monkeypatch):
    c, pianifica = _cog(monkeypatch)
    monkeypatch.setattr(sm.scheduler, "list_pending_for_guild", AsyncMock(return_value=[]))
    monkeypatch.setattr(sm.db, "is_module_active_for_guild", AsyncMock(return_value=True))
    canale = MagicMock(spec=discord.TextChannel)
    canale.id, canale.mention = 5, "#x"
    utente = MagicMock(spec=discord.Member)
    utente.guild_permissions = discord.Permissions(manage_guild=True)
    ruolo = MagicMock(spec=discord.Role, id=8, mentionable=True)
    await c.set_scheduled_message.callback(c, fake_interaction(user=utente), canale, "1h", "ciao", None, None, False, ruolo)
    pianifica.assert_not_called()


@pytest.mark.asyncio
async def test_albero_nuove_opzioni_e_salta():
    bot = ext.Bot(command_prefix="!", intents=discord.Intents.default())
    await sm.setup(bot)
    o = comando_nel_gruppo("admin-messaggi", "programmati crea").to_dict(bot.tree)["options"]
    assert [x["name"] for x in o] == ["channel", "duration", "message", "ripeti", "ora", "salta_se_ultimo", "ping_ruolo"]
    obbl = [x.get("required", False) for x in o]
    assert obbl == sorted(obbl, reverse=True)
    s = comando_nel_gruppo("admin-messaggi", "programmati salta").to_dict(bot.tree)["options"]
    assert s[0]["autocomplete"]

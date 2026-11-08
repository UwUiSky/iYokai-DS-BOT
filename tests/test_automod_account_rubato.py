"""
tests/test_automod_account_rubato.py
====================================
Difesa dagli account rubati (D67): un solo avviso allo staff per persona (aggiornato), timeout subito, messaggi
cancellati, DM con le istruzioni, ticket per il messaggio dopo, nessuna esenzione dello staff, opzione per server.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.automod import account_rubato as cog_mod
from core import account_rubato as ar
from core import account_rubato_logic as lg
from core import immagini_opzioni
from core.bounded_cache import BoundedCache
from tests.support.discord_fakes import fake_guild, fake_member, fake_message, fake_text_channel

GUILD = 777000901
TESTO = "Hai vinto un Nitro gratis, ritiralo qui http://x.example"


def messaggio(ambiente, n, canale_id, *, testo=TESTO, guild=None, membro=None):
    guild = guild or ambiente.guild
    canale = ambiente.canali.setdefault(canale_id, fake_text_channel(canale_id))
    msg = fake_message(1000 + n, author=membro or ambiente.membro, channel=canale, guild=guild, content=testo)
    msg.attachments, msg.message_snapshots, msg.webhook_id = [], [], None
    return msg


@pytest.fixture
def ambiente(monkeypatch):
    membro = fake_member(555, "rubato")
    membro.is_timed_out = MagicMock(return_value=False)
    guild = fake_guild(GUILD, owner_id=1)
    guild.get_member = MagicMock(return_value=membro)
    membro.guild = guild
    log = fake_text_channel(222)
    log.send = AsyncMock(return_value=SimpleNamespace(id=5000))
    parziale = MagicMock()
    parziale.edit = AsyncMock()
    log.get_partial_message = MagicMock(return_value=parziale)
    canali = {}
    guild.get_channel = MagicMock(side_effect=lambda i: log if i == 222 else None)
    guild.get_channel_or_thread = MagicMock(side_effect=lambda i: canali.setdefault(i, fake_text_channel(i)))
    bot = SimpleNamespace(get_guild=lambda i: guild if i == GUILD else None)
    cattura = SimpleNamespace(isola=AsyncMock(), cancella=AsyncMock(), cancella_molti=AsyncMock(), dm=AsyncMock(return_value=True),
                              blocco=AsyncMock(return_value=True))
    monkeypatch.setattr(ar, "registro", lg.RegistroInvii())
    monkeypatch.setattr(ar, "_avvisi", BoundedCache(100))
    monkeypatch.setattr(ar, "_dm_fatti", BoundedCache(100))
    monkeypatch.setattr(ar.opzioni, "attivo", AsyncMock(return_value=True))
    monkeypatch.setattr(ar, "lingua_risposta", AsyncMock(return_value="it"))
    monkeypatch.setattr(ar.bot_roles, "isola", cattura.isola)
    monkeypatch.setattr(ar.bot_roles, "cancella_messaggio", cattura.cancella)
    monkeypatch.setattr(ar.bot_roles, "cancella_messaggi", cattura.cancella_molti)
    import cogs.moderation._shared as condiviso
    import core.database as database
    from core import verify_blocchi

    monkeypatch.setattr(condiviso, "try_dm", cattura.dm)
    monkeypatch.setattr(verify_blocchi, "registra_limitazione", cattura.blocco)
    monkeypatch.setattr(immagini_opzioni, "leggi", AsyncMock(return_value=immagini_opzioni.OpzioniImmagini(True, "cancella", 10, 222)))
    monkeypatch.setattr(database.db, "get_guild_setting", AsyncMock(return_value=None))
    return SimpleNamespace(bot=bot, guild=guild, membro=membro, log=log, canali=canali, parziale=parziale, **vars(cattura))


async def tre_invii(ambiente):
    esiti = [await ar.controlla_messaggio(ambiente.bot, messaggio(ambiente, n, 10 + n)) for n in range(3)]
    return esiti


@pytest.mark.asyncio
async def test_due_invii_non_fanno_nulla(ambiente):
    assert await ar.controlla_messaggio(ambiente.bot, messaggio(ambiente, 0, 10)) is False
    assert await ar.controlla_messaggio(ambiente.bot, messaggio(ambiente, 1, 11)) is False
    ambiente.isola.assert_not_called()
    ambiente.log.send.assert_not_called()


@pytest.mark.asyncio
async def test_tre_canali_limitano_cancellano_avvisano_una_volta(ambiente):
    assert await tre_invii(ambiente) == [False, False, True]
    ambiente.isola.assert_awaited_once()
    assert ambiente.isola.await_args.args[1].total_seconds() == lg.TIMEOUT_UGUALI_S
    ambiente.cancella.assert_awaited()  # il messaggio che scatta
    ambiente.cancella_molti.assert_not_called()  # gli altri due stanno in canali diversi: uno a uno
    assert ambiente.cancella.await_count == 3
    ambiente.log.send.assert_awaited_once()
    embed = ambiente.log.send.await_args.kwargs["embed"]
    assert "3 invii in 3 canali" in embed.description
    assert not embed.image.url and not embed.thumbnail.url
    assert "files" not in ambiente.log.send.await_args.kwargs and "file" not in ambiente.log.send.await_args.kwargs


@pytest.mark.asyncio
async def test_il_dm_ha_il_testo_dell_owner_e_apre_il_ticket(ambiente):
    await tre_invii(ambiente)
    ambiente.dm.assert_awaited_once()
    embed = ambiente.dm.await_args.args[1]
    assert embed.description.startswith("Sei stato limitato da iYokai per una presunta violazione del tuo account")
    assert "cambia la password" in embed.description and "autenticazione a due fattori" in embed.description
    assert "controlla le app autorizzate" in embed.description and embed.description.endswith("scrivimi qui.")
    ambiente.blocco.assert_awaited_once()
    assert ambiente.blocco.await_args.args[:2] == (ambiente.guild, 555)
    assert "compromesso" in ambiente.blocco.await_args.args[2]


@pytest.mark.asyncio
async def test_un_quarto_invio_aggiorna_l_avviso_e_non_rimanda_il_dm(ambiente):
    await tre_invii(ambiente)
    assert await ar.controlla_messaggio(ambiente.bot, messaggio(ambiente, 3, 13)) is True
    ambiente.log.send.assert_awaited_once()
    ambiente.parziale.edit.assert_awaited_once()
    assert "4 invii in 4 canali" in ambiente.parziale.edit.await_args.kwargs["embed"].description
    ambiente.dm.assert_awaited_once()


@pytest.mark.asyncio
async def test_gia_in_timeout_non_si_rimette_il_timeout(ambiente):
    ambiente.membro.is_timed_out.return_value = True
    await tre_invii(ambiente)
    ambiente.isola.assert_not_called()


@pytest.mark.asyncio
async def test_lo_staff_si_limita_come_tutti(ambiente):
    ambiente.membro.guild_permissions = discord.Permissions(administrator=True)
    await tre_invii(ambiente)
    ambiente.isola.assert_awaited_once()


@pytest.mark.asyncio
async def test_opzione_spenta_non_fa_nulla(ambiente, monkeypatch):
    monkeypatch.setattr(ar.opzioni, "attivo", AsyncMock(return_value=False))
    assert await tre_invii(ambiente) == [False, False, False]
    ambiente.isola.assert_not_called()
    ambiente.dm.assert_not_called()


@pytest.mark.asyncio
async def test_immagine_malevola_limita_subito_per_un_giorno(ambiente):
    assert await ar.controlla_messaggio(ambiente.bot, messaggio(ambiente, 0, 10, testo=""), malevola=True) is True
    assert ambiente.isola.await_args.args[1].total_seconds() == lg.TIMEOUT_MALEVOLE_S
    assert "immagini malevole" in ambiente.log.send.await_args.kwargs["embed"].description


@pytest.mark.asyncio
async def test_bot_e_webhook_non_si_contano(ambiente):
    bot_msg = messaggio(ambiente, 0, 10, membro=fake_member(9, "bot", bot=True))
    web = messaggio(ambiente, 1, 11)
    web.webhook_id = 42
    for msg in (bot_msg, web):
        for _ in range(4):
            assert await ar.controlla_messaggio(ambiente.bot, msg) is False
    ambiente.isola.assert_not_called()


@pytest.mark.asyncio
async def test_messaggio_breve_o_senza_allegati_non_ha_firma(ambiente):
    for n in range(5):
        assert await ar.controlla_messaggio(ambiente.bot, messaggio(ambiente, n, 10 + n, testo="ok")) is False


@pytest.mark.asyncio
async def test_inoltrato_uguale_in_tre_canali(ambiente):
    for n in range(3):
        msg = messaggio(ambiente, n, 10 + n, testo="")
        msg.message_snapshots = [SimpleNamespace(content="Hai vinto 1000 euro, clicca il link qui sotto", attachments=[])]
        esito = await ar.controlla_messaggio(ambiente.bot, msg)
    assert esito is True


@pytest.mark.asyncio
async def test_cog_ignora_i_bot_e_i_privati(ambiente, monkeypatch):
    controlla = AsyncMock()
    monkeypatch.setattr(cog_mod.account_rubato, "controlla_messaggio", controlla)
    cog = cog_mod.AccountRubatoCog(ambiente.bot)
    privato = messaggio(ambiente, 0, 10)
    privato.guild = None
    await cog.on_message(privato)
    robot = messaggio(ambiente, 1, 11, membro=fake_member(9, "bot", bot=True))
    await cog.on_message(robot)
    controlla.assert_not_called()
    await cog.on_message(messaggio(ambiente, 2, 12))
    controlla.assert_awaited_once()


@pytest.mark.asyncio
async def test_senza_canale_di_log_nessun_avviso_ma_si_agisce(ambiente):
    ambiente.guild.get_channel = MagicMock(return_value=None)
    await tre_invii(ambiente)
    ambiente.isola.assert_awaited_once()
    ambiente.log.send.assert_not_called()


@pytest.mark.asyncio
async def test_invii_contemporanei_un_solo_avviso_e_un_solo_timeout(ambiente, monkeypatch):
    """Lo spam arriva a raffica: due messaggi gestiti insieme non devono creare due avvisi né due timeout."""
    import asyncio

    async def lingua_lenta(*_a, **_k):
        await asyncio.sleep(0)
        return "it"

    async def invio_lento(*_a, **_k):
        await asyncio.sleep(0)
        return SimpleNamespace(id=5000)

    monkeypatch.setattr(ar, "lingua_risposta", lingua_lenta)
    ambiente.log.send.side_effect = invio_lento
    for n in range(2):
        await ar.controlla_messaggio(ambiente.bot, messaggio(ambiente, n, 10 + n))
    ambiente.isola.side_effect = lambda *a, **k: ambiente.membro.is_timed_out.configure_mock(return_value=True)
    await asyncio.gather(*(ar.controlla_messaggio(ambiente.bot, messaggio(ambiente, n, 10 + n)) for n in (2, 3)))
    ambiente.log.send.assert_awaited_once()
    ambiente.isola.assert_awaited_once()

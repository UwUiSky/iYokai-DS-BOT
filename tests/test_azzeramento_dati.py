"""
tests/test_azzeramento_dati.py
==============================
UTL-228 (#128, D111) # UTL-228: azzerare i dati del bot per un server, con 30 giorni di ritardo.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core import azzeramento_dati_logic as logica
from core.repositories.azzeramento_repo import AzzeramentoRepository

pytestmark = pytest.mark.asyncio

ADESSO = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
SERVER, PROPRIETARIO, ALTRO_ADMIN, NUOVO, OWNER_BOT = 900, 42, 7, 43, 1


@pytest.fixture
async def ambiente(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(logica, "azzeramento_repo", AzzeramentoRepository(lambda: clean_db))
    await database_module.db.ensure_guild_exists(SERVER)
    await database_module.db.set_guild_setting(SERVER, "log_channel_id", 111, changed_by=1)
    return database_module.db, clean_db


async def _azioni(pool):
    righe = await pool.fetch("SELECT action_type, execute_at FROM scheduled_actions WHERE guild_id = $1 AND executed = FALSE", SERVER)
    return {r["action_type"]: r["execute_at"] for r in righe}


async def test_la_richiesta_non_cancella_niente_e_mette_in_coda_avviso_ed_esecuzione(ambiente):
    db, pool = ambiente
    r = await logica.chiedi(SERVER, PROPRIETARIO, PROPRIETARIO, ADESSO)
    assert r.esegui_il == ADESSO + timedelta(days=30) and r.stato == "attiva"
    assert await db.get_guild_setting(SERVER, "log_channel_id") == 111
    azioni = await _azioni(pool)
    assert azioni[logica.AZIONE_PREAVVISO] == ADESSO + timedelta(days=27)
    assert azioni[logica.AZIONE_ESEGUI] == ADESSO + timedelta(days=30)
    assert await logica.chiedi(SERVER, PROPRIETARIO, PROPRIETARIO, ADESSO) is None  # una sola richiesta


async def test_non_si_azzera_prima_dei_30_giorni(ambiente):
    db, pool = ambiente
    await logica.chiedi(SERVER, PROPRIETARIO, PROPRIETARIO, ADESSO)
    quasi = ADESSO + timedelta(days=30) - timedelta(minutes=1)
    esito, tolte = await logica.esegui(pool, SERVER, PROPRIETARIO, quasi)
    assert esito == logica.NON_PRONTA and tolte == {}
    assert await db.get_guild_setting(SERVER, "log_channel_id") == 111


async def test_dopo_30_giorni_si_cancella_tutto_con_il_registro(ambiente):
    db, pool = ambiente
    await logica.chiedi(SERVER, PROPRIETARIO, PROPRIETARIO, ADESSO)
    esito, tolte = await logica.esegui(pool, SERVER, PROPRIETARIO, ADESSO + timedelta(days=30))
    assert esito == logica.ESEGUITA and "guild_config" in tolte
    assert await db.get_guild_setting(SERVER, "log_channel_id") is None
    assert await pool.fetchval("SELECT count(*) FROM guild_config_history WHERE guild_id = $1", SERVER) == 0
    assert await pool.fetchval("SELECT count(*) FROM richieste_azzeramento") == 0
    # una seconda esecuzione non fa danni
    assert (await logica.esegui(pool, SERVER, PROPRIETARIO, ADESSO + timedelta(days=31)))[0] == logica.NESSUNA


async def test_annullamento_da_proprietario_del_server_e_del_bot(ambiente):
    db, pool = ambiente
    await logica.chiedi(SERVER, PROPRIETARIO, PROPRIETARIO, ADESSO)
    with pytest.raises(PermissionError):  # un admin qualunque non può
        await logica.annulla(SERVER, ALTRO_ADMIN, PROPRIETARIO, OWNER_BOT)
    assert await logica.azzeramento_repo.get(SERVER) is not None
    assert await logica.annulla(SERVER, OWNER_BOT, PROPRIETARIO, OWNER_BOT) is not None  # owner del bot
    assert await _azioni(pool) == {}  # anche la coda è vuota
    esito, _ = await logica.esegui(pool, SERVER, PROPRIETARIO, ADESSO + timedelta(days=40))
    assert esito == logica.NESSUNA and await db.get_guild_setting(SERVER, "log_channel_id") == 111
    await logica.chiedi(SERVER, PROPRIETARIO, PROPRIETARIO, ADESSO)
    assert await logica.annulla(SERVER, PROPRIETARIO, PROPRIETARIO, OWNER_BOT) is not None  # proprietario del server


async def test_cambio_di_proprietario_sospende_e_serve_la_conferma_del_nuovo(ambiente):
    db, pool = ambiente
    await logica.chiedi(SERVER, PROPRIETARIO, PROPRIETARIO, ADESSO)
    assert await logica.sospendi_se_cambiato(SERVER, PROPRIETARIO) is None  # stesso proprietario: niente
    sospesa = await logica.sospendi_se_cambiato(SERVER, NUOVO)
    assert sospesa.stato == "sospesa" and await _azioni(pool) == {}
    esito, _ = await logica.esegui(pool, SERVER, NUOVO, ADESSO + timedelta(days=60))
    assert esito == logica.NESSUNA and await db.get_guild_setting(SERVER, "log_channel_id") == 111
    with pytest.raises(PermissionError):  # solo chi possiede il server ora
        await logica.riprendi(SERVER, PROPRIETARIO, NUOVO, ADESSO)
    ripresa = await logica.riprendi(SERVER, NUOVO, NUOVO, ADESSO + timedelta(days=5))
    assert ripresa.stato == "attiva" and ripresa.esegui_il == ADESSO + timedelta(days=35)
    assert set(await _azioni(pool)) == {logica.AZIONE_PREAVVISO, logica.AZIONE_ESEGUI}


async def test_proprietario_cambiato_senza_evento_non_cancella(ambiente):
    """Il bot era spento quando il proprietario è cambiato: all'esecuzione si controlla di nuovo."""
    db, pool = ambiente
    await logica.chiedi(SERVER, PROPRIETARIO, PROPRIETARIO, ADESSO)
    esito, _ = await logica.esegui(pool, SERVER, NUOVO, ADESSO + timedelta(days=30))
    assert esito == logica.SOSPESA
    assert await db.get_guild_setting(SERVER, "log_channel_id") == 111
    assert (await logica.azzeramento_repo.get(SERVER)).stato == "sospesa"


async def test_server_non_in_memoria_non_cancella_e_riprova(ambiente):
    db, pool = ambiente
    await logica.chiedi(SERVER, PROPRIETARIO, PROPRIETARIO, ADESSO)
    with pytest.raises(logica.ServerNonPronto):
        await logica.esegui(pool, SERVER, None, ADESSO + timedelta(days=30))
    assert await db.get_guild_setting(SERVER, "log_channel_id") == 111


async def test_permessi_solo_il_proprietario_chiede(ambiente):
    with pytest.raises(PermissionError):
        await logica.chiedi(SERVER, ALTRO_ADMIN, PROPRIETARIO, ADESSO)
    with pytest.raises(PermissionError):
        await logica.chiedi(SERVER, OWNER_BOT, PROPRIETARIO, ADESSO)  # nemmeno l'owner del bot: non lo possiede
    assert not logica.puo_chiedere(5, None)
    assert logica.puo_annullare(OWNER_BOT, PROPRIETARIO, OWNER_BOT) and not logica.puo_annullare(5, PROPRIETARIO, OWNER_BOT)


def test_nome_del_server_scritto_a_mano():
    assert logica.nome_confermato("  Il mio server ", "Il mio server")
    assert not logica.nome_confermato("il mio server", "Il mio server")
    assert not logica.nome_confermato("", "Il mio server") and not logica.nome_confermato(None, "x")


# ---- comando reset, finestra e lavori dello scheduler ----
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import discord  # noqa: E402
from discord.ext import commands  # noqa: E402

from cogs.utility import azzeramento_dati as cog_modulo  # noqa: E402
from cogs.utility import config_history as storico  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member  # noqa: E402


def _storico_cog():
    return storico.ConfigHistoryCog(commands.Bot(command_prefix="!", intents=discord.Intents.default()))


def _modale(guild, utente, scritto, riprendi=False):
    m = cog_modulo.ConfermaNomeModal("t", "n", riprendi=riprendi)
    m.nome._value = scritto
    i = fake_interaction(guild=guild, user=fake_member(user_id=utente))
    i.client = MagicMock()
    i.client.get_user.return_value.send = AsyncMock()
    return m, i


async def test_reset_senza_dati_resta_il_reset_di_prima(ambiente):
    cog = _storico_cog()
    i = fake_interaction(guild=fake_guild(SERVER, owner_id=PROPRIETARIO), user=fake_member(user_id=PROPRIETARIO))
    await cog.reset.callback(cog, i)
    assert isinstance(i.response.send_message.call_args.kwargs["view"], storico.ResetConfirmView)


async def test_anche_i_dati_un_admin_non_apre_la_finestra(ambiente):
    cog = _storico_cog()
    i = fake_interaction(guild=fake_guild(SERVER, owner_id=PROPRIETARIO), user=fake_member(user_id=ALTRO_ADMIN))
    await cog.reset.callback(cog, i, True, False)
    i.response.send_modal.assert_not_called()
    assert "proprietario" in i.response.send_message.call_args.args[0]


async def test_anche_i_dati_il_proprietario_apre_la_finestra(ambiente):
    cog = _storico_cog()
    i = fake_interaction(guild=fake_guild(SERVER, owner_id=PROPRIETARIO), user=fake_member(user_id=PROPRIETARIO))
    await cog.reset.callback(cog, i, True, False)
    assert isinstance(i.response.send_modal.call_args.args[0], cog_modulo.ConfermaNomeModal)


async def test_finestra_nome_sbagliato_non_registra_niente(ambiente):
    guild = fake_guild(SERVER, "Il mio server", owner_id=PROPRIETARIO)
    m, i = _modale(guild, PROPRIETARIO, "il mio server")
    await m.on_submit(i)
    assert await logica.azzeramento_repo.get(SERVER) is None
    m, i = _modale(guild, ALTRO_ADMIN, "Il mio server")  # nome giusto ma non è il proprietario
    await m.on_submit(i)
    assert await logica.azzeramento_repo.get(SERVER) is None


async def test_finestra_nome_giusto_registra_e_avvisa(ambiente):
    guild = fake_guild(SERVER, "Il mio server", owner_id=PROPRIETARIO)
    m, i = _modale(guild, PROPRIETARIO, "Il mio server")
    await m.on_submit(i)
    assert (await logica.azzeramento_repo.get(SERVER)).stato == "attiva"
    i.client.get_user.return_value.send.assert_awaited_once()  # avviso all'inizio


async def test_annulla_dati_solo_proprietari(ambiente, monkeypatch):
    await logica.chiedi(SERVER, PROPRIETARIO, PROPRIETARIO, ADESSO)
    cog = _storico_cog()
    guild = fake_guild(SERVER, owner_id=PROPRIETARIO)
    admin = fake_interaction(guild=guild, user=fake_member(user_id=ALTRO_ADMIN))
    await cog.reset.callback(cog, admin, False, True)
    assert await logica.azzeramento_repo.get(SERVER) is not None
    monkeypatch.setattr(storico, "config_bot", SimpleNamespace(OWNER_ID=OWNER_BOT))
    owner_bot = fake_interaction(guild=guild, user=fake_member(user_id=OWNER_BOT))
    await cog.reset.callback(cog, owner_bot, False, True)
    assert await logica.azzeramento_repo.get(SERVER) is None


async def test_lavoro_esegui_sospende_se_il_proprietario_e_cambiato(ambiente):
    db, pool = ambiente
    await logica.chiedi(SERVER, PROPRIETARIO, PROPRIETARIO, ADESSO - timedelta(days=31))
    bot = MagicMock()
    guild = fake_guild(SERVER, "S", owner_id=NUOVO)
    bot.get_guild.return_value = guild
    bot.get_user.return_value.send = AsyncMock()
    cog = cog_modulo.AzzeramentoDatiCog.__new__(cog_modulo.AzzeramentoDatiCog)
    cog.bot = bot
    await cog.esegui(SERVER, PROPRIETARIO, {})
    assert (await logica.azzeramento_repo.get(SERVER)).stato == "sospesa"
    assert await db.get_guild_setting(SERVER, "log_channel_id") == 111
    bot.get_user.return_value.send.assert_awaited_once()  # il nuovo proprietario è avvisato


async def test_lavoro_esegui_cancella_se_tutto_e_in_regola(ambiente):
    db, pool = ambiente
    await logica.chiedi(SERVER, PROPRIETARIO, PROPRIETARIO, ADESSO - timedelta(days=31))
    bot = MagicMock()
    bot.get_guild.return_value = fake_guild(SERVER, "S", owner_id=PROPRIETARIO)
    bot.get_user.return_value.send = AsyncMock()
    cog = cog_modulo.AzzeramentoDatiCog.__new__(cog_modulo.AzzeramentoDatiCog)
    cog.bot = bot
    await cog.esegui(SERVER, PROPRIETARIO, {})
    assert await db.get_guild_setting(SERVER, "log_channel_id") is None

"""
tests/test_config_history_filtri.py
===================================
CFG-004 e CFG-005 (#122): storico delle modifiche con filtri (chi, tipo, date), vista prima/dopo e CSV.
"""

import csv
import io
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from core import config_history_logic as logica

pytestmark = pytest.mark.asyncio


async def _riempi(db, pool):
    await db.ensure_guild_exists(500)
    await db.set_module_active_for_guild(500, "automod", True, changed_by=11)
    await db.set_guild_setting(500, "welcome_channel_id", 7, changed_by=22)
    await db.set_guild_language(500, "en", changed_by=11)
    await db.ensure_guild_exists(501)
    await db.set_guild_setting(501, "welcome_channel_id", 9, changed_by=11)
    # date diverse, senza aspettare
    righe = await pool.fetch("SELECT id FROM guild_config_history WHERE guild_id = 500 ORDER BY id")
    for indice, r in enumerate(righe):
        await pool.execute(
            "UPDATE guild_config_history SET created_at = $2 WHERE id = $1",
            r["id"],
            datetime(2026, 10, 1 + indice * 5, 12, 0, tzinfo=timezone.utc),
        )
    return [r["id"] for r in righe]


@pytest.fixture
async def db_pronto(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    return database_module.db, clean_db


async def test_filtri_per_autore_tipo_e_date(db_pronto):
    db, pool = db_pronto
    ids = await _riempi(db, pool)
    tutte = await db.get_config_history_filtrato(500)
    assert [v.id for v in tutte] == sorted(ids, reverse=True)  # solo il server 500, dalla più recente
    assert {v.changed_by for v in await db.get_config_history_filtrato(500, changed_by=22)} == {22}
    assert [v.change_type for v in await db.get_config_history_filtrato(500, change_type="module")] == ["module"]
    dal = logica.leggi_data("2026-10-05")
    al = logica.fine_giornata(logica.leggi_data("2026-10-06"))
    # le modifiche sono del 1, 6 e 11 ottobre: tra il 5 e il 6 (compreso) c'è solo quella del 6
    assert [v.id for v in await db.get_config_history_filtrato(500, dal=dal, prima_del=al)] == [ids[1]]
    assert await db.get_config_history_filtrato(500, limit=2) == tutte[:2]


async def test_le_date_si_leggono_in_due_formati_e_si_rifiuta_il_resto():
    assert logica.leggi_data("2026-10-14") == datetime(2026, 10, 14, tzinfo=timezone.utc)
    assert logica.leggi_data("14/10/2026") == datetime(2026, 10, 14, tzinfo=timezone.utc)
    assert logica.leggi_data("ieri") is None and logica.leggi_data("") is None and logica.leggi_data(None) is None


async def test_csv_con_intestazione_bom_e_celle_senza_formule(db_pronto):
    db, pool = db_pronto
    await _riempi(db, pool)
    await db.set_guild_setting(500, "welcome_message", "=HYPERLINK(\"http://x\")", changed_by=33)
    contenuto = logica.csv_storico(await db.get_config_history_filtrato(500))
    assert contenuto.startswith(b"\xef\xbb\xbf")
    righe = list(csv.reader(io.StringIO(contenuto.decode("utf-8-sig"))))
    assert righe[0] == ["id", "data_utc", "autore", "tipo", "chiave", "prima", "dopo"]
    assert len(righe) == 5  # intestazione + 4 modifiche del server 500
    nuova = righe[1]
    assert nuova[2] == "33"
    assert nuova[6].startswith("'") is False  # il JSON comincia con una virgoletta
    assert not any(cella.startswith(("=", "+", "-", "@")) for riga in righe[1:] for cella in riga)


async def test_csv_neutralizza_una_chiave_che_inizia_con_formula():
    voce = MagicMock(id=1, changed_by=None, change_type="setting", key_name="=cmd|' /C calc'!A0", old_value=None,
                     new_value="+1", created_at=datetime(2026, 10, 1, tzinfo=timezone.utc))
    riga = list(csv.reader(io.StringIO(logica.csv_storico([voce]).decode("utf-8-sig"))))[1]
    assert riga[4].startswith("'=") and riga[6] == '"+1"'


async def test_vista_prima_dopo_sta_nei_limiti_di_discord(db_pronto):
    db, pool = db_pronto
    await _riempi(db, pool)
    lungo = "x" * 5000
    await db.set_guild_setting(500, "welcome_message", lungo, changed_by=1)
    voce = (await db.get_config_history_filtrato(500, limit=1))[0]
    testo = logica.dettaglio_prima_dopo(voce)
    assert "**Prima**" in testo and "**Dopo**" in testo and len(testo) < 2000


async def _cog(db_pronto):
    import cogs.utility.config_history as modulo

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await modulo.setup(bot)
    return bot, bot.get_cog("ConfigHistoryCog")


def _interazione(guild_id=500):
    i = MagicMock()
    i.guild.id = guild_id
    i.response.send_message = AsyncMock()
    i.response.is_done = MagicMock(return_value=False)
    i.followup.send = AsyncMock()
    return i


async def test_il_comando_mostra_solo_la_voce_del_proprio_server(db_pronto):
    db, pool = db_pronto
    ids = await _riempi(db, pool)
    altra = (await db.get_config_history_filtrato(501))[0].id
    bot, cog = await _cog(db_pronto)
    try:
        i = _interazione()
        await cog.history.callback(cog, i, 10, None, None, None, None, altra, False)
        assert "non trovata" in i.response.send_message.call_args.args[0]
        i = _interazione()
        await cog.history.callback(cog, i, 10, None, None, None, None, ids[0], False)
        assert "**Prima**" in i.response.send_message.call_args.args[0]
        i = _interazione()
        await cog.history.callback(cog, i, 10, None, None, "ieri", None, None, False)
        assert "Data non valida" in i.response.send_message.call_args.args[0]
        i = _interazione()
        await cog.history.callback(cog, i, 10, None, None, None, None, None, True)
        allegato = i.response.send_message.call_args.kwargs.get("file")
        assert allegato is not None and allegato.filename == "iyokai-storico-500.csv"
    finally:
        await bot.close()

"""
NF-04 (#37, #75): comandi `/utility privacy esporta|cancella` e
`/owner privacy richieste|approva|rifiuta`.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from core.command_groups import GRUPPI

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def cog(clean_db, monkeypatch):
    import cogs.utility.privacy as modulo
    import core.database as database_module
    from core.repositories.data_deletion_request_repo import DataDeletionRequestRepository

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(
        modulo, "data_deletion_request_repo", DataDeletionRequestRepository(pool_provider=lambda: clean_db)
    )
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await modulo.setup(bot)
    yield bot.get_cog("PrivacyCog"), modulo, clean_db
    await bot.close()


def _interazione(user_id=1001):
    i = MagicMock()
    i.user.id = user_id
    i.response.defer = AsyncMock()
    i.response.send_message = AsyncMock()
    i.followup.send = AsyncMock()
    return i


async def test_i_comandi_stanno_nei_gruppi_giusti(cog):
    _, _, _ = cog
    privacy_utente = GRUPPI["utility"].get_command("privacy")
    privacy_owner = GRUPPI["owner"].get_command("privacy")
    assert {c.name for c in privacy_utente.commands} == {"esporta", "cancella"}
    assert {c.name for c in privacy_owner.commands} == {"richieste", "approva", "rifiuta"}


async def test_esporta_manda_un_file_effimero_con_i_dati(cog):
    c, _, pool = cog
    await pool.execute("INSERT INTO rank_card_prefs (user_id, colore, tema) VALUES (1001, '#FFFFFF', 'scuro')")
    i = _interazione()

    await c.privacy_esporta.callback(c, i)

    i.response.defer.assert_awaited_once_with(ephemeral=True)
    chiamata = i.followup.send.await_args
    assert chiamata.kwargs["ephemeral"] is True
    file = chiamata.kwargs["file"]
    assert file.filename.endswith(".json")
    dati = json.loads(file.fp.read())
    assert dati["utente"] == 1001 and "rank_card_prefs" in dati["tabelle"]


async def test_cancella_crea_la_richiesta_e_spiega_cosa_resta(cog):
    c, modulo, pool = cog
    i = _interazione()

    await c.privacy_cancella.callback(c, i, "voglio uscire")

    i.response.defer.assert_awaited_once_with(ephemeral=True)
    testo = i.followup.send.await_args.args[0]
    assert "ban" in testo and "kick" in testo
    righe = await pool.fetch("SELECT * FROM data_deletion_requests")
    assert len(righe) == 1 and righe[0]["user_id"] == 1001 and righe[0]["motivo"] == "voglio uscire"


async def test_cancella_due_volte_non_crea_una_seconda_richiesta(cog):
    c, _, pool = cog
    await c.privacy_cancella.callback(c, _interazione(), None)
    i = _interazione()

    await c.privacy_cancella.callback(c, i, None)

    assert await pool.fetchval("SELECT count(*) FROM data_deletion_requests") == 1
    assert "già" in i.followup.send.await_args.args[0]


async def test_richieste_elenca_quelle_in_attesa(cog):
    c, _, _ = cog
    await c.privacy_cancella.callback(c, _interazione(1001), "x")
    i = _interazione(1)

    await c.privacy_richieste.callback(c, i)

    embed = i.response.send_message.await_args.kwargs["embed"]
    assert "1001" in embed.description


async def test_richieste_vuote(cog):
    c, _, _ = cog
    i = _interazione(1)

    await c.privacy_richieste.callback(c, i)

    assert "Nessuna" in i.response.send_message.await_args.args[0]


async def test_approva_cancella_avvisa_l_utente_e_riferisce(cog):
    c, _, pool = cog
    await pool.execute("INSERT INTO rank_card_prefs (user_id) VALUES (1001)")
    await c.privacy_cancella.callback(c, _interazione(1001), None)
    richiesta = await pool.fetchval("SELECT id FROM data_deletion_requests")
    utente = MagicMock()
    utente.send = AsyncMock()
    c.bot = MagicMock()
    c.bot.fetch_user = AsyncMock(return_value=utente)
    i = _interazione(1)

    await c.privacy_approva.callback(c, i, richiesta)

    assert await pool.fetchval("SELECT count(*) FROM rank_card_prefs") == 0
    utente.send.assert_awaited_once()
    assert "cancellate" in i.followup.send.await_args.args[0]


async def test_approva_con_dm_chiusi_funziona_lo_stesso(cog):
    c, _, pool = cog
    await c.privacy_cancella.callback(c, _interazione(1001), None)
    richiesta = await pool.fetchval("SELECT id FROM data_deletion_requests")
    utente = MagicMock()
    utente.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403, reason="x"), "dm chiusi"))
    c.bot = MagicMock()
    c.bot.fetch_user = AsyncMock(return_value=utente)
    i = _interazione(1)

    await c.privacy_approva.callback(c, i, richiesta)

    assert await pool.fetchval("SELECT stato FROM data_deletion_requests") == "eseguita"
    assert "messaggi privati" in i.followup.send.await_args.args[0]


async def test_approva_richiesta_inesistente(cog):
    c, _, _ = cog
    i = _interazione(1)

    await c.privacy_approva.callback(c, i, 999)

    assert "non trovata" in i.followup.send.await_args.args[0]


async def test_rifiuta_chiude_senza_cancellare(cog):
    c, _, pool = cog
    await pool.execute("INSERT INTO rank_card_prefs (user_id) VALUES (1001)")
    await c.privacy_cancella.callback(c, _interazione(1001), None)
    richiesta = await pool.fetchval("SELECT id FROM data_deletion_requests")
    utente = MagicMock()
    utente.send = AsyncMock()
    c.bot = MagicMock()
    c.bot.fetch_user = AsyncMock(return_value=utente)
    i = _interazione(1)

    await c.privacy_rifiuta.callback(c, i, richiesta, "richiesta incompleta")

    assert await pool.fetchval("SELECT stato FROM data_deletion_requests") == "rifiutata"
    assert await pool.fetchval("SELECT count(*) FROM rank_card_prefs") == 1
    assert "richiesta incompleta" in utente.send.await_args.args[0]

"""
tests/test_ticket_close_deletion.py
=======================================
Eliminazione del canale dopo /ticket close e /ticket forceclose.
BUG-1 (#2, #42): TextChannel.delete non accetta `delay`.
BUG-30: l'eliminazione passa dallo scheduler persistente, così un
riavvio o una ricarica del cog nei 10 secondi di attesa non lascia il
canale per sempre; forceclose funziona anche su un ticket già chiuso.
"""

from types import SimpleNamespace

import discord
import pytest
from discord.ext import commands

import cogs.tickets.tickets as tickets_module
from cogs.tickets.tickets import TICKET_DELETE_ACTION_TYPE
from core.repositories.ticket_repo import ticket_repo
from core.scheduler import Scheduler
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_text_channel

GUILD_ID = 100
CHANNEL_ID = 200


def _errore_http(classe, status: int):
    return classe(response=SimpleNamespace(status=status, reason="errore"), message="errore finto")


@pytest.fixture(autouse=True)
def _pool(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    return clean_db


@pytest.fixture
def scheduler_di_test(monkeypatch):
    """Uno scheduler vero (stesso database), separato da quello globale."""
    nuovo = Scheduler()
    monkeypatch.setattr(tickets_module, "scheduler", nuovo)
    return nuovo


@pytest.fixture
async def bot(scheduler_di_test):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await tickets_module.setup(bot)
    yield bot
    await bot.close()


@pytest.fixture
def canale(bot, monkeypatch):
    """Il canale del ticket, nella cache del bot come dopo il login."""
    canale = fake_text_channel(channel_id=CHANNEL_ID)
    canale.history.side_effect = _errore_http(discord.Forbidden, 403)
    monkeypatch.setattr(bot, "get_channel", lambda cid: canale if cid == CHANNEL_ID else None)
    return canale


def _interazione(canale, *, staff: bool = False):
    guild = fake_guild(guild_id=GUILD_ID)
    guild.get_channel.return_value = None
    guild.get_member.return_value = None
    interaction = fake_interaction(guild=guild, channel=canale)
    if staff:
        interaction.user.guild_permissions = discord.Permissions(manage_guild=True)
    return interaction


async def _apri_ticket(interaction) -> None:
    await ticket_repo.create_ticket(
        interaction.guild.id, interaction.user.id, interaction.channel.id, category_label="test"
    )


async def _azioni_pianificate(pool) -> list:
    return await pool.fetch(
        "SELECT * FROM scheduled_actions WHERE action_type = $1 ORDER BY id",
        TICKET_DELETE_ACTION_TYPE,
    )


async def _fai_passare_il_tempo(pool) -> None:
    await pool.execute(
        "UPDATE scheduled_actions SET execute_at = now() - interval '1 second', "
        "next_attempt_at = CASE WHEN next_attempt_at IS NULL THEN NULL "
        "ELSE now() - interval '1 second' END"
    )


def _cog(bot):
    return bot.get_cog("TicketsCog")


async def test_delete_non_accetta_il_parametro_delay():
    """BUG-1: sul finto autospec la vecchia chiamata solleva come col bot vero."""
    canale = fake_text_channel()
    with pytest.raises(TypeError):
        await canale.delete(reason="motivo", delay=10)


async def test_close_pianifica_l_eliminazione_nello_scheduler(bot, canale, clean_db):
    interaction = _interazione(canale)
    await _apri_ticket(interaction)

    await _cog(bot).close.callback(_cog(bot), interaction)

    interaction.response.send_message.assert_awaited_once()
    canale.delete.assert_not_awaited()  # non subito: dopo l'attesa
    assert (await ticket_repo.get_ticket_by_channel(CHANNEL_ID)).status == "closed"

    azioni = await _azioni_pianificate(clean_db)
    assert len(azioni) == 1
    assert azioni[0]["guild_id"] == GUILD_ID
    attesa = await clean_db.fetchval(
        "SELECT extract(epoch FROM execute_at - now()) FROM scheduled_actions WHERE id = $1",
        azioni[0]["id"],
    )
    assert 5 < attesa <= 10


async def test_close_poi_ricarica_del_cog_il_canale_viene_eliminato_lo_stesso(
    bot, canale, clean_db, scheduler_di_test
):
    """BUG-30: cog_unload (ricarica o bot.close) non deve perdere l'eliminazione."""
    interaction = _interazione(canale)
    await _apri_ticket(interaction)
    await _cog(bot).close.callback(_cog(bot), interaction)

    await bot.remove_cog("TicketsCog")  # chiama cog_unload, come un riavvio
    await tickets_module.setup(bot)

    await scheduler_di_test._run_due_actions()
    canale.delete.assert_not_awaited()  # i 10 secondi non sono ancora passati

    await _fai_passare_il_tempo(clean_db)
    await scheduler_di_test._run_due_actions()

    canale.delete.assert_awaited_once_with(reason=f"Ticket chiuso da {interaction.user}")
    assert (await _azioni_pianificate(clean_db))[0]["executed"] is True


async def test_close_con_transcript_che_esplode_pianifica_comunque_l_eliminazione(
    bot, canale, clean_db, monkeypatch
):
    interaction = _interazione(canale)
    await _apri_ticket(interaction)

    async def _transcript_rotto(*args, **kwargs):
        raise RuntimeError("errore imprevisto nel transcript")

    monkeypatch.setattr(_cog(bot), "_deliver_transcript", _transcript_rotto)

    await _cog(bot).close.callback(_cog(bot), interaction)  # non deve sollevare

    assert len(await _azioni_pianificate(clean_db)) == 1


async def test_eliminazione_rimandata_se_il_transcript_e_ancora_in_corso(
    bot, canale, clean_db, scheduler_di_test
):
    cog = _cog(bot)
    cog._transcript_in_corso.add(CHANNEL_ID)

    await cog.handle_ticket_delete_channel(GUILD_ID, 1, {"channel_id": CHANNEL_ID, "reason": "x"})

    canale.delete.assert_not_awaited()
    assert len(await _azioni_pianificate(clean_db)) == 1  # ripianificata


@pytest.mark.parametrize("classe, status", [(discord.NotFound, 404), (discord.Forbidden, 403)])
async def test_handler_non_solleva_su_404_e_403(bot, canale, classe, status):
    canale.delete.side_effect = _errore_http(classe, status)

    await _cog(bot).handle_ticket_delete_channel(
        GUILD_ID, 1, {"channel_id": CHANNEL_ID, "reason": "x"}
    )

    canale.delete.assert_awaited_once()


async def test_handler_canale_gia_sparito_non_solleva(bot, monkeypatch):
    """Canale non in cache e 404 da Discord: non c'è più nulla da eliminare."""
    richiesti = []

    async def _fetch_channel(channel_id):
        richiesti.append(channel_id)
        raise _errore_http(discord.NotFound, 404)

    monkeypatch.setattr(bot, "get_channel", lambda cid: None)
    monkeypatch.setattr(bot, "fetch_channel", _fetch_channel)

    await _cog(bot).handle_ticket_delete_channel(
        GUILD_ID, 1, {"channel_id": CHANNEL_ID, "reason": "x"}
    )

    assert richiesti == [CHANNEL_ID]


async def test_errore_5xx_viene_riprovato_dallo_scheduler(
    bot, canale, clean_db, scheduler_di_test
):
    interaction = _interazione(canale)
    await _apri_ticket(interaction)
    await _cog(bot).close.callback(_cog(bot), interaction)
    canale.delete.side_effect = _errore_http(discord.DiscordServerError, 503)

    await _fai_passare_il_tempo(clean_db)
    await scheduler_di_test._run_due_actions()

    azione = (await _azioni_pianificate(clean_db))[0]
    assert azione["executed"] is False and azione["attempts"] == 1
    assert azione["failed_reason"] is None

    canale.delete.side_effect = None  # Discord è tornato
    await _fai_passare_il_tempo(clean_db)
    await scheduler_di_test._run_due_actions()

    assert canale.delete.await_count == 2
    assert (await _azioni_pianificate(clean_db))[0]["executed"] is True


async def test_forceclose_elimina_subito_il_canale(bot, canale, clean_db):
    interaction = _interazione(canale, staff=True)
    await _apri_ticket(interaction)

    await _cog(bot).forceclose.callback(_cog(bot), interaction)

    canale.delete.assert_awaited_once()
    ticket = await ticket_repo.get_ticket_by_channel(CHANNEL_ID)
    assert ticket.status == "closed" and ticket.force_closed is True


async def test_forceclose_funziona_su_un_ticket_gia_chiuso_con_il_canale_rimasto(
    bot, canale, clean_db
):
    """BUG-30: il database dice "chiuso" ma il canale c'è ancora."""
    interaction = _interazione(canale, staff=True)
    await _apri_ticket(interaction)
    await ticket_repo.close_ticket(CHANNEL_ID, interaction.user.id)

    await _cog(bot).forceclose.callback(_cog(bot), interaction)

    canale.delete.assert_awaited_once()


async def test_forceclose_fuori_da_un_canale_ticket_rifiuta(bot, canale):
    interaction = _interazione(canale, staff=True)  # nessun ticket per questo canale

    await _cog(bot).forceclose.callback(_cog(bot), interaction)

    canale.delete.assert_not_awaited()
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True


async def test_forceclose_con_transcript_che_esplode_elimina_comunque(
    bot, canale, clean_db, monkeypatch
):
    interaction = _interazione(canale, staff=True)
    await _apri_ticket(interaction)

    async def _transcript_rotto(*args, **kwargs):
        raise RuntimeError("errore imprevisto nel transcript")

    monkeypatch.setattr(_cog(bot), "_deliver_transcript", _transcript_rotto)

    await _cog(bot).forceclose.callback(_cog(bot), interaction)

    canale.delete.assert_awaited_once()


async def test_forceclose_con_errore_5xx_ripianifica_l_eliminazione(bot, canale, clean_db):
    interaction = _interazione(canale, staff=True)
    await _apri_ticket(interaction)
    canale.delete.side_effect = _errore_http(discord.DiscordServerError, 503)

    await _cog(bot).forceclose.callback(_cog(bot), interaction)  # non deve sollevare

    assert len(await _azioni_pianificate(clean_db)) == 1

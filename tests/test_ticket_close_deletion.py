"""
tests/test_ticket_close_deletion.py
=======================================
BUG-1 (#2, #42): /ticket close chiamava channel.delete(delay=10), ma
TextChannel.delete non accetta `delay` (firma reale: (self, *,
reason=None)) — ogni chiusura andava in crash con TypeError, il
ticket restava chiuso nel database ma il canale non veniva mai
eliminato. fake_text_channel() (autospec) riproduce lo stesso errore
di discord.py vero, a differenza di un finto scritto a mano.

Il fix sposta l'attesa dei 10 secondi in una coroutine propria
(_elimina_dopo), lanciata come task tracciato in un set del cog (non
raccolto dal garbage collector) e cancellato in cog_unload.
"""

import asyncio

import discord
import pytest

from cogs.tickets.tickets import TicketsCog
from core.repositories.ticket_repo import ticket_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_text_channel


class _FakeHTTPResponse:
    status = 403
    reason = "Forbidden"


def _collega_pool_di_test(monkeypatch, clean_db) -> None:
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()


@pytest.fixture(autouse=True)
def _pool(monkeypatch, clean_db):
    _collega_pool_di_test(monkeypatch, clean_db)
    return clean_db


class _FakeBot:
    def __init__(self) -> None:
        self.loop = asyncio.get_event_loop()

    async def fetch_user(self, user_id: int):
        raise discord.NotFound(response=_FakeHTTPResponse(), message="non trovato")


async def _crea_ticket_aperto(guild_id: int, channel_id: int, user_id: int) -> None:
    await ticket_repo.create_ticket(guild_id, user_id, channel_id, category_label="test")


class TestElaminaDopoChiusura:
    @pytest.mark.asyncio
    async def test_delete_non_riceve_piu_il_parametro_delay(self):
        """
        Riproduzione diretta di BUG-1: la vecchia chiamata
        `channel.delete(reason=..., delay=10)` su un fake autospec
        solleva TypeError, esattamente come col bot vero.
        """
        canale = fake_text_channel()
        with pytest.raises(TypeError):
            await canale.delete(reason="motivo", delay=10)

    @pytest.mark.asyncio
    async def test_elimina_dopo_cancella_il_canale_senza_delay(self):
        cog = TicketsCog(_FakeBot())
        canale = fake_text_channel()

        await cog._elimina_dopo(canale, 0, "Ticket chiuso da test")

        canale.delete.assert_awaited_once_with(reason="Ticket chiuso da test")

    @pytest.mark.asyncio
    async def test_elimina_dopo_non_solleva_se_il_canale_e_gia_sparito(self):
        cog = TicketsCog(_FakeBot())
        canale = fake_text_channel()
        canale.delete.side_effect = discord.NotFound(
            response=_FakeHTTPResponse(), message="canale già eliminato"
        )

        await cog._elimina_dopo(canale, 0, "motivo")  # non deve sollevare

    @pytest.mark.asyncio
    async def test_pianifica_eliminazione_tiene_un_riferimento_al_task(self):
        cog = TicketsCog(_FakeBot())
        canale = fake_text_channel()

        cog._pianifica_eliminazione(canale, 0, "motivo")

        assert len(cog._eliminazioni_pianificate) == 1
        task = next(iter(cog._eliminazioni_pianificate))
        await task  # lascia finire il task per non sporcare il test successivo
        assert len(cog._eliminazioni_pianificate) == 0

    @pytest.mark.asyncio
    async def test_cog_unload_cancella_i_task_pendenti(self):
        cog = TicketsCog(_FakeBot())
        canale = fake_text_channel()

        cog._pianifica_eliminazione(canale, 10, "motivo")
        task = next(iter(cog._eliminazioni_pianificate))

        cog.cog_unload()
        await asyncio.sleep(0)  # lascia propagare la cancellazione

        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_ticket_close_non_va_piu_in_crash(self, clean_db):
        """
        Test end-to-end del comando /ticket close: prima del fix,
        andava in crash con TypeError prima ancora di rispondere
        all'utente.
        """
        guild = fake_guild(guild_id=100)
        channel = fake_text_channel(channel_id=200)
        channel.history.side_effect = discord.Forbidden(
            response=_FakeHTTPResponse(), message="niente permessi"
        )
        guild.get_channel.return_value = None
        guild.get_member.return_value = None

        interaction = fake_interaction(guild=guild, channel=channel)

        await _crea_ticket_aperto(guild.id, channel.id, interaction.user.id)

        cog = TicketsCog(_FakeBot())

        await cog.close.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        assert len(cog._eliminazioni_pianificate) == 1
        task = next(iter(cog._eliminazioni_pianificate))
        await task
        channel.delete.assert_awaited_once_with(
            reason=f"Ticket chiuso da {interaction.user}"
        )

        ticket = await ticket_repo.get_ticket_by_channel(channel.id)
        assert ticket.status == "closed"

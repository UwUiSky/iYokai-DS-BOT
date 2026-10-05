"""
tests/test_tickets_correzioni.py
================================
Correzioni al sistema di ticket (issue #62, voci M 6.x).

Database vero (clean_db) e repository veri. I ticket si aprono con il
codice di produzione (`_open_ticket_channel`, lo stesso del bottone
"Apri Ticket"); di Discord ci sono solo i finti fedeli di
tests/support/discord_fakes.py.
"""

from unittest.mock import MagicMock, create_autospec

import discord
import pytest
from discord import app_commands

import cogs.tickets.tickets as modulo
from cogs.tickets.tickets import TicketsCog, _open_ticket_channel
from core.database import db
from core.repositories.ticket_repo import ticket_repo
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_role,
    fake_text_channel,
)

ID_SERVER = 100
ID_UTENTE = 20
ID_STAFF = 30
ID_RUOLO_SUPPORTO = 500
ID_CATEGORIA = 900


@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID_SERVER, modulo.MODULE_TICKETS, True)
    yield
    database_module.db._modules_cache.clear()


def _errore_http(stato: int = 400) -> discord.HTTPException:
    return discord.HTTPException(MagicMock(status=stato, reason="errore"), "errore finto")


class Server:
    """Un server finto con una categoria che crea canali numerati da 1000."""

    def __init__(self) -> None:
        self.guild = fake_guild(ID_SERVER)
        self.guild.default_role = fake_role(role_id=ID_SERVER, name="@everyone", position=0)
        self.categoria = create_autospec(discord.CategoryChannel, instance=True)
        self.categoria.id = ID_CATEGORIA
        self.canali: list = []
        self.categoria.create_text_channel.side_effect = self._crea_canale

    async def _crea_canale(self, name, **kwargs):
        canale = fake_text_channel(1000 + len(self.canali), name)
        canale.guild = self.guild
        self.canali.append(canale)
        return canale

    def utente(self, user_id: int = ID_UTENTE, *, ruoli=None, manage_guild: bool = False):
        membro = fake_member(
            user_id,
            roles=ruoli or [],
            guild_permissions=discord.Permissions(manage_guild=manage_guild),
        )
        membro.guild = self.guild
        return membro

    def staff(self):
        return self.utente(ID_STAFF, manage_guild=True)

    def interazione(self, utente=None, canale=None):
        return fake_interaction(
            guild=self.guild, user=utente or self.utente(), channel=canale
        )

    async def apri_ticket(self, utente=None, etichetta=None):
        """Apre un ticket come fa il bottone del pannello. Restituisce il canale."""
        interazione = self.interazione(utente)
        await _open_ticket_channel(interazione, self.guild, self.categoria, etichetta)
        return self.canali[-1]


def _testo(chiamata) -> str:
    return chiamata.args[0] if chiamata.args else chiamata.kwargs.get("content", "")


# ====================================================================
# M 6.6 — claim, priority, add e remove sono riservati allo staff
# ====================================================================
async def _claim(cog, interazione, membro):
    await cog.claim.callback(cog, interazione)


async def _priority(cog, interazione, membro):
    await cog.priority.callback(cog, interazione, app_commands.Choice(name="urgent", value="urgent"))


async def _add(cog, interazione, membro):
    await cog.add.callback(cog, interazione, membro)


async def _remove(cog, interazione, membro):
    await cog.remove.callback(cog, interazione, membro)


COMANDI_STAFF = {"claim": _claim, "priority": _priority, "add": _add, "remove": _remove}


@pytest.mark.parametrize("nome", COMANDI_STAFF)
async def test_chi_ha_aperto_il_ticket_non_puo_usare_i_comandi_dello_staff(nome):
    server = Server()
    canale = await server.apri_ticket()
    interazione = server.interazione(server.utente(), canale)
    cog = TicketsCog(bot=None)

    await COMANDI_STAFF[nome](cog, interazione, server.utente(77))

    risposta = interazione.response.send_message.call_args
    assert "Solo lo staff" in _testo(risposta)
    assert risposta.kwargs["ephemeral"] is True
    canale.set_permissions.assert_not_awaited()
    ticket = await ticket_repo.get_ticket_by_channel(canale.id)
    assert ticket.claimed_by is None
    assert ticket.priority == "normal"


@pytest.mark.parametrize("nome", COMANDI_STAFF)
async def test_lo_staff_puo_usare_i_comandi(nome):
    server = Server()
    canale = await server.apri_ticket()
    interazione = server.interazione(server.staff(), canale)
    cog = TicketsCog(bot=None)

    await COMANDI_STAFF[nome](cog, interazione, server.utente(77))

    assert "Solo lo staff" not in _testo(interazione.response.send_message.call_args)
    ticket = await ticket_repo.get_ticket_by_channel(canale.id)
    if nome == "claim":
        assert ticket.claimed_by == ID_STAFF
    elif nome == "priority":
        assert ticket.priority == "urgent"
    else:
        canale.set_permissions.assert_awaited_once()


async def test_un_ruolo_di_supporto_puo_prendere_in_carico():
    server = Server()
    canale = await server.apri_ticket()
    cog = TicketsCog(bot=None)
    admin = server.interazione(server.staff())
    ruolo = fake_role(ID_RUOLO_SUPPORTO, "Supporto")
    await cog.ticket_support_role_add.callback(cog, admin, ruolo)

    operatore = server.utente(40, ruoli=[ruolo])
    await cog.claim.callback(cog, server.interazione(operatore, canale))

    assert (await ticket_repo.get_ticket_by_channel(canale.id)).claimed_by == 40


@pytest.mark.parametrize("nome", ("add", "remove"))
async def test_add_e_remove_errore_di_discord_risposta_chiara(nome):
    server = Server()
    canale = await server.apri_ticket()
    canale.set_permissions.side_effect = _errore_http(403)
    interazione = server.interazione(server.staff(), canale)
    cog = TicketsCog(bot=None)

    await COMANDI_STAFF[nome](cog, interazione, server.utente(77))

    assert "Non sono riuscito" in _testo(interazione.response.send_message.call_args)


# ====================================================================
# M 6.7 — /ticket-support-role remove toglie anche il ruolo storico
# ====================================================================
async def test_remove_toglie_il_ruolo_impostato_con_ticket_setup():
    server = Server()
    ruolo = fake_role(ID_RUOLO_SUPPORTO, "Supporto")
    server.guild.get_role.side_effect = lambda role_id: ruolo if role_id == ID_RUOLO_SUPPORTO else None
    cog = TicketsCog(bot=None)
    # Il ruolo "storico" lo scrive /ticket-setup.
    await cog.ticket_setup.callback(cog, server.interazione(server.staff()), server.categoria, ruolo)
    assert await modulo._support_role_ids(ID_SERVER) == [ID_RUOLO_SUPPORTO]

    await cog.ticket_support_role_remove.callback(cog, server.interazione(server.staff()), ruolo)

    assert await modulo._support_role_ids(ID_SERVER) == []
    # Il ruolo non vede più i ticket nuovi…
    await server.apri_ticket()
    permessi = server.categoria.create_text_channel.call_args.kwargs["overwrites"]
    assert ruolo not in permessi
    # …e chi lo ha non è più staff.
    operatore = server.interazione(server.utente(40, ruoli=[ruolo]))
    assert await modulo._is_ticket_staff(operatore) is False


async def test_remove_del_ruolo_storico_non_lascia_un_null_nella_configurazione():
    """Un `null` nell'export verrebbe poi rifiutato da /config import."""
    server = Server()
    ruolo = fake_role(ID_RUOLO_SUPPORTO, "Supporto")
    cog = TicketsCog(bot=None)
    await cog.ticket_setup.callback(cog, server.interazione(server.staff()), server.categoria, ruolo)

    await cog.ticket_support_role_remove.callback(cog, server.interazione(server.staff()), ruolo)

    impostazioni = (await db.get_full_config(ID_SERVER))["settings"]
    assert modulo.SETTING_SUPPORT_ROLE not in impostazioni


async def test_remove_di_un_ruolo_non_configurato_lo_dice():
    server = Server()
    cog = TicketsCog(bot=None)
    interazione = server.interazione(server.staff())

    await cog.ticket_support_role_remove.callback(cog, interazione, fake_role(123, "Altro"))

    assert "non è tra i ruoli di supporto" in _testo(interazione.response.send_message.call_args)


# ====================================================================
# M 6.5 — un canale cancellato a mano chiude il ticket
# ====================================================================
async def test_canale_cancellato_a_mano_l_utente_puo_riaprire():
    server = Server()
    primo = await server.apri_ticket()
    cog = TicketsCog(bot=None)

    await cog.on_guild_channel_delete(primo)

    ticket = await ticket_repo.get_ticket_by_channel(primo.id)
    assert ticket.status == "closed"
    assert ticket.closed_at is not None
    assert ticket.closed_by is None  # non sappiamo chi ha cancellato il canale
    secondo = await server.apri_ticket()
    assert secondo.id != primo.id
    assert (await ticket_repo.get_ticket_by_channel(secondo.id)).status == "open"


async def test_canale_qualunque_cancellato_non_tocca_i_ticket():
    server = Server()
    canale = await server.apri_ticket()
    cog = TicketsCog(bot=None)

    await cog.on_guild_channel_delete(fake_text_channel(424242, "altro"))

    assert (await ticket_repo.get_ticket_by_channel(canale.id)).status == "open"


async def test_canale_di_un_ticket_gia_chiuso_non_cambia_chi_lo_ha_chiuso():
    server = Server()
    canale = await server.apri_ticket()
    await ticket_repo.close_ticket(canale.id, ID_STAFF)
    cog = TicketsCog(bot=None)

    await cog.on_guild_channel_delete(canale)

    assert (await ticket_repo.get_ticket_by_channel(canale.id)).closed_by == ID_STAFF

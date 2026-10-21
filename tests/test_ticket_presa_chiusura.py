"""
tests/test_ticket_presa_chiusura.py
===================================
#120 (catalogo ticket): presa in carico con categoria, esclusiva e testi (TKT-028, 050, 053),
squadra del pannello (TKT-044), assegnazione al primo che risponde (TKT-052), conferma e
chi può chiudere (TKT-054, 057), DM, ruoli e transcript alla chiusura (TKT-039, 043, 075),
thread delle note (TKT-034), richiesta di chiusura (TKT-055). Database vero; Discord finto.
"""

from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest

import cogs.tickets.tickets as modulo
from core.database import db
from core.repositories.ticket_form_repo import ticket_form_repo
from core.repositories.ticket_opzioni_repo import ticket_opzioni_repo
from core.repositories.ticket_repo import ticket_repo
from core.scheduler import Scheduler
from tests.support.discord_fakes import fake_interaction, fake_text_channel
from tests.test_ticket_opzioni import ID_CATEGORIA, ID_SERVER, RUOLO_SQUADRA, RUOLO_VIP, STAFF, UTENTE, Server

CANALE = 4000
ID_PRESI = 902


@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(modulo, "scheduler", Scheduler())
    database_module.db._modules_cache.clear()
    yield
    database_module.db._modules_cache.clear()


async def _scena(**opzioni):
    s = Server()
    p = await ticket_form_repo.crea_pannello(ID_SERVER, "Supporto", ID_CATEGORIA, "Apri")
    if opzioni:
        await ticket_opzioni_repo.imposta(p.id, **opzioni)
    await ticket_repo.create_ticket(ID_SERVER, UTENTE, CANALE, ticket_number=7, panel_id=p.id)
    canale = fake_text_channel(CANALE)
    canale.guild = s.guild
    canale.overwrites_for = MagicMock(side_effect=lambda _x: discord.PermissionOverwrite())
    return s, canale


def _inter(s, user, canale):
    return fake_interaction(guild=s.guild, user=user, channel=canale)


def _cog():
    return modulo.TicketsCog(bot=None)


def _testi(inter) -> str:
    return str(inter.response.send_message.call_args) + str(inter.followup.send.call_args)


# ---------------------------------------------------------------- presa in carico
async def test_presa_sposta_il_ticket_chiude_la_scrittura_allo_staff_e_usa_il_testo():
    s, canale = await _scena(categoria_presi=ID_PRESI, claim_esclusivo="scrivere", ruoli_staff=(RUOLO_SQUADRA,),
                             testo_presa="Ciao {utente}, ti segue {staff}.")
    presi = create_autospec(discord.CategoryChannel, instance=True)
    presi.id, presi.channels = ID_PRESI, []
    vecchio = s.guild.get_channel.side_effect
    s.guild.get_channel = MagicMock(side_effect=lambda i: presi if i == ID_PRESI else vecchio(i))
    squadra = s.membro(STAFF, ruoli=(RUOLO_SQUADRA,))
    inter = _inter(s, squadra, canale)
    await _cog().claim.callback(_cog(), inter)

    assert (await ticket_repo.get_ticket_by_channel(CANALE)).claimed_by == STAFF
    canale.edit.assert_awaited_once()
    assert canale.edit.call_args.kwargs["category"] is presi
    per_ruolo = {c.args[0]: c.kwargs["overwrite"] for c in canale.set_permissions.await_args_list}
    assert per_ruolo[s.ruoli[RUOLO_SQUADRA]].send_messages is False
    assert per_ruolo[squadra].send_messages is True
    assert f"<@{UTENTE}>" in inter.followup.send.call_args.args[0]


async def test_rilascio_rimette_lo_staff_e_usa_il_testo():
    s, canale = await _scena(claim_esclusivo="vedere", ruoli_staff=(RUOLO_SQUADRA,), testo_rilascio="Libero!")
    squadra = s.membro(STAFF, ruoli=(RUOLO_SQUADRA,))
    await ticket_repo.claim_ticket(CANALE, STAFF)
    inter = _inter(s, squadra, canale)
    await _cog().rilascia.callback(_cog(), inter)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).claimed_by is None
    ow = canale.set_permissions.await_args_list[-1].kwargs["overwrite"]
    assert ow.view_channel is True and ow.send_messages is True
    assert inter.followup.send.call_args.args[0] == "Libero!"


async def test_chi_non_e_della_squadra_del_pannello_non_e_staff():
    s, canale = await _scena(ruoli_staff=(RUOLO_SQUADRA,))
    inter = _inter(s, s.membro(STAFF, ruoli=(RUOLO_VIP,)), canale)
    await _cog().claim.callback(_cog(), inter)
    assert "Solo lo staff" in _testi(inter)


async def test_il_primo_dello_staff_che_scrive_prende_il_ticket():
    s, canale = await _scena(assegna_auto=True, ruoli_staff=(RUOLO_SQUADRA,))
    canale.send = AsyncMock()
    cog = _cog()
    for uid in (STAFF, STAFF + 1):
        autore = s.membro(uid, ruoli=(RUOLO_SQUADRA,))
        messaggio = MagicMock(guild=s.guild, channel=canale, author=autore)
        autore.bot = False
        await cog.on_message(messaggio)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).claimed_by == STAFF
    canale.send.assert_awaited_once()


# ---------------------------------------------------------------- chiusura
async def test_se_l_utente_non_puo_chiudere_lo_chiude_solo_lo_staff():
    s, canale = await _scena(utente_chiude=False)
    inter = _inter(s, s.membro(UTENTE), canale)
    await _cog().close.callback(_cog(), inter, None)
    assert "lo staff" in _testi(inter)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).status == "open"
    cog = _cog()
    cog._transcript_senza_bloccare = AsyncMock()
    await cog.close.callback(cog, _inter(s, s.membro(STAFF, admin=True), canale), None)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).status == "closed"


async def test_con_la_conferma_si_chiude_solo_dopo_il_bottone():
    s, canale = await _scena(conferma_chiusura=True)
    cog = _cog()
    cog._transcript_senza_bloccare = AsyncMock()
    utente = s.membro(UTENTE)
    inter = _inter(s, utente, canale)
    await cog.close.callback(cog, inter, "fatto")
    vista = inter.response.send_message.call_args.kwargs["view"]
    assert isinstance(vista, modulo.ConfermaChiusura)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).status == "open"
    clic = _inter(s, utente, canale)
    await vista.conferma.callback(clic)
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    assert t.status == "closed" and t.close_reason == "fatto"


async def test_alla_chiusura_ruoli_tolti_dm_scelto_e_transcript_senza_dm():
    s, canale = await _scena(dm_chiusura="Grazie {utente}!", transcript_dm=False)
    utente = s.membro(UTENTE, ruoli=(RUOLO_VIP,))
    utente.remove_roles = AsyncMock()
    await ticket_repo.set_ruoli_dati(CANALE, [RUOLO_VIP])
    cog = _cog()
    cog._deliver_transcript = AsyncMock()
    ticket = await ticket_repo.get_ticket_by_channel(CANALE)
    await cog._transcript_senza_bloccare(s.guild, canale, ticket)
    assert cog._deliver_transcript.call_args.kwargs["dm"] is False
    utente.remove_roles.assert_awaited_once()
    assert "Grazie" in utente.send.call_args.args[0]


# ---------------------------------------------------------------- note e richiesta di chiusura
async def test_note_crea_il_thread_una_volta_sola():
    s, canale = await _scena()
    thread = MagicMock(id=4242, mention="<#4242>", add_user=AsyncMock())
    canale.create_thread = AsyncMock(return_value=thread)
    s.guild.get_thread = MagicMock(side_effect=lambda i: thread if i == 4242 else None)
    staff = s.membro(STAFF, admin=True)
    await _cog().note.callback(_cog(), _inter(s, staff, canale))
    await _cog().note.callback(_cog(), _inter(s, staff, canale))
    canale.create_thread.assert_awaited_once()
    assert canale.create_thread.call_args.kwargs["type"] is discord.ChannelType.private_thread
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).note_thread_id == 4242


async def test_richiesta_di_chiusura_rifiutata_poi_scaduta_non_chiude():
    s, canale = await _scena()
    cog = _cog()
    await cog.chiedi_chiusura.callback(cog, _inter(s, s.membro(STAFF, admin=True), canale), 2)
    ticket = await ticket_repo.get_ticket_by_channel(CANALE)
    payload = {"channel_id": CANALE, "richiesta": ticket.chiusura_richiesta_at.isoformat()}
    rifiuta = modulo.BottoneRichiestaChiusura(ticket.id, "r")
    await rifiuta.callback(_inter(s, s.membro(UTENTE), canale))
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).chiusura_richiesta_at is None
    cog._chiudi_da_sistema = AsyncMock()
    await cog.handle_richiesta_chiusura(ID_SERVER, UTENTE, payload)
    cog._chiudi_da_sistema.assert_not_awaited()


async def test_richiesta_di_chiusura_senza_risposta_chiude():
    s, canale = await _scena()
    cog = _cog()
    await cog.chiedi_chiusura.callback(cog, _inter(s, s.membro(STAFF, admin=True), canale), 2)
    ticket = await ticket_repo.get_ticket_by_channel(CANALE)
    cog.bot = MagicMock(get_channel=MagicMock(return_value=canale))
    cog._chiudi_da_sistema = AsyncMock()
    await cog.handle_richiesta_chiusura(
        ID_SERVER, UTENTE, {"channel_id": CANALE, "richiesta": ticket.chiusura_richiesta_at.isoformat()}
    )
    cog._chiudi_da_sistema.assert_awaited_once()


async def test_accetta_la_chiusura_solo_chi_ha_aperto():
    s, canale = await _scena()
    await ticket_repo.richiedi_chiusura(CANALE)
    ticket = await ticket_repo.get_ticket_by_channel(CANALE)
    bottone = modulo.BottoneRichiestaChiusura(ticket.id, "a")
    estraneo = _inter(s, s.membro(UTENTE + 9), canale)
    await bottone.callback(estraneo)
    assert "Risponde solo" in _testi(estraneo)
    cog = _cog()
    cog._transcript_senza_bloccare = AsyncMock()
    cog._richiedi_voto = AsyncMock()
    inter = _inter(s, s.membro(UTENTE), canale)
    inter.client.get_cog = MagicMock(return_value=cog)
    await bottone.callback(inter)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).status == "closed"


async def test_se_l_utente_scrive_nel_ticket_la_richiesta_di_chiusura_decade():
    """«Se non rispondi entro N ore»: scrivere «no, non va ancora» è una risposta, il ticket non si chiude."""
    s, canale = await _scena()
    cog = _cog()
    await cog.chiedi_chiusura.callback(cog, _inter(s, s.membro(STAFF, admin=True), canale), 2)
    ticket = await ticket_repo.get_ticket_by_channel(CANALE)
    payload = {"channel_id": CANALE, "richiesta": ticket.chiusura_richiesta_at.isoformat()}
    messaggio = MagicMock(guild=s.guild, channel=canale, author=s.membro(UTENTE), content="non funziona ancora")
    messaggio.author.bot = False
    await cog.on_message(messaggio)
    cog.bot = MagicMock(get_channel=MagicMock(return_value=canale))
    cog._chiudi_da_sistema = AsyncMock()
    await cog.handle_richiesta_chiusura(ID_SERVER, UTENTE, payload)
    cog._chiudi_da_sistema.assert_not_awaited()

"""
tests/test_support_service.py
=============================
SPEC B.9, B.2 (#107): assistenza e segnalazioni di iYokai App, database vero e canali finti fedeli.
"""

from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest

from core import support_service as ss
from core.repositories.user_app_repo import UserAppRepository
from tests.support.discord_fakes import fake_message, fake_text_channel


@pytest.fixture(autouse=True)
def db_vero(monkeypatch, clean_db):
    repo = UserAppRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(ss, "user_app_repo", repo)
    return repo


def _thread(thread_id=900):
    t = create_autospec(discord.Thread, instance=True)
    t.id = thread_id
    return t


def _client(canale):
    client = MagicMock()
    client.get_channel = MagicMock(side_effect=lambda i: canale if i == canale.id else None)
    client.fetch_user = AsyncMock()
    return client


async def test_la_richiesta_apre_un_thread_e_salva_il_numero(db_vero):
    canale = fake_text_channel(55)
    thread = _thread(901)
    canale.create_thread = AsyncMock(return_value=thread)

    aperta = await ss.apri_richiesta(_client(canale), 55, 7, "Anna", "Non va", "Il bot non risponde")

    assert aperta.thread_id == 901
    assert ss.titolo_thread(aperta.numero, "Non va") == canale.create_thread.await_args.kwargs["name"]
    assert "ID 7" in thread.send.await_args.args[0]
    assert thread.send.await_args.kwargs["allowed_mentions"].everyone is False
    assert (await db_vero.richiesta(aperta.numero))["thread_id"] == 901


async def test_senza_canale_non_si_salva_niente(db_vero):
    with pytest.raises(ss.SupportoNonAttivo):
        await ss.apri_richiesta(_client(fake_text_channel(55)), 0, 7, "Anna", "x", "y")
    assert await db_vero.richieste_utente(7) == []


async def test_troppe_richieste_aperte(db_vero):
    canale = fake_text_channel(55)
    canale.create_thread = AsyncMock(side_effect=lambda **kw: _thread(len(canale.create_thread.await_args_list) + 1000))
    for _ in range(3):
        await ss.apri_richiesta(_client(canale), 55, 7, "Anna", "x", "y")
    with pytest.raises(ss.TroppeRichieste):
        await ss.apri_richiesta(_client(canale), 55, 7, "Anna", "x", "y")


async def test_thread_non_creato_chiude_la_richiesta(db_vero):
    canale = fake_text_channel(55)
    canale.create_thread = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=403), "no"))
    with pytest.raises(ss.SupportoNonAttivo):
        await ss.apri_richiesta(_client(canale), 55, 7, "Anna", "x", "y")
    assert (await db_vero.richieste_utente(7))[0]["stato"] == "chiusa"


async def test_risposta_dell_utente_solo_sulla_propria_richiesta_aperta(db_vero):
    canale = fake_text_channel(55)
    thread = _thread(902)
    canale.create_thread = AsyncMock(return_value=thread)
    client = _client(canale)
    client.get_channel = MagicMock(side_effect=lambda i: {55: canale, 902: thread}.get(i))
    aperta = await ss.apri_richiesta(client, 55, 7, "Anna", "x", "y")

    await ss.risposta_dell_utente(client, 7, aperta.numero, "ancora io")
    assert "ancora io" in thread.send.await_args.args[0]
    with pytest.raises(ss.RichiestaNonTrovata):
        await ss.risposta_dell_utente(client, 8, aperta.numero, "intruso")
    await db_vero.chiudi_richiesta(aperta.numero)
    with pytest.raises(ss.RichiestaNonTrovata):
        await ss.risposta_dell_utente(client, 7, aperta.numero, "tardi")


async def test_staff_risponde_e_l_utente_riceve_in_dm(db_vero):
    canale = fake_text_channel(55)
    thread = _thread(903)
    thread.id = 903
    canale.create_thread = AsyncMock(return_value=thread)
    client = _client(canale)
    aperta = await ss.apri_richiesta(client, 55, 7, "Anna", "x", "y")
    utente = MagicMock()
    utente.send = AsyncMock()
    client.fetch_user.return_value = utente

    staff = fake_message(1, content="Prova a rientrare nel server")
    staff.author.bot = False
    staff.channel = thread
    assert await ss.inoltra_risposta_staff(client, staff)
    assert "Prova a rientrare" in utente.send.await_args.args[0] and f"#{aperta.numero}" in utente.send.await_args.args[0]

    bot = fake_message(2, content="x")
    bot.author.bot = True
    bot.channel = thread
    assert not await ss.inoltra_risposta_staff(client, bot)
    altro = fake_message(3, content="in un altro thread")
    altro.author.bot = False
    altro.channel = _thread(999)
    assert not await ss.inoltra_risposta_staff(client, altro)


async def test_thread_archiviato_chiude_la_richiesta(db_vero):
    canale = fake_text_channel(55)
    thread = _thread(904)
    canale.create_thread = AsyncMock(return_value=thread)
    client = _client(canale)
    aperta = await ss.apri_richiesta(client, 55, 7, "Anna", "x", "y")
    utente = MagicMock()
    utente.send = AsyncMock()
    client.fetch_user.return_value = utente

    assert await ss.chiudi_se_archiviato(client, thread)
    assert "chiusa" in utente.send.await_args.args[0]
    assert (await db_vero.richiesta(aperta.numero))["stato"] == "chiusa"
    assert not await ss.chiudi_se_archiviato(client, thread)  # una volta sola

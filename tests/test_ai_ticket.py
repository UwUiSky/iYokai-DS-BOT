"""
tests/test_ai_ticket.py
=======================
Ticket con l'AI (§25.65, §25.66, §25.97): prima risposta automatica una sola volta e solo se accesa, bottone
persistente, parole chiave scelte anche dall'AI, file delle risposte standard conservati nel database.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.ai import ticket_ai
from core import ticket_ai_parole_logic as parole
from core.ai_servizio import imposta_servizio_ai
from core.database import db
from core.repositories.ai_repo import ai_repo
from core.repositories.ai_ticket_repo import ai_ticket_repo
from tests.support.ai_finto import TrasportoFinto, fornitore, servizio_finto
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel

G, U, CH, PANNELLO = 9001, 9002, 9003, 7


def test_parole_dell_ai_lette_con_cura_e_unite_a_quelle_contate():
    assert parole.leggi_parole(json.dumps({"parole": ["Rimborso", "soldi indietro", 5, "il"]})) == ["rimbor", "soldi", "indiet"]
    assert parole.leggi_parole("non json") == [] and parole.leggi_parole(json.dumps({"parole": "x"})) == []
    assert parole.unisci(["a", "b"], ["b", "c"]) == ["a", "b", "c"]


@pytest.fixture
def repo(clean_db, monkeypatch):
    for r in (ai_ticket_repo, ai_repo):
        monkeypatch.setattr(r, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(db, "_pool", clean_db, raising=False)
    yield clean_db
    imposta_servizio_ai(None)


def _ticket(**kw):
    base = dict(guild_id=G, user_id=U, panel_id=PANNELLO, status="open", standard_reply_id=None, first_response_at=None)
    return SimpleNamespace(**{**base, **kw})


async def _con_ai(repo, risposta="Leggi le regole nel canale #regole."):
    servizio, trasporto = servizio_finto(ai_repo, fornitori=[fornitore(fascia="media")], trasporto=TrasportoFinto(risposte={"alfa": risposta}))
    imposta_servizio_ai(servizio)
    await ai_repo.registra_consenso(G, U, True)
    return trasporto


async def test_prima_risposta_solo_se_accesa_una_volta_e_con_ai(repo):
    cog = ticket_ai.AiTicketCog(MagicMock())
    canale = fake_text_channel(channel_id=CH)
    t = _ticket()
    assert await cog.prima_risposta(canale, t, "Come funzionano le regole?") is False  # pannello spento
    await ai_ticket_repo.imposta_prima_risposta(G, PANNELLO, True)
    assert await cog.prima_risposta(canale, t, "Come funzionano le regole?") is False  # AI ferma
    assert not canale.send.await_count
    await _con_ai(repo)
    assert await cog.prima_risposta(canale, t, "Come funzionano le regole?") is True  # il posto si era liberato
    assert "regole" in canale.send.call_args.kwargs["embed"].description
    assert await cog.prima_risposta(canale, t, "ancora?") is False  # una sola volta
    assert canale.send.await_count == 1


async def test_il_primo_messaggio_dell_utente_fa_partire_la_risposta(repo, monkeypatch):
    await ai_ticket_repo.imposta_prima_risposta(G, PANNELLO, True)
    await _con_ai(repo)
    t = _ticket()
    monkeypatch.setattr(ticket_ai.ticket_repo, "get_ticket_by_channel", AsyncMock(return_value=t))
    monkeypatch.setattr(ticket_ai.asyncio, "sleep", AsyncMock())
    cog = ticket_ai.AiTicketCog(MagicMock())
    canale = fake_text_channel(channel_id=CH)
    msg = MagicMock(guild=fake_guild(G), channel=canale, content="aiuto con le regole")
    msg.author = MagicMock(id=U, bot=False)
    await cog.on_message(msg)
    assert canale.send.await_count == 1
    # un messaggio dello staff, o di un altro utente, non fa partire niente
    altro = MagicMock(guild=fake_guild(G), channel=fake_text_channel(channel_id=CH + 1), content="x")
    altro.author = MagicMock(id=U + 1, bot=False)
    await cog.on_message(altro)
    # se lo staff ha già risposto, l'AI non si aggiunge
    monkeypatch.setattr(ticket_ai.ticket_repo, "get_ticket_by_channel", AsyncMock(return_value=_ticket(first_response_at=1)))
    canale2 = fake_text_channel(channel_id=CH + 2)
    msg2 = MagicMock(guild=fake_guild(G), channel=canale2, content="ciao")
    msg2.author = MagicMock(id=U, bot=False)
    await cog.on_message(msg2)
    canale2.send.assert_not_awaited()


async def test_comando_prima_risposta_per_pannello(repo, monkeypatch):
    monkeypatch.setattr(ticket_ai.ticket_form_repo, "pannello_per_nome", AsyncMock(side_effect=lambda g, n: SimpleNamespace(id=PANNELLO, name=n) if n == "Supporto" else None))
    cog = ticket_ai.AiTicketCog(MagicMock())
    i = fake_interaction(guild=fake_guild(G), user=fake_member(U)); i.guild_id = G
    await cog.prima_risposta_cmd.callback(cog, i, "Boh", True)
    assert "Nessun pannello" in i.response.send_message.call_args.args[0]
    await cog.prima_risposta_cmd.callback(cog, i, "Supporto", True)
    assert await ai_ticket_repo.prima_risposta_attiva(G, PANNELLO) is True


def test_il_bottone_e_persistente_con_id_fisso():
    vista = ticket_ai.AssistenteTicketView()
    assert vista.timeout is None and [c.custom_id for c in vista.children] == ["aitk:chiedi"]


async def test_file_delle_risposte_standard_restano_nel_database(repo):
    r = await repo.fetchval("INSERT INTO ticket_panels (guild_id, name, category_id, button_label) VALUES ($1, 'P', 1, 'b') RETURNING id", G)
    rid = await repo.fetchval(
        "INSERT INTO ticket_standard_replies (guild_id, panel_id, title, keywords, body) VALUES ($1, $2, 't', 'k', 'b') RETURNING id", G, r
    )
    assert await ai_ticket_repo.salva_allegati(G, rid, [("a.png", b"\x89PNG"), ("b.txt", b"ciao")]) == 2
    assert await ai_ticket_repo.allegati_di(rid) == [("a.png", b"\x89PNG"), ("b.txt", b"ciao")]
    await repo.execute("DELETE FROM ticket_standard_replies WHERE id = $1", rid)
    assert await ai_ticket_repo.allegati_di(rid) == []  # spariscono con la risposta

"""
tests/test_ticket_trascrizioni_conservazione.py
===============================================
TKT-072 (D111): conservazione cifrata per 90 giorni. Il dato salvato non contiene il testo in chiaro, scade, si pulisce,
senza chiave non si salva, e il server può accorciare o spegnere. Database vero.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core import data_registry, retention_worker
from core import ticket_trascrizioni_logic as logica
from core import ticket_trascrizioni_servizio as servizio
from core.oauth_crypto import generate_key
from core.repositories.ticket_repo import ticket_repo
from core.repositories.ticket_trascrizioni_repo import ticket_trascrizioni_repo as repo

GUILD = 8800


@pytest.fixture
async def conn(clean_db, monkeypatch):
    monkeypatch.setattr(repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(ticket_repo, "_pool_provider", lambda: clean_db)
    chiave = generate_key()
    monkeypatch.setattr(servizio, "config", SimpleNamespace(TICKET_TRASCRIZIONI_KEY=chiave, OAUTH_ENCRYPTION_KEY=""))
    await ticket_repo.create_ticket(GUILD, 700000000000000001, 55, category_label="Aiuto")
    t = await ticket_repo.get_ticket_by_channel(55)
    return SimpleNamespace(pool=clean_db, chiave=chiave, ticket=t)


@pytest.mark.asyncio
async def test_il_dato_salvato_non_contiene_il_testo_in_chiaro(conn):
    segreto = "numero di carta 4111 1111 1111 1111 e <b>nota</b>"
    pagina = f"<html><body>{segreto}<img src='data:image/png;base64,QUJD'></body></html>"
    rid = await servizio.conserva(GUILD, conn.ticket, [pagina])
    assert rid
    grezzo = await conn.pool.fetchrow("SELECT * FROM ticket_trascrizioni WHERE id=$1", rid)
    tutto = " ".join(str(v) for v in dict(grezzo).values())
    assert "4111" not in tutto and "carta" not in tutto and "QUJD" not in tutto and "<html" not in tutto
    assert logica.apri(grezzo["cifrato"], GUILD, conn.ticket.id, conn.chiave) == [pagina]
    # legato alla riga: copiato su un altro ticket non si apre; con un'altra chiave neppure
    assert logica.apri(grezzo["cifrato"], GUILD, conn.ticket.id + 1, conn.chiave) is None
    assert logica.apri(grezzo["cifrato"], GUILD, conn.ticket.id, generate_key()) is None


@pytest.mark.asyncio
async def test_scade_in_90_giorni_al_massimo_e_si_pulisce(conn):
    adesso = datetime.now(timezone.utc)
    rid = await servizio.conserva(GUILD, conn.ticket, ["x"], adesso)
    riga = await conn.pool.fetchrow("SELECT scade_il FROM ticket_trascrizioni WHERE id=$1", rid)
    assert abs((riga["scade_il"] - adesso) - timedelta(days=90)) < timedelta(seconds=5)
    assert logica.scadenza(adesso, 5000) - adesso == timedelta(days=90)
    assert await repo.leggi(GUILD, rid) is not None
    await conn.pool.execute("UPDATE ticket_trascrizioni SET scade_il = now() - interval '1 minute' WHERE id=$1", rid)
    assert await repo.leggi(GUILD, rid) is None  # scaduta: invisibile anche prima della pulizia
    assert await repo.elenco(GUILD, logica.Filtro(), 25) == []
    assert await repo.pulisci_scadute() == 1
    assert await conn.pool.fetchval("SELECT count(*) FROM ticket_trascrizioni") == 0


@pytest.mark.asyncio
async def test_la_pulizia_automatica_del_registro_la_toglie(conn):
    rid = await servizio.conserva(GUILD, conn.ticket, ["x"])
    await conn.pool.execute("UPDATE ticket_trascrizioni SET scade_il = now() - interval '1 day' WHERE id=$1", rid)
    tolte = await retention_worker.pulisci_scaduti(conn.pool)
    assert tolte.get("ticket_trascrizioni") == 1
    assert "ticket_trascrizioni" in {t.nome for t in data_registry.REGISTRO}


@pytest.mark.asyncio
async def test_server_accorcia_o_spegne(conn):
    await repo.imposta_opzioni(GUILD, True, 7)
    adesso = datetime.now(timezone.utc)
    rid = await servizio.conserva(GUILD, conn.ticket, ["x"], adesso)
    scade = await conn.pool.fetchval("SELECT scade_il FROM ticket_trascrizioni WHERE id=$1", rid)
    assert abs((scade - adesso) - timedelta(days=7)) < timedelta(seconds=5)
    await repo.imposta_opzioni(GUILD, False, 7)
    assert await servizio.attiva(GUILD) is False
    assert await servizio.conserva(GUILD, conn.ticket, ["y"]) is None
    assert (await repo.opzioni(999)).attiva is True and (await repo.opzioni(999)).giorni == 90  # di base: accesa a 90


@pytest.mark.asyncio
async def test_senza_chiave_non_si_salva_niente(conn, monkeypatch):
    monkeypatch.setattr(servizio, "config", SimpleNamespace(TICKET_TRASCRIZIONI_KEY="", OAUTH_ENCRYPTION_KEY=""))
    assert await servizio.attiva(GUILD) is False
    assert await servizio.conserva(GUILD, conn.ticket, ["testo in chiaro"]) is None
    assert await conn.pool.fetchval("SELECT count(*) FROM ticket_trascrizioni") == 0


def test_chiave_di_riserva_e_giorni():
    assert logica.chiave_da_config(SimpleNamespace(TICKET_TRASCRIZIONI_KEY="", OAUTH_ENCRYPTION_KEY="K")) == "K"
    assert logica.chiave_da_config(SimpleNamespace(TICKET_TRASCRIZIONI_KEY="T", OAUTH_ENCRYPTION_KEY="K")) == "T"
    assert [logica.giorni_validi(x) for x in ("0", "1", "90", "91", "abc", None)] == [None, 1, 90, None, None, None]


@pytest.mark.asyncio
async def test_ricerca_per_utente_pannello_voto_e_motivo(conn):
    p = await conn.pool.fetchval(
        "INSERT INTO ticket_panels (guild_id, name, category_id, button_label) VALUES ($1,'Supporto',1,'x') RETURNING id", GUILD
    )
    await conn.pool.execute("UPDATE tickets SET panel_id=$2, rating=4, close_reason='risolto con 100% di successo' WHERE id=$1", conn.ticket.id, p)
    t = await ticket_repo.get_ticket_by_channel(55)
    await servizio.conserva(GUILD, t, ["x"])
    f = logica.Filtro
    assert len(await repo.elenco(GUILD, f(), 25)) == 1
    assert len(await repo.elenco(GUILD, f(utente_id=700000000000000001), 25)) == 1
    assert await repo.elenco(GUILD, f(utente_id=700000000000000002), 25) == []
    assert len(await repo.elenco(GUILD, f(panel_id=p, voto=4), 25)) == 1
    assert await repo.elenco(GUILD, f(voto=5), 25) == []
    assert len(await repo.elenco(GUILD, f(motivo="100%"), 25)) == 1
    assert await repo.elenco(GUILD, f(motivo="%"), 25) != [] and await repo.elenco(GUILD, f(motivo="zzz"), 25) == []
    assert await repo.elenco(GUILD + 1, f(), 25) == []  # un altro server non vede niente
    r = (await repo.elenco(GUILD, f(), 25))[0]
    assert (r.voto, r.nome_pannello, r.motivo) == (4, "Supporto", "risolto con 100% di successo")


def test_filtro_da_form_ignora_valori_strani():
    f = logica.filtro_da_form("<@700000000000000001>", "x", "9", "a\x00b")
    assert f == logica.Filtro(700000000000000001, None, None, "ab")

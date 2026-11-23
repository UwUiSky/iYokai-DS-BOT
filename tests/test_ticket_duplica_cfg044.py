"""
tests/test_ticket_duplica_cfg044.py
===================================
CFG-044 (D121): duplicare un pannello di ticket già configurato (domande, motivi, opzioni, accessi e risposte
pronte approvate) e copiare una risposta pronta su un altro pannello. Database vero.
"""

import pytest

from core.database import db
from core.repositories.ticket_form_repo import PannelloGiaEsistente, TroppiPannelli, ticket_form_repo
from core.repositories.ticket_standard_repo import ticket_standard_repo

G = 960001


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    yield


async def _pannello(nome="Supporto"):
    p = await ticket_form_repo.crea_pannello(G, nome, 111, "Apri", None, "Ciao {utente}")
    await ticket_form_repo.aggiungi_domanda(p.id, "Che problema hai?")
    await db.pool.execute("INSERT INTO ticket_panel_motivi (panel_id, posizione, etichetta) VALUES ($1, 1, 'Pagamenti')", p.id)
    await db.pool.execute("INSERT INTO ticket_panel_opzioni (panel_id, max_aperti, ruoli_staff) VALUES ($1, 3, '{5,6}')", p.id)
    await db.pool.execute("INSERT INTO ticket_panel_accesso (panel_id, posizione, role_id, permetti) VALUES ($1, 1, 9, true)", p.id)
    return p


async def test_duplica_copia_tutto_con_un_altro_nome_e_categoria():
    p = await _pannello()
    n = await ticket_form_repo.duplica_pannello(G, p.id, "Supporto 2", 222)
    assert n.id != p.id and n.name == "Supporto 2" and n.category_id == 222 and n.welcome_text == "Ciao {utente}"
    assert len(await ticket_form_repo.elenca_domande(n.id)) == 1
    assert await db.pool.fetchval("SELECT etichetta FROM ticket_panel_motivi WHERE panel_id = $1", n.id) == "Pagamenti"
    assert await db.pool.fetchval("SELECT max_aperti FROM ticket_panel_opzioni WHERE panel_id = $1", n.id) == 3
    assert await db.pool.fetchval("SELECT role_id FROM ticket_panel_accesso WHERE panel_id = $1", n.id) == 9
    # indipendenti: cambiare la copia non tocca l'originale
    await db.pool.execute("UPDATE ticket_panel_opzioni SET max_aperti = 9 WHERE panel_id = $1", n.id)
    assert await db.pool.fetchval("SELECT max_aperti FROM ticket_panel_opzioni WHERE panel_id = $1", p.id) == 3


async def test_duplica_copia_solo_le_risposte_approvate_senza_gli_usi():
    p = await _pannello()
    r = await ticket_standard_repo.crea_proposta(G, p.id, "Rimborso", "rimborso", "Scrivi a...", None)
    await ticket_standard_repo.approva(r.id, 1)
    await ticket_standard_repo.usata(r.id)
    await ticket_standard_repo.crea_proposta(G, p.id, "Bozza", "x", "non approvata", None)
    n = await ticket_form_repo.duplica_pannello(G, p.id, "Copia", None)
    copie = await ticket_standard_repo.tutte_del_pannello(G, n.id)
    assert [c.title for c in copie] == ["Rimborso"]
    assert copie[0].status == "approved" and copie[0].use_count == 0
    assert n.category_id == p.category_id  # senza categoria resta quella dell'originale


async def test_nome_gia_usato_e_tetto_dei_pannelli():
    p = await _pannello()
    with pytest.raises(PannelloGiaEsistente):
        await ticket_form_repo.duplica_pannello(G, p.id, "supporto", None)
    from core import ticket_form_logic as form

    for i in range(form.MAX_PANNELLI_PER_SERVER - 1):
        await ticket_form_repo.duplica_pannello(G, p.id, f"P{i}", None)
    with pytest.raises(TroppiPannelli):
        await ticket_form_repo.duplica_pannello(G, p.id, "Uno di troppo", None)


async def test_copia_risposta_su_un_altro_pannello_solo_nello_stesso_server():
    a, b = await _pannello("A"), await _pannello("B")
    r = await ticket_standard_repo.crea_proposta(G, a.id, "Rimborso", "k", "testo", None)
    await ticket_standard_repo.approva(r.id, 1)
    nuova = await ticket_standard_repo.copia_su_pannello(G, r.id, b.id)
    assert nuova is not None and nuova.panel_id == b.id and nuova.status == "approved"
    assert await ticket_standard_repo.copia_su_pannello(G + 1, r.id, b.id) is None  # un altro server non la vede
    assert await ticket_standard_repo.copia_su_pannello(G, r.id, 999999) is None  # pannello inesistente

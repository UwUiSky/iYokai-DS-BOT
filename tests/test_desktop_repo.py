"""
tests/test_desktop_repo.py
==========================
SPEC D.1, D.5-D.7, D.9 (#108): token (solo impronta), avvisi, eventi e azioni su PostgreSQL vero.
"""

import pytest

from core.repositories.desktop_repo import DesktopRepository, PreferenzeDesktop


@pytest.fixture
def repo(clean_db):
    return DesktopRepository(pool_provider=lambda: clean_db)


async def test_token_si_riconosce_si_sostituisce_si_revoca(repo):
    await repo.imposta_token(5, "a" * 64)
    assert await repo.utente_del_token("a" * 64) == 5 and await repo.collegato(5)
    await repo.imposta_token(5, "b" * 64)
    assert await repo.utente_del_token("a" * 64) is None and await repo.utente_del_token("b" * 64) == 5
    assert await repo.revoca_token(5) and not await repo.revoca_token(5)
    assert await repo.utente_del_token("b" * 64) is None and not await repo.collegato(5)


async def test_avvisi_spenti_di_base_poi_acceso_con_parole(repo):
    assert await repo.preferenze(5) == PreferenzeDesktop()
    assert await repo.utenti_con_avvisi() == {}
    await repo.imposta_parole(5, ["ciao"])
    assert await repo.utenti_con_avvisi() == {}  # le parole da sole non accendono nulla
    await repo.imposta_menzioni(5, True)
    await repo.imposta_menzioni(6, True)
    assert await repo.utenti_con_avvisi() == {5: ["ciao"], 6: []}
    assert await repo.preferenze(5) == PreferenzeDesktop(True, ("ciao",))
    await repo.imposta_menzioni(5, False)
    assert await repo.utenti_con_avvisi() == {6: []}


async def test_eventi_dopo_id_filtro_e_tetto(repo):
    for n in range(5):
        await repo.aggiungi_evento(5, "menzione" if n % 2 == 0 else "parola", message_id=n, testo=f"t{n}", massimo=3)
    await repo.aggiungi_evento(6, "menzione", message_id=99)
    tutti = await repo.eventi(5)
    assert [e["message_id"] for e in tutti] == [2, 3, 4]  # al massimo 3: i più vecchi spariscono
    assert [e["message_id"] for e in await repo.eventi(5, dopo=tutti[0]["id"])] == [3, 4]
    assert [e["message_id"] for e in await repo.eventi(5, tipo="parola")] == [3]
    assert [e["message_id"] for e in await repo.eventi(5, limite=1)] == [4]
    assert [e["message_id"] for e in await repo.eventi(6)] == [99]


async def test_azioni_per_server_e_per_utente(repo):
    await repo.registra_azione(5, 100, "blocca_canale", "x" * 400, "ok")
    await repo.registra_azione(6, 100, "timeout", "u", "ok")
    await repo.registra_azione(5, 200, "annuncio", "", "rifiutata")
    assert [a["azione"] for a in await repo.azioni_server(100)] == ["timeout", "blocca_canale"]
    assert len((await repo.azioni_server(100))[1]["dettaglio"]) == 300
    assert [a["guild_id"] for a in await repo.azioni_utente(5)] == [200, 100]

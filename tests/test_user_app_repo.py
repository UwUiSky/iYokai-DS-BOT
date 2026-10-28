"""
tests/test_user_app_repo.py
===========================
SPEC B.2, B.5, B.8, B.9, B.10 (#107): dati personali di iYokai App, contro PostgreSQL vero.
"""

import pytest

from core.repositories.user_app_repo import Impostazioni, UserAppRepository


@pytest.fixture
def repo(clean_db):
    return UserAppRepository(pool_provider=lambda: clean_db)


async def test_segnalibri_tetto_doppioni_e_proprieta(repo):
    primo = await repo.salva_segnalibro(7, 1, 2, 100, "Anna", "ciao")
    assert await repo.salva_segnalibro(7, 1, 2, 100, "Anna", "ciao") == primo  # stesso messaggio, stesso numero
    assert await repo.salva_segnalibro(7, 1, 2, 101, "Anna", "due", massimo=2) is not None
    assert await repo.salva_segnalibro(7, 1, 2, 102, "Anna", "tre", massimo=2) is None
    assert [r["message_id"] for r in await repo.segnalibri(7)] == [101, 100]  # i più recenti prima
    pagina = await repo.segnalibri(7, limite=1)
    assert [r["message_id"] for r in await repo.segnalibri(7, dopo=pagina[0]["id"])] == [100]
    assert not await repo.rimuovi_segnalibro(8, primo)  # di un altro: no
    assert await repo.rimuovi_segnalibro(7, primo)


async def test_risposte_salvate(repo):
    assert await repo.salva_risposta(7, "ciao", "Ciao a tutti") == "nuova"
    assert await repo.salva_risposta(7, "ciao", "Ciao!", titolo="T", colore=0xFF0000) == "aggiornata"
    riga = await repo.risposta(7, "ciao")
    assert (riga["testo"], riga["titolo"], riga["colore"]) == ("Ciao!", "T", 0xFF0000)
    assert await repo.risposta(8, "ciao") is None
    assert await repo.salva_risposta(7, "altra", "x", massimo=1) == "piena"
    assert await repo.salva_risposta(7, "ciao", "ancora", massimo=1) == "aggiornata"  # il tetto non blocca la modifica
    await repo.salva_risposta(7, "ci_ao", "x")
    assert await repo.nomi_risposte(7, "ci_") == ["ci_ao"]  # il carattere _ non è un jolly
    assert await repo.rimuovi_risposta(7, "ciao") and not await repo.rimuovi_risposta(7, "ciao")


async def test_impostazioni_e_storico(repo):
    assert await repo.impostazioni(7) == Impostazioni()
    await repo.imposta(7, "risposte_private", False)
    await repo.imposta(7, "storico", True)
    assert await repo.impostazioni(7) == Impostazioni(risposte_private=False, storico=True)
    with pytest.raises(ValueError):
        await repo.imposta(7, "user_id; DROP TABLE x", True)

    for n in range(5):
        await repo.registra_comando(7, f"/cmd{n}", None, massimo=3)
    assert [r["comando"] for r in await repo.storico(7)] == ["/cmd4", "/cmd3", "/cmd2"]
    await repo.imposta(7, "storico", False)  # spegnere lo storico lo cancella
    assert await repo.storico(7) == []


async def test_azzera_storico_conta_le_righe(repo):
    await repo.registra_comando(7, "/a", 5)
    await repo.registra_comando(7, "/b", None)
    assert await repo.azzera_storico(7) == 2


async def test_playlist(repo):
    assert await repo.crea_playlist(7, "rock")
    assert not await repo.crea_playlist(7, "rock")
    assert not await repo.crea_playlist(7, "pop", massimo=1)
    assert await repo.aggiungi_brano(7, "rock", "Queen - Bohemian Rhapsody") == "ok"
    assert await repo.aggiungi_brano(7, "rock", "AC/DC - Thunderstruck", massimo=2) == "ok"
    assert await repo.aggiungi_brano(7, "rock", "altro", massimo=2) == "piena"
    assert await repo.aggiungi_brano(7, "jazz", "x") == "manca"
    assert await repo.playlist(7, "rock") == ["Queen - Bohemian Rhapsody", "AC/DC - Thunderstruck"]
    assert [(r["nome"], r["brani"]) for r in await repo.elenco_playlist(7)] == [("rock", 2)]
    assert await repo.togli_brano(7, "rock", 1) and not await repo.togli_brano(7, "rock", 5)
    assert await repo.playlist(7, "rock") == ["AC/DC - Thunderstruck"]
    assert await repo.playlist(8, "rock") is None
    assert await repo.rimuovi_playlist(7, "rock")


async def test_richieste_di_assistenza(repo):
    n = await repo.apri_richiesta(7, "Non funziona", "Testo")
    assert await repo.apri_richiesta(7, "B", "t", massimo_aperte=1) is None
    await repo.imposta_thread_richiesta(n, 555)
    riga = await repo.richiesta_da_thread(555)
    assert (riga["id"], riga["user_id"], riga["stato"]) == (n, 7, "aperta")
    assert await repo.richiesta_da_thread(556) is None
    await repo.chiudi_richiesta(n)
    assert (await repo.richieste_utente(7))[0]["stato"] == "chiusa"
    assert await repo.apri_richiesta(7, "C", "t", massimo_aperte=1) is not None  # chiusa: non conta più


async def test_somme_per_il_profilo_globale(repo, clean_db):
    await clean_db.execute(
        "INSERT INTO leveling_totals (guild_id, user_id, xp_total, level, coins_total) VALUES (1, 7, 500, 3, 10), "
        "(2, 7, 700, 4, 5), (3, 7, 0, 0, 0), (1, 8, 99, 1, 1)"
    )
    somme = await repo.somme_globali(7)
    assert (somme.xp_totale, somme.server, somme.monete) == (1200, 2, 15)
    await clean_db.execute("INSERT INTO profile_items (guild_id, user_id, item_id) VALUES (1, 7, 'stella'), (2, 7, 'stella'), (2, 7, 'luna')")
    assert await repo.medaglie(7) == ["luna", "stella"]
    assert await repo.clan_dell_utente(7) == []

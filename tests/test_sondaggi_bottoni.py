"""
tests/test_sondaggi_bottoni.py
==============================
D69 B22 (UTL-088, 089, 091, 093, 094, 096): limiti dei componenti, regole dei voti, pesi, voto una volta senza corse,
chiusura una sola volta, modifica con voti. Archivio su PostgreSQL vero.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from core import sondaggi_logic as L
from core.repositories.sondaggi_repo import SondaggiRepository

G = 11
ADESSO = datetime.now(timezone.utc)


def test_limiti_dei_componenti():
    for quante in range(2, L.MAX_OPZIONI + 1):
        righe = L.righe_bottoni(quante)
        assert len(righe) <= 5 and all(len(r) <= 5 for r in righe)
        assert L.conta_componenti(quante) <= L.MAX_COMPONENTI
    assert len(L.custom_id(2**63 - 1, 19)) < 100
    assert len(L.etichetta_bottone(19, "x" * 80)) <= 45


def test_opzioni():
    assert L.leggi_opzioni("a | b") == ["a", "b"]
    assert L.leggi_opzioni("solo") == "poche"
    assert L.leggi_opzioni("|".join(str(i) for i in range(21))) == "troppe"
    assert L.leggi_opzioni("a|A") == "doppie"
    assert len(L.leggi_opzioni("x" * 200 + "|b")[0]) == 80


def test_pesi_e_ruoli():
    assert L.peso_votante({1, 2}, {1: 3, 2: 5}) == 5 and L.peso_votante({9}, {1: 3}) == 1
    assert L.puo_votare({1}, []) and L.puo_votare({1}, [1, 2]) and not L.puo_votare({3}, [1, 2])
    assert L.scelte_dopo_voto({1}, 2, False) == {2} and L.scelte_dopo_voto({1}, 2, True) == {1, 2}
    assert L.scelte_dopo_voto({1, 2}, 2, True) == {1}


@pytest.fixture
def repo(clean_db):
    return SondaggiRepository(pool_provider=lambda: clean_db)


async def _nuovo(repo, **kw):
    return await repo.crea(G, 5, 99, "domanda?", ["a", "b", "c"], scade_il=ADESSO + timedelta(hours=1), **kw)


@pytest.mark.asyncio
async def test_voto_singolo_sostituisce_e_multiplo_alterna(repo):
    s = await _nuovo(repo)
    assert (await repo.vota(s, 1, 0, 1, ADESSO))[0] == "ok"
    assert (await repo.vota(s, 1, 0, 1, ADESSO))[0] == "uguale"
    assert (await repo.vota(s, 1, 2, 1, ADESSO))[1] == {2}
    assert await repo.risultati(s, False) == [("a", 0), ("b", 0), ("c", 1)]
    m = await _nuovo(repo, multipla=True)
    await repo.vota(m, 1, 0, 1, ADESSO)
    assert (await repo.vota(m, 1, 1, 1, ADESSO))[1] == {0, 1}
    assert (await repo.vota(m, 1, 0, 1, ADESSO))[1] == {1}


@pytest.mark.asyncio
async def test_clic_insieme_un_solo_voto_e_pesi(repo):
    s = await _nuovo(repo, pesato=True)
    await asyncio.gather(*[repo.vota(s, 7, i % 3, 4, ADESSO) for i in range(6)])
    assert await repo.votanti(s) == 1
    assert sum(v for _, v in await repo.risultati(s, True)) == 4
    assert await repo.imposta_peso(G, 1, 3) == "ok"
    for r in range(2, 26):
        assert await repo.imposta_peso(G, r, 2) == "ok"
    assert await repo.imposta_peso(G, 99, 2) == "pieno" and await repo.imposta_peso(G, 1, 9) == "ok"
    assert (await repo.pesi(G))[1] == 9 and await repo.togli_peso(G, 1)


@pytest.mark.asyncio
async def test_chiusura_una_volta_totali_restano_voti_spariscono(repo):
    s = await _nuovo(repo, anonimo=True)
    await repo.vota(s, 1, 0, 1, ADESSO)
    await repo.vota(s, 2, 0, 1, ADESSO)
    assert sorted(await asyncio.gather(repo.chiudi(s), repo.chiudi(s))) == [False, True]
    assert await repo.risultati(s, False) == [("a", 2), ("b", 0), ("c", 0)]
    assert await repo.votanti(s) == 0
    assert (await repo.vota(s, 3, 1, 1, ADESSO))[0] == "chiuso"


@pytest.mark.asyncio
async def test_scaduto_non_vota_e_chi_esce_perde_il_voto(repo):
    s = await _nuovo(repo)
    assert (await repo.vota(s, 1, 0, 1, ADESSO + timedelta(hours=2)))[0] == "chiuso"
    await repo.vota(s, 1, 0, 1, ADESSO)
    assert await repo.togli_voti_utente(G + 1, 1) == 0
    assert await repo.togli_voti_utente(G, 1) == 1 and await repo.votanti(s) == 0


@pytest.mark.asyncio
async def test_modifica_tiene_i_voti_delle_opzioni_rimaste(repo):
    s = await _nuovo(repo)
    await repo.vota(s, 1, 1, 1, ADESSO)
    await repo.vota(s, 2, 2, 1, ADESSO)
    assert await repo.modifica(s, "nuova?", ["z", "b", "c2"], None) == 1
    assert await repo.risultati(s, False) == [("z", 0), ("b", 1), ("c2", 0)]
    await repo.chiudi(s)
    assert await repo.modifica(s, "x", ["a", "b"], None) is None


@pytest.mark.asyncio
async def test_canale_cancellato_toglie_sondaggi_con_voti(repo):
    s = await _nuovo(repo)
    await repo.vota(s, 1, 0, 1, ADESSO)
    assert await repo.elimina_del_canale(G + 1, 5) == 0
    assert await repo.elimina_del_canale(G, 5) == 1
    assert await repo.prendi(s) is None and await repo.votanti(s) == 0


@pytest.mark.asyncio
async def test_conferma_modifica_ricontrolla_il_permesso(repo, monkeypatch):
    """Alla conferma chi non è l'autore e non ha «Gestisci messaggi» non scrive nulla; l'autore sì."""
    from unittest.mock import AsyncMock, MagicMock

    import discord

    from cogs.utility import sondaggi_bottoni as M
    from tests.support.discord_fakes import fake_interaction, fake_member

    monkeypatch.setattr(M, "sondaggi_repo", repo)
    monkeypatch.setattr(M, "lingua_interazione", AsyncMock(return_value="it"))
    s = await _nuovo(repo)
    cog = MagicMock()
    cog.scrivi_modifica = AsyncMock(return_value="sb_modificato")

    async def clic(autore: bool, permessi: discord.Permissions):
        vista = M.ConfermaModifica(cog, 99, s, "nuova?", ["a", "b"], None, ("Si", "No"))
        i = fake_interaction(user=fake_member(user_id=99 if autore else 5), permissions=permessi)
        await vista.conferma.callback(i)
        return vista, i

    vista, i = await clic(False, discord.Permissions.none())
    cog.scrivi_modifica.assert_not_awaited()
    assert vista.is_finished()
    _, i = await clic(True, discord.Permissions.none())
    cog.scrivi_modifica.assert_awaited_once_with(s, "nuova?", ["a", "b"], None)
    await repo.chiudi(s)
    cog.scrivi_modifica.reset_mock()
    await clic(False, discord.Permissions(manage_messages=True))
    cog.scrivi_modifica.assert_awaited_once()

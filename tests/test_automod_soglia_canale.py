"""
tests/test_automod_soglia_canale.py
===================================
Soglie per canale (AMD-008): una regola personale scatta quando in un canale arrivano troppi messaggi in poco
tempo, di chiunque (i bot no); dopo lo scatto resta quieta per la finestra, poi il conteggio riparte.
"""

import pytest

import cogs.automod.automod as modulo_automod
from core.bounded_cache import BoundedCache

from core import automod_regole_service as servizio
from core.repositories.automod_liste_repo import automod_liste_repo
from core.automod_regole_logic import Regola, azioni_dai_nomi_vecchi
from tests.test_automod_regole_filtri import GUILD_ID, _msg, cog  # noqa: F401  (la fixture)


@pytest.fixture(autouse=True)
def liste(clean_db, monkeypatch):
    monkeypatch.setattr(automod_liste_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(modulo_automod, "_quiete_soglia_canale", BoundedCache(100))  # ogni test parte senza quiete


async def _regola(numero=3, secondi=10, **extra):
    await servizio.crea_personale(
        GUILD_ID,
        Regola(chiave="x", tipo="personale", nome="Flood", azioni=azioni_dai_nomi_vecchi(("delete",), 600),
               innesco={"tipo": "soglia_canale", "numero": numero, "secondi": secondi}, **extra),
        1,
    )


async def test_scatta_al_numero_di_messaggi_nel_canale_anche_di_persone_diverse(cog):
    await _regola()
    a, b, c = _msg("uno", autore=1), _msg("due", autore=2), _msg("tre", autore=3)
    for m in (a, b, c):
        await cog.on_message(m)
    a.delete.assert_not_awaited()
    b.delete.assert_not_awaited()
    c.delete.assert_awaited_once()


async def test_dopo_lo_scatto_quiete_per_la_finestra_poi_si_riparte(cog, monkeypatch):
    """Niente scatti a raffica: dopo uno scatto il canale resta quieto per i secondi della soglia."""
    ora = {"v": 1000.0}
    monkeypatch.setattr(modulo_automod, "_adesso", lambda: ora["v"])
    await _regola()
    messaggi = [_msg(f"m{i}", autore=i + 1) for i in range(6)]
    for m in messaggi:
        await cog.on_message(m)
    assert [m.delete.await_count for m in messaggi] == [0, 0, 1, 0, 0, 0]
    ora["v"] += 11  # finita la quiete: il conteggio riparte da zero
    dopo = [_msg(f"d{i}", autore=i + 1) for i in range(3)]
    for m in dopo:
        await cog.on_message(m)
    assert [m.delete.await_count for m in dopo] == [0, 0, 1]


async def test_canali_diversi_hanno_conteggi_diversi(cog):
    await _regola()
    messaggi = [_msg("x", canale=100 + i % 3) for i in range(6)]
    for m in messaggi:
        await cog.on_message(m)
    assert all(m.delete.await_count == 0 for m in messaggi)


async def test_i_bot_non_contano(cog):
    await _regola()
    messaggi = [_msg("x", autore=10 + i, bot=True) for i in range(5)]
    for m in messaggi:
        await cog.on_message(m)
    assert all(m.delete.await_count == 0 for m in messaggi)

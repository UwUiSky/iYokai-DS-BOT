"""
tests/test_anti_automazione_b16.py
==================================
Controllo anti-automazione nei comandi di guadagno (ECO-158), #125 B16. Funzioni coperte: catalogo #125
"""

import random
from unittest.mock import AsyncMock

import pytest

import core.anti_automazione as aa
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member


class _Sempre:
    """Un caso che fa sempre scattare il controllo."""

    def randint(self, a, b):
        return 1 if (a, b) == (1, 1000) else random.randint(a, b)

    choice = staticmethod(random.choice)
    shuffle = staticmethod(random.shuffle)


def test_somma_ha_una_sola_risposta_giusta_e_scelte_diverse():
    rng = random.Random(3)
    for _ in range(300):
        domanda, scelte, giusta = aa.somma_con_scelte(rng)
        a, b = map(int, domanda.split(" + "))
        assert giusta == a + b and sorted(scelte).count(giusta) == 1 and len(set(scelte)) == 3 and all(s > 0 for s in scelte)


@pytest.fixture(autouse=True)
def _pulisci():
    aa._verificati.clear()
    yield
    aa._verificati.clear()


@pytest.mark.asyncio
async def test_spento_o_fuori_dai_server_non_ferma(monkeypatch):
    async def nessuno(*a, **k):
        return False

    i = fake_interaction(guild=fake_guild(1), user=fake_member(1))
    assert await aa.serve_controllo(i, 0) is False
    i.response.send_message.assert_not_awaited()
    i2 = fake_interaction(guild=fake_guild(1), user=fake_member(1))
    i2.guild = None
    assert await aa.serve_controllo(i2, 500, _Sempre()) is False


@pytest.mark.asyncio
async def test_controllo_ferma_il_comando_e_la_risposta_giusta_verifica(monkeypatch):
    import core.ui_base as ui

    async def nessuno(*a, **k):
        return False

    monkeypatch.setattr(ui, "_utente_o_server_in_blacklist", nessuno)
    i = fake_interaction(guild=fake_guild(1), user=fake_member(1))
    assert await aa.serve_controllo(i, 1000, _Sempre()) is True
    view = i.response.send_message.await_args.kwargs["view"]
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    estraneo = fake_interaction(guild=fake_guild(1), user=fake_member(2))
    assert await view.interaction_check(estraneo) is False
    sbagliato = next(b for b in view.children if b.label != str(view.giusta))
    j = fake_interaction(guild=fake_guild(1), user=fake_member(1))
    j.response.edit_message = AsyncMock()
    await sbagliato.callback(j)
    assert not aa.e_verificato(1, 1)
    giusto = next(b for b in view.children if b.label == str(view.giusta))
    k = fake_interaction(guild=fake_guild(1), user=fake_member(1))
    await giusto.callback(k)  # un solo tentativo: il secondo non conta
    assert not aa.e_verificato(1, 1)
    i2 = fake_interaction(guild=fake_guild(1), user=fake_member(1))
    assert await aa.serve_controllo(i2, 1000, _Sempre()) is True
    v2 = i2.response.send_message.await_args.kwargs["view"]
    g = next(b for b in v2.children if b.label == str(v2.giusta))
    k2 = fake_interaction(guild=fake_guild(1), user=fake_member(1))
    k2.response.edit_message = AsyncMock()
    await g.callback(k2)
    assert aa.e_verificato(1, 1) and not aa.e_verificato(1, 2) and not aa.e_verificato(2, 1)
    i3 = fake_interaction(guild=fake_guild(1), user=fake_member(1))
    assert await aa.serve_controllo(i3, 1000, _Sempre()) is False  # verificato: passa
    assert not aa.e_verificato(1, 1, adesso=10**12)  # dopo 10 minuti scade

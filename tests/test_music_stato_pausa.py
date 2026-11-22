"""
tests/test_music_stato_pausa.py
===============================
MUS-053 (pausa a canale vuoto, ripresa al rientro) e MUS-061 (titolo come stato dei bot della flotta, mai del
principale, con tetto di aggiornamenti), con oggetti finti.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import cogs.music.eventi as eventi_module
from cogs.music.eventi import MusicEventiCog
from core import music_stato_logic as stato


def test_titolo_per_stato_una_riga_e_tetto():
    assert stato.titolo_per_stato("  ciao \n  mondo ") == "ciao mondo"
    assert len(stato.titolo_per_stato("x" * 500)) == stato.STATO_MAX and stato.titolo_per_stato("x" * 500).endswith("…")


def test_limite_stato_un_cambio_ogni_pausa_e_vale_l_ultimo():
    ora = [100.0]
    lim = stato.LimiteStato(pausa=15, orologio=lambda: ora[0])
    assert lim.richiedi(1, "a") == 0
    lim.segna_applicato(1)
    ora[0] = 105
    assert lim.richiedi(1, "b") == pytest.approx(10)
    assert lim.richiedi(1, "c") == pytest.approx(10) and lim.voluto[1] == "c"
    assert lim.richiedi(2, "z") == 0  # un altro bot ha il suo conto
    ora[0] = 116
    assert lim.richiedi(1, "d") == 0


def _impostazioni(monkeypatch, **valori):
    async def get(g, k, d=None):
        return valori.get(k, d)

    monkeypatch.setattr(eventi_module, "db", SimpleNamespace(get_guild_setting=get))


class _Canale:
    def __init__(self, membri):
        self.members = membri


def _player(canale, **kw):
    base = dict(
        channel=canale, current=SimpleNamespace(title="x"), paused=False,
        pause=AsyncMock(), is_radio=False, is_nonstop=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _umano(i):
    return SimpleNamespace(id=i, bot=False)


def _voce(canale):
    return SimpleNamespace(channel=canale)


async def _giro(cog, player, membro, prima, dopo):
    worker = SimpleNamespace(user=SimpleNamespace(id=500))
    membro.guild = SimpleNamespace(id=7, voice_client=player)
    await cog.su_voce(worker, membro, _voce(prima), _voce(dopo))


@pytest.mark.asyncio
async def test_pausa_quando_l_ultimo_esce_e_riprende_al_rientro(monkeypatch):
    _impostazioni(monkeypatch)
    cog = MusicEventiCog(bot=SimpleNamespace())
    canale = _Canale([])
    player = _player(canale)
    uscito = _umano(1)
    await _giro(cog, player, uscito, canale, None)
    player.pause.assert_awaited_once_with(True)
    canale.members = [uscito]
    await _giro(cog, player, uscito, None, canale)
    assert player.pause.await_args_list[-1].args == (False,)


@pytest.mark.asyncio
async def test_non_riprende_una_pausa_messa_a_mano(monkeypatch):
    _impostazioni(monkeypatch)
    cog = MusicEventiCog(bot=SimpleNamespace())
    canale = _Canale([_umano(1)])
    player = _player(canale, paused=True)
    await _giro(cog, player, _umano(2), None, canale)
    player.pause.assert_not_called()
    canale.members = []
    await _giro(cog, player, _umano(1), canale, None)  # già in pausa a mano: non la tocchiamo
    player.pause.assert_not_called()


@pytest.mark.asyncio
async def test_resta_in_riproduzione_se_c_e_ancora_qualcuno_o_se_spenta_o_radio(monkeypatch):
    _impostazioni(monkeypatch)
    cog = MusicEventiCog(bot=SimpleNamespace())
    canale = _Canale([_umano(2), SimpleNamespace(id=9, bot=True)])
    player = _player(canale)
    await _giro(cog, player, _umano(1), canale, None)
    player.pause.assert_not_called()
    canale.members = []
    radio = _player(canale, is_radio=True)
    await _giro(cog, radio, _umano(1), canale, None)
    radio.pause.assert_not_called()
    _impostazioni(monkeypatch, music_empty_pause=False)
    await _giro(cog, player, _umano(1), canale, None)
    player.pause.assert_not_called()


@pytest.mark.asyncio
async def test_il_bot_che_esce_toglie_lo_stato(monkeypatch):
    cog = MusicEventiCog(bot=SimpleNamespace())
    cambi = []

    async def change_presence(activity=None):
        cambi.append(activity)

    worker = SimpleNamespace(user=SimpleNamespace(id=500), change_presence=change_presence)
    await cog.imposta_stato(worker, "Brano")
    assert cambi[0].name == "Brano"
    membro = SimpleNamespace(id=500, bot=True, guild=SimpleNamespace(id=7))
    cog.limite_stato._ultimo.clear()
    await cog.su_voce(worker, membro, _voce(object()), _voce(None))
    assert cambi[-1] is None


@pytest.mark.asyncio
async def test_stato_mai_sul_principale_e_con_tetto(monkeypatch):
    principale = SimpleNamespace(change_presence=AsyncMock())
    cog = MusicEventiCog(bot=principale)
    await cog.imposta_stato(principale, "Brano")
    principale.change_presence.assert_not_called()

    worker = SimpleNamespace(change_presence=AsyncMock())
    await cog.imposta_stato(worker, "Uno")
    assert worker.change_presence.await_count == 1
    await cog.imposta_stato(worker, "Due")  # troppo presto: aspetta e poi vale l'ultimo
    await cog.imposta_stato(worker, "Tre")
    assert worker.change_presence.await_count == 1 and len(cog._stato_in_attesa) == 1
    assert cog.limite_stato.voluto[id(worker)] == "Tre"
    for task in cog._stato_in_attesa.values():
        task.cancel()


@pytest.mark.asyncio
async def test_togliere_lo_stato_senza_averlo_messo_non_chiama_discord():
    worker = SimpleNamespace(change_presence=AsyncMock())
    cog = MusicEventiCog(bot=SimpleNamespace())
    await cog.imposta_stato(worker, None)
    worker.change_presence.assert_not_called()


@pytest.mark.asyncio
async def test_inizio_brano_mette_il_titolo_solo_se_acceso(monkeypatch):
    worker = SimpleNamespace(change_presence=AsyncMock())
    cog = MusicEventiCog(bot=SimpleNamespace())
    traccia = SimpleNamespace(title="Titolo", length=1000, extras={})
    player = SimpleNamespace(guild=SimpleNamespace(id=7), client=worker, queue=SimpleNamespace(mode=None), current=traccia)
    _impostazioni(monkeypatch)
    await cog.su_inizio_brano(SimpleNamespace(player=player, track=traccia))
    worker.change_presence.assert_not_called()
    _impostazioni(monkeypatch, music_bot_status=True)
    await cog.su_inizio_brano(SimpleNamespace(player=player, track=traccia))
    assert worker.change_presence.await_args.kwargs["activity"].name == "Titolo"

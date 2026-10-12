"""
tests/test_music_queue_cmds.py
==================================
Catalogo MUS (issue #126) sulla coda: join, skipto, remove, previous,
history, queue con ricerca e quote per utente, play in cima. Logica pura
in core/music_queue_logic.py; i comandi con un player finto.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord
import pytest

import cogs.music.player as player_module
from cogs.music.player import MusicCog
from core.music_queue_logic import (
    format_share,
    indices_of_absent,
    indices_of_user,
    own_shuffle_order,
    previous_track_position,
    range_to_indices,
    requester_of,
    search_titles,
    share_by_user,
)



async def _senza_impostazioni(guild_id, key, default=None):
    return default


# ----------------------------- logica pura -----------------------------
def test_richiedente_letto_dagli_extras():
    t = SimpleNamespace(extras=SimpleNamespace(requester_id=7))
    assert requester_of(t) == 7
    assert requester_of(SimpleNamespace(extras=SimpleNamespace())) is None
    assert requester_of(SimpleNamespace()) is None


def test_quote_per_utente():
    quote = share_by_user([1, 1, 2, None])
    assert quote == [(1, 2, 50), (2, 1, 25)]
    assert share_by_user([]) == []
    testo = format_share(quote)
    assert "<@1> — 2 brani (50%)" in testo and "<@2> — 1 brano (25%)" in testo
    molti = share_by_user(list(range(100)))
    assert len(format_share(molti, 1024)) <= 1024
    assert format_share(molti).count("\n") == 4  # al massimo 5 utenti


def test_ricerca_nella_coda():
    titoli = ["Blue Monday", "Bluebird", "Red"]
    assert search_titles(titoli, "BLUE") == [(1, "Blue Monday"), (2, "Bluebird")]
    assert search_titles(titoli, "  ") == []
    assert len(search_titles(["a"] * 50, "a")) == 10


def test_intervalli_e_utenti():
    assert range_to_indices(2, 3, 5) == [1, 2]
    assert range_to_indices(4, None, 5) == [3]
    assert range_to_indices(4, 99, 5) == [3, 4]  # oltre la fine: si ferma alla fine
    assert "solo 5" in range_to_indices(6, None, 5)
    assert "non è valido" in range_to_indices(3, 2, 5)
    assert range_to_indices(1, None, 0) == "La coda è vuota."
    assert indices_of_user([1, 2, 1, None], 1) == [0, 2]
    assert indices_of_absent([1, 2, 3, None], {2}) == [0, 2]  # senza richiedente: resta


def test_brano_precedente_a_coda_finita_riprende_l_ultimo_finito():
    assert previous_track_position(1, c_e_un_corrente=False) == 0
    assert previous_track_position(0, c_e_un_corrente=False) is None


def test_brano_precedente():
    assert previous_track_position(0) is None
    assert previous_track_position(1) is None
    assert previous_track_position(2) == 0
    assert previous_track_position(5) == 3


# ----------------------------- comandi -----------------------------
class _Risposta:
    def __init__(self):
        self.inviati = []
        self.embeds = []

    async def defer(self, **kw):
        pass

    async def send_message(self, content=None, embed=None, **kw):
        if content is not None:
            self.inviati.append(content)
        if embed is not None:
            self.embeds.append(embed)


class _Canale:
    def __init__(self, membri):
        self.id = 11
        self.members = membri


class _Utente(discord.Member):
    def __init__(self, membri=()):
        self._voce = SimpleNamespace(channel=_Canale([SimpleNamespace(id=i) for i in membri]))

    @property
    def voice(self):
        return self._voce

    @property
    def id(self):
        return 1


class _Interazione:
    def __init__(self, membri=()):
        self.guild = SimpleNamespace(id=900)
        self.user = _Utente(membri)
        self.response = _Risposta()
        self.followup = _Risposta()
        self.followup.send = self.followup.send_message


class _Storico(list):
    def delete(self, i):
        del self[i]


class _Coda:
    def __init__(self, tracce, storico=None):
        self.tracce = list(tracce)
        self.history = _Storico(storico or [])
        self.mode = None

    def __len__(self):
        return len(self.tracce)

    def __iter__(self):
        return iter(self.tracce)

    def __getitem__(self, i):
        return self.tracce[i]

    def delete(self, i):
        del self.tracce[i]

    def put_at(self, i, t):
        self.tracce.insert(i, t)

    def put(self, t):
        self.tracce.extend(t if isinstance(t, list) else [t])

    def clear(self):
        self.tracce.clear()

    async def put_wait(self, t):
        self.tracce.extend(t if isinstance(t, list) else [t])

    @property
    def is_empty(self):
        return not self.tracce


def _t(titolo, uid=None):
    extras = SimpleNamespace(requester_id=uid) if uid else SimpleNamespace()
    return SimpleNamespace(title=titolo, length=1000, extras=extras)


def _cog(player, monkeypatch):
    monkeypatch.setattr(
        player_module, "db", SimpleNamespace(
            is_module_active_for_guild=AsyncMock(return_value=True), get_guild_setting=_senza_impostazioni
        )
    )
    guild_w = SimpleNamespace(voice_client=player)
    worker = SimpleNamespace(worker_index=1, get_guild=lambda gid: guild_w)

    class _F:
        async def get_worker_for_channel(self, g, c):
            return 1, worker

    return MusicCog(bot=SimpleNamespace(music_fleet=_F()))


def _player(tracce, corrente=None, storico=None):
    return SimpleNamespace(
        queue=_Coda(tracce, storico),
        current=corrente,
        skip=AsyncMock(),
        play=AsyncMock(),
        playing=True,
    )


@pytest.mark.asyncio
async def test_skipto_toglie_i_brani_prima_e_salta(monkeypatch):
    player = _player([_t("a"), _t("b"), _t("c")])
    cog = _cog(player, monkeypatch)
    i = _Interazione()

    await cog.skipto.callback(cog, i, numero=3)

    assert [t.title for t in player.queue] == ["c"]
    player.skip.assert_awaited_once()
    assert "c" in i.response.inviati[0]


@pytest.mark.asyncio
async def test_skipto_oltre_la_coda_rifiuta(monkeypatch):
    player = _player([_t("a")])
    cog = _cog(player, monkeypatch)
    i = _Interazione()
    await cog.skipto.callback(cog, i, numero=5)
    assert "1 brani" in i.response.inviati[0]
    player.skip.assert_not_called()
    assert len(player.queue) == 1


@pytest.mark.asyncio
async def test_remove_intervallo_utente_e_assenti(monkeypatch):
    player = _player([_t("a", 1), _t("b", 2), _t("c", 2), _t("d", 3), _t("e")])
    cog = _cog(player, monkeypatch)

    i = _Interazione()
    await cog.remove.callback(cog, i, da=2, a=3)
    assert [t.title for t in player.queue] == ["a", "d", "e"]

    i = _Interazione()
    await cog.remove.callback(cog, i, utente=SimpleNamespace(id=1))
    assert [t.title for t in player.queue] == ["d", "e"]

    i = _Interazione(membri=[99])  # l'utente 3 non è nel canale
    await cog.remove.callback(cog, i, assenti=True)
    assert [t.title for t in player.queue] == ["e"]  # "e" non ha richiedente noto: resta


@pytest.mark.asyncio
async def test_remove_vuole_un_solo_criterio(monkeypatch):
    player = _player([_t("a", 1)])
    cog = _cog(player, monkeypatch)
    for kw in ({}, {"da": 1, "assenti": True}, {"a": 2}):
        i = _Interazione()
        await cog.remove.callback(cog, i, **kw)
        assert "UN solo criterio" in i.response.inviati[0]
    assert len(player.queue) == 1


@pytest.mark.asyncio
async def test_previous_rimette_il_corrente_in_cima_e_suona_il_precedente(monkeypatch):
    prima, ora = _t("prima"), _t("ora")
    player = _player([_t("dopo")], corrente=ora, storico=[prima, ora])
    cog = _cog(player, monkeypatch)
    i = _Interazione()

    await cog.previous.callback(cog, i)

    player.play.assert_awaited_once_with(prima, add_history=False)
    assert [t.title for t in player.queue] == ["ora", "dopo"]
    # lo storico non conserva il brano lasciato: due "previous" non fanno avanti-indietro
    assert list(player.queue.history) == [prima]


@pytest.mark.asyncio
async def test_previous_a_coda_finita_riprende_l_ultimo_brano_finito(monkeypatch):
    finito = _t("finito")
    player = _player([], corrente=None, storico=[_t("vecchio"), finito])
    cog = _cog(player, monkeypatch)
    await cog.previous.callback(cog, _Interazione())
    player.play.assert_awaited_once_with(finito, add_history=False)
    assert list(player.queue.tracce) == []


@pytest.mark.asyncio
async def test_previous_senza_storico_lo_dice(monkeypatch):
    player = _player([], corrente=_t("ora"), storico=[_t("ora")])
    cog = _cog(player, monkeypatch)
    i = _Interazione()
    await cog.previous.callback(cog, i)
    assert "precedente" in i.response.inviati[0]
    player.play.assert_not_called()


@pytest.mark.asyncio
async def test_history_mostra_gli_ultimi_senza_il_corrente(monkeypatch):
    storico = [_t(f"t{n}") for n in range(15)]
    player = _player([], corrente=storico[-1], storico=storico)
    cog = _cog(player, monkeypatch)
    i = _Interazione()

    await cog.history.callback(cog, i)

    descr = i.response.embeds[0].description
    assert descr.startswith("1. t13")
    assert "t14" not in descr
    assert descr.count("\n") == 9  # al massimo 10 righe


@pytest.mark.asyncio
async def test_queue_cerca_e_mostra_le_quote(monkeypatch):
    player = _player([_t("Blue Monday", 1), _t("Red", 1), _t("Bluebird", 2)], corrente=_t("x"))
    cog = _cog(player, monkeypatch)

    i = _Interazione()
    await cog.queue_command.callback(cog, i, cerca="blue")
    assert i.response.embeds[0].description == "1. Blue Monday\n3. Bluebird"

    i = _Interazione()
    await cog.queue_command.callback(cog, i)
    campo = i.response.embeds[0].fields[0]
    assert campo.name == "Chi ha messo cosa" and "<@1> — 2 brani (67%)" in campo.value
    assert len(campo.value) <= 1024

    i = _Interazione()
    await cog.queue_command.callback(cog, i, cerca="zzz")
    assert "Nessun brano" in i.response.embeds[0].description


@pytest.mark.asyncio
async def test_play_in_cima_mette_il_brano_per_primo_e_ricorda_chi_lo_ha_messo(monkeypatch):
    nuovo = _t("nuovo")
    player = _player([_t("gia1"), _t("gia2")])
    player.channel = None
    guild_w = SimpleNamespace(voice_client=player)
    worker = SimpleNamespace(worker_index=1, get_guild=lambda gid: guild_w)

    class _F:
        async def get_or_assign_worker_for_channel(self, g, c):
            return 1, worker

    monkeypatch.setattr(
        player_module, "db", SimpleNamespace(
            is_module_active_for_guild=AsyncMock(return_value=True), get_guild_setting=_senza_impostazioni
        )
    )
    player.node = object()
    cog = MusicCog(bot=SimpleNamespace(music_fleet=_F()))
    i = _Interazione()

    with patch.object(cog, "_cerca", new=AsyncMock(return_value=([nuovo], player.node))):
        await cog.play.callback(cog, i, query="nuovo", in_cima=True)

    assert [t.title for t in player.queue][0] == "nuovo"
    assert requester_of(nuovo) == 1


@pytest.mark.asyncio
async def test_join_senza_nodi_libera_la_sessione(monkeypatch):
    monkeypatch.setattr(
        player_module, "db", SimpleNamespace(
            is_module_active_for_guild=AsyncMock(return_value=True), get_guild_setting=_senza_impostazioni
        )
    )
    guild_w = SimpleNamespace(voice_client=None, get_channel=lambda cid: object())
    worker = SimpleNamespace(worker_index=1, get_guild=lambda gid: guild_w)
    rilasci = []

    class _F:
        async def get_or_assign_worker_for_channel(self, g, c):
            return 1, worker

        async def release_session(self, g, c):
            rilasci.append((g, c))

    gestore = SimpleNamespace(node_for=lambda k: None)
    cog = MusicCog(bot=SimpleNamespace(music_fleet=_F(), music_nodes=gestore))
    i = _Interazione()
    await cog.join.callback(cog, i)
    assert "nodo Lavalink" in i.followup.inviati[0]
    assert rilasci == [(900, 11)]


def test_mescola_solo_i_propri_brani_lascia_gli_altri_al_loro_posto():
    import random

    richiedenti = [1, 2, 1, 2, 1, None]
    for seme in range(20):
        ordine = own_shuffle_order(richiedenti, 1, random.Random(seme))
        assert sorted(ordine) == list(range(6))
        for posto in (1, 3, 5):  # non sono di 1: restano fermi
            assert ordine[posto] == posto
        assert {ordine[0], ordine[2], ordine[4]} == {0, 2, 4}
    assert own_shuffle_order([2, 2], 1) == [0, 1]  # nessun brano suo


@pytest.mark.asyncio
async def test_shuffle_solo_miei_tocca_solo_i_brani_dell_utente(monkeypatch):
    tracce = [_t("a", 1), _t("b", 2), _t("c", 1), _t("d", 2), _t("e", 1)]
    player = _player(tracce)
    cog = _cog(player, monkeypatch)
    for seme in range(5):  # a prescindere dal sorteggio
        i = _Interazione()
        await cog.shuffle.callback(cog, i, solo_miei=True)
        titoli = [t.title for t in player.queue]
        assert titoli[1] == "b" and titoli[3] == "d"
        assert sorted(titoli) == ["a", "b", "c", "d", "e"]


@pytest.mark.asyncio
async def test_skipto_in_loop_all_rimette_in_fondo_i_brani_saltati(monkeypatch):
    import wavelink

    player = _player([_t("a"), _t("b"), _t("c"), _t("d")])
    player.queue.mode = wavelink.QueueMode.loop_all
    cog = _cog(player, monkeypatch)
    await cog.skipto.callback(cog, _Interazione(), numero=3)
    assert [t.title for t in player.queue] == ["c", "d", "a", "b"]


@pytest.mark.asyncio
async def test_shuffle_solo_miei_non_lascia_mai_la_coda_vuota_tra_un_await_e_l_altro(monkeypatch):
    """Atomico: clear e put senza await in mezzo (un altro comando non vede la coda vuota)."""
    player = _player([_t("a", 1), _t("b", 2), _t("c", 1)])
    eventi = []
    originale_clear, originale_put = player.queue.clear, player.queue.put
    player.queue.clear = lambda: (eventi.append("clear"), originale_clear())[1]
    player.queue.put = lambda t: (eventi.append("put"), originale_put(t))[1]

    async def _vietato(t):
        raise AssertionError("put_wait: un await con la coda vuota")

    player.queue.put_wait = _vietato
    cog = _cog(player, monkeypatch)
    for _ in range(5):
        await cog.shuffle.callback(cog, _Interazione(), solo_miei=True)
    assert len(player.queue) == 3
    assert eventi[:2] == ["clear", "put"]

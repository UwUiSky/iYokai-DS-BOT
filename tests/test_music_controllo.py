"""
tests/test_music_controllo.py
=============================
Coda e posizione (MUS-022..026, 028, 033, 034), modalità DJ (MUS-051) e voto per saltare (MUS-052),
con un player finto. La logica pura è in test_music_dj_logic.py.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

import cogs.music.player as player_module
from cogs.music.controllo import MusicControlloCog, sposta_elemento
from tests.test_music_queue_cmds import _cog, _Interazione, _player, _t, _Utente


class _Persona(_Utente):
    def __init__(self, uid=1, staff=False, ruoli=(), membri=()):
        super().__init__(membri)
        self._uid, self._staff, self._ruoli = uid, staff, [SimpleNamespace(id=r) for r in ruoli]

    @property
    def id(self):
        return self._uid

    @property
    def roles(self):
        return self._ruoli

    @property
    def guild_permissions(self):
        return SimpleNamespace(manage_guild=self._staff)


def _umani(*ids):
    return [SimpleNamespace(id=i, bot=False) for i in ids] + [SimpleNamespace(id=999, bot=True)]


def _prepara(player, monkeypatch, impostazioni=None, utente=None, canale_membri=(1, 2, 3)):
    musica = _cog(player, monkeypatch)
    monkeypatch.setattr(
        player_module, "db", SimpleNamespace(
            is_module_active_for_guild=AsyncMock(return_value=True), get_guild_setting=_legge(impostazioni or {})
        ),
    )
    import cogs.music.controllo as controllo_module

    monkeypatch.setattr(controllo_module, "db", player_module.db)
    player.channel = SimpleNamespace(id=11, members=_umani(*canale_membri))
    controllo = MusicControlloCog(bot=SimpleNamespace(get_cog=lambda nome: musica))
    i = _Interazione()
    i.user = utente or _Persona(1, membri=canale_membri)
    i.user._voce = SimpleNamespace(channel=player.channel)
    i.guild = SimpleNamespace(id=900)
    return controllo, musica, i


def _legge(valori):
    async def get(g, k, d=None):
        return valori.get(k, d)

    return get


def titoli(player):
    return [t.title for t in player.queue]


def test_sposta_elemento():
    assert sposta_elemento(list("abcd"), 0, 2) == list("bcad")
    assert sposta_elemento(list("abcd"), 3, 0) == list("dabc")
    assert sposta_elemento(list("abcd"), 1, 99) == list("acdb")


@pytest.mark.asyncio
async def test_togli_solo_i_propri_brani(monkeypatch):
    player = _player([_t("mio", 1), _t("altrui", 2)])
    c, _m, i = _prepara(player, monkeypatch)
    await c.coda_togli.callback(c, i, posizione=2)
    assert titoli(player) == ["mio", "altrui"]
    assert "solo i brani" in i.response.inviati[0]
    i2 = _Interazione()
    i2.user, i2.guild, i2.response = i.user, i.guild, type(i.response)()
    await c.coda_togli.callback(c, i2, posizione=1)
    assert titoli(player) == ["altrui"]


@pytest.mark.asyncio
async def test_togli_dj_e_staff_toccano_tutto(monkeypatch):
    player = _player([_t("a", 2), _t("b", 3)])
    c, _m, i = _prepara(player, monkeypatch, utente=_Persona(1, staff=True))
    await c.coda_togli.callback(c, i, posizione=2)
    assert titoli(player) == ["a"]
    player2 = _player([_t("a", 2)])
    c, _m, i = _prepara(player2, monkeypatch, {"music_dj_role_id": 50}, utente=_Persona(1, ruoli=[50]))
    await c.coda_togli.callback(c, i, posizione=1)
    assert titoli(player2) == []


@pytest.mark.asyncio
async def test_togli_posizione_inesistente(monkeypatch):
    player = _player([_t("a", 1)])
    c, _m, i = _prepara(player, monkeypatch)
    await c.coda_togli.callback(c, i, posizione=5)
    assert "1 brani" in i.response.inviati[0] and titoli(player) == ["a"]


@pytest.mark.asyncio
async def test_ultimo_toglie_l_ultimo_messo_da_te(monkeypatch):
    player = _player([_t("a", 1), _t("x", 2), _t("b", 1), _t("y", 2)])
    c, _m, i = _prepara(player, monkeypatch)
    await c.coda_ultimo.callback(c, i)
    assert titoli(player) == ["a", "x", "y"]


@pytest.mark.asyncio
async def test_miei_toglie_tutti_e_solo_i_tuoi(monkeypatch):
    player = _player([_t("a", 1), _t("x", 2), _t("b", 1)])
    c, _m, i = _prepara(player, monkeypatch)
    await c.coda_miei.callback(c, i)
    assert titoli(player) == ["x"]
    c2, _m, i2 = _prepara(_player([_t("x", 2)]), monkeypatch)
    await c2.coda_miei.callback(c2, i2)
    assert "nessun" in i2.response.inviati[0].lower()


@pytest.mark.asyncio
async def test_sposta_e_cima_rispettano_i_permessi(monkeypatch):
    player = _player([_t("a", 1), _t("b", 1), _t("c", 2)])
    c, _m, i = _prepara(player, monkeypatch)
    await c.coda_sposta.callback(c, i, da=1, a=2)
    assert titoli(player) == ["b", "a", "c"]
    i.response.inviati.clear()
    await c.coda_cima.callback(c, i, posizione=3)  # di un altro: rifiutato
    assert titoli(player) == ["b", "a", "c"]
    await c.coda_cima.callback(c, i, posizione=2)
    assert titoli(player) == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_subito_solo_per_privilegiati(monkeypatch):
    player = _player([_t("a", 1), _t("b", 1)])
    c, _m, i = _prepara(player, monkeypatch)  # tre persone nel canale: non è da solo
    await c.coda_subito.callback(c, i, posizione=2)
    player.skip.assert_not_called()
    assert titoli(player) == ["a", "b"]
    c, _m, i = _prepara(player, monkeypatch, utente=_Persona(1, staff=True))
    await c.coda_subito.callback(c, i, posizione=2)
    assert titoli(player) == ["b", "a"]
    player.skip.assert_awaited_once()


@pytest.mark.asyncio
async def test_subito_da_soli_nel_canale(monkeypatch):
    player = _player([_t("a", 1), _t("b", 1)])
    c, _m, i = _prepara(player, monkeypatch, canale_membri=(1,))
    await c.coda_subito.callback(c, i, posizione=2)
    player.skip.assert_awaited_once()


@pytest.mark.asyncio
async def test_ricomincia_e_vai_a(monkeypatch):
    player = _player([], corrente=SimpleNamespace(title="x", length=200_000, is_seekable=True))
    player.seek, player.position = AsyncMock(), 60_000
    c, _m, i = _prepara(player, monkeypatch)
    await c.brano_ricomincia.callback(c, i)
    player.seek.assert_awaited_with(0)
    await c.brano_vai_a.callback(c, i, punto="+0:30")
    player.seek.assert_awaited_with(90_000)
    await c.brano_vai_a.callback(c, i, punto="-2:00")
    player.seek.assert_awaited_with(0)
    n = player.seek.await_count
    i2 = _Interazione()
    i2.user, i2.guild = i.user, i.guild
    await c.brano_vai_a.callback(c, i2, punto="xx")
    assert player.seek.await_count == n and "non valido" in i2.response.inviati[0].lower()


@pytest.mark.asyncio
async def test_vai_a_su_una_diretta_rifiuta(monkeypatch):
    player = _player([], corrente=SimpleNamespace(title="radio", length=0, is_seekable=False))
    player.seek = AsyncMock()
    c, _m, i = _prepara(player, monkeypatch)
    await c.brano_vai_a.callback(c, i, punto="1:00")
    player.seek.assert_not_called()


@pytest.mark.asyncio
async def test_modalita_dj_ferma_chi_non_e_dj(monkeypatch):
    player = _player([_t("a", 1)], corrente=SimpleNamespace(title="x", length=200_000, is_seekable=True))
    player.seek, player.position = AsyncMock(), 0
    c, _m, i = _prepara(player, monkeypatch, {"music_dj_mode": True, "music_dj_role_id": 50})
    await c.brano_ricomincia.callback(c, i)
    player.seek.assert_not_called()
    assert "DJ" in i.response.inviati[0]
    c, _m, i = _prepara(player, monkeypatch, {"music_dj_mode": True, "music_dj_role_id": 50}, utente=_Persona(1, ruoli=[50]))
    await c.brano_ricomincia.callback(c, i)
    player.seek.assert_awaited_once()


@pytest.mark.asyncio
async def test_modalita_dj_blocca_i_comandi_del_player(monkeypatch):
    player = _player([_t("a", 1)])
    player.pause = AsyncMock()
    _c, musica, i = _prepara(player, monkeypatch, {"music_dj_mode": True})
    await musica.pause.callback(musica, i)
    player.pause.assert_not_called()
    assert "DJ" in i.response.inviati[0]


@pytest.mark.asyncio
async def test_senza_modalita_dj_il_comando_passa(monkeypatch):
    player = _player([_t("a", 1)])
    player.pause = AsyncMock()
    _c, musica, i = _prepara(player, monkeypatch)
    await musica.pause.callback(musica, i)
    player.pause.assert_awaited_once()


# ----------------------------- voto per saltare -----------------------------
@pytest.mark.asyncio
async def test_salta_subito_chi_ha_messo_il_brano(monkeypatch):
    player = _player([], corrente=_t("x", 1))
    _c, musica, i = _prepara(player, monkeypatch)
    await musica.skip.callback(musica, i)
    player.skip.assert_awaited_once()


@pytest.mark.asyncio
async def test_voto_per_saltare_serve_meta_degli_ascoltatori(monkeypatch):
    player = _player([], corrente=_t("x", 9))
    _c, musica, i = _prepara(player, monkeypatch, canale_membri=(1, 2, 3, 4))
    await musica.skip.callback(musica, i)
    player.skip.assert_not_called()
    assert "1 su 2" in i.response.inviati[0]
    await musica.skip.callback(musica, i)  # lo stesso utente: non conta due volte
    assert "già" in i.response.inviati[1]
    _c, musica2, i2 = _prepara(player, monkeypatch, canale_membri=(1, 2, 3, 4), utente=_Persona(2, membri=(1, 2, 3, 4)))
    musica2.voti_salto = musica.voti_salto
    await musica2.skip.callback(musica2, i2)
    player.skip.assert_awaited_once()


@pytest.mark.asyncio
async def test_staff_e_dj_saltano_senza_voto(monkeypatch):
    player = _player([], corrente=_t("x", 9))
    _c, musica, i = _prepara(player, monkeypatch, canale_membri=(1, 2, 3, 4), utente=_Persona(1, staff=True))
    await musica.skip.callback(musica, i)
    player.skip.assert_awaited_once()


# ----------------------------- testo e karaoke (MUS-046) -----------------------------
import asyncio  # noqa: E402

import cogs.music.controllo as controllo_module  # noqa: E402
from core.music_lyrics_logic import ServizioNonRisponde, Testi  # noqa: E402

_LRC = "[00:00.50]uno\n[00:01.00]due\n[00:02.00]tre\n"


class _Messaggio:
    def __init__(self):
        self.modifiche = []

    async def edit(self, **kw):
        self.modifiche.append(kw["content"])
        assert kw["allowed_mentions"].everyone is False


def _con_followup(i, messaggio):
    async def invia(content=None, embed=None, **kw):
        if embed is not None:
            i.followup.embeds.append(embed)
        else:
            i.followup.inviati.append(content)
        return messaggio

    i.followup.send = invia


def _brano():
    return SimpleNamespace(title="Artista - Canzone", author="Artista", length=200_000, is_seekable=True)


@pytest.mark.asyncio
async def test_testo_servizio_che_non_risponde_lo_dice(monkeypatch):
    player = _player([], corrente=_brano())
    c, _m, i = _prepara(player, monkeypatch)
    _con_followup(i, None)

    async def giu(*a, **k):
        raise ServizioNonRisponde()

    monkeypatch.setattr(controllo_module, "cerca_testi", giu)
    await c.brano_testo.callback(c, i)
    assert "non risponde" in i.followup.inviati[0]


@pytest.mark.asyncio
async def test_testo_mostrato_troncato_senza_menzioni(monkeypatch):
    player = _player([], corrente=_brano())
    c, _m, i = _prepara(player, monkeypatch)
    _con_followup(i, None)

    async def trovato(*a, **k):
        return Testi("Canzone", "Artista", "@everyone " + "ciao " * 2000, "")

    monkeypatch.setattr(controllo_module, "cerca_testi", trovato)
    await c.brano_testo.callback(c, i)
    assert len(i.followup.embeds[0].description) <= 3000


@pytest.mark.asyncio
async def test_testo_pausa_tra_due_richieste(monkeypatch):
    player = _player([], corrente=_brano())
    c, _m, i = _prepara(player, monkeypatch)
    _con_followup(i, None)

    async def trovato(*a, **k):
        return Testi("C", "A", "ciao", "")

    monkeypatch.setattr(controllo_module, "cerca_testi", trovato)
    await c.brano_testo.callback(c, i)
    await c.brano_testo.callback(c, i)
    assert "secondi" in i.response.inviati[-1]


@pytest.mark.asyncio
async def test_karaoke_segue_la_posizione_e_si_ferma_con_il_brano(monkeypatch):
    monkeypatch.setattr(controllo_module, "KARAOKE_INTERVALLO", 0.01)
    brano = _brano()
    player = _player([], corrente=brano)
    player.position = 0
    c, _m, i = _prepara(player, monkeypatch)
    messaggio = _Messaggio()
    _con_followup(i, messaggio)

    async def trovato(*a, **k):
        return Testi("C", "A", "x", _LRC)

    monkeypatch.setattr(controllo_module, "cerca_testi", trovato)
    await c.brano_karaoke.callback(c, i)
    compito = c.karaoke[900]
    player.position = 1_200
    await asyncio.sleep(0.05)
    player.position = 2_500
    await asyncio.sleep(0.05)
    assert any("**due**" in m for m in messaggio.modifiche)
    assert any("**tre**" in m for m in messaggio.modifiche)
    # secondo karaoke nello stesso server: rifiutato
    i2 = _Interazione()
    i2.user, i2.guild = i.user, i.guild
    await c.brano_karaoke.callback(c, i2)
    assert "già" in i2.response.inviati[0]
    player.current = None  # stop: il brano non c'è più
    await asyncio.wait_for(compito, 1)
    assert 900 not in c.karaoke
    assert "finito" in messaggio.modifiche[-1].lower()


@pytest.mark.asyncio
async def test_karaoke_senza_tempi_manda_al_testo(monkeypatch):
    player = _player([], corrente=_brano())
    c, _m, i = _prepara(player, monkeypatch)
    _con_followup(i, _Messaggio())

    async def solo_testo(*a, **k):
        return Testi("C", "A", "ciao", "")

    monkeypatch.setattr(controllo_module, "cerca_testi", solo_testo)
    await c.brano_karaoke.callback(c, i)
    assert "senza i tempi" in i.followup.inviati[0] and 900 not in c.karaoke

"""
tests/test_music_coda_b3.py
===========================
Catalogo MUS (issue #126) B3 «coda»: ordine equo (MUS-037), cerca (MUS-035),
salta per intervallo o utente (MUS-030), pulisci gli assenti (MUS-027),
mescola che resta (MUS-038). Logica pura + comandi con un player finto.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import cogs.music.player as player_module
from core.music_queue_logic import fair_order, find_in_queue, indici_da_saltare, indici_di_assenti
from core.music_settings_logic import MusicSettings, load_music_settings, summary_lines
from tests.test_music_queue_cmds import _cog, _Interazione, _player, _t, _Utente


# ----------------------------- logica pura -----------------------------
def test_ordine_equo_a_giro_tra_utenti():
    assert fair_order([1, 1, 1, 2, 2, 3]) == [0, 3, 5, 1, 4, 2]
    assert fair_order([]) == []
    assert fair_order([5]) == [0]


def test_ordine_equo_tiene_l_ordine_dei_brani_e_conta_i_senza_richiedente():
    ordine = fair_order([None, 2, None, 2, 1])
    assert sorted(ordine) == [0, 1, 2, 3, 4]
    assert ordine == [0, 1, 4, 2, 3]  # None e' un utente a parte; prima comparsa: None, 2, 1


def test_cerca_in_coda_senza_maiuscole_e_accenti():
    titoli = ["Città Vuota", "altro", "CITTA di notte"]
    assert find_in_queue(titoli, "citta") == [(1, "Città Vuota"), (3, "CITTA di notte")]
    assert find_in_queue(titoli, "zzz") == []
    assert find_in_queue(titoli, "  ") == []


def test_cerca_in_coda_ha_un_tetto():
    titoli = [f"brano {i}" for i in range(30)]
    assert len(find_in_queue(titoli, "brano")) == 10
    assert find_in_queue(titoli, "brano", limite=3)[-1] == (3, "brano 2")


def test_da_saltare_per_intervallo():
    r = [1, 2, 3, 4, 5]
    assert indici_da_saltare(r, da=2, a=4) == [1, 2, 3]
    assert indici_da_saltare(r, da=4) == [3, 4]
    assert indici_da_saltare(r, a=2) == [0, 1]
    assert indici_da_saltare(r, da=3, a=99) == [2, 3, 4]  # tagliato alla lunghezza
    assert indici_da_saltare(r, da=9, a=12) == []
    assert indici_da_saltare(r, da=4, a=2) == []


def test_da_saltare_per_utente_e_insieme():
    r = [1, 2, 1, 2, 1]
    assert indici_da_saltare(r, utente_id=1) == [0, 2, 4]
    assert indici_da_saltare(r, da=2, a=4, utente_id=1) == [2]
    assert indici_da_saltare(r) == []


def test_assenti():
    assert indici_di_assenti([1, 2, None, 3, 2], {1, 3}) == [1, 4]
    assert indici_di_assenti([None, None], set()) == []


# ----------------------------- impostazione -----------------------------
def test_riepilogo_ha_la_riga_della_coda():
    assert any("equa" in r for r in summary_lines(MusicSettings(queue_mode="equa")))


@pytest.mark.asyncio
async def test_lettura_modo_coda_valido():
    async def get(g, k, d=None):
        return {"music_queue_mode": "equa"}.get(k, d)

    assert (await load_music_settings(SimpleNamespace(get_guild_setting=get), 1)).queue_mode == "equa"

    async def brutto(g, k, d=None):
        return {"music_queue_mode": "boh"}.get(k, d)

    assert (await load_music_settings(SimpleNamespace(get_guild_setting=brutto), 1)).queue_mode == "normale"
    assert MusicSettings().queue_mode == "normale"


# ----------------------------- comandi -----------------------------
def _cog_con(player, monkeypatch, modo="normale", gestisci=True):
    cog = _cog(player, monkeypatch)

    async def get(g, k, d=None):
        return {"music_queue_mode": modo}.get(k, d)

    monkeypatch.setattr(
        player_module,
        "db",
        SimpleNamespace(is_module_active_for_guild=AsyncMock(return_value=True), get_guild_setting=get),
    )
    return cog


class _Gestore(_Utente):
    def __init__(self, si):
        super().__init__()
        self._si = si

    @property
    def guild_permissions(self):
        return SimpleNamespace(manage_guild=self._si)


def _admin(i, si=True):
    i.user = _Gestore(si)
    return i


@pytest.mark.asyncio
async def test_coda_cerca_risponde_effimero_con_al_massimo_10_righe(monkeypatch):
    player = _player([_t(f"brano {n}") for n in range(25)])
    cog = _cog_con(player, monkeypatch)
    i = _Interazione()
    await cog.coda_cerca.callback(cog, i, testo="brano")
    assert i.response.inviati == [] and len(i.response.embeds) == 1
    assert i.response.embeds[0].description.count("\n") + 1 == 10
    assert len(i.response.embeds[0].description) <= 4096


@pytest.mark.asyncio
async def test_coda_cerca_senza_risultati(monkeypatch):
    player = _player([_t("a")])
    cog = _cog_con(player, monkeypatch)
    i = _Interazione()
    await cog.coda_cerca.callback(cog, i, testo="zzz")
    assert i.response.embeds == [] and len(i.response.inviati) == 1


@pytest.mark.asyncio
async def test_coda_salta_toglie_per_intervallo(monkeypatch):
    player = _player([_t(c, 1) for c in "abcde"])
    cog = _cog_con(player, monkeypatch)
    i = _admin(_Interazione())
    await cog.coda_salta.callback(cog, i, da=2, a=3, utente=None)
    assert [t.title for t in player.queue] == ["a", "d", "e"]
    assert "2" in i.response.inviati[0]


@pytest.mark.asyncio
async def test_coda_salta_per_utente(monkeypatch):
    player = _player([_t("a", 1), _t("b", 2), _t("c", 1)])
    cog = _cog_con(player, monkeypatch)
    i = _admin(_Interazione())
    await cog.coda_salta.callback(cog, i, da=None, a=None, utente=SimpleNamespace(id=1))
    assert [t.title for t in player.queue] == ["b"]


@pytest.mark.asyncio
async def test_coda_salta_serve_un_opzione_e_il_permesso(monkeypatch):
    player = _player([_t("a", 1)])
    cog = _cog_con(player, monkeypatch)
    i = _admin(_Interazione())
    await cog.coda_salta.callback(cog, i, da=None, a=None, utente=None)
    assert len(player.queue) == 1 and i.response.inviati
    i2 = _admin(_Interazione(), si=False)
    await cog.coda_salta.callback(cog, i2, da=1, a=1, utente=None)
    assert len(player.queue) == 1 and i2.response.inviati


@pytest.mark.asyncio
async def test_coda_salta_non_ha_await_tra_lettura_e_scrittura(monkeypatch):
    player = _player([_t(c, 1) for c in "abc"])

    async def _vietato(t):
        raise AssertionError("put_wait con la coda svuotata")

    player.queue.put_wait = _vietato
    cog = _cog_con(player, monkeypatch)
    await cog.coda_salta.callback(cog, _admin(_Interazione()), da=1, a=1, utente=None)
    assert [t.title for t in player.queue] == ["b", "c"]


def _con_canale(player, presenti):
    player.channel = SimpleNamespace(members=[SimpleNamespace(id=p) for p in presenti])
    return player


@pytest.mark.asyncio
async def test_coda_pulisci_toglie_chi_non_e_nel_canale(monkeypatch):
    player = _con_canale(_player([_t("a", 1), _t("b", 2), _t("c", None), _t("d", 3)]), [1, 3])
    cog = _cog_con(player, monkeypatch)
    i = _admin(_Interazione())
    await cog.coda_pulisci.callback(cog, i)
    assert [t.title for t in player.queue] == ["a", "c", "d"]
    assert "1" in i.response.inviati[0]


@pytest.mark.asyncio
async def test_coda_pulisci_solo_per_chi_gestisce_il_server(monkeypatch):
    player = _con_canale(_player([_t("a", 2)]), [1])
    cog = _cog_con(player, monkeypatch)
    i = _admin(_Interazione(), si=False)
    await cog.coda_pulisci.callback(cog, i)
    assert len(player.queue) == 1


@pytest.mark.asyncio
async def test_aggiunta_in_coda_equa_riordina(monkeypatch):
    from core.music_queue_logic import requester_of

    player = _player([_t("a", 1), _t("b", 1), _t("c", 2)])
    cog = _cog_con(player, monkeypatch, modo="equa")
    cog._applica_modo_coda(player, MusicSettings(queue_mode="equa"))
    assert [t.title for t in player.queue] == ["a", "c", "b"]
    player.mescola_fisso = True
    player.queue.tracce.append(_t("z", 1))
    cog._applica_modo_coda(player, MusicSettings(queue_mode="equa"))
    assert [t.title for t in player.queue][-1] == "z"  # mescola fisso: non si riordina
    assert requester_of(player.queue[0]) == 1


@pytest.mark.asyncio
async def test_shuffle_resta_accende_e_spegne(monkeypatch):
    player = _player([_t("a"), _t("b"), _t("c")])
    cog = _cog_con(player, monkeypatch)
    await cog.shuffle.callback(cog, _Interazione(), resta=True)
    assert player.mescola_fisso is True
    await cog.shuffle.callback(cog, _Interazione(), resta=False)
    assert player.mescola_fisso is False


@pytest.mark.asyncio
async def test_shuffle_resta_con_coda_corta_si_accende_lo_stesso(monkeypatch):
    player = _player([_t("a")])
    cog = _cog_con(player, monkeypatch)
    i = _Interazione()
    await cog.shuffle.callback(cog, i, resta=True)
    assert player.mescola_fisso is True and i.response.inviati


@pytest.mark.asyncio
async def test_nuovo_brano_con_mescola_fisso_entra_a_caso():
    cog = player_module.MusicCog(bot=SimpleNamespace())
    posti = set()
    for _ in range(40):
        p = _player([_t(c) for c in "abcdef"])
        p.mescola_fisso = True
        await cog._aggiungi_in_fondo(p, [_t("z")], MusicSettings())
        posti.add([t.title for t in p.queue].index("z"))
    assert len(posti) > 1


@pytest.mark.asyncio
async def test_coda_pulisci_senza_elenco_dei_presenti_non_tocca_la_coda(monkeypatch):
    """Canale non leggibile (o elenco vuoto): senza sapere chi c'è non si toglie niente."""
    for player in (_player([_t("a", 1), _t("b", 2)]), _con_canale(_player([_t("a", 1), _t("b", 2)]), [])):
        cog = _cog_con(player, monkeypatch)
        i = _admin(_Interazione())
        await cog.coda_pulisci.callback(cog, i)
        assert [t.title for t in player.queue] == ["a", "b"]
        assert "non ho tolto niente" in i.response.inviati[0]

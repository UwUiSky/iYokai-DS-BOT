"""
tests/test_music_capitoli.py
============================
Catalogo MUS (issue #126) giro r7mus: MUS-017, video lunghi (D111, D115).
Analizzatore dell'elenco con orari, limiti, voci della coda con inizio e fine.
"""

import pytest

from core import music_capitoli_logic as cl

ORA = 3600_000


def _titoli(voci):
    return [v.titolo for v in voci]


def _inizi(voci):
    return [v.inizio_ms for v in voci]


# ----------------------------- formati degli orari -----------------------------
@pytest.mark.parametrize("riga,atteso", [
    ("0:00 Intro", 0), ("00:00 Intro", 0), ("1:02:03 Intro", ORA + 123_000), ("01:02:03 Intro", ORA + 123_000),
    ("75:30 Intro", 75 * 60_000 + 30_000), ("0:59 Intro", 59_000), ("10:5 Intro", None), ("1:60 Intro", None),
    ("1:75:00 Intro", None), ("12 Intro", None), ("Intro", None), ("", None), ("abc 1:00", None),
])
def test_formati_degli_orari(riga, atteso):
    trovato = cl._riga_con_orario(riga)
    assert (trovato[0] if trovato else None) == atteso


@pytest.mark.parametrize("riga", [
    "0:00 Titolo", "00:00 - Titolo", "0:00 – Titolo", "0:00 — Titolo", "0:00: Titolo", "0:00) Titolo", "0:00 | Titolo",
    "[0:00] Titolo", "(0:00) Titolo", "[00:00] - Titolo", "1. 0:00 Titolo", "01) 0:00 - Titolo", "- 0:00 Titolo",
    "• 0:00 Titolo", "▶ 0:00 Titolo", "  0:00   Titolo  ", "0:00.Titolo", "0:00 > Titolo",
])
def test_separatori_diversi_tra_orario_e_titolo(riga):
    ms, titolo = cl._riga_con_orario(riga)
    assert ms == 0 and cl.titolo_pulito(titolo) == "Titolo"


def test_orario_in_fondo_alla_riga():
    assert cl._riga_con_orario_in_fondo("Titolo - 3:45")[0] == 225_000
    assert cl._riga_con_orario_in_fondo("Titolo [1:02:03]")[0] == ORA + 123_000
    assert cl._riga_con_orario_in_fondo("Titolo") is None


# ----------------------------- elenchi interi -----------------------------
DESCRIZIONE = """Grazie per aver guardato! Iscriviti https://example.com/x

Tracklist:
00:00 Prima canzone
03:30 - Seconda canzone
7:05 – Terza canzone (live)
1:02:03 Ultima

Segui su @social
"""


def test_elenco_dalla_descrizione_con_inizi_e_fine():
    voci = cl.analizza_elenco(DESCRIZIONE, durata_ms=ORA + 600_000)
    assert _titoli(voci) == ["Prima canzone", "Seconda canzone", "Terza canzone (live)", "Ultima"]
    assert _inizi(voci) == [0, 210_000, 425_000, ORA + 123_000]
    assert [v.fine_ms for v in voci] == [210_000, 425_000, ORA + 123_000, ORA + 600_000]  # ferma all'orario del dopo


def test_elenco_con_orari_in_fondo_se_nessuna_riga_comincia_con_un_orario():
    testo = "Prima - 0:00\nSeconda - 3:30\nTerza - 7:05\n"
    voci = cl.analizza_elenco(testo, 20 * 60_000)
    assert _titoli(voci) == ["Prima", "Seconda", "Terza"] and _inizi(voci) == [0, 210_000, 425_000]


def test_meno_di_3_voci_non_e_un_elenco():
    assert cl.analizza_elenco("0:00 Uno\n3:00 Due\n") == []
    assert cl.analizza_elenco("") == [] and cl.analizza_elenco(None) == []
    assert cl.analizza_elenco("Nessun orario qui\nsolo testo") == []


def test_orari_fuori_ordine_o_doppi_o_oltre_il_video_si_saltano():
    testo = "0:00 A\n5:00 B\n4:00 Fuori ordine\n5:00 Doppio\n5:02 Troppo vicino\n9:00 C\n99:00 Oltre\n"
    voci = cl.analizza_elenco(testo, durata_ms=30 * 60_000)
    assert _titoli(voci) == ["A", "B", "C"]
    assert voci[-1].fine_ms == 30 * 60_000
    oltre = cl.analizza_elenco("0:00 A\n10:00 B\n20:00 C\n40:00 D\n", durata_ms=25 * 60_000)
    assert _titoli(oltre) == ["A", "B", "C"]


def test_tetto_di_100_voci():
    testo = "\n".join(f"{n // 60}:{n % 60:02d} Brano {n}" for n in range(0, 100 * 10, 10) if True)
    assert len(cl.analizza_elenco(testo[:5000], durata_ms=None)) <= cl.MAX_VOCI
    molti = "\n".join(f"{n}:00 Brano {n}" for n in range(0, 150))
    voci = cl.analizza_elenco(molti, durata_ms=200 * 60_000)
    assert len(voci) == cl.MAX_VOCI and voci[-1].titolo == "Brano 99"


def test_titoli_puliti_da_link_menzioni_e_simboli():
    testo = "0:00 @everyone [clic](http://x.it) `codice`\n3:00 https://spam.example/x Bella\n6:00 \x00\x07Ciao​ mondo\n9:00 \n"
    voci = cl.analizza_elenco(testo, durata_ms=20 * 60_000)
    assert voci[0].titolo == "everyone (clic) codice"
    assert "@" not in "".join(_titoli(voci)) and "`" not in "".join(_titoli(voci)) and "http" not in "".join(_titoli(voci))
    assert voci[1].titolo == "Bella" and voci[2].titolo.startswith("Ciao")
    assert voci[3].titolo == "Brano 4"  # titolo vuoto: nome di riserva
    assert all(len(t) <= cl.MAX_TITOLO for t in _titoli(voci))


def test_titolo_lungo_e_testi_enormi_non_bloccano():
    voci = cl.analizza_elenco("0:00 " + "x" * 5000 + "\n5:00 B\n10:00 C\n", 30 * 60_000)
    assert len(voci[0].titolo) == cl.MAX_TITOLO
    enorme = ("0:00 a" + " " * 50 + "\n") * 5000 + ("9" * 100000)
    assert isinstance(cl.analizza_elenco(enorme, 10 ** 9), list)
    lunga = "1:" * 30000 + "x"
    assert cl.analizza_elenco(lunga) == []


def test_senza_durata_l_ultima_voce_dura_un_minuto():
    voci = cl.analizza_elenco("0:00 A\n5:00 B\n10:00 C\n")
    assert voci[-1].fine_ms == 10 * 60_000 + 60_000


# ----------------------------- capitoli di Lavalink o YouTube -----------------------------
def test_capitoli_in_millisecondi_come_voci():
    capitoli = [
        {"title": "B", "start": 300_000}, {"name": "A", "startTime": 0}, {"title": "C", "start_time": 600_000},
        {"title": "storto", "start": "x"}, {"title": "negativo", "start": -5}, 5, None, {"title": "bool", "start": True},
    ]
    voci = cl.voci_da_capitoli(capitoli, 20 * 60_000)
    assert _titoli(voci) == ["A", "B", "C"] and _inizi(voci) == [0, 300_000, 600_000]
    assert cl.voci_da_capitoli("no") == [] and cl.voci_da_capitoli([{"title": "solo", "start": 0}]) == []


# ----------------------------- limite di 8 ore -----------------------------
def test_video_oltre_8_ore_rifiutato():
    assert cl.video_troppo_lungo(8 * ORA + 1) is True
    assert cl.video_troppo_lungo(8 * ORA) is False
    assert cl.video_troppo_lungo(9 * ORA, is_stream=True) is False
    assert cl.video_troppo_lungo(None) is False and cl.video_troppo_lungo("x") is False


# ----------------------------- voci della coda e player -----------------------------
import time  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

import wavelink  # noqa: E402

from core import music_capitoli_player as cp  # noqa: E402


def _video(durata=3 * ORA, titolo="Mix lungo", sorgente="youtube"):
    return wavelink.Playable({
        "encoded": "QAAA", "pluginInfo": {}, "userData": {},
        "info": {
            "identifier": "dQw4w9WgXcQ", "isSeekable": True, "author": "Canale", "length": durata, "isStream": False,
            "position": 0, "title": titolo, "uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "artworkUrl": None, "isrc": None, "sourceName": sorgente,
        },
    })


def test_le_voci_diventano_brani_dello_stesso_video_con_inizio_e_fine():
    voci = cl.analizza_elenco(DESCRIZIONE, durata_ms=ORA + 600_000)
    video = _video(ORA + 600_000)
    brani = cp.brani_da_voci(video, voci, richiedente=77)
    assert [b.title for b in brani] == _titoli(voci)
    assert all(b.encoded == video.encoded and b.source == "youtube" for b in brani)  # lo stesso video, non scaricato
    assert [b.length for b in brani] == [v.fine_ms - v.inizio_ms for v in voci]
    primo = brani[1]
    assert (primo.extras.requester_id, primo.extras.capitolo_inizio_ms, primo.extras.capitolo_fine_ms) == (77, 210_000, 425_000)
    assert cp.limiti_del_brano(primo) == (210_000, 425_000)
    assert cp.limiti_del_brano(video) is None


async def test_play_parte_dal_punto_giusto_e_si_ferma_al_brano_dopo():
    voci = cl.analizza_elenco(DESCRIZIONE, durata_ms=ORA + 600_000)
    brano = cp.brani_da_voci(_video(ORA + 600_000), voci, 1)[1]
    player = object.__new__(cp.PlayerCapitoli)
    with patch.object(wavelink.Player, "play", new=AsyncMock(return_value=brano)) as base:
        await player.play(brano)
        assert base.await_args.kwargs["start"] == 210_000 and base.await_args.kwargs["end"] == 425_000
        await player.play(brano, start=5_000)  # un riavvio dopo 5 s dal punto del brano
        assert base.await_args.kwargs["start"] == 215_000
        await player.play(_video())  # un brano normale non cambia
        assert base.await_args.kwargs["start"] == 0 and base.await_args.kwargs["end"] is None


async def test_seek_e_posizione_sono_relativi_al_brano():
    voci = cl.analizza_elenco(DESCRIZIONE, durata_ms=ORA + 600_000)
    brano = cp.brani_da_voci(_video(ORA + 600_000), voci, 1)[1]  # inizia a 3:30, dura 3:35
    player = object.__new__(cp.PlayerCapitoli)
    player._current, player._connected, player._paused = brano, True, False
    player._last_update, player._last_position = time.monotonic_ns(), 210_000 + 40_000  # 40 s dentro il brano
    with patch.object(type(player), "connected", new=True), patch.object(type(player), "playing", new=True):
        assert 39_000 <= player.position <= 42_000
        player._paused = True
        assert player.position == 40_000
        player._last_position = 3_000_000  # oltre la fine (ritardo di Lavalink): non supera la durata del brano
        assert player.position == brano.length
        player._last_position = 100_000  # prima dell'inizio: mai negativa
        assert player.position == 0
    player._guild = SimpleNamespace(id=1)
    player._node = SimpleNamespace(_update_player=AsyncMock())
    await player.seek(30_000)
    assert player._node._update_player.await_args.kwargs["data"] == {"position": 240_000}
    await player.seek(10 ** 9)  # oltre la fine del brano: si ferma sul brano
    assert player._node._update_player.await_args.kwargs["data"] == {"position": 425_000}
    await player.seek(0)
    assert player._node._update_player.await_args.kwargs["data"] == {"position": 210_000}


def test_un_player_normale_resta_come_prima():
    player = object.__new__(cp.PlayerCapitoli)
    player._current, player._connected, player._paused = _video(), True, True
    player._last_update, player._last_position = time.monotonic_ns(), 5_000
    with patch.object(type(player), "connected", new=True), patch.object(type(player), "playing", new=True):
        assert player.position == 5_000


# ----------------------------- sostituzione nella coda e limite di 8 ore -----------------------------
import cogs.music.player as player_module  # noqa: E402
from cogs.music.player import MusicCog  # noqa: E402


def _player_con_coda(*tracce, corrente=None):
    coda = wavelink.Queue()
    for t in tracce:
        coda.put(t)
    return SimpleNamespace(
        queue=coda, current=corrente, skip=AsyncMock(), guild=SimpleNamespace(id=9), channel=SimpleNamespace(id=4),
    )


async def test_le_voci_prendono_il_posto_del_video_nella_coda():
    voci = cl.analizza_elenco(DESCRIZIONE, durata_ms=ORA + 600_000)
    prima, video, dopo = _video(titolo="prima"), _video(ORA + 600_000), _video(titolo="dopo")
    player = _player_con_coda(prima, video, dopo)
    cog = MusicCog(bot=SimpleNamespace())
    assert await cog._applica_elenco(player, video, voci, 5) == 4
    assert [t.title for t in player.queue] == ["prima", *_titoli(voci), "dopo"]
    assert all(t is not video for t in player.queue)
    assert await cog._applica_elenco(player, video, voci, 5) is None  # il video non c'e' piu': niente doppioni
    assert len(player.queue) == 6


async def test_se_il_video_sta_gia_suonando_parte_il_primo_brano():
    voci = cl.analizza_elenco(DESCRIZIONE, durata_ms=ORA + 600_000)
    video = _video(ORA + 600_000)
    player = _player_con_coda(_video(titolo="dopo"), corrente=video)
    cog = MusicCog(bot=SimpleNamespace())
    assert await cog._applica_elenco(player, video, voci, 5) == 4
    assert [t.title for t in player.queue] == [*_titoli(voci), "dopo"]
    player.skip.assert_awaited_once_with(force=True)
    estraneo = _player_con_coda(corrente=_video())
    assert await cog._applica_elenco(estraneo, video, voci, 5) is None
    estraneo.skip.assert_not_awaited()


async def test_la_proposta_parte_solo_per_i_video_lunghi_di_youtube(monkeypatch):
    cog = MusicCog(bot=SimpleNamespace())
    lanciati = []
    monkeypatch.setattr(cog, "_proponi_elenco", lambda *a: lanciati.append(a) or _niente())
    await cog._pianifica_proposta_elenco(SimpleNamespace(), SimpleNamespace(), _video(5 * 60_000))
    await cog._pianifica_proposta_elenco(SimpleNamespace(), SimpleNamespace(), _video(sorgente="soundcloud"))
    assert lanciati == []
    await cog._pianifica_proposta_elenco(SimpleNamespace(), SimpleNamespace(), _video())
    assert len(lanciati) == 1


async def _niente():
    return None


async def test_la_proposta_manda_un_messaggio_nascosto_con_i_bottoni(monkeypatch):
    import cogs.music.player as modulo

    cog = MusicCog(bot=SimpleNamespace())
    voci = cl.analizza_elenco(DESCRIZIONE, durata_ms=ORA + 600_000)
    monkeypatch.setattr(modulo, "voci_del_video", AsyncMock(return_value=voci))
    monkeypatch.setattr(modulo, "lingua_interazione", AsyncMock(return_value="it"))
    inviato = AsyncMock(return_value=SimpleNamespace())
    inter = SimpleNamespace(user=SimpleNamespace(id=5), followup=SimpleNamespace(send=inviato))
    await cog._proponi_elenco(inter, _player_con_coda(), _video(ORA + 600_000))
    kw = inviato.await_args.kwargs
    assert kw["ephemeral"] is True and kw["view"].utente_id == 5 and len(kw["view"].children) == 2
    assert "4 brani" in inviato.await_args.args[0] and "né tagliato" in inviato.await_args.args[0]
    monkeypatch.setattr(modulo, "voci_del_video", AsyncMock(return_value=[]))
    inviato.reset_mock()
    await cog._proponi_elenco(inter, _player_con_coda(), _video())
    inviato.assert_not_awaited()  # nessun elenco: silenzio


async def test_la_vista_solo_per_chi_ha_messo_il_video_e_un_solo_clic():
    from core.music_capitoli_view import CapitoliView

    chiamate = []

    async def applica():
        chiamate.append(1)
        return 4

    vista = CapitoliView(5, "it", applica)

    def inter(uid):
        return SimpleNamespace(
            user=SimpleNamespace(id=uid), locale=None,
            response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock(), edit_message=AsyncMock()),
            edit_original_response=AsyncMock(),
        )

    assert await vista.interaction_check(inter(9)) is False
    i = inter(5)
    await vista._usa(i)
    await vista._usa(inter(5))  # secondo clic: niente
    assert chiamate == [1] and "4 brani" in i.edit_original_response.await_args.kwargs["content"]


async def test_video_oltre_8_ore_rifiutato_senza_entrare_in_canale(monkeypatch):
    from tests.test_music_f2 import _CanaleDelWorker, _FlottaDi, _GuildDelWorker, _Gestore, _Interazione
    from core.music_nodes import MAIN_KEY

    async def senza(guild_id, key, default=None):
        return default

    monkeypatch.setattr(player_module, "db", SimpleNamespace(
        is_module_active_for_guild=AsyncMock(return_value=True), get_guild_setting=senza,
    ))
    canale = _CanaleDelWorker(11)
    worker = SimpleNamespace(worker_index=2, get_guild=lambda gid: _GuildDelWorker(canale))
    gestore = _Gestore()
    nodo = object()
    gestore.nodi = {MAIN_KEY: nodo, "w2": nodo}
    cog = MusicCog(bot=SimpleNamespace(music_fleet=_FlottaDi(worker), music_nodes=gestore))
    lungo = SimpleNamespace(title="Dieci ore", length=10 * ORA, is_stream=False, raw_data={}, extras=None)
    from unittest.mock import patch as _patch

    with _patch.object(cog, "_cerca", new=AsyncMock(return_value=([lungo], nodo))):
        i = _Interazione()
        await cog.play.callback(cog, i, query="x")
    assert canale.cls is None and "8 ore" in i.followup.inviati[0] and "10:00:00" in i.followup.inviati[0]
    ok = SimpleNamespace(title="Otto ore", length=8 * ORA, is_stream=False, raw_data={}, extras=None)
    with _patch.object(cog, "_cerca", new=AsyncMock(return_value=([ok], nodo))):
        i = _Interazione()
        await cog.play.callback(cog, i, query="x")
    assert canale.cls is not None  # esattamente 8 ore: ammesso

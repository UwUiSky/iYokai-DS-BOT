"""
tests/test_music_f2.py
==========================
Fase F2 della musica (issue #64, D10): un nodo wavelink per bot, versione
di Lavalink, scelta esplicita del nodo, radio, brani locali, limiti.
Nessuna connessione vera a Lavalink o a Discord: la prova sul serio è in
revisione/03-verifica/VERIFICA_LIVE.md.
"""

import ast
import asyncio
import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord
import pytest
import wavelink

import cogs.music.player as player_module
from cogs.music.player import MSG_ALTRO_CANALE, MusicCog, chiave_del_bot
from core.music_logic import (
    LavalinkNodeConfig,
    choose_node,
    is_safe_local_filename,
    is_supported_lavalink,
    local_path_for_node,
    msg_canale_pieno,
    needs_raw_fetch,
    node_identifier,
    order_nodes,
    paginate_lines,
    parse_semver,
    public_node_base,
    truncate_title,
    voice_join_problem,
)
from core.music_nodes import MAIN_KEY, MusicNodeManager, worker_key


async def _senza_impostazioni(guild_id, key, default=None):
    return default


ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Logica pura
# ---------------------------------------------------------------------------
def test_versione_di_lavalink_minima_4_2_0():
    assert is_supported_lavalink("4.2.0")
    assert is_supported_lavalink("4.10.1")
    assert is_supported_lavalink("v5.0.0")
    assert not is_supported_lavalink("4.1.1")  # M 8.11: sotto la 4.2.0 si scarta
    assert not is_supported_lavalink("3.7.12")
    assert not is_supported_lavalink(None)
    assert not is_supported_lavalink("boh")
    assert parse_semver("4.2.0-beta.1") == (4, 2, 0)


def test_identificatori_diversi_per_bot_e_per_server():
    a = node_identifier(public_node_base("https://eu.lavalink.test:443"), "main")
    b = node_identifier(public_node_base("https://eu.lavalink.test:443"), "w1")
    c = node_identifier(public_node_base("https://us.lavalink.test:443"), "w1")
    assert len({a, b, c}) == 3  # il Pool tiene un solo nodo per identificatore


class _Nodo:
    def __init__(self, identifier, connesso=True, giocatori=0):
        self.identifier = identifier
        self.status = SimpleNamespace(name="CONNECTED" if connesso else "DISCONNECTED")
        self.players = {i: None for i in range(giocatori)}


def test_scelta_nodo_pubblici_prima_locale_per_ultimo_solo_connessi():
    locale = _Nodo(node_identifier("iyokai-local-node", "w1"), giocatori=0)
    pesante = _Nodo("pub-a@w1", giocatori=5)
    leggero = _Nodo("pub-b@w1", giocatori=1)
    morto = _Nodo("pub-c@w1", connesso=False)
    ordine = order_nodes([locale, pesante, morto, leggero])
    assert ordine == [leggero, pesante, locale]
    assert choose_node([locale, pesante, morto, leggero]) is leggero
    assert choose_node([locale]) is locale  # il locale resta l'ultima risorsa
    assert choose_node([morto]) is None


def test_nomi_di_file_locali():
    assert is_safe_local_filename("inedito.mp3")
    for brutto in ["", "../x.mp3", "a/b.mp3", "a\\b.mp3", "..", ".", " x.mp3", "x\x00.mp3"]:
        assert not is_safe_local_filename(brutto), brutto
    assert local_path_for_node("/audio/local/", "a.mp3") == "/audio/local/a.mp3"


def test_solo_spotify_va_preso_senza_prefisso_di_ricerca():
    assert needs_raw_fetch("spotify:track:abc")
    assert not needs_raw_fetch("local:/etc/passwd")  # BUG-10 + sicurezza
    assert not needs_raw_fetch("una canzone")


def test_titolo_lungo_resta_nel_limite_dell_embed():
    assert len(truncate_title("x" * 300)) == 256
    assert truncate_title("breve") == "breve"
    embed = discord.Embed(title=truncate_title("🎵 " + "y" * 300))
    assert len(embed.title) <= 256


def test_pagine_della_playlist_radio_stanno_nei_4096():
    righe = [f"`{i}` **{'t' * 140}** (3:00)" for i in range(300)]
    pagine = paginate_lines(righe)
    assert len(pagine) > 1
    assert all(len(p) <= 4096 for p in pagine)
    assert sum(p.count("\n") + 1 for p in pagine) == 300  # nessuna riga persa
    assert paginate_lines([]) == [""]


def test_problemi_di_ingresso_in_vocale():
    assert "palco" in voice_join_problem(
        is_stage=True, user_limit=0, presenti=0, puo_superare_limite=False
    )
    assert voice_join_problem(
        is_stage=False, user_limit=2, presenti=2, puo_superare_limite=False
    ) == msg_canale_pieno(2, 2)
    assert voice_join_problem(
        is_stage=False, user_limit=2, presenti=2, puo_superare_limite=True
    ) is None
    assert voice_join_problem(
        is_stage=False, user_limit=0, presenti=50, puo_superare_limite=False
    ) is None


# ---------------------------------------------------------------------------
# Gestore dei nodi (M 8.1, 8.2, 8.11)
# ---------------------------------------------------------------------------
class _Client:
    def __init__(self, nome):
        self.nome = nome

    async def wait_until_ready(self):
        return None


def _gestore(connetti, versione="4.2.0", pubblici=2):
    configs = [LavalinkNodeConfig(f"http://pub{i}.test:80", "pw") for i in range(pubblici)]
    locale = LavalinkNodeConfig("http://127.0.0.1:2333", "pw")

    async def leggi(nodo):
        return versione(nodo) if callable(versione) else versione

    return MusicNodeManager(configs, locale, connetti=connetti, leggi_versione=leggi, retries=2)


@pytest.mark.asyncio
async def test_ogni_bot_ha_il_suo_nodo_con_il_suo_client():
    visti = []

    async def connetti(nodo, client):
        visti.append((nodo.identifier, client.nome))
        nodo._status = wavelink.NodeStatus.CONNECTED

    g = _gestore(connetti)
    principale, w3 = _Client("main"), _Client("w3")
    await asyncio.gather(*g.avvia(principale, MAIN_KEY), *g.avvia(w3, worker_key(3)))

    nodi_w3 = g.nodi_di("w3")
    assert nodi_w3 and all(n.client is w3 for n in nodi_w3)
    assert all(n.client is principale for n in g.nodi_di("main"))
    assert not ({n.identifier for n in nodi_w3} & {n.identifier for n in g.nodi_di("main")})
    assert g.node_for("w3") in nodi_w3
    assert all(n.identifier.endswith("@w3") for n in nodi_w3)
    assert len(visti) == 2 * 3  # (2 pubblici + 1 locale) per bot


@pytest.mark.asyncio
async def test_primo_nodo_irraggiungibile_gli_altri_si_collegano():
    async def connetti(nodo, client):
        if "pub0" in nodo.uri:
            raise OSError("irraggiungibile")
        nodo._status = wavelink.NodeStatus.CONNECTED

    g = _gestore(connetti)
    await asyncio.gather(*g.avvia(_Client("main"), MAIN_KEY))

    collegati = {n.uri for n in g.nodi_di(MAIN_KEY) if n.status is wavelink.NodeStatus.CONNECTED}
    assert collegati == {"http://pub1.test:80", "http://127.0.0.1:2333"}
    assert g.node_for(MAIN_KEY) is not None


@pytest.mark.asyncio
async def test_un_nodo_che_esaurisce_i_tentativi_viene_scartato():
    async def connetti(nodo, client):
        return None  # wavelink termina senza errore ma il nodo resta DISCONNECTED

    g = _gestore(connetti)
    await asyncio.gather(*g.avvia(_Client("main"), MAIN_KEY))
    assert g.node_for(MAIN_KEY) is None


@pytest.mark.asyncio
async def test_nodo_lavalink_4_1_scartato_con_avviso(caplog):
    async def connetti(nodo, client):
        nodo._status = wavelink.NodeStatus.CONNECTED

    g = _gestore(connetti, versione=lambda n: "4.1.1" if "pub0" in n.uri else "4.2.0")
    with caplog.at_level("WARNING", logger="iyokai.music"):
        await asyncio.gather(*g.avvia(_Client("main"), MAIN_KEY))

    connessi = {n.uri for n in g.nodi_di(MAIN_KEY) if n.status is wavelink.NodeStatus.CONNECTED}
    assert "http://pub0.test:80" not in connessi
    assert "http://pub1.test:80" in connessi
    assert any("4.2.0" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_close_ferma_i_task_e_chiude_il_pool():
    fermo = asyncio.Event()

    async def connetti(nodo, client):
        await fermo.wait()

    g = _gestore(connetti)
    g.avvia(_Client("main"), MAIN_KEY)
    assert g.tasks
    with patch("wavelink.Pool.close", new=AsyncMock()) as chiudi_pool:
        await g.close()
    chiudi_pool.assert_awaited_once()
    assert not g.tasks


@pytest.mark.asyncio
async def test_cog_unload_chiude_i_nodi():
    chiuso = []

    class _G:
        async def close(self):
            chiuso.append(True)

    cog = MusicCog(bot=SimpleNamespace(music_nodes=_G()))
    await cog.cog_unload()
    assert chiuso == [True]


def test_chiave_del_bot():
    assert chiave_del_bot(object()) == MAIN_KEY
    assert chiave_del_bot(SimpleNamespace(worker_index=4)) == "w4"


# ---------------------------------------------------------------------------
# /music play: il player nasce sul nodo del suo bot (M 8.1)
# ---------------------------------------------------------------------------
class _Risposta:
    def __init__(self):
        self.inviati = []

    async def defer(self, **kw):
        pass

    async def send_message(self, content=None, **kw):
        self.inviati.append(content)


class _Followup:
    def __init__(self):
        self.inviati = []

    async def send(self, content=None, **kw):
        self.inviati.append(content)


class _Utente(discord.Member):
    def __init__(self, canale_id):
        self._voce = SimpleNamespace(channel=SimpleNamespace(id=canale_id))

    @property
    def voice(self):
        return self._voce

    @property
    def id(self):
        return 1

    @property
    def guild_permissions(self):
        return discord.Permissions()


class _Interazione:
    def __init__(self, guild_id=900, canale_id=11):
        self.guild = SimpleNamespace(id=guild_id)
        self.user = _Utente(canale_id)
        self.response = _Risposta()
        self.followup = _Followup()


class _Gestore:
    def __init__(self):
        self.nodi = {}
        self.locali = {}

    def node_for(self, chiave):
        return self.nodi.get(chiave)

    def locale_di(self, chiave):
        return self.locali.get(chiave)


class _CanaleDelWorker:
    """Registra con quali argomenti il cog chiede il player."""

    def __init__(self, canale_id):
        self.id = canale_id
        self.cls = None

    async def connect(self, cls):
        self.cls = cls
        player = SimpleNamespace(
            autoplay=None,
            playing=True,
            queue=SimpleNamespace(put_wait=AsyncMock(), is_empty=True),
            node=cls.keywords["nodes"][0],
        )
        return player


class _GuildDelWorker:
    def __init__(self, canale):
        self.voice_client = None
        self._canale = canale

    def get_channel(self, channel_id):
        return self._canale


class _FlottaDi:
    def __init__(self, worker_bot):
        self.worker_bot = worker_bot
        self.rilasci = []

    async def get_or_assign_worker_for_channel(self, guild_id, channel_id):
        return self.worker_bot.worker_index, self.worker_bot

    async def get_worker_for_channel(self, guild_id, channel_id):
        return None

    async def guild_has_session(self, guild_id):
        return True

    async def release_session(self, guild_id, channel_id):
        self.rilasci.append((guild_id, channel_id))


@pytest.fixture
def modulo_attivo(monkeypatch):
    finto = SimpleNamespace(
            is_module_active_for_guild=AsyncMock(return_value=True), get_guild_setting=_senza_impostazioni
        )
    monkeypatch.setattr(player_module, "db", finto)


@pytest.mark.asyncio
async def test_il_player_di_un_worker_nasce_sul_nodo_di_quel_worker(modulo_attivo):
    canale = _CanaleDelWorker(11)
    worker = SimpleNamespace(worker_index=2, get_guild=lambda gid: _GuildDelWorker(canale))
    gestore = _Gestore()
    nodo_main, nodo_w2 = object(), object()
    gestore.nodi = {MAIN_KEY: nodo_main, "w2": nodo_w2}
    bot = SimpleNamespace(music_fleet=_FlottaDi(worker), music_nodes=gestore)
    cog = MusicCog(bot=bot)
    traccia = SimpleNamespace(title="T", length=1000)

    with patch.object(cog, "_cerca", new=AsyncMock(return_value=([traccia], nodo_w2))) as cerca:
        i = _Interazione()
        await cog.play.callback(cog, i, query="qualcosa")

    # la ricerca parte dal nodo del worker 2, non da quello del principale
    assert cerca.await_args.args[1] is nodo_w2
    assert canale.cls.keywords["nodes"] == [nodo_w2]
    assert canale.cls.func is wavelink.Player


@pytest.mark.asyncio
async def test_play_senza_nodi_collegati_lo_dice_e_libera_il_worker(modulo_attivo):
    canale = _CanaleDelWorker(11)
    worker = SimpleNamespace(worker_index=1, get_guild=lambda gid: _GuildDelWorker(canale))
    flotta = _FlottaDi(worker)
    cog = MusicCog(bot=SimpleNamespace(music_fleet=flotta, music_nodes=_Gestore()))
    i = _Interazione()

    await cog.play.callback(cog, i, query="qualcosa")

    assert "nodo Lavalink" in i.followup.inviati[0]
    assert flotta.rilasci == [(900, 11)]  # lo slot non resta occupato


@pytest.mark.asyncio
async def test_ricerca_senza_risultati_non_fa_entrare_il_bot_e_libera_lo_slot(modulo_attivo):
    canale = _CanaleDelWorker(11)
    worker = SimpleNamespace(worker_index=1, get_guild=lambda gid: _GuildDelWorker(canale))
    flotta = _FlottaDi(worker)
    gestore = _Gestore()
    gestore.nodi["w1"] = object()
    cog = MusicCog(bot=SimpleNamespace(music_fleet=flotta, music_nodes=gestore))

    with patch.object(cog, "_cerca", new=AsyncMock(return_value=([], gestore.nodi["w1"]))):
        i = _Interazione()
        await cog.play.callback(cog, i, query="niente")

    assert canale.cls is None
    assert flotta.rilasci == [(900, 11)]


# ---------------------------------------------------------------------------
# LIM-34: canale palco, pieno, tempo scaduto
# ---------------------------------------------------------------------------
class _Palco(discord.StageChannel):
    def __init__(self):
        pass

    @property
    def members(self):
        return []

    @property
    def id(self):
        return 5

    @property
    def guild(self):
        return SimpleNamespace(me=None)


class _Vocale:
    id = 6
    user_limit = 2
    members = [1, 2]
    guild = SimpleNamespace(me="io")

    def __init__(self, permessi=None, errore=None):
        self._permessi = permessi or discord.Permissions()
        self._errore = errore

    def permissions_for(self, me):
        return self._permessi

    async def connect(self, cls):
        if self._errore:
            raise self._errore
        return SimpleNamespace(autoplay=None)


@pytest.mark.asyncio
async def test_canale_palco_ha_un_messaggio_chiaro():
    player, errore = await MusicCog(bot=None)._entra_in_canale(_Palco(), object())
    assert player is None and "palco" in errore


@pytest.mark.asyncio
async def test_canale_pieno_ha_un_messaggio_chiaro():
    player, errore = await MusicCog(bot=None)._entra_in_canale(_Vocale(), object())
    assert player is None and errore == msg_canale_pieno(2, 2)


@pytest.mark.asyncio
async def test_canale_pieno_ma_il_bot_puo_muovere_membri_entra():
    canale = _Vocale(permessi=discord.Permissions(move_members=True))
    player, errore = await MusicCog(bot=None)._entra_in_canale(canale, object())
    assert errore is None and player is not None


@pytest.mark.asyncio
async def test_tempo_scaduto_ha_un_messaggio_chiaro():
    canale = _Vocale(permessi=discord.Permissions(administrator=True), errore=asyncio.TimeoutError())
    player, errore = await MusicCog(bot=None)._entra_in_canale(canale, object())
    assert player is None and "in tempo" in errore


# ---------------------------------------------------------------------------
# M 8.6 / 8.7: un bot per canale; utente in un altro canale rifiutato
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_utente_in_un_altro_canale_viene_rifiutato(modulo_attivo):
    class _Flotta:
        async def get_worker_for_channel(self, guild_id, channel_id):
            return None  # nel SUO canale non c'è nessun player

        async def guild_has_session(self, guild_id):
            return True  # ma il server ne ha una altrove

    cog = MusicCog(bot=SimpleNamespace(music_fleet=_Flotta()))
    for comando in (cog.skip, cog.stop, cog.pause, cog.disconnect):
        i = _Interazione(canale_id=99)
        await comando.callback(cog, i)
        assert i.response.inviati == [MSG_ALTRO_CANALE]


# ---------------------------------------------------------------------------
# Radio: nodo, esenzione, brani locali, avvio automatico (M 8.4, 8.5, 8.8, 8.17)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_brano_locale_si_trova_solo_sul_nodo_locale_e_senza_ricerca_youtube():
    locale, pubblico = object(), object()
    gestore = _Gestore()
    gestore.nodi[MAIN_KEY] = pubblico
    gestore.locali[MAIN_KEY] = locale
    cog = MusicCog(bot=SimpleNamespace(music_nodes=gestore))
    traccia = object()

    with patch("wavelink.Pool.fetch_tracks", new=AsyncMock(return_value=[traccia])) as grezzo, patch(
        "wavelink.Playable.search", new=AsyncMock()
    ) as ricerca:
        trovata = await cog._resolve_radio_track("local:/audio/local/a.mp3")

    assert trovata is traccia
    grezzo.assert_awaited_once_with("/audio/local/a.mp3", node=locale)
    ricerca.assert_not_called()


@pytest.mark.asyncio
async def test_brano_locale_senza_nodo_locale_non_ripiega_su_un_nodo_pubblico():
    gestore = _Gestore()
    gestore.nodi[MAIN_KEY] = object()  # c'è un pubblico, il locale no
    cog = MusicCog(bot=SimpleNamespace(music_nodes=gestore))

    with patch("wavelink.Pool.fetch_tracks", new=AsyncMock()) as grezzo, patch(
        "wavelink.Playable.search", new=AsyncMock()
    ) as ricerca:
        assert await cog._resolve_radio_track("local:/audio/local/a.mp3") is None

    grezzo.assert_not_called()
    ricerca.assert_not_called()


@pytest.mark.asyncio
async def test_add_local_usa_il_percorso_visto_dal_nodo_e_rifiuta_i_nomi_strani(monkeypatch, tmp_path):
    class _Cfg:
        MAIN_RADIO_LOCAL_FOLDER = str(tmp_path)
        LAVALINK_LOCAL_ROOT = "/audio/local"
        OWNER_ID = 0

    class _Repo:
        def __init__(self):
            self.salvati = []

        async def add_track(self, **kw):
            self.salvati.append(kw)
            return 1

    repo = _Repo()
    monkeypatch.setattr(player_module, "config", _Cfg())
    monkeypatch.setattr(player_module, "main_radio_repo", repo)
    cog = MusicCog(bot=None)
    visti = []

    async def _risolvi(identifier, nodo=None):
        visti.append(identifier)
        return SimpleNamespace(title="T", length=1000)

    cog._resolve_radio_track = _risolvi

    class _I:
        user = SimpleNamespace(id=1)

        def __init__(self):
            self.response = _Risposta()
            self.followup = _Followup()

    i = _I()
    await cog.nonstop_main_add_local.callback(cog, i, filename="inedito.mp3", label=None)
    assert visti == ["local:/audio/local/inedito.mp3"]  # non il percorso del bot
    assert repo.salvati[0]["identifier"] == "local:/audio/local/inedito.mp3"

    i2 = _I()
    await cog.nonstop_main_add_local.callback(cog, i2, filename="sub/inedito.mp3", label=None)
    assert "non valido" in i2.response.inviati[0]
    assert len(repo.salvati) == 1


@pytest.mark.asyncio
async def test_add_track_rifiuta_un_percorso_local_scritto_a_mano(monkeypatch):
    cog = MusicCog(bot=None)

    class _I:
        user = SimpleNamespace(id=1)
        response = _Risposta()
        followup = _Followup()

    i = _I()
    await cog.nonstop_main_add_track.callback(cog, i, query="local:/etc/passwd", label=None)
    assert "add-local" in i.response.inviati[0]


def test_la_cartella_inediti_viene_creata_all_avvio(monkeypatch, tmp_path):
    cartella = tmp_path / "radio" / "inediti"
    monkeypatch.setattr(
        player_module, "config", SimpleNamespace(MAIN_RADIO_LOCAL_FOLDER=str(cartella))
    )
    assert not cartella.exists()
    player_module.crea_cartella_locale()
    assert cartella.is_dir()


@pytest.mark.asyncio
async def test_il_memory_guard_non_scollega_la_radio_in_un_canale_vuoto():
    from core.memory_guard import MemoryGuard

    class _VC:
        def __init__(self, radio):
            self.channel = SimpleNamespace(id=1, members=[])
            self.disconnessioni = 0
            if radio:
                self.is_radio = True

        async def disconnect(self, force=False):
            self.disconnessioni += 1

    radio, normale = _VC(radio=True), _VC(radio=False)
    bot = SimpleNamespace(voice_clients=[radio, normale])
    await MemoryGuard()._cleanup_idle_voice_clients(bot)

    assert radio.disconnessioni == 0
    assert normale.disconnessioni == 1


def test_next_track_index_ha_un_chiamante_in_produzione():
    """M 8.17: la funzione della radio non resta più senza chiamanti."""
    chiamanti = []
    for percorso in list((ROOT / "cogs").rglob("*.py")) + list((ROOT / "core").rglob("*.py")):
        if percorso.name == "main_radio_logic.py":
            continue
        for nodo in ast.walk(ast.parse(percorso.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Call) and getattr(nodo.func, "id", "") == "next_track_index":
                chiamanti.append(percorso.name)
    assert chiamanti


class _CanaleRadio:
    id = 77
    guild = None

    def __init__(self, player):
        self._player = player

    async def connect(self, cls):
        return self._player


class _PlayerRadio:
    def __init__(self):
        self.autoplay = None
        self.queue = SimpleNamespace(mode=None, put_wait=AsyncMock())
        self.play = AsyncMock()


@pytest.mark.asyncio
async def test_radio_avviata_resta_in_un_canale_vuoto_e_usa_il_nodo_giusto(monkeypatch):
    from datetime import datetime, timezone

    tracce = [
        SimpleNamespace(id=1, identifier="local:/audio/local/a.mp3", duration_ms=180_000, label="A"),
        SimpleNamespace(id=2, identifier="yt-b", duration_ms=180_000, label="B"),
    ]

    class _Repo:
        async def list_tracks(self):
            return tracce

        async def get_state(self):
            return SimpleNamespace(
                track_index=0, track_started_at=datetime.now(timezone.utc), is_active=True
            )

        async def set_state(self, **kw):
            pass

    monkeypatch.setattr(player_module, "main_radio_repo", _Repo())
    gestore = _Gestore()
    gestore.nodi[MAIN_KEY] = "pubblico"
    gestore.locali[MAIN_KEY] = "locale"
    cog = MusicCog(bot=SimpleNamespace(music_nodes=gestore))
    nodi_usati = []

    async def _risolvi(identifier, nodo=None):
        nodi_usati.append(nodo)
        return SimpleNamespace(title=identifier, length=1000)

    cog._resolve_radio_track = _risolvi
    scelto = []
    player = _PlayerRadio()

    async def _entra(canale, nodo):
        scelto.append(nodo)
        return player, None

    cog._entra_in_canale = _entra

    esito = await cog._avvia_radio(SimpleNamespace(id=5), object())

    assert "Radio avviata" in esito
    assert scelto == ["locale"]  # la playlist ha un brano locale: il player nasce sul nodo locale
    assert set(nodi_usati) == {"locale"}
    assert player.is_radio is True
    assert player.inactive_channel_tokens is None


@pytest.mark.asyncio
async def test_il_bot_principale_in_vocale_senza_player_avvia_la_radio(monkeypatch, modulo_attivo):
    guild = SimpleNamespace(id=5, voice_client=None)
    bot = SimpleNamespace(user=SimpleNamespace(id=42))
    cog = MusicCog(bot=bot)
    avviate = []

    async def _avvia(g, canale):
        avviate.append((g.id, canale.id))
        return "ok"

    cog._avvia_radio = _avvia
    dopo = SimpleNamespace(channel=SimpleNamespace(id=77))
    prima = SimpleNamespace(channel=None)

    # un altro utente: niente
    await cog.on_voice_state_update(SimpleNamespace(id=1, guild=guild), prima, dopo)
    # il bot entra senza player: parte la radio
    await cog.on_voice_state_update(SimpleNamespace(id=42, guild=guild), prima, dopo)
    await asyncio.gather(*cog.task_in_background)
    assert avviate == [(5, 77)]

    # il bot esce: lo stato condiviso non si tocca, niente avvio
    await cog.on_voice_state_update(
        SimpleNamespace(id=42, guild=guild), dopo, SimpleNamespace(channel=None)
    )
    # il bot è entrato con /owner radio start (player già presente): niente doppio avvio
    guild.voice_client = object()
    await cog.on_voice_state_update(SimpleNamespace(id=42, guild=guild), prima, dopo)
    assert not cog.task_in_background
    assert avviate == [(5, 77)]


# ---------------------------------------------------------------------------
# Embed e interfacce nuove: guardiano dei limiti
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_nowplaying_con_titolo_di_300_caratteri_ha_un_embed_valido(modulo_attivo):
    player = SimpleNamespace(
        current=SimpleNamespace(title="z" * 300, length=60_000),
        position=1000,
        queue=SimpleNamespace(mode=None, __len__=lambda s: 0),
    )

    class _Q:
        mode = None

        def __len__(self):
            return 0

    player.queue = _Q()
    guild_w = SimpleNamespace(voice_client=player)
    worker = SimpleNamespace(worker_index=1, get_guild=lambda gid: guild_w)

    class _F:
        async def get_worker_for_channel(self, g, c):
            return 1, worker

    cog = MusicCog(bot=SimpleNamespace(music_fleet=_F()))
    i = _Interazione()
    inviati = []

    async def _invia(content=None, embed=None, **kw):
        inviati.append(embed)

    i.response.send_message = _invia
    await cog.nowplaying.callback(cog, i)

    assert len(inviati[0].title) <= 256


@pytest.mark.asyncio
async def test_list_tracks_con_300_brani_e_a_pagine_con_due_bottoni(monkeypatch):
    tracce = [
        SimpleNamespace(id=i, label="titolo " * 20, duration_ms=180_000) for i in range(300)
    ]

    class _Repo:
        async def list_tracks(self):
            return tracce

    monkeypatch.setattr(player_module, "main_radio_repo", _Repo())
    cog = MusicCog(bot=None)
    inviati = []

    class _I:
        user = SimpleNamespace(id=1)

        class response:
            @staticmethod
            async def send_message(content=None, embed=None, view=None, ephemeral=False):
                inviati.append((embed, view))

    await cog.nonstop_main_list_tracks.callback(cog, _I())

    embed, view = inviati[0]
    assert len(embed.description) <= 4096
    assert view is not None
    assert len(view.children) == 2 and len(view.children) <= 25  # guardiano: componenti
    assert view.children[0].disabled and not view.children[1].disabled


# ---------------------------------------------------------------------------
# Worker, cablaggio
# ---------------------------------------------------------------------------
def test_il_worker_e_autoshardato_e_ha_solo_due_intent():
    from discord.ext import commands

    from core.music_worker_bot import MusicWorkerBot

    w = MusicWorkerBot(worker_index=1)
    assert isinstance(w, commands.AutoShardedBot)
    attivi = {nome for nome, valore in w.intents if valore}
    assert attivi == {"guilds", "voice_states"}
    assert w._connection.max_messages is None


def test_main_svuota_le_sessioni_vecchie_prima_di_creare_la_flotta():
    """M 8.18: il cablaggio di music_session_repo.clear_all() in main()."""
    albero = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    funzione = next(
        n for n in ast.walk(albero) if isinstance(n, ast.AsyncFunctionDef) and n.name == "main"
    )
    ordine = {}
    for nodo in ast.walk(funzione):
        if isinstance(nodo, ast.Call):
            nome = ast.unparse(nodo.func)
            ordine.setdefault(nome, nodo.lineno)
    assert "music_session_repo.clear_all" in ordine
    assert ordine["db.run_migrations"] < ordine["music_session_repo.clear_all"]
    assert ordine["music_session_repo.clear_all"] < ordine["MusicFleet"]
    assert ordine["music_session_repo.clear_all"] < ordine["bot.start"] if "bot.start" in ordine else True


def test_il_requirements_chiede_wavelink_3_5_1():
    riga = next(
        r for r in (ROOT / "requirements.txt").read_text().splitlines() if r.startswith("wavelink")
    )
    assert riga.replace(" ", "") == "wavelink>=3.5.1"


@pytest.mark.asyncio
async def test_avviso_se_la_cartella_inediti_e_impostata_ma_manca_il_nodo_locale(monkeypatch, caplog):
    gestore = _Gestore()  # nessun nodo locale collegato
    monkeypatch.setattr(player_module, "config", SimpleNamespace(MAIN_RADIO_LOCAL_FOLDER="/x"))
    with caplog.at_level("WARNING", logger="iyokai.music"):
        await player_module.avvisa_se_manca_il_nodo_locale(gestore, [])
    assert any("nodo Lavalink locale non è collegato" in r.getMessage() for r in caplog.records)

    caplog.clear()
    gestore.locali[MAIN_KEY] = object()  # collegato: nessun avviso
    with caplog.at_level("WARNING", logger="iyokai.music"):
        await player_module.avvisa_se_manca_il_nodo_locale(gestore, [])
    assert not caplog.records

    monkeypatch.setattr(player_module, "config", SimpleNamespace(MAIN_RADIO_LOCAL_FOLDER=""))
    gestore.locali.clear()
    with caplog.at_level("WARNING", logger="iyokai.music"):
        await player_module.avvisa_se_manca_il_nodo_locale(gestore, [])  # cartella non impostata
    assert not caplog.records

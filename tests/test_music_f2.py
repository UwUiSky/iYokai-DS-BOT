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
    classify_query,
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


def test_le_query_degli_utenti_non_sono_mai_grezze():
    """BUG-10 + sicurezza: percorsi e `//host/x` rifiutati, il testo ha sempre il prefisso."""
    for brutta in ["//audio/local/x.mp3", "/etc/passwd", "local:/etc/passwd", "file:///x",
                   "C:\\x.mp3", "~/x", "ftp://a/b", "http:///x", "spotify:boh", ""]:
        assert classify_query(brutta) == "rifiutata", brutta
    assert classify_query("https://youtu.be/x") == "url"
    assert classify_query("spotify:track:4b93D55xv3YCH5mT4p6HPn") == "spotify"
    assert classify_query("una canzone") == "testo"


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


def _gestore(connetti, versione="4.2.0", pubblici=2, **kw):
    configs = [LavalinkNodeConfig(f"http://pub{i}.test:80", "pw") for i in range(pubblici)]
    locale = LavalinkNodeConfig("http://127.0.0.1:2333", "pw")

    async def leggi(nodo):
        return versione(nodo) if callable(versione) else versione

    kw.setdefault("attesa_pronto", 0.3)
    kw.setdefault("pause_riprova", (0.05,))
    return MusicNodeManager(
        configs, locale, connetti=connetti, leggi_versione=leggi, retries=2, **kw
    )


async def _aspetta(condizione, secondi=3.0):
    fine = asyncio.get_running_loop().time() + secondi
    while not condizione():
        assert asyncio.get_running_loop().time() < fine, "condizione mai verificata"
        await asyncio.sleep(0.02)


def _connessi(g, chiave):
    return {n.uri for n in g.nodi_di(chiave) if n.status is wavelink.NodeStatus.CONNECTED}


async def _chiudi(g):
    with patch("wavelink.Pool.close", new=AsyncMock()):
        await g.close()


def _connetti_in_ritardo(ritardo=0.1):
    """Come wavelink: torna con il nodo CONNECTING, CONNECTED arriva piu' tardi (messaggio `ready`)."""

    async def connetti(nodo, client):
        nodo._status = wavelink.NodeStatus.CONNECTING

        async def _ready():
            await asyncio.sleep(ritardo)
            nodo._status = wavelink.NodeStatus.CONNECTED

        asyncio.get_running_loop().create_task(_ready())

    return connetti


@pytest.mark.asyncio
async def test_il_nodo_che_diventa_connected_dopo_il_ritorno_di_connect_non_viene_scartato():
    g = _gestore(_connetti_in_ritardo(0.15), attesa_pronto=2.0)
    g.avvia(_Client("main"), MAIN_KEY)

    await _aspetta(lambda: len(_connessi(g, MAIN_KEY)) == 3)
    assert g.node_for(MAIN_KEY) is not None
    await _chiudi(g)


@pytest.mark.asyncio
async def test_con_un_lavalink_finto_vero_il_nodo_si_collega_e_resta():
    """Websocket e /v4/info veri (tests/support/fake_lavalink.py): parte CONNECTING, poi `ready`."""
    from tests.support import fake_lavalink

    runner = await fake_lavalink.start(23417)
    try:
        class _C:
            user = SimpleNamespace(id=111)

            async def wait_until_ready(self):
                pass

            def dispatch(self, *a, **k):
                pass

        g = MusicNodeManager([], LavalinkNodeConfig("http://127.0.0.1:23417", "x"), retries=1,
                             attesa_pronto=5.0)
        g.avvia(_C(), MAIN_KEY)
        await _aspetta(lambda: g.node_for(MAIN_KEY) is not None, 6)
        assert g.node_for(MAIN_KEY).status is wavelink.NodeStatus.CONNECTED
        assert "iyokai-local-node@main" in wavelink.Pool.nodes
        await g.close()
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_ogni_bot_ha_il_suo_nodo_con_il_suo_client():
    g = _gestore(_connetti_in_ritardo(0.02))
    principale, w3 = _Client("main"), _Client("w3")
    g.avvia(principale, MAIN_KEY)
    g.avvia(w3, worker_key(3))
    await _aspetta(lambda: len(_connessi(g, "w3")) == 3 and len(_connessi(g, MAIN_KEY)) == 3)

    nodi_w3 = g.nodi_di("w3")
    assert all(n.client is w3 for n in nodi_w3)
    assert all(n.client is principale for n in g.nodi_di("main"))
    assert not ({n.identifier for n in nodi_w3} & {n.identifier for n in g.nodi_di("main")})
    assert g.node_for("w3") in nodi_w3
    assert all(n.identifier.endswith("@w3") for n in nodi_w3)
    await _chiudi(g)


@pytest.mark.asyncio
async def test_primo_nodo_irraggiungibile_gli_altri_si_collegano():
    ritardo = _connetti_in_ritardo(0.02)

    async def connetti(nodo, client):
        if "pub0" in nodo.uri:
            raise OSError("irraggiungibile")
        await ritardo(nodo, client)

    g = _gestore(connetti)
    g.avvia(_Client("main"), MAIN_KEY)

    await _aspetta(lambda: _connessi(g, MAIN_KEY) == {"http://pub1.test:80", "http://127.0.0.1:2333"})
    assert g.node_for(MAIN_KEY) is not None
    await _chiudi(g)


@pytest.mark.asyncio
async def test_un_nodo_che_non_diventa_mai_connected_viene_scartato_e_poi_riprovato():
    tentativi = []

    async def connetti(nodo, client):
        tentativi.append(nodo.identifier)  # non diventa mai CONNECTED

    g = _gestore(connetti, pubblici=0, attesa_pronto=0.05)
    g.avvia(_Client("main"), MAIN_KEY)

    await _aspetta(lambda: len(tentativi) >= 3)  # M 8.2: non si arrende dopo il primo giro
    assert g.node_for(MAIN_KEY) is None
    await _chiudi(g)


@pytest.mark.asyncio
async def test_il_nodo_si_ricollega_quando_lavalink_torna():
    stato = {"su": False}
    ritardo = _connetti_in_ritardo(0.02)

    async def connetti(nodo, client):
        if not stato["su"]:
            raise OSError("giu'")
        await ritardo(nodo, client)

    g = _gestore(connetti, pubblici=0)
    g.avvia(_Client("main"), MAIN_KEY)
    await asyncio.sleep(0.2)
    assert g.node_for(MAIN_KEY) is None

    stato["su"] = True
    await _aspetta(lambda: g.node_for(MAIN_KEY) is not None)
    await _chiudi(g)


@pytest.mark.asyncio
async def test_nodo_lavalink_4_1_scartato_con_avviso(caplog):
    g = _gestore(
        _connetti_in_ritardo(0.02),
        versione=lambda n: "4.1.1" if "pub0" in n.uri else "4.2.0",
    )
    with caplog.at_level("WARNING", logger="iyokai.music"):
        g.avvia(_Client("main"), MAIN_KEY)
        await _aspetta(lambda: "http://pub1.test:80" in _connessi(g, MAIN_KEY))
        await _aspetta(lambda: any("4.2.0" in r.getMessage() for r in caplog.records))

    assert "http://pub0.test:80" not in _connessi(g, MAIN_KEY)
    await _chiudi(g)


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

    async def connect(self, cls, **kw):
        self.cls = cls
        player = SimpleNamespace(
            autoplay=None,
            playing=True,
            queue=SimpleNamespace(put_wait=AsyncMock(), is_empty=True),
            node=cls.keywords["nodes"][0],
            set_volume=AsyncMock(),
        )
        self.player = player
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
    canale.player.set_volume.assert_awaited_once_with(100)  # MUS-047: volume all'ingresso
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

    async def connect(self, cls, **kw):
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

    async def connect(self, cls, **kw):
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


# ---------------------------------------------------------------------------
# Correzioni del cacciatore-bug (12/10)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_play_con_una_query_a_percorso_e_rifiutato_prima_di_assegnare_un_worker(modulo_attivo):
    flotta = _FlottaDi(SimpleNamespace(worker_index=1))
    cog = MusicCog(bot=SimpleNamespace(music_fleet=flotta, music_nodes=_Gestore()))
    for brutta in ["//audio/local/x.mp3", "local:/audio/local/x.mp3", "/etc/passwd"]:
        i = _Interazione()
        await cog.play.callback(cog, i, query=brutta)
        assert "non è valida" in i.followup.inviati[0]
    assert flotta.rilasci == []


@pytest.mark.asyncio
async def test_il_testo_libero_ha_sempre_il_prefisso_di_ricerca():
    nodo = object()
    with patch("wavelink.Pool.fetch_tracks", new=AsyncMock(return_value=[1])) as grezzo, patch(
        "wavelink.Playable.search", new=AsyncMock()
    ) as ricerca:
        await MusicCog._cerca_su("//audio/local/x.mp3", nodo)
        grezzo.assert_not_called()
        await MusicCog._cerca_su("due parole", nodo)

    grezzo.assert_awaited_once_with("ytmsearch:due parole", node=nodo)
    ricerca.assert_not_called()


@pytest.mark.asyncio
async def test_solo_la_radio_e_esente_dal_canale_vuoto_non_tutto_il_nodo_locale():
    g = MusicNodeManager([], LavalinkNodeConfig("http://127.0.0.1:2333", "x"))
    (locale,) = g.costruisci_nodi(_Client("main"), MAIN_KEY)
    assert locale._inactive_channel_tokens == 3  # il default di wavelink: i worker liberano lo slot


@pytest.mark.asyncio
async def test_due_play_insieme_nello_stesso_canale_un_solo_connect_e_nessun_rilascio(modulo_attivo):
    class _Canale2(_CanaleDelWorker):
        connessioni = 0

        async def connect(self, cls, **kw):
            _Canale2.connessioni += 1
            await asyncio.sleep(0.05)  # il 2o play arriva mentre il 1o si collega
            player = await super().connect(cls)
            guild.voice_client = player
            return player

    canale = _Canale2(11)
    guild = _GuildDelWorker(canale)
    worker = SimpleNamespace(worker_index=2, get_guild=lambda gid: guild)
    flotta = _FlottaDi(worker)
    gestore = _Gestore()
    gestore.nodi["w2"] = object()
    cog = MusicCog(bot=SimpleNamespace(music_fleet=flotta, music_nodes=gestore))
    tracce = [SimpleNamespace(title=f"T{n}", length=1000, extras=None) for n in range(2)]

    async def _cerca(query, nodo, locale=None):
        return [tracce[int(query)]], nodo

    with patch.object(cog, "_cerca", new=_cerca):
        a, b = _Interazione(), _Interazione()
        await asyncio.gather(
            cog.play.callback(cog, a, query="0"), cog.play.callback(cog, b, query="1")
        )

    assert _Canale2.connessioni == 1
    assert flotta.rilasci == []
    assert "Aggiunta" in a.followup.inviati[0] and "Aggiunta" in b.followup.inviati[0]


@pytest.mark.asyncio
async def test_ricerca_fallita_non_libera_lo_slot_se_il_bot_sta_gia_suonando(modulo_attivo):
    canale = _CanaleDelWorker(11)
    guild = _GuildDelWorker(canale)
    guild.voice_client = SimpleNamespace(node=object(), playing=True)
    worker = SimpleNamespace(worker_index=1, get_guild=lambda gid: guild)
    flotta = _FlottaDi(worker)
    cog = MusicCog(bot=SimpleNamespace(music_fleet=flotta, music_nodes=_Gestore()))

    with patch.object(cog, "_cerca", new=AsyncMock(return_value=([], object()))):
        await cog.play.callback(cog, _Interazione(), query="niente")

    assert flotta.rilasci == []


@pytest.mark.asyncio
async def test_il_worker_scollegato_a_mano_libera_la_sessione_e_spostato_la_segue():
    from core.music_fleet import handle_worker_voice_update

    rilasci, mosse = [], []

    class _F:
        async def release_session(self, g, c):
            rilasci.append((g, c))

    import core.music_fleet as modulo

    class _Repo:
        async def move_session(self, g, a, b):
            mosse.append((g, a, b))

    bot = SimpleNamespace(user=SimpleNamespace(id=42))
    guild = SimpleNamespace(id=900)
    membro = SimpleNamespace(id=42, guild=guild)

    def stato(cid):
        return SimpleNamespace(channel=None if cid is None else SimpleNamespace(id=cid))

    with patch.object(modulo, "music_session_repo", _Repo()):
        await handle_worker_voice_update(_F(), bot, membro, stato(11), stato(None))
        await handle_worker_voice_update(_F(), bot, membro, stato(11), stato(22))
        await handle_worker_voice_update(_F(), bot, membro, stato(None), stato(11))  # entra: niente
        await handle_worker_voice_update(
            _F(), bot, SimpleNamespace(id=7, guild=guild), stato(11), stato(None)
        )  # un altro utente: niente

    assert rilasci == [(900, 11)]
    assert mosse == [(900, 11, 22)]


def test_i_file_gitignore_coprono_plugin_e_inediti_di_lavalink():
    testo = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "deploy/lavalink/plugins/" in testo
    assert "deploy/lavalink/radio-local/" in testo


# ---------------------------------------------------------------------------
# Revisore capo (13/10): URL sicuri, attesa limitata, buchi di copertura
# ---------------------------------------------------------------------------
class _ClienteVero:
    """Quanto basta a wavelink per collegare un nodo vero."""

    user = SimpleNamespace(id=111)

    async def wait_until_ready(self):
        pass

    def dispatch(self, *a, **k):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "indirizzo",
    [
        "http://127.0.0.1:2333/v4/info",
        "http://10.0.0.5/a.mp3",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost/a.mp3",
        "http://[::1]/a.mp3",
        "http://192.168.1.10/a.mp3",
    ],
)
async def test_un_url_interno_non_arriva_mai_a_lavalink(indirizzo):
    with patch("wavelink.Playable.search", new=AsyncMock()) as ricerca, patch(
        "wavelink.Pool.fetch_tracks", new=AsyncMock()
    ) as grezzo:
        assert await MusicCog._cerca_su(indirizzo, object()) is None
    ricerca.assert_not_called()
    grezzo.assert_not_called()


@pytest.mark.asyncio
async def test_un_url_pubblico_arriva_a_lavalink():
    nodo = object()
    with patch("wavelink.Playable.search", new=AsyncMock(return_value=["x"])) as ricerca:
        assert await MusicCog._cerca_su("https://93.184.216.34/a.mp3", nodo) == ["x"]
    ricerca.assert_awaited_once_with("https://93.184.216.34/a.mp3", node=nodo)


@pytest.mark.asyncio
async def test_il_nome_host_che_risolve_a_un_ip_interno_e_rifiutato():
    risolvi = AsyncMock(return_value=False)
    with patch.object(player_module, "url_e_sicuro", new=risolvi), patch(
        "wavelink.Playable.search", new=AsyncMock()
    ) as ricerca:
        assert await MusicCog._cerca_su("https://nome.finto.test/a.mp3", object()) is None
    risolvi.assert_awaited_once()
    ricerca.assert_not_called()


@pytest.mark.asyncio
async def test_l_avviso_del_nodo_locale_ha_un_attesa_limitata_con_un_nodo_morto_vero(
    monkeypatch, caplog
):
    """Porta chiusa: i task di collegamento non finiscono mai, l'avviso arriva comunque."""
    monkeypatch.setattr(player_module, "config", SimpleNamespace(MAIN_RADIO_LOCAL_FOLDER="/x"))
    g = MusicNodeManager(
        [],
        LavalinkNodeConfig("http://127.0.0.1:1", "x"),
        retries=1,
        attesa_pronto=0.3,
        pause_riprova=(30.0,),
    )
    task = g.avvia(_ClienteVero(), MAIN_KEY)
    try:
        with caplog.at_level("WARNING", logger="iyokai.music"):
            await asyncio.wait_for(
                player_module.avvisa_se_manca_il_nodo_locale(g, task, attesa=1.0), timeout=10
            )
        assert any("nodo Lavalink locale non è collegato" in r.getMessage() for r in caplog.records)
        assert all(not t.done() for t in task)  # il ricollegamento prosegue in background
    finally:
        await g.close()


@pytest.mark.parametrize(
    "brutta",
    ["ciao\x00mondo", "ciao\x1b[0m", "a\tb", "a\nb", "file:x", "FILE:/etc/passwd", "file:///x"],
)
def test_classify_query_rifiuta_caratteri_di_controllo_e_file(brutta):
    assert classify_query(brutta) == "rifiutata"


def test_paginate_lines_rispetta_ogni_limite_da_solo():
    # solo il tetto di righe
    pagine = paginate_lines(["a"] * 30, max_chars=3500, max_lines=25)
    assert [p.count("\n") + 1 for p in pagine] == [25, 5]
    # solo il tetto di caratteri (poche righe lunghe)
    pagine = paginate_lines(["x" * 100] * 10, max_chars=350, max_lines=25)
    assert all(len(p) <= 350 for p in pagine) and len(pagine) > 1
    # una riga piu' lunga del tetto viene tagliata
    (unica,) = paginate_lines(["y" * 5000], max_chars=3500, max_lines=25)
    assert len(unica) <= 3500


def _con_impostazioni(monkeypatch, **chiavi):
    async def leggi(guild_id, key, default=None):
        return chiavi.get(key, default)

    monkeypatch.setattr(
        player_module,
        "db",
        SimpleNamespace(is_module_active_for_guild=AsyncMock(return_value=True), get_guild_setting=leggi),
    )


class _Lista(list):
    """Una playlist finta: lista di tracce con un nome."""

    name = "Lista"


def _playlist(durate_ms):
    return _Lista(
        SimpleNamespace(title=f"T{n}", length=ms, extras=None, is_stream=False)
        for n, ms in enumerate(durate_ms)
    )


def _cog_per_play(monkeypatch, **chiavi):
    _con_impostazioni(monkeypatch, **chiavi)
    monkeypatch.setattr(wavelink, "Playlist", _Lista)
    canale = _CanaleDelWorker(11)
    guild = _GuildDelWorker(canale)
    worker = SimpleNamespace(worker_index=1, get_guild=lambda gid: guild)
    flotta = _FlottaDi(worker)
    gestore = _Gestore()
    gestore.nodi["w1"] = object()
    return MusicCog(bot=SimpleNamespace(music_fleet=flotta, music_nodes=gestore)), flotta, canale


@pytest.mark.asyncio
async def test_playlist_con_brani_oltre_la_durata_massima_li_scarta_e_lo_dice(monkeypatch):
    cog, flotta, canale = _cog_per_play(monkeypatch, music_max_track_minutes=5)
    lista = _playlist([60_000, 3_600_000, 120_000])  # il 2o dura un'ora
    i = _Interazione()
    with patch.object(cog, "_cerca", new=AsyncMock(return_value=(lista, object()))):
        await cog.play.callback(cog, i, query="https://93.184.216.34/lista")

    messa = canale.player.queue.put_wait.await_args.args[0]
    assert [t.title for t in messa] == ["T0", "T2"]
    assert "1 oltre la durata massima" in i.followup.inviati[0]


@pytest.mark.asyncio
async def test_playlist_tutta_oltre_la_durata_massima_non_fa_entrare_il_bot(monkeypatch):
    cog, flotta, canale = _cog_per_play(monkeypatch, music_max_track_minutes=1)
    i = _Interazione()
    with patch.object(
        cog, "_cerca", new=AsyncMock(return_value=(_playlist([600_000, 900_000]), object()))
    ):
        await cog.play.callback(cog, i, query="https://93.184.216.34/lista")

    assert canale.cls is None  # niente connect
    assert "durata massima di 1 minuti" in i.followup.inviati[0]
    assert flotta.rilasci == [(900, 11)]


@pytest.mark.asyncio
async def test_playlist_in_cima_mette_le_tracce_in_testa_nello_stesso_ordine(monkeypatch):
    cog, flotta, canale = _cog_per_play(monkeypatch)
    lista = _playlist([1000, 1000, 1000])
    player = SimpleNamespace(
        queue=SimpleNamespace(
            put_at=lambda pos, t: coda.insert(pos, t), put_wait=AsyncMock(), is_empty=False
        ),
        playing=True,
        node=object(),
    )
    coda = [SimpleNamespace(title="gia")]
    canale._player = player
    cog.bot.music_fleet.worker_bot.get_guild = lambda gid: SimpleNamespace(
        voice_client=player, get_channel=lambda c: canale
    )
    i = _Interazione()
    with patch.object(cog, "_cerca", new=AsyncMock(return_value=(lista, player.node))):
        await cog.play.callback(cog, i, query="https://93.184.216.34/lista", in_cima=True)

    assert [t.title for t in coda] == ["T0", "T1", "T2", "gia"]
    player.queue.put_wait.assert_not_called()


@pytest.mark.asyncio
async def test_join_fuori_dal_canale_permesso_e_rifiutato_senza_assegnare_un_worker(monkeypatch):
    _con_impostazioni(monkeypatch, music_allowed_voice_channel_id=555)
    flotta = _FlottaDi(SimpleNamespace(worker_index=1))
    assegnazioni = []
    flotta.get_or_assign_worker_for_channel = AsyncMock(side_effect=assegnazioni.append)
    cog = MusicCog(bot=SimpleNamespace(music_fleet=flotta, music_nodes=_Gestore()))
    i = _Interazione(canale_id=11)  # non e' il 555

    await cog.join.callback(cog, i)

    assert i.followup.inviati or i.response.inviati
    assert "555" in (i.followup.inviati + i.response.inviati)[0]
    flotta.get_or_assign_worker_for_channel.assert_not_called()


@pytest.mark.asyncio
async def test_join_nel_canale_permesso_procede(monkeypatch):
    _con_impostazioni(monkeypatch, music_allowed_voice_channel_id=11)
    canale = _CanaleDelWorker(11)
    guild = _GuildDelWorker(canale)
    worker = SimpleNamespace(worker_index=1, get_guild=lambda gid: guild)
    flotta = _FlottaDi(worker)
    gestore = _Gestore()
    gestore.nodi["w1"] = object()
    cog = MusicCog(bot=SimpleNamespace(music_fleet=flotta, music_nodes=gestore))
    i = _Interazione(canale_id=11)

    await cog.join.callback(cog, i)

    assert canale.cls is not None
    assert "Sono entrato" in i.followup.inviati[-1]


@pytest.mark.asyncio
async def test_la_radio_non_parte_due_volte_mentre_e_gia_in_avvio(monkeypatch, modulo_attivo):
    guild = SimpleNamespace(id=5, voice_client=None)
    cog = MusicCog(bot=SimpleNamespace(user=SimpleNamespace(id=42)))
    cog._avvia_radio = AsyncMock(return_value="ok")
    cog._radio_in_avvio.add(5)  # /owner radio start sta gia' avviando
    dopo = SimpleNamespace(channel=SimpleNamespace(id=77))

    await cog.on_voice_state_update(
        SimpleNamespace(id=42, guild=guild), SimpleNamespace(channel=None), dopo
    )

    assert not cog.task_in_background
    cog._avvia_radio.assert_not_called()


@pytest.mark.asyncio
async def test_la_radio_non_parte_da_sola_a_modulo_spento(monkeypatch):
    monkeypatch.setattr(
        player_module,
        "db",
        SimpleNamespace(is_module_active_for_guild=AsyncMock(return_value=False)),
    )
    guild = SimpleNamespace(id=5, voice_client=None)
    cog = MusicCog(bot=SimpleNamespace(user=SimpleNamespace(id=42)))
    cog._avvia_radio = AsyncMock(return_value="ok")

    await cog.on_voice_state_update(
        SimpleNamespace(id=42, guild=guild),
        SimpleNamespace(channel=None),
        SimpleNamespace(channel=SimpleNamespace(id=77)),
    )

    assert not cog.task_in_background
    cog._avvia_radio.assert_not_called()

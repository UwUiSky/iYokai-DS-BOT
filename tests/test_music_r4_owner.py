"""
tests/test_music_r4_owner.py
============================
Catalogo MUS (issue #126) giro r4mus, blocco 5: comandi dell'owner in `/owner radio`.
MUS-070 nodi senza password, MUS-067 player attivi, MUS-068 riconnetti, MUS-069 log ripulito,
MUS-011 fonti accese o spente, MUS-063 parole vietate in tutto il bot.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import wavelink

import cogs.music.owner as modulo
from cogs.music.owner import MusicOwnerCog, conta_player
from core import music_sources as ms
from core.music_nodes import MusicNodeManager
from core.music_owner_logic import (
    LOG_MAX_BYTE,
    coda_del_file,
    host_del_nodo,
    parola_globale_valida,
    riga_nodo,
    ripulisci_log,
)
from core.music_settings_logic import MusicSettings, imposta_parole_globali, parole_globali, title_blocked
from core.repositories.music_owner_repo import MusicOwnerRepository
from tests.test_music_playlist import _Risposte


# --------------------------- logica pura ---------------------------
def test_mus070_host_senza_password_ne_credenziali():
    assert host_del_nodo("http://127.0.0.1:2333") == "127.0.0.1:2333"
    assert host_del_nodo("https://utente:segreta@lava.example.com") == "lava.example.com"
    assert "segreta" not in riga_nodo("main", "pub@main", "https://utente:segreta@lava.example.com:443", "connected", 2)
    assert host_del_nodo("") == "?"


def test_mus069_log_ripulito_dalle_chiavi():
    segreto = "chiaveSuperSegreta123"
    log = (
        f"2026 INFO connessione con {segreto}\nAuthorization: Bearer abcdef\npassword=hunter22\n"
        "url https://utente:pwd@host/x\n\"accessToken\": \"zzzz\"\nnormale riga\n"
    )
    pulito = ripulisci_log(log, [segreto, "ab"])  # un segreto troppo corto non si sostituisce
    assert segreto not in pulito and "hunter22" not in pulito and "pwd@" not in pulito
    assert "abcdef" not in pulito and "zzzz" not in pulito
    assert "normale riga" in pulito


def test_mus069_si_manda_solo_la_coda_del_file():
    contenuto = b"vecchia riga\n" * 100000 + b"ultima riga\n"
    testo = coda_del_file(contenuto, 1000)
    assert len(testo) <= 1000 and testo.endswith("ultima riga\n") and testo.startswith("vecchia riga")
    assert coda_del_file(b"corto") == "corto"
    assert LOG_MAX_BYTE < 10 * 1024 * 1024


def test_mus063_parola_valida():
    assert parola_globale_valida("  due   parole ") == "due parole"
    for male in ("a", "", "x" * 61, "<@1>", "a/b"):
        assert parola_globale_valida(male) is None


def test_mus063_elenco_globale_blocca_i_titoli_di_ogni_server():
    imposta_parole_globali(["Parolaccia"])
    try:
        assert title_blocked("Una PAROLÀCCIA qui", MusicSettings()) is True
        assert title_blocked("Titolo pulito", MusicSettings()) is False
        assert "parolaccia" in parole_globali()
    finally:
        imposta_parole_globali([])
    assert title_blocked("parolaccia", MusicSettings()) is False


def test_mus011_override_accende_e_spegne_senza_toccare_l_ambiente(monkeypatch):
    monkeypatch.delenv("MUSIC_SOURCES_ENABLED", raising=False)
    try:
        assert "youtube" in ms.fonti_accese_dall_owner() and "tidal" not in ms.fonti_accese_dall_owner()
        ms.imposta_override({"youtube": False, "tidal": True, "inventata": True})
        accese = ms.fonti_accese_dall_owner()
        assert "youtube" not in accese and "tidal" in accese and "inventata" not in accese
        assert ms.stato_fonte("youtube") == ms.STATO_SPENTA
    finally:
        ms.imposta_override({})
    assert "youtube" in ms.fonti_accese_dall_owner()


def test_mus067_conta_player():
    def server(vc):
        return SimpleNamespace(voice_client=vc)

    c1 = SimpleNamespace(guilds=[server(SimpleNamespace(playing=True)), server(None)])
    c2 = SimpleNamespace(guilds=[server(SimpleNamespace(playing=False)), server(SimpleNamespace(playing=True))])
    assert conta_player([c1, c2]) == (2, 3)
    assert conta_player([]) == (0, 0)


# --------------------------- gestore dei nodi ---------------------------
class _NodoFinto:
    def __init__(self, identificatore, stato):
        self.identifier, self.status, self.uri = identificatore, stato, "http://h:2333"
        self.players = {1: object()}


@pytest.mark.asyncio
async def test_mus068_riconnetti_riparte_solo_i_nodi_non_collegati():
    gestore = MusicNodeManager([], None)
    vivo = _NodoFinto("a@main", wavelink.NodeStatus.CONNECTED)
    morto = _NodoFinto("b@main", wavelink.NodeStatus.DISCONNECTED)
    gestore._nodi["main"] = [vivo, morto]
    client = object()
    gestore._client_di_nodo = {"a@main": client, "b@main": client}
    lanciati = []

    async def _collega(c, n):
        lanciati.append(n.identifier)

    gestore._collega_uno = _collega
    assert await gestore.riconnetti() == 1
    await asyncio.sleep(0)
    assert lanciati == ["b@main"]
    righe = gestore.descrivi_nodi()
    assert ("main", "b@main", "http://h:2333", "disconnected", 1) in righe


# --------------------------- repository ---------------------------
@pytest.fixture
def repo(clean_db):
    return MusicOwnerRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_repo_fonti_e_parole(repo):
    await repo.imposta_fonte("youtube", False, 1)
    await repo.imposta_fonte("youtube", False, 1)
    await repo.imposta_fonte("tidal", True, 1)
    assert await repo.override_fonti() == {"youtube": False, "tidal": True}
    assert await repo.togli_override("youtube") is True and await repo.togli_override("youtube") is False
    assert await repo.aggiungi_parola("brutta", 1) == "ok"
    assert await repo.aggiungi_parola("brutta", 1) == "gia"
    assert await repo.parole() == ["brutta"]
    assert await repo.togli_parola("brutta") is True and await repo.togli_parola("brutta") is False


@pytest.mark.asyncio
async def test_repo_parole_hanno_un_tetto(repo):
    from core.music_owner_logic import MAX_PAROLE_GLOBALI

    for n in range(MAX_PAROLE_GLOBALI):
        assert await repo.aggiungi_parola(f"parola{n}", 1) == "ok"
    assert await repo.aggiungi_parola("una di troppo", 1) == "pieno"


# --------------------------- comandi ---------------------------
def _interazione(user_id):
    risposte = _Risposte()
    inviati = []

    async def _segui(testo=None, **kw):
        inviati.append((testo, kw))

    return SimpleNamespace(
        user=SimpleNamespace(id=user_id), response=risposte, followup=SimpleNamespace(send=_segui),
        guild_id=1,
    ), risposte, inviati


def _cog(monkeypatch, repo=None, gestore=None):
    monkeypatch.setattr(modulo, "config", SimpleNamespace(OWNER_ID=42, LAVALINK_PASSWORD="", LAVALINK_LOG_FILE=""))
    if repo is not None:
        monkeypatch.setattr(modulo, "music_owner_repo", repo)
    bot = SimpleNamespace(music_nodes=gestore, music_fleet=SimpleNamespace(worker_bots=[]), guilds=[])
    return MusicOwnerCog(bot)


@pytest.mark.asyncio
async def test_ogni_comando_e_solo_dell_owner(monkeypatch, repo):
    cog = _cog(monkeypatch, repo, MagicMock())
    for chiamata in (
        lambda i: cog.nodi.callback(cog, i),
        lambda i: cog.stato.callback(cog, i),
        lambda i: cog.riconnetti.callback(cog, i),
        lambda i: cog.log.callback(cog, i),
        lambda i: cog.sorgente.callback(cog, i, "youtube", "spento"),
        lambda i: cog.blocca_parola.callback(cog, i, "aggiungi", "xx yy"),
    ):
        i, r, _ = _interazione(7)
        await chiamata(i)
        assert "solo per il proprietario" in r.testi[-1]
    assert await repo.override_fonti() == {} and await repo.parole() == []


@pytest.mark.asyncio
async def test_sorgente_spegne_e_riaccende(monkeypatch, repo):
    monkeypatch.delenv("MUSIC_SOURCES_ENABLED", raising=False)
    cog = _cog(monkeypatch, repo)
    try:
        i, r, _ = _interazione(42)
        await cog.sorgente.callback(cog, i, "youtube", "spento")
        assert "YouTube" in r.testi[-1] and "youtube" not in ms.fonti_accese_dall_owner()
        assert await repo.override_fonti() == {"youtube": False}
        await cog.sorgente.callback(cog, i, "youtube", "predefinito")
        assert "youtube" in ms.fonti_accese_dall_owner() and await repo.override_fonti() == {}
        await cog.sorgente.callback(cog, i, "inventata", "acceso")
        assert "sconosciuta" in r.testi[-1]
    finally:
        ms.imposta_override({})


@pytest.mark.asyncio
async def test_blocca_parola_aggiunge_toglie_e_filtra(monkeypatch, repo):
    cog = _cog(monkeypatch, repo)
    try:
        i, r, _ = _interazione(42)
        await cog.blocca_parola.callback(cog, i, "aggiungi", "  Brutta ")
        assert "brutta" in r.testi[-1] and title_blocked("che BRUTTA", MusicSettings())
        await cog.blocca_parola.callback(cog, i, "aggiungi", "brutta")
        assert "già" in r.testi[-1]
        await cog.blocca_parola.callback(cog, i, "aggiungi", "<@1>")
        assert "non valida" in r.testi[-1]
        await cog.blocca_parola.callback(cog, i, "togli", "BRUTTA")
        assert "tolta" in r.testi[-1] and not title_blocked("che brutta", MusicSettings())
    finally:
        imposta_parole_globali([])


@pytest.mark.asyncio
async def test_riconnetti_ha_una_pausa(monkeypatch):
    gestore = MagicMock()
    gestore.riconnetti = AsyncMock(return_value=2)
    cog = _cog(monkeypatch, None, gestore)
    i, r, _ = _interazione(42)
    await cog.riconnetti.callback(cog, i)
    assert "2" in r.testi[-1]
    await cog.riconnetti.callback(cog, i)
    assert "un minuto" in r.testi[-1] and gestore.riconnetti.await_count == 1


@pytest.mark.asyncio
async def test_log_manda_la_coda_ripulita(monkeypatch, tmp_path):
    cog = _cog(monkeypatch)
    file = tmp_path / "spring.log"
    file.write_text("riga uno\npassword=segretissima\nriga tre\n", encoding="utf-8")
    modulo.config.LAVALINK_LOG_FILE = str(file)
    i, _, inviati = _interazione(42)
    i.response = SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock())
    await cog.log.callback(cog, i)
    allegato = inviati[-1][1]["file"]
    contenuto = allegato.fp.read().decode()
    assert "riga tre" in contenuto and "segretissima" not in contenuto
    modulo.config.LAVALINK_LOG_FILE = str(tmp_path / "manca.log")
    await cog.log.callback(cog, i)
    assert "Non riesco" in inviati[-1][0]
    modulo.config.LAVALINK_LOG_FILE = ""
    i2, r2, _ = _interazione(42)
    await cog.log.callback(cog, i2)
    assert "LAVALINK_LOG_FILE" in r2.testi[-1]


@pytest.mark.asyncio
async def test_nodi_non_mostrano_la_password(monkeypatch):
    gestore = MagicMock()
    gestore.descrivi_nodi.return_value = [("main", "pub@main", "https://u:pw@lava.it:443", "connected", 1)]
    cog = _cog(monkeypatch, None, gestore)
    i, r, _ = _interazione(42)
    await cog.nodi.callback(cog, i)
    assert "lava.it:443" in r.testi[-1] and "pw" not in r.testi[-1].replace("lava", "")

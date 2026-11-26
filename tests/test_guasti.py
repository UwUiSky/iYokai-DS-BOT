"""
tests/test_guasti.py
====================
Prove di guasto a metà: PostgreSQL che cade e torna, Lavalink che cade e torna. Il database è davanti a un proxy TCP
che si stacca davvero (connessioni chiuse, porta che rifiuta), Lavalink è il finto con WebSocket vero di
`tests/support/fake_lavalink.py`. Si verifica che i giri non muoiano, che l'owner sia avvisato una volta sola quando
cadono e quando tornano, che /salute dica la verità e che la musica si ricolleghi da sola.
Funzioni coperte: consiglio 25/11/2026, blocco C voce 10
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
import wavelink

from core import giro_periodico as gp
from core import music_nodes, salute
from core.database import db
from core.music_logic import LavalinkNodeConfig
from core.music_nodes import MAIN_KEY, MusicNodeManager
from core.pool_db import PoolConCorsie
from tests.support import fake_lavalink
from tests.support.proxy_guasto import ProxyGuasto, porta_libera


async def _aspetta(condizione, secondi=10.0, passo=0.02):
    fine = asyncio.get_running_loop().time() + secondi
    while not condizione():
        assert asyncio.get_running_loop().time() < fine, "condizione mai verificata"
        await asyncio.sleep(passo)


@pytest.fixture
def giri_veloci(monkeypatch):
    monkeypatch.setattr(gp, "PAUSA_BASE_SECONDI", 0.05)
    monkeypatch.setattr(gp, "PAUSA_MASSIMA_SECONDI", 0.2)
    monkeypatch.setattr(gp, "GIRI", {})
    monkeypatch.setattr(gp, "ascoltatori_caduta", [])
    monkeypatch.setattr(gp, "ascoltatori_ripresa", [])


# ---------------------------------------------------------------- PostgreSQL


@pytest.fixture
async def database_dietro_proxy(clean_db, monkeypatch):
    """Un pool vero verso PostgreSQL, ma attraverso un proxy che il test può staccare."""
    url = urlsplit(os.environ["DATABASE_URL"])
    proxy = ProxyGuasto(url.hostname or "127.0.0.1", url.port or 5432)
    await proxy.avvia()
    dsn = f"postgresql://{url.username}:{url.password}@127.0.0.1:{proxy.porta}{url.path}"
    pool = await PoolConCorsie(
        dsn, min_size=1, max_size=4, max_queries=50000, max_inactive_connection_lifetime=300.0, loop=None,
        connection_class=__import__("asyncpg").Connection, record_class=__import__("asyncpg").Record,
        command_timeout=2, timeout=1,
    )
    monkeypatch.setattr(db, "_pool", pool)
    monkeypatch.setattr(gp, "_dsn_e_pool", lambda: (dsn, pool))
    yield proxy, pool, dsn
    await proxy.ripristina()
    await gp.leadership.rilascia()
    await pool.close()
    await proxy.chiudi()


async def test_postgresql_cade_a_meta_i_giri_non_muoiono_l_owner_e_avvisato_e_tutto_riparte(
    giri_veloci, database_dietro_proxy, monkeypatch
):
    proxy, pool, dsn = database_dietro_proxy
    monkeypatch.setattr(salute, "TIMEOUT_DATABASE_SECONDI", 1.0)
    caduti, tornati = [], []
    gp.ascoltatori_caduta.append(lambda nome, n, testo: caduti.append(nome))
    gp.ascoltatori_ripresa.append(lambda nome: tornati.append(nome))
    letture = []

    @gp.giro_periodico(seconds=0.05, subito=True)
    async def lavoro():
        letture.append(await db.pool.fetchval("SELECT count(*) FROM giri_periodici"))  # sbaglia se il database è giù

    lavoro.start()
    bot = SimpleNamespace(is_ready=lambda: True)
    try:
        await _aspetta(lambda: len(letture) >= 3)
        assert (await salute.rapporto(bot, pool))["stato"] in ("ok", "degradato")

        # --- PostgreSQL cade ---
        await proxy.interrompi()
        prima = len(letture)
        await _aspetta(lambda: lavoro.errori_consecutivi >= gp.ERRORI_PER_AVVISO and caduti, secondi=20)
        assert lavoro.is_running(), "il giro è morto alla prima eccezione di PostgreSQL"
        assert len(letture) == prima  # nessuna lettura riuscita a database giù
        assert caduti == [lavoro.nome]  # un solo avviso per la caduta, non uno a errore
        giu = await salute.rapporto(bot, pool)
        assert giu["stato"] == "giu" and giu["database"]["ok"] is False

        # --- PostgreSQL torna ---
        await proxy.ripristina()
        await _aspetta(lambda: len(letture) > prima, secondi=15)
        assert lavoro.is_running() and lavoro.errori_consecutivi == 0
        await _aspetta(lambda: tornati == [lavoro.nome])  # e l'owner sa che è tornato
        su = await salute.rapporto(bot, pool)
        assert su["stato"] == "ok" and su["database"]["ok"] is True
        assert gp.giri_in_difficolta() == []
    finally:
        lavoro.cancel()


async def test_senza_database_i_giri_non_perdono_la_leadership_e_ripartono(giri_veloci, database_dietro_proxy):
    """Con il database giù il lock di leadership non si può verificare: si resta leader (il lavoro non si ferma per un guasto)."""
    proxy, pool, dsn = database_dietro_proxy
    mio = gp.Leadership()
    assert await mio.sono_leader(dsn) is True  # preso il lock
    await proxy.interrompi()
    assert await mio.sono_leader(dsn) is True  # connessione persa, non verificabile: si resta leader
    await proxy.ripristina()
    assert await mio.sono_leader(dsn) is True  # ripreso il lock da solo
    await mio.rilascia()


async def test_il_pool_si_riprende_dopo_la_caduta_senza_riavviare_il_bot(giri_veloci, database_dietro_proxy):
    proxy, pool, dsn = database_dietro_proxy
    assert await pool.fetchval("SELECT 1") == 1
    await proxy.interrompi()
    with pytest.raises(Exception):
        await pool.fetchval("SELECT 1")
    await proxy.ripristina()
    for _ in range(40):  # asyncpg sostituisce da sé le connessioni rotte al prossimo uso
        try:
            assert await pool.fetchval("SELECT 1") == 1
            break
        except Exception:
            await asyncio.sleep(0.1)
    else:
        raise AssertionError("il pool non si è ripreso")


# ---------------------------------------------------------------- Lavalink


class _Client:
    """Un client Discord finto con un `user`; gli eventi di wavelink vanno al gestore, come fa discord.py."""

    user = SimpleNamespace(id=111)

    def __init__(self):
        self.gestore: MusicNodeManager | None = None
        self.chiusure: list[str] = []

    async def wait_until_ready(self):
        return None

    def dispatch(self, nome, *args):
        if nome == "wavelink_node_disconnected" and self.gestore is not None:
            self.chiusure.append(args[0].node.identifier)
            asyncio.get_running_loop().create_task(self.gestore.su_nodo_disconnesso(*args))


async def test_lavalink_cade_a_meta_e_la_musica_si_ricollega_da_sola(monkeypatch):
    monkeypatch.setattr(music_nodes, "RIPARTENZA_DOPO_CADUTA", 0.1)
    porta_vera = porta_libera()
    runner = await fake_lavalink.start(porta_vera)
    proxy = ProxyGuasto("127.0.0.1", porta_vera)  # il nodo parla con il proxy: staccandolo Lavalink «cade» davvero
    await proxy.avvia()
    client = _Client()
    gestore = MusicNodeManager(
        [], LavalinkNodeConfig(f"http://127.0.0.1:{proxy.porta}", "x"), retries=1, attesa_pronto=5.0, pause_riprova=(0.2,)
    )
    client.gestore = gestore
    gestore.avvia(client, MAIN_KEY)
    try:
        await _aspetta(lambda: gestore.node_for(MAIN_KEY) is not None, 10)
        nodo = gestore.node_for(MAIN_KEY)
        assert nodo.status is wavelink.NodeStatus.CONNECTED

        # --- Lavalink cade: connessioni chiuse, porta che rifiuta ---
        await proxy.interrompi()
        # wavelink prova a riconnettersi da solo, poi rinuncia: il nodo resta DISCONNECTED. È il caso che prima
        # lasciava la musica morta per sempre. Si aspetta la rinuncia vera prima di far tornare Lavalink.
        await _aspetta(lambda: nodo.status is wavelink.NodeStatus.DISCONNECTED and nodo._websocket is None, 30)
        assert gestore.node_for(MAIN_KEY) is None  # nessun nodo collegato: la musica non parte, il bot sì
        await asyncio.sleep(1.5)  # anche dopo un po' non si muove da solo: senza il gestore resterebbe morto
        assert nodo.status is wavelink.NodeStatus.DISCONNECTED

        # --- Lavalink torna (stessa porta) ---
        await proxy.ripristina()
        await _aspetta(lambda: gestore.node_for(MAIN_KEY) is not None, 60)
        assert gestore.node_for(MAIN_KEY).status is wavelink.NodeStatus.CONNECTED
    finally:
        await proxy.chiudi()
        await runner.cleanup()
        await gestore.close()


async def test_avvio_senza_lavalink_il_nodo_si_collega_quando_compare(monkeypatch):
    """Lavalink assente all'avvio: nessun errore, e quando parte il nodo si collega da solo."""
    porta = porta_libera()
    client = _Client()
    gestore = MusicNodeManager(
        [], LavalinkNodeConfig(f"http://127.0.0.1:{porta}", "x"), retries=1, attesa_pronto=2.0, pause_riprova=(0.2,)
    )
    client.gestore = gestore
    gestore.avvia(client, MAIN_KEY)
    runner = None
    try:
        await asyncio.sleep(1.0)
        assert gestore.node_for(MAIN_KEY) is None  # non c'è: il bot è partito lo stesso
        runner = await fake_lavalink.start(porta)
        await _aspetta(lambda: gestore.node_for(MAIN_KEY) is not None, 30)
    finally:
        if runner is not None:
            await runner.cleanup()
        await gestore.close()

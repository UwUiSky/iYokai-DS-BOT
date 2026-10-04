"""
tests/test_safe_http.py
===========================
Test di core/safe_http.py (SEC-8, SEC-18, BUG-20) — protezione SSRF
sui feed. I test che verificano il comportamento della richiesta vera
(limite di byte, redirect seguiti a mano) usano un server aiohttp
reale in locale (aiohttp.test_utils), che gira su 127.0.0.1 con una
porta casuale: per QUEI SOLI test si disattivano il controllo sull'IP
di destinazione e quello sulla porta (monkeypatch). I test sul rifiuto
degli indirizzi interni ammettono invece solo la porta del server
finto e contano le richieste che riceve: devono essere zero.
"""

import ipaddress
import socket

import aiohappyeyeballs
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

import core.safe_http as safe_http_module
from core.safe_http import _ip_e_bloccato, _schema_e_porta_ammessi, safe_get


def _consenti_qualsiasi_ip_e_porta(monkeypatch) -> None:
    """
    Disattiva SOLO i controlli sull'IP di destinazione e sulla porta
    — necessario perché il server finto di questi test gira su
    127.0.0.1 con una porta casuale, non 80/443 su un IP pubblico.
    Il resto del comportamento (redirect a mano, limite di byte,
    timeout) resta quello vero.
    """
    monkeypatch.setattr(safe_http_module, "_ip_e_bloccato", lambda ip: False)
    monkeypatch.setattr(safe_http_module, "_schema_e_porta_ammessi", lambda url: True)


class TestIpEBloccato:
    @pytest.mark.parametrize(
        "indirizzo",
        [
            "127.0.0.1",  # loopback
            "169.254.169.254",  # metadati cloud (link-local)
            "10.0.0.5",  # privato
            "172.16.0.1",  # privato
            "192.168.1.1",  # privato
            "0.0.0.0",  # non specificato
            "224.0.0.1",  # multicast
            "::1",  # loopback IPv6
            "fe80::1",  # link-local IPv6
            "fc00::1",  # privato IPv6 (ULA)
            # SEC-18: tutto ciò che non è "instradabile su Internet".
            "100.64.0.1",  # CGNAT (rete condivisa del provider)
            "192.88.99.1",  # relay 6to4 (deprecato)
            "fec0::1",  # site-local IPv6 (deprecato)
            "192.0.2.1",  # documentazione
            "198.18.0.1",  # benchmark
            "240.0.0.1",  # riservato
            "255.255.255.255",  # broadcast
            "ff02::1",  # multicast IPv6
            "::ffff:127.0.0.1",  # loopback IPv4 "travestito" da IPv6
            "::ffff:10.0.0.5",  # privato IPv4 "travestito" da IPv6
            "::ffff:100.64.0.1",  # CGNAT "travestito" da IPv6
        ],
    )
    def test_ip_pericolosi_sono_bloccati(self, indirizzo):
        assert _ip_e_bloccato(ipaddress.ip_address(indirizzo)) is True

    @pytest.mark.parametrize(
        "indirizzo",
        # IP pubblici reali, usati solo come esempio: nessuna richiesta
        # di rete viene fatta.
        ["8.8.8.8", "1.1.1.1", "2001:4860:4860::8888", "::ffff:8.8.8.8"],
    )
    def test_ip_pubblico_non_e_bloccato(self, indirizzo):
        assert _ip_e_bloccato(ipaddress.ip_address(indirizzo)) is False


class TestSchemaEPortaAmmessi:
    def test_http_porta_default_ammesso(self):
        assert _schema_e_porta_ammessi("http://esempio.com/feed.xml") is True

    def test_https_porta_default_ammesso(self):
        assert _schema_e_porta_ammessi("https://esempio.com/feed.xml") is True

    def test_porta_non_standard_rifiutata(self):
        assert _schema_e_porta_ammessi("http://esempio.com:8420/feed.xml") is False

    def test_schema_non_http_rifiutato(self):
        assert _schema_e_porta_ammessi("file:///etc/passwd") is False
        assert _schema_e_porta_ammessi("ftp://esempio.com/feed.xml") is False


@pytest.mark.asyncio
async def test_localhost_viene_rifiutato_senza_connettersi():
    risultato = await safe_get("http://127.0.0.1:8420/qualsiasi")
    assert risultato is None


@pytest.mark.asyncio
async def test_metadati_cloud_vengono_rifiutati():
    risultato = await safe_get("http://169.254.169.254/latest/meta-data/")
    assert risultato is None


@pytest.mark.asyncio
async def test_risposta_troppo_grande_viene_rifiutata(monkeypatch):
    _consenti_qualsiasi_ip_e_porta(monkeypatch)

    async def handler(request):
        return web.Response(body=b"x" * 100)

    app = web.Application()
    app.router.add_get("/grande", handler)
    server = TestServer(app)
    await server.start_server()
    try:
        url = f"http://127.0.0.1:{server.port}/grande"
        risultato = await safe_get(url, max_bytes=50)
        assert risultato is None
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_risposta_sotto_il_limite_viene_restituita(monkeypatch):
    _consenti_qualsiasi_ip_e_porta(monkeypatch)

    async def handler(request):
        return web.Response(text="contenuto del feed")

    app = web.Application()
    app.router.add_get("/piccola", handler)
    server = TestServer(app)
    await server.start_server()
    try:
        url = f"http://127.0.0.1:{server.port}/piccola"
        risultato = await safe_get(url, max_bytes=2_000_000)
        assert risultato == "contenuto del feed"
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_redirect_verso_ip_privato_viene_rifiutato(monkeypatch):
    # Il server di partenza è "consentito" (loopback finto per il
    # test), ma il redirect punta a un IP privato vero: la
    # ricontrolla ad ogni passo deve rifiutarlo comunque.
    monkeypatch.setattr(safe_http_module, "_schema_e_porta_ammessi", lambda url: True)

    def blocca_solo_ip_privati_veri(ip):
        return ip.is_private and str(ip) != "127.0.0.1"

    monkeypatch.setattr(safe_http_module, "_ip_e_bloccato", blocca_solo_ip_privati_veri)

    async def handler(request):
        raise web.HTTPFound(location="http://10.0.0.5/segreto")

    app = web.Application()
    app.router.add_get("/redirect", handler)
    server = TestServer(app)
    await server.start_server()
    try:
        url = f"http://127.0.0.1:{server.port}/redirect"
        risultato = await safe_get(url)
        assert risultato is None
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_redirect_verso_destinazione_sicura_viene_seguito(monkeypatch):
    _consenti_qualsiasi_ip_e_porta(monkeypatch)

    async def handler_redirect(request):
        raise web.HTTPFound(location="/destinazione")

    async def handler_destinazione(request):
        return web.Response(text="pagina finale")

    app = web.Application()
    app.router.add_get("/redirect", handler_redirect)
    app.router.add_get("/destinazione", handler_destinazione)
    server = TestServer(app)
    await server.start_server()
    try:
        url = f"http://127.0.0.1:{server.port}/redirect"
        risultato = await safe_get(url)
        assert risultato == "pagina finale"
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_troppi_redirect_vengono_rifiutati(monkeypatch):
    _consenti_qualsiasi_ip_e_porta(monkeypatch)

    async def handler_redirect_infinito(request):
        raise web.HTTPFound(location=str(request.rel_url))

    app = web.Application()
    app.router.add_get("/loop", handler_redirect_infinito)
    server = TestServer(app)
    await server.start_server()
    try:
        url = f"http://127.0.0.1:{server.port}/loop"
        risultato = await safe_get(url)
        assert risultato is None
    finally:
        await server.close()


# ---------------------------------------------------------------------
# BUG-20: un URL malformato vale "rifiutato" (None), mai un'eccezione.
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://x:99999/",  # porta fuori intervallo
        "http://[::1/",  # IPv6 senza parentesi chiusa
        "http://a..b/",  # etichetta vuota nel nome
        "http://" + "a" * 64 + ".com/",  # etichetta più lunga di 63 caratteri
    ],
)
@pytest.mark.asyncio
async def test_url_malformato_restituisce_none_senza_sollevare(url):
    assert await safe_get(url) is None


@pytest.mark.asyncio
async def test_redirect_verso_url_malformato_restituisce_none(monkeypatch):
    # Solo l'IP del server finto viene consentito: il controllo su
    # schema e porta resta quello vero, perché è lì che l'URL
    # malformato del redirect deve essere scartato.
    monkeypatch.setattr(safe_http_module, "_ip_e_bloccato", lambda ip: False)

    async def handler(request):
        # web.HTTPFound convaliderebbe da sé l'URL: l'header va scritto a mano.
        return web.Response(status=302, headers={"Location": "http://x:99999/"})

    app = web.Application()
    app.router.add_get("/redirect", handler)
    server = TestServer(app)
    await server.start_server()
    monkeypatch.setattr(safe_http_module, "ALLOWED_PORTS", {80, 443, server.port})
    try:
        risultato = await safe_get(f"http://127.0.0.1:{server.port}/redirect")
        assert risultato is None
    finally:
        await server.close()


# ---------------------------------------------------------------------
# SEC-18: DNS rebinding. Il nome va risolto UNA volta sola, e la
# connessione parte verso gli stessi IP che hanno passato il controllo.
# ---------------------------------------------------------------------

IP_PUBBLICO_DI_ESEMPIO = "93.184.216.34"


@pytest.fixture
async def server_interno():
    """Un servizio "interno" su 127.0.0.1 che conta le richieste ricevute."""
    richieste: list[str] = []

    async def handler(request):
        richieste.append(request.path)
        return web.Response(text="segreto interno")

    app = web.Application()
    app.router.add_get("/{resto:.*}", handler)
    server = TestServer(app)
    await server.start_server()
    server.richieste = richieste
    yield server
    await server.close()


def _dns_finto(monkeypatch, risposte: dict[str, list[list[str]]]) -> list[str]:
    """
    Sostituisce la risoluzione DNS di sistema per i nomi in
    `risposte`: a ogni ricerca dello stesso nome risponde con il
    gruppo di IP successivo (l'ultimo gruppo si ripete). Restituisce
    l'elenco dei nomi cercati, nell'ordine.
    """
    ricerche: list[str] = []
    getaddrinfo_vero = socket.getaddrinfo

    def finto(host, port, *args, **kwargs):
        if host not in risposte:
            return getaddrinfo_vero(host, port, *args, **kwargs)
        ricerche.append(host)
        gruppi = risposte[host]
        indirizzi = gruppi.pop(0) if len(gruppi) > 1 else gruppi[0]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 0)) for ip in indirizzi]

    monkeypatch.setattr(socket, "getaddrinfo", finto)
    return ricerche


def _solo_connessioni_locali(monkeypatch) -> list[str]:
    """
    Nessun test deve uscire su Internet: le connessioni verso
    127.0.0.1 partono davvero (così il server finto le riceverebbe),
    quelle verso qualunque altro IP vengono rifiutate subito.
    Restituisce l'elenco degli IP verso cui si è tentato di connettersi.
    """
    tentativi: list[str] = []
    connessione_vera = aiohappyeyeballs.start_connection

    async def solo_locali(addr_infos, **kwargs):
        tentativi.extend(info[4][0] for info in addr_infos)
        locali = [info for info in addr_infos if info[4][0] == "127.0.0.1"]
        if not locali:
            raise OSError("rete esterna disattivata nei test")
        return await connessione_vera(locali, **kwargs)

    monkeypatch.setattr(aiohappyeyeballs, "start_connection", solo_locali)
    return tentativi


@pytest.mark.asyncio
async def test_dns_rebinding_non_porta_a_una_connessione_verso_loopback(monkeypatch, server_interno):
    # Prima risposta: IP pubblico (passa il controllo). Seconda: loopback.
    ricerche = _dns_finto(
        monkeypatch, {"rebind.test": [[IP_PUBBLICO_DI_ESEMPIO], ["127.0.0.1"]]}
    )
    tentativi = _solo_connessioni_locali(monkeypatch)
    monkeypatch.setattr(safe_http_module, "ALLOWED_PORTS", {80, 443, server_interno.port})

    risultato = await safe_get(f"http://rebind.test:{server_interno.port}/segreto")

    assert server_interno.richieste == []
    assert risultato is None
    # Una sola risoluzione, e la connessione tentata solo verso l'IP
    # che ha passato il controllo.
    assert ricerche == ["rebind.test"]
    assert tentativi == [IP_PUBBLICO_DI_ESEMPIO]


@pytest.mark.asyncio
async def test_risposta_dns_mista_scarta_gli_ip_interni(monkeypatch, server_interno):
    _dns_finto(monkeypatch, {"misto.test": [["127.0.0.1", IP_PUBBLICO_DI_ESEMPIO]]})
    tentativi = _solo_connessioni_locali(monkeypatch)
    monkeypatch.setattr(safe_http_module, "ALLOWED_PORTS", {80, 443, server_interno.port})

    risultato = await safe_get(f"http://misto.test:{server_interno.port}/segreto")

    assert server_interno.richieste == []
    assert risultato is None
    assert tentativi == [IP_PUBBLICO_DI_ESEMPIO]


@pytest.mark.asyncio
async def test_nome_host_ammesso_viene_scaricato_passando_dal_resolver(monkeypatch, server_interno):
    # Il percorso normale (nome host -> resolver -> connessione) deve
    # continuare a funzionare: qui il nome risolve al server finto, e
    # solo per questo test il suo IP è trattato come ammesso.
    _dns_finto(monkeypatch, {"feed.test": [["127.0.0.1"]]})
    monkeypatch.setattr(safe_http_module, "_ip_e_bloccato", lambda ip: False)
    monkeypatch.setattr(safe_http_module, "ALLOWED_PORTS", {80, 443, server_interno.port})

    risultato = await safe_get(f"http://feed.test:{server_interno.port}/feed.rss")

    assert risultato == "segreto interno"
    assert server_interno.richieste == ["/feed.rss"]


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "localhost",
        "2130706433",  # 127.0.0.1 scritto come numero intero
        "127.1",  # forma abbreviata
        "0x7f.0.0.1",  # esadecimale
        "[::ffff:127.0.0.1]",  # IPv4 dentro un IPv6
        "127.0.0.1.",  # punto finale
    ],
)
@pytest.mark.asyncio
async def test_ogni_scrittura_di_loopback_viene_rifiutata_senza_connettersi(
    monkeypatch, server_interno, host
):
    # La porta del server finto è ammessa: a fermare la richiesta deve
    # essere il controllo sull'IP, non quello sulla porta.
    monkeypatch.setattr(safe_http_module, "ALLOWED_PORTS", {80, 443, server_interno.port})

    risultato = await safe_get(f"http://{host}:{server_interno.port}/segreto")

    assert risultato is None
    assert server_interno.richieste == []

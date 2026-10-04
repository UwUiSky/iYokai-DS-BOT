"""
tests/test_safe_http.py
===========================
Test di core/safe_http.py (SEC-8) — protezione SSRF sui feed. I test
sugli IP realmente pericolosi (127.0.0.1, 169.254.169.254) non usano
nessun server finto: vengono rifiutati PRIMA di qualunque tentativo
di connessione, dalla sola risoluzione DNS/controllo IP. I test che
verificano il comportamento della richiesta vera (limite di byte,
redirect seguiti a mano) usano un server aiohttp reale in locale
(aiohttp.test_utils) — che gira anch'esso su 127.0.0.1 con una porta
casuale, quindi per QUEI SOLI test si disattivano temporaneamente il
controllo sull'IP di destinazione e quello sulla porta ammessa
(monkeypatch), lasciando invariato tutto il resto (redirect seguiti
a mano, limite di byte).
"""

import ipaddress

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
        ],
    )
    def test_ip_pericolosi_sono_bloccati(self, indirizzo):
        assert _ip_e_bloccato(ipaddress.ip_address(indirizzo)) is True

    def test_ip_pubblico_non_e_bloccato(self):
        # 8.8.8.8 (Google Public DNS) — un IP pubblico reale, usato
        # solo come esempio, nessuna richiesta di rete viene fatta.
        assert _ip_e_bloccato(ipaddress.ip_address("8.8.8.8")) is False


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

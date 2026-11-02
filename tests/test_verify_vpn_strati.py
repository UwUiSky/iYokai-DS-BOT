"""
tests/test_verify_vpn_strati.py
===============================
D64: file dei dati, banca dati ASN, servizio esterno (finto: timeout, errore, tetto, cache) e l'insieme
degli strati in `core/verify_vpn.py`. Nessun file vero, nessuna rete.
"""

import asyncio
import logging

import pytest

from core import geoip_paesi, verify_vpn, verify_vpn_dati as dati_mod, verify_vpn_esterno as esterno
from core import verify_vpn_logic as logica

CHIAVE = "k" * 40


class _Lettore:
    def __init__(self, dati):
        self.dati = dati
        self.chiamate = 0

    def get(self, ip):
        self.chiamate += 1
        if ip == "boom":
            raise ValueError("storto")
        return self.dati.get(ip)

    def close(self):
        pass


def _dati(asn=(), tor=(), reti="", fusi=None):
    return dati_mod.Dati(
        asn_hosting=frozenset(asn), nodi_tor=frozenset(tor), reti=logica.ElencoReti.da_testo(reti), fusi=fusi or {},
    )


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    for nome in ("GEOIP_ASN_MMDB", "GEOIP_PAESI_MMDB", "VPN_DATI_CARTELLA", "VPN_PROXYCHECK_KEY", "VPN_SERVIZIO_TETTO"):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setattr(geoip_paesi, "_lettore", None)
    monkeypatch.setattr(geoip_paesi, "_provato", False)
    dati_mod.azzera()
    esterno.azzera()
    yield
    dati_mod.azzera()
    esterno.azzera()


# ------------------------------------------------------------- file dei dati
def test_senza_file_i_dati_sono_vuoti_senza_errori(monkeypatch, tmp_path):
    monkeypatch.setenv("VPN_DATI_CARTELLA", str(tmp_path / "non_esiste"))
    d = dati_mod.dati()
    assert d.asn_hosting == frozenset() and d.nodi_tor == frozenset() and len(d.reti) == 0 and d.fusi == {}
    assert dati_mod.asn_da_ip(logica.ip_controllabile("8.8.8.8")) is None  # banca dati ASN spenta


def test_i_file_si_leggono_e_si_ricaricano_quando_cambiano(monkeypatch, tmp_path):
    monkeypatch.setenv("VPN_DATI_CARTELLA", str(tmp_path))
    (tmp_path / "asn_hosting.txt").write_text("ASN,Entity\n1442,x\n")
    (tmp_path / "tor_uscita.txt").write_text("1.2.3.4\n")
    (tmp_path / "reti_vpn.txt").write_text("5.5.5.0/24\n")
    (tmp_path / "reti_datacenter.txt").write_text("6.6.0.0/16\n2001:db9::/32\n")
    (tmp_path / "fuso_paesi.txt").write_text("Europe/Rome\tIT\n")
    d = dati_mod.dati()
    assert d.asn_hosting == {1442} and d.nodi_tor == {"1.2.3.4"} and len(d.reti) == 3
    assert d.fusi == {"Europe/Rome": frozenset({"IT"})}
    (tmp_path / "tor_uscita.txt").write_text("1.2.3.4\n9.9.9.9\n")
    assert dati_mod.dati().nodi_tor == {"1.2.3.4"}  # il controllo è a intervalli, non a ogni richiesta
    dati_mod.ricarica()
    assert dati_mod.dati().nodi_tor == {"1.2.3.4", "9.9.9.9"}


def test_un_file_rotto_non_ferma_gli_altri(monkeypatch, tmp_path):
    monkeypatch.setenv("VPN_DATI_CARTELLA", str(tmp_path))
    (tmp_path / "tor_uscita.txt").write_bytes(b"\xff\xfe\x00 binario")
    (tmp_path / "asn_hosting.txt").write_text("1442\n")
    d = dati_mod.dati()
    assert d.asn_hosting == {1442} and d.nodi_tor == frozenset()


def test_asn_da_banca_dati_con_lettore_finto_e_cache_con_tetto():
    lettore = _Lettore({"8.8.8.8": {"autonomous_system_number": 15169}})
    dati_mod.usa_lettore_asn(lettore)
    ip = logica.ip_controllabile("8.8.8.8")
    assert dati_mod.asn_da_ip(ip) == 15169
    assert dati_mod.asn_da_ip(ip) == 15169
    assert lettore.chiamate == 1  # la seconda viene dalla cache
    assert dati_mod.asn_da_ip(logica.ip_controllabile("1.1.1.1")) is None  # non in banca dati
    assert dati_mod._cache_asn.max_size > 0 and len(dati_mod._cache_asn) <= dati_mod._cache_asn.max_size


def test_un_errore_del_lettore_asn_non_rompe(monkeypatch):
    class Rotto:
        def get(self, ip):
            raise RuntimeError("boom")

    dati_mod.usa_lettore_asn(Rotto())
    assert dati_mod.asn_da_ip(logica.ip_controllabile("8.8.8.8")) is None


def test_file_mmdb_assente_o_rotto_spegne_solo_lo_strato(monkeypatch, tmp_path):
    monkeypatch.setenv("GEOIP_ASN_MMDB", str(tmp_path / "no.mmdb"))
    assert dati_mod.asn_da_ip(logica.ip_controllabile("8.8.8.8")) is None
    (tmp_path / "rotto.mmdb").write_bytes(b"non e' una banca dati")
    dati_mod.azzera()
    monkeypatch.setenv("GEOIP_ASN_MMDB", str(tmp_path / "rotto.mmdb"))
    assert dati_mod.asn_da_ip(logica.ip_controllabile("8.8.8.8")) is None


# ---------------------------------------------------------- servizio esterno
def _servizio(risposte, *, tetto=3, ttl=3600, timeout=0.2, ora=None):
    chiamate = []

    async def richiedi(ip):
        chiamate.append(ip)
        r = risposte.pop(0) if risposte else {"status": "ok"}
        if isinstance(r, BaseException):
            raise r
        if callable(r):
            return await r()
        return r

    s = esterno.ServizioEsterno("CHIAVE-SEGRETA", tetto=tetto, richiedi=richiedi, ttl=ttl, timeout=timeout,
                                oggi=ora or (lambda: "2026-11-01"), adesso=lambda: 1000.0)
    return s, chiamate


def _risposta(ip, proxy):
    return {"status": "ok", "node": "x", ip: {"proxy": "yes" if proxy else "no", "type": "VPN" if proxy else ""}}


@pytest.mark.asyncio
async def test_il_servizio_dice_si_o_no_e_la_cache_evita_la_seconda_chiamata():
    s, chiamate = _servizio([_risposta("8.8.8.8", True), _risposta("1.1.1.1", False)])
    assert await s.controlla("8.8.8.8", "imp1") is True
    assert await s.controlla("8.8.8.8", "imp1") is True
    assert await s.controlla("1.1.1.1", "imp2") is False
    assert await s.controlla("1.1.1.1", "imp2") is False
    assert chiamate == ["8.8.8.8", "1.1.1.1"]
    assert s.usate_oggi == 2


@pytest.mark.asyncio
async def test_risposta_ipv6_con_chiave_in_forma_diversa():
    s, _ = _servizio([{"status": "ok", "2606:4700:4700:0:0:0:0:1111": {"proxy": "yes"}}])
    assert await s.controlla("2606:4700:4700::1111", "i") is True


@pytest.mark.asyncio
async def test_timeout_errore_o_risposta_storta_non_bloccano_nessuno(caplog):
    caplog.set_level(logging.DEBUG)

    async def lenta():
        await asyncio.sleep(5)

    s, chiamate = _servizio([lenta, RuntimeError("giu"), {"status": "denied", "message": "chiave"},
                             {"status": "ok"}, "non un dict", None], tetto=10)
    for n in range(6):
        assert await s.controlla(f"8.8.8.{n}", f"i{n}") is None  # sempre «non so»: la verifica prosegue
    assert len(chiamate) == 6
    assert "CHIAVE-SEGRETA" not in caplog.text  # la chiave non va mai nei log


@pytest.mark.asyncio
async def test_un_errore_non_resta_in_cache_a_lungo_ma_non_martella_il_servizio():
    s, chiamate = _servizio([RuntimeError("giu"), _risposta("8.8.8.8", True)], tetto=10)
    assert await s.controlla("8.8.8.8", "i") is None
    assert await s.controlla("8.8.8.8", "i") is None  # pausa breve dopo un errore
    assert len(chiamate) == 1
    s._adesso = lambda: 1000.0 + esterno.PAUSA_DOPO_ERRORE + 1
    assert await s.controlla("8.8.8.8", "i") is True
    assert len(chiamate) == 2


@pytest.mark.asyncio
async def test_tetto_giornaliero_poi_si_riparte_il_giorno_dopo():
    giorno = ["2026-11-01"]
    s, chiamate = _servizio([_risposta(f"8.8.8.{n}", False) for n in range(10)], tetto=2, ora=lambda: giorno[0])
    assert await s.controlla("8.8.8.1", "a") is False
    assert await s.controlla("8.8.8.2", "b") is False
    assert await s.controlla("8.8.8.3", "c") is None  # tetto raggiunto: si salta senza chiamare
    assert len(chiamate) == 2
    assert await s.controlla("8.8.8.1", "a") is False  # chi è in cache risponde anche a tetto finito
    giorno[0] = "2026-11-02"
    assert await s.controlla("8.8.8.3", "c") is False
    assert len(chiamate) == 3 and s.usate_oggi == 1


@pytest.mark.asyncio
async def test_la_cache_scade_e_ha_un_tetto():
    s, chiamate = _servizio([_risposta("8.8.8.8", True), _risposta("8.8.8.8", False)], ttl=60)
    assert await s.controlla("8.8.8.8", "i") is True
    s._adesso = lambda: 1000.0 + 61
    assert await s.controlla("8.8.8.8", "i") is False
    assert len(chiamate) == 2
    assert s._cache.max_size > 0


def test_senza_chiave_il_servizio_e_spento(monkeypatch):
    assert esterno.servizio() is None
    esterno.azzera()
    esterno.azzera()
    monkeypatch.setenv("VPN_PROXYCHECK_KEY", "  ")
    assert esterno.servizio() is None
    esterno.azzera()  # la chiave si legge una volta sola per processo
    monkeypatch.setenv("VPN_PROXYCHECK_KEY", "abc")
    monkeypatch.setenv("VPN_SERVIZIO_TETTO", "50")
    s = esterno.servizio()
    assert s is not None and s.tetto == 50 and esterno.servizio() is s
    monkeypatch.setenv("VPN_SERVIZIO_TETTO", "storto")
    esterno.azzera()
    assert esterno.servizio().tetto == esterno.TETTO_DI_BASE


# --------------------------------------------------------- insieme degli strati
FUSI = {"Europe/Rome": frozenset({"IT"}), "America/New_York": frozenset({"US"})}


@pytest.mark.asyncio
async def test_ogni_strato_da_solo_blocca_e_dice_il_metodo():
    dati_mod.usa_lettore_asn(_Lettore({"8.8.8.8": {"autonomous_system_number": 666}}))
    dati_mod.usa_dati(_dati(asn={666}, tor={"2.2.2.2", "2001:db8:1::1".replace("db8:1", "4700")}, reti="3.3.3.0/24\n2606:aaaa::/32"))
    chiedi = lambda ip, **k: verify_vpn.rileva(ip, chiave=CHIAVE, **k)  # noqa: E731
    assert (await chiedi("8.8.8.8")).metodi == ("asn",)
    assert (await chiedi("2.2.2.2")).metodi == ("tor",)
    assert (await chiedi("2001:4700::1")).metodi == ("tor",)
    assert (await chiedi("3.3.3.9")).metodi == ("elenco",)
    assert (await chiedi("2606:aaaa:1::7")).metodi == ("elenco",)
    r = await chiedi("5.5.5.5", segnali_intestazioni=(logica.METODO_INTESTAZIONI,))
    assert r.bloccato and r.metodi == ("intestazioni",)
    assert not (await chiedi("5.5.5.5")).bloccato  # nessuno strato: passa


@pytest.mark.asyncio
async def test_ip_privati_e_locali_non_si_bloccano_mai_nemmeno_se_nelle_liste():
    dati_mod.usa_dati(_dati(tor={"10.0.0.1", "127.0.0.1"}, reti="10.0.0.0/8\n127.0.0.0/8\n192.168.0.0/16\n::/0"))
    for ip in ("10.0.0.1", "127.0.0.1", "192.168.1.1", "::1", "203.0.113.5", "?", ""):
        r = await verify_vpn.rileva(ip, chiave=CHIAVE, segnali_intestazioni=(logica.METODO_INTESTAZIONI,))
        assert not r.bloccato and r.metodi == (), ip


@pytest.mark.asyncio
async def test_il_fuso_da_solo_non_blocca_con_un_altro_segnale_debole_si():
    geoip_paesi.usa_lettore(_Lettore({"5.5.5.5": {"country": {"iso_code": "RO"}}}))
    dati_mod.usa_dati(_dati(fusi=FUSI))
    r = await verify_vpn.rileva("5.5.5.5", chiave=CHIAVE, fuso="Europe/Rome")
    assert not r.bloccato and r.metodi == ("fuso",)
    r = await verify_vpn.rileva("5.5.5.5", chiave=CHIAVE, fuso="Europe/Rome", segnali_intestazioni=(logica.METODO_VIA,))
    assert r.bloccato and set(r.metodi) == {"fuso", "via"}
    geoip_paesi.usa_lettore(_Lettore({"5.5.5.5": {"country": {"iso_code": "IT"}}}))
    r = await verify_vpn.rileva("5.5.5.5", chiave=CHIAVE, fuso="Europe/Rome", segnali_intestazioni=(logica.METODO_VIA,))
    assert not r.bloccato  # fuso coerente: resta solo Via, debole


@pytest.mark.asyncio
async def test_servizio_esterno_solo_senza_un_segnale_forte_e_mai_per_ip_privati():
    dati_mod.usa_dati(_dati(tor={"2.2.2.2"}))
    s, chiamate = _servizio([_risposta("7.7.7.7", True)])
    esterno.usa_servizio(s)
    assert (await verify_vpn.rileva("2.2.2.2", chiave=CHIAVE)).metodi == ("tor",)
    assert chiamate == []  # già bloccato in locale: non si spende il tetto
    assert (await verify_vpn.rileva("10.1.1.1", chiave=CHIAVE)).metodi == ()
    assert chiamate == []  # un IP privato non esce mai dal server
    r = await verify_vpn.rileva("7.7.7.7", chiave=CHIAVE)
    assert r.bloccato and r.metodi == ("servizio",) and chiamate == ["7.7.7.7"]


@pytest.mark.asyncio
async def test_servizio_che_fallisce_non_blocca():
    dati_mod.usa_dati(_dati())
    s, _ = _servizio([RuntimeError("giu")])
    esterno.usa_servizio(s)
    assert not (await verify_vpn.rileva("7.7.7.7", chiave=CHIAVE)).bloccato


@pytest.mark.asyncio
async def test_la_cache_del_servizio_usa_l_impronta_non_l_ip():
    dati_mod.usa_dati(_dati())
    s, _ = _servizio([_risposta("7.7.7.7", True)])
    esterno.usa_servizio(s)
    await verify_vpn.rileva("7.7.7.7", chiave=CHIAVE)
    assert "7.7.7.7" not in str(s._cache.keys())
    assert verify_vpn.impronta_ip("7.7.7.7", CHIAVE) == verify_vpn.impronta_ip("7.7.7.7", CHIAVE)
    assert verify_vpn.impronta_ip("7.7.7.7", CHIAVE) != verify_vpn.impronta_ip("7.7.7.8", CHIAVE)

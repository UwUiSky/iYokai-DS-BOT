"""
tests/test_music_r5_radio_mondo.py
==================================
Catalogo MUS (issue #126) giro r5mus: MUS-010, radio dal mondo con l'elenco pubblico radio-browser.info.
Logica pura (lettura dell'elenco, indirizzi sicuri, pagine), rete finta, vista a pagine e comando.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core import music_radio_mondo as rm


def _riga(i=1, **extra):
    base = {
        "stationuuid": f"u{i}", "name": f"Radio {i}", "url": f"https://radio{i}.example.com/live",
        "url_resolved": f"https://radio{i}.example.com/live.mp3", "codec": "MP3", "bitrate": 128,
        "countrycode": "IT", "lastcheckok": 1, "hls": 0,
    }
    base.update(extra)
    return base


@pytest.fixture(autouse=True)
def _cache_pulita():
    rm.svuota_cache()
    yield
    rm.svuota_cache()


# ----------------------------- logica pura -----------------------------
def test_nome_ricerca_valido():
    assert rm.nome_ricerca_valido("  rock   fm ") == "rock fm"
    for male in ("", " ", "a", "x" * 61, "due\nrighe", "tab\tqui"):
        assert rm.nome_ricerca_valido(male) is None


def test_la_pagina_non_supera_25_e_la_ricerca_ha_un_tetto():
    assert 1 <= rm.PER_PAGINA <= 25
    assert rm.MAX_PAGINE * rm.PER_PAGINA <= 100


def test_indirizzo_della_ricerca_e_codificato_e_senza_chiavi():
    url = rm.indirizzo_ricerca("de1.api.radio-browser.info", "rock & roll/../x", 2)
    assert url.startswith("https://de1.api.radio-browser.info/json/stations/search?")
    assert " " not in url and "&roll" not in url  # il testo dell'utente e' codificato
    assert f"offset={2 * rm.PER_PAGINA}" in url
    assert f"limit={rm.PER_PAGINA + 1}" in url
    assert "hidebroken=true" in url


def test_stazione_valida_https_e_http_porta_80():
    s = rm.stazione_da_json(_riga(1))
    assert s.nome == "Radio 1" and s.url == "https://radio1.example.com/live.mp3"
    assert "IT" in s.dettaglio and "MP3" in s.dettaglio and "128" in s.dettaglio
    assert rm.stazione_da_json(_riga(2, url_resolved="http://r.example.com/live")) is not None


def test_stazione_scartata_se_non_adatta():
    male = [
        _riga(lastcheckok=0),                                  # non risponde
        _riga(hls=1),                                          # playlist HLS
        _riga(name="   "),                                     # senza nome
        _riga(url_resolved="ftp://x.example.com/a"),           # schema non ammesso
        _riga(url_resolved="file:///etc/passwd"),
        _riga(url_resolved="https://x.example.com:8443/a"),    # porta che safe_http rifiuta
        _riga(url_resolved="https://x.example.com/" + "a" * 400),  # troppo lungo
        _riga(url_resolved="https://x.example.com/a b"),       # spazio
        _riga(url_resolved="", url=""),
        _riga(url_resolved=None, url=None),
        {"name": 5},
        "non un dizionario",
    ]
    for riga in male:
        assert rm.stazione_da_json(riga) is None, riga


def test_si_usa_url_se_manca_url_resolved():
    s = rm.stazione_da_json(_riga(url_resolved="", url="https://u.example.com/s"))
    assert s.url == "https://u.example.com/s"


def test_nome_e_dettaglio_troncati_a_100():
    s = rm.stazione_da_json(_riga(name="N" * 300, countrycode="IT"))
    assert len(s.nome) <= 100 and len(s.dettaglio) <= 100


def test_testo_non_json_o_non_lista_da_nessuna_stazione():
    assert rm.stazioni_da_testo("non json") == []
    assert rm.stazioni_da_testo('{"a": 1}') == []
    assert rm.stazioni_da_testo("[]") == []


def test_stesso_indirizzo_una_volta_sola():
    testo = json.dumps([_riga(1), _riga(2, url_resolved=_riga(1)["url_resolved"])])
    assert len(rm.stazioni_da_testo(testo)) == 1


# ----------------------------- rete finta -----------------------------
async def _tutto_sicuro(url):
    return True


async def test_cerca_stazioni_ogni_richiesta_passa_da_safe_get_con_tetto_di_byte():
    chiamate = []

    async def scarica(url, *, max_bytes):
        chiamate.append((url, max_bytes))
        return json.dumps([_riga(i) for i in range(1, rm.PER_PAGINA + 2)])

    pagina = await rm.cerca_stazioni("rock", 0, scarica=scarica, controlla=_tutto_sicuro)
    assert len(chiamate) == 1
    assert chiamate[0][0].startswith("https://") and 0 < chiamate[0][1] <= 1_000_000
    assert len(pagina.stazioni) == rm.PER_PAGINA and pagina.ha_altre is True


async def test_ultima_pagina_senza_altre():
    async def scarica(url, *, max_bytes):
        return json.dumps([_riga(1), _riga(2)])

    pagina = await rm.cerca_stazioni("rock", 0, scarica=scarica, controlla=_tutto_sicuro)
    assert len(pagina.stazioni) == 2 and pagina.ha_altre is False


async def test_indirizzi_di_stream_non_sicuri_sono_tolti():
    controllati = []

    async def controlla(url):
        controllati.append(url)
        return "radio2" not in url

    async def scarica(url, *, max_bytes):
        return json.dumps([_riga(1), _riga(2), _riga(3)])

    pagina = await rm.cerca_stazioni("rock", 0, scarica=scarica, controlla=controlla)
    assert [s.nome for s in pagina.stazioni] == ["Radio 1", "Radio 3"]
    assert len(controllati) == 3  # ogni stream controllato


async def test_server_che_non_risponde_si_passa_al_successivo():
    visti = []

    async def scarica(url, *, max_bytes):
        visti.append(url)
        return None if len(visti) == 1 else json.dumps([_riga(1)])

    pagina = await rm.cerca_stazioni("rock", 0, scarica=scarica, controlla=_tutto_sicuro)
    assert len(visti) == 2 and visti[0].split("/")[2] != visti[1].split("/")[2]
    assert [s.nome for s in pagina.stazioni] == ["Radio 1"]


async def test_nessun_server_risponde_da_none():
    async def scarica(url, *, max_bytes):
        return None

    assert await rm.cerca_stazioni("rock", 0, scarica=scarica, controlla=_tutto_sicuro) is None


async def test_risposta_non_valida_da_none_non_pagina_vuota():
    async def scarica(url, *, max_bytes):
        return "<html>errore</html>"

    assert await rm.cerca_stazioni("rock", 0, scarica=scarica, controlla=_tutto_sicuro) is None


async def test_pagina_oltre_il_tetto_e_nome_non_valido_non_escono_in_rete():
    async def scarica(url, *, max_bytes):  # pragma: no cover
        raise AssertionError("niente rete")

    assert await rm.cerca_stazioni("rock", rm.MAX_PAGINE, scarica=scarica, controlla=_tutto_sicuro) is None
    assert await rm.cerca_stazioni("x", 0, scarica=scarica, controlla=_tutto_sicuro) is None
    assert await rm.cerca_stazioni("rock", -1, scarica=scarica, controlla=_tutto_sicuro) is None


async def test_la_stessa_ricerca_si_ricorda_per_poco():
    n = 0

    async def scarica(url, *, max_bytes):
        nonlocal n
        n += 1
        return json.dumps([_riga(1)])

    await rm.cerca_stazioni("Rock", 0, scarica=scarica, controlla=_tutto_sicuro)
    await rm.cerca_stazioni("rock", 0, scarica=scarica, controlla=_tutto_sicuro)
    assert n == 1
    await rm.cerca_stazioni("rock", 1, scarica=scarica, controlla=_tutto_sicuro)
    assert n == 2


async def test_la_memoria_ha_un_tetto():
    async def scarica(url, *, max_bytes):
        return json.dumps([_riga(1)])

    for i in range(rm.CACHE_MAX + 20):
        await rm.cerca_stazioni(f"radio{i:03d}", 0, scarica=scarica, controlla=_tutto_sicuro)
    assert rm.dimensione_cache() <= rm.CACHE_MAX


def test_il_modulo_usa_solo_safe_http_per_la_rete():
    """Nessun client HTTP diretto: ogni richiesta passa da core/safe_http."""
    import inspect

    sorgente = inspect.getsource(rm)
    for vietato in ("aiohttp", "requests", "urllib.request", "httpx"):
        assert vietato not in sorgente
    assert "safe_get" in sorgente and "url_e_sicuro" in sorgente


# ----------------------------- vista e comando -----------------------------
import discord  # noqa: E402

from core.music_mondo_view import RadioMondoView, intestazione_pagina  # noqa: E402


def _pagina(n, ha_altre=False):
    return rm.PaginaStazioni(tuple(rm.stazione_da_json(_riga(i)) for i in range(1, n + 1)), ha_altre)


def _inter(user_id=5):
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id), data={"values": ["1"]},
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()), edit_original_response=AsyncMock(),
    )


async def test_vista_menu_con_al_massimo_25_voci_e_bottoni_secondo_la_pagina():
    vista = RadioMondoView(5, "rock", 0, _pagina(rm.PER_PAGINA, ha_altre=True), "it", AsyncMock(), AsyncMock())
    menu = next(c for c in vista.children if isinstance(c, discord.ui.Select))
    assert 1 <= len(menu.options) <= 25
    prec, succ = [c for c in vista.children if isinstance(c, discord.ui.Button)]
    assert prec.disabled and not succ.disabled
    ultima = RadioMondoView(5, "rock", rm.MAX_PAGINE - 1, _pagina(3, ha_altre=True), "it", AsyncMock(), AsyncMock())
    assert [c for c in ultima.children if isinstance(c, discord.ui.Button)][1].disabled


async def test_vista_solo_per_chi_ha_dato_il_comando():
    vista = RadioMondoView(5, "rock", 0, _pagina(2), "it", AsyncMock(), AsyncMock())
    estraneo = _inter(user_id=9)
    assert await vista.interaction_check(estraneo) is False
    estraneo.response.send_message.assert_awaited_once()


async def test_scelta_di_una_stazione_chiama_avvia_con_quella_stazione():
    avvia = AsyncMock()
    vista = RadioMondoView(5, "rock", 0, _pagina(3), "it", AsyncMock(), avvia)
    inter = _inter()
    await vista._scelta(inter)
    avvia.assert_awaited_once()
    assert avvia.await_args.args[1].nome == "Radio 2"


async def test_scelta_fuori_indice_non_avvia_niente():
    avvia = AsyncMock()
    vista = RadioMondoView(5, "rock", 0, _pagina(1), "it", AsyncMock(), avvia)
    await vista._scelta(_inter())
    avvia.assert_not_awaited()


async def test_pagina_successiva_cerca_e_aggiorna_il_messaggio():
    cerca = AsyncMock(return_value=_pagina(2))
    vista = RadioMondoView(5, "rock", 0, _pagina(rm.PER_PAGINA, ha_altre=True), "it", cerca, AsyncMock())
    inter = _inter()
    await vista._successiva(inter)
    cerca.assert_awaited_once_with("rock", 1)
    assert vista.pagina == 1
    inter.edit_original_response.assert_awaited_once()
    assert "rock" in intestazione_pagina("rock", 1, vista.dati, "it")


async def test_pagina_che_non_risponde_da_un_errore_e_resta_dov_e():
    vista = RadioMondoView(5, "rock", 0, _pagina(2, ha_altre=True), "it", AsyncMock(return_value=None), AsyncMock())
    inter = _inter()
    await vista._successiva(inter)
    assert vista.pagina == 0
    inter.followup.send.assert_awaited_once()


async def test_comando_radio_con_pausa_e_senza_voce(monkeypatch):
    import cogs.music.mondo as mondo

    cog = mondo.MusicMondoCog(SimpleNamespace(get_cog=lambda n: SimpleNamespace(controlli_base=AsyncMock(return_value=True))))
    inter = SimpleNamespace(
        guild=SimpleNamespace(id=1), user=SimpleNamespace(id=5),
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    monkeypatch.setattr(mondo, "lingua_interazione", AsyncMock(return_value="it"))
    monkeypatch.setattr(mondo, "testo_per", AsyncMock(return_value="x"))
    chiamate = []

    async def finta(nome, pagina, **kw):
        chiamate.append(nome)
        return _pagina(2)

    monkeypatch.setattr(mondo, "cerca_stazioni", finta)
    await cog.radio.callback(cog, inter, "rock")
    assert chiamate == ["rock"] and inter.followup.send.await_args.kwargs["ephemeral"] is True
    # seconda ricerca subito dopo: respinta dalla pausa, nessuna rete
    inter.response.send_message.reset_mock()
    await cog.radio.callback(cog, inter, "rock")
    assert chiamate == ["rock"]
    inter.response.send_message.assert_awaited_once()

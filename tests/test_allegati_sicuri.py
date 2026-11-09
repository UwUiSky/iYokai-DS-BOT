"""
tests/test_allegati_sicuri.py
=============================
Copia sicura degli allegati nei log (D61, #152): tipo dai byte, nessuna decodifica nel bot, cartella fuori dal
sito, anteprima solo ricodificata, link firmati, intestazioni di download, conservazione a tempo e /privacy.
"""

import os
import re
from types import SimpleNamespace

import pytest

from core import allegati_sicuri as al
from core import data_registry
from core.immagini_byte_logic import MALEVOLA, PULITA, SOSPETTA
from core.immagini_pipeline import EsitoImmagine
from tests.support import immagini_finte as f

G, C, M, U = 777152001, 11, 22, 33
HTML = b"<html><script>alert(1)</script></html>"


@pytest.fixture
async def ambiente(clean_db, tmp_path, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setenv(al.VARIABILE_CARTELLA, str(tmp_path / "all"))

    async def pulita(dati, nome, ct, guild_id):
        return EsitoImmagine(PULITA, "s", png=b"\x89PNG-ricodificato")

    monkeypatch.setattr(al.immagini_pipeline, "analizza_immagine", pulita)
    return al.cartella()


def test_tipo_solo_dai_primi_byte_mai_dal_nome():
    assert al.tipo_dai_byte(f.png()) == "png"
    assert al.tipo_dai_byte(HTML) == al.GENERICO
    assert al.tipo_dai_byte(b"<svg xmlns='http://www.w3.org/2000/svg'/>") == al.GENERICO


@pytest.mark.asyncio
async def test_file_png_con_byte_html_si_salva_generico_senza_anteprima_e_senza_analisi(ambiente, monkeypatch):
    chiamate = []

    async def spia(*a):
        chiamate.append(a)

    monkeypatch.setattr(al.immagini_pipeline, "analizza_immagine", spia)
    copia = await al.salva(G, C, M, U, "log", "foto.png", HTML, content_type="image/png")
    assert copia.tipo == al.GENERICO and copia.anteprima is None
    assert chiamate == []  # nessun decoder per cio' che non e' un'immagine vera
    assert [p.read_bytes() for p in ambiente.iterdir()] == [HTML]  # byte intatti


@pytest.mark.asyncio
async def test_immagine_pulita_ha_originale_e_anteprima_con_nomi_casuali(ambiente):
    dati = f.png()
    copia = await al.salva(G, C, M, U, "log", "../../etc/passwd.png", dati)
    assert copia.nome_file == "passwd.png"
    nomi = {p.name for p in ambiente.iterdir()}
    assert len(nomi) == 2 and all(re.fullmatch(r"[0-9a-f]{32}", n) for n in nomi)
    assert (await al.leggi(copia.id))[1] == dati
    assert (await al.leggi(copia.id, anteprima=True))[1] == b"\x89PNG-ricodificato"


@pytest.mark.asyncio
@pytest.mark.parametrize("verdetto", [SOSPETTA, MALEVOLA])
async def test_immagine_sospetta_non_si_conserva(ambiente, monkeypatch, verdetto):
    async def esito(*a):
        return EsitoImmagine(verdetto, "s", ("x",))

    monkeypatch.setattr(al.immagini_pipeline, "analizza_immagine", esito)
    copia = await al.salva(G, C, M, U, "log", "a.png", f.png())
    assert copia.stato == al.STATO_BLOCCATA and not copia.con_file
    assert list(ambiente.iterdir()) == []
    assert await al.leggi(copia.id) is None


@pytest.mark.asyncio
async def test_troppo_grande_non_si_salva(ambiente):
    assert await al.salva(G, C, M, U, "log", "a.bin", b"0" * (al.MAX_BYTE + 1)) is None


def test_cartella_dentro_il_sito_e_rifiutata(tmp_path, monkeypatch):
    from core.web_panel_server import CARTELLA

    monkeypatch.setenv(al.VARIABILE_CARTELLA, str(CARTELLA / "static" / "x"))
    with pytest.raises(RuntimeError):
        al.cartella()


def test_token_firmato_scade_e_non_si_falsifica():
    t = al.crea_token("k" * 32, 5, adesso=1000)
    assert al.leggi_token("k" * 32, t, adesso=1001) == (5, False)
    assert al.leggi_token("k" * 32, t, adesso=1000 + al.SECONDI_LINK + 1) is None
    assert al.leggi_token("altra" * 8, t, adesso=1001) is None
    assert al.leggi_token("k" * 32, t.replace("5.o", "6.o"), adesso=1001) is None
    assert al.leggi_token("k" * 32, "x" * 500) is None


def test_intestazioni_di_download():
    h = al.intestazioni_download('a"b\r\n.png')
    assert h["Content-Disposition"].startswith("attachment;") and "\n" not in h["Content-Disposition"]
    assert h["X-Content-Type-Options"] == "nosniff" and h["Content-Security-Policy"] == "sandbox"


@pytest.mark.asyncio
async def test_scadenza_e_orfani_si_tolgono_privacy_toglie_la_riga(ambiente):
    a = await al.salva(G, C, M, U, "log", "a.png", f.png())
    b = await al.salva(G, C, M + 1, U + 1, "log", "b.txt", b"ciao")
    from core.database import db

    await db.pool.execute("UPDATE allegati_copie SET scade_il = now() - interval '1 day' WHERE id = $1", a.id)
    assert await al.pulisci() == 2  # originale e anteprima di a
    assert {p.name for p in ambiente.iterdir()} and len(list(ambiente.iterdir())) == 1
    await db.pool.execute("DELETE FROM allegati_copie WHERE id = $1", b.id)  # come /privacy
    for p in ambiente.iterdir():
        os.utime(p, (1, 1))
    assert await al.pulisci() == 1 and list(ambiente.iterdir()) == []


def test_registro_dati_conosce_la_tabella():
    voce = next(t for t in data_registry.REGISTRO if t.nome == "allegati_copie")
    assert voce.colonne_utente == ("user_id",) and voce.utente == "cancella"


# ------------------------------------------------------------------ download dal pannello
async def _app_download(clean_db, allegati_url="https://allegati.example.invalid"):
    import secrets

    from aiohttp.test_utils import TestClient, TestServer

    from core.repositories.web_panel_session_repo import WebPanelSessionRepository
    from core.web_panel_server import build_app

    chiave = secrets.token_urlsafe(48)
    app = build_app(
        bot=SimpleNamespace(), sessioni=WebPanelSessionRepository(lambda: clean_db), oauth=None, client_id="1",
        client_secret="s" * 8, url_pubblico="https://pannello.example", chiave=chiave, allegati_url=allegati_url,
    )
    client = TestClient(TestServer(app))
    await client.start_server()
    return client, chiave


@pytest.mark.asyncio
async def test_download_ha_le_intestazioni_di_sicurezza_e_nessun_cookie(ambiente, clean_db):
    copia = await al.salva(G, C, M, U, "log", "foto<1>.png", HTML)
    client, chiave = await _app_download(clean_db)
    try:
        url = "/allegato/" + al.crea_token(chiave, copia.id)
        r = await client.get(url, headers={"Host": "allegati.example.invalid"})
        assert r.status == 200 and await r.read() == HTML
        assert r.headers["Content-Disposition"].startswith("attachment;")
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["Content-Security-Policy"] == "sandbox"
        assert r.headers["Content-Type"].startswith("application/octet-stream")
        assert "Set-Cookie" not in r.headers
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_download_solo_dal_sottodominio_con_link_buono(ambiente, clean_db):
    copia = await al.salva(G, C, M, U, "log", "a.txt", b"ciao")
    client, chiave = await _app_download(clean_db)
    try:
        url = "/allegato/" + al.crea_token(chiave, copia.id)
        assert (await client.get(url, headers={"Host": "pannello.example"})).status == 404  # host del pannello
        falso = url[:-4] + "0000"
        assert (await client.get(falso, headers={"Host": "allegati.example.invalid"})).status == 404
    finally:
        await client.close()
    senza, chiave2 = await _app_download(clean_db, allegati_url="")
    try:
        url = "/allegato/" + al.crea_token(chiave2, copia.id)
        assert (await senza.get(url)).status == 404  # sotto-dominio non configurato: spento
    finally:
        await senza.close()

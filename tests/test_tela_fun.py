"""
tests/test_tela_fun.py
======================
Tela di pixel del server (FUN-013, FUN-014, #131): regole, immagine, pausa e pagamento atomici, due pixel insieme sulla
stessa casella, moderazione, comandi e pagina web pubblica in sola lettura.
Funzioni coperte: FUN-013, FUN-014
"""

import asyncio
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from cogs.fun import tela as cog_tela
from cogs.fun.tela import TelaCog
from core import tela_logic as tl
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.tela_repo import Esito, TelaRepository
from core.tela_image import disegna
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G = 100


# ---------------------------------------------------------------- regole pure
def test_palette_16_colori_distinti_e_fondo_scuro():
    assert len(tl.PALETTE) == tl.NUMERO_COLORI == 16 and len({c for _, c in tl.PALETTE}) == 16
    assert tl.rgb(0) == (7, 7, 11) and tl.rgb(4) == (194, 74, 58)
    assert tl.colore_valido(15) and not tl.colore_valido(16) and not tl.colore_valido(-1)
    assert tl.coordinate_valide(0, 99) and not tl.coordinate_valide(100, 0) and not tl.coordinate_valide(0, -1)


def test_finestra_centrata_e_dentro_la_tela():
    assert tl.finestra(50, 50, 1) == (0, 0, 100)
    assert tl.finestra(50, 50, 2) == (25, 25, 50)
    assert tl.finestra(0, 0, 3) == (0, 0, 25)  # l'angolo non esce
    assert tl.finestra(99, 99, 4) == (90, 90, 10)
    with pytest.raises(ValueError):
        tl.finestra(1, 1, 9)
    assert tl.scala(100) == 8 and tl.scala(10) == 80


def test_costo_per_saltare_la_pausa():
    assert tl.costo_accorciare(0, 10) == 0 and tl.costo_accorciare(100, 0) == 0
    assert tl.costo_accorciare(1, 10) == 10 and tl.costo_accorciare(60, 10) == 10 and tl.costo_accorciare(61, 10) == 20
    assert tl.formatta_attesa(75) == "1:15" and tl.formatta_attesa(-3) == "0:00"


def test_disegna_mette_i_colori_al_posto_giusto_e_rifiuta_zone_storte():
    png = disegna([(10, 20, 4), (11, 20, 13), (99, 99, 3)], 0, 0, 100)
    img = Image.open(io.BytesIO(png)).convert("RGB")
    s, m = tl.scala(100), 28
    assert img.size == (100 * s + m, 100 * s + m)
    assert img.getpixel((m + 10 * s + 2, m + 20 * s + 2)) == tl.rgb(4)
    assert img.getpixel((m + 11 * s + 2, m + 20 * s + 2)) == tl.rgb(13)
    assert img.getpixel((m + 5 * s, m + 5 * s)) == tl.rgb(0)  # casella vuota
    zoom = Image.open(io.BytesIO(disegna([(95, 95, 8)], 90, 90, 10))).convert("RGB")
    assert zoom.getpixel((m + 5 * 80 + 4, m + 5 * 80 + 4)) == tl.rgb(8)  # zona 90..99, casella (95, 95)
    for storto in ((0, 0, 7), (95, 0, 10), (-1, 0, 100)):
        with pytest.raises(ValueError):
            disegna([], *storto)


# ---------------------------------------------------------------- database
@pytest.fixture
def r(clean_db, monkeypatch):
    import core.ui_base as ui

    async def nessuno(*a, **k):
        return False

    async def attivo(*a, **k):
        return True

    monkeypatch.setattr(ui, "_utente_o_server_in_blacklist", nessuno)
    ripo = TelaRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(cog_tela, "tela_repo", ripo)
    monkeypatch.setattr(cog_tela.db, "is_module_active_for_guild", attivo)
    return SimpleNamespace(t=ripo, lev=LevelingRepository(pool_provider=lambda: clean_db), pool=clean_db)


@pytest.mark.asyncio
async def test_pixel_pausa_e_autore(r):
    assert (await r.t.colora(G, 1, 5, 6, 4)).esito is Esito.OK
    p = await r.t.pixel(G, 5, 6)
    assert (p.colore, p.user_id) == (4, 1)
    again = await r.t.colora(G, 1, 7, 7, 4)  # stessa persona: in pausa
    assert again.esito is Esito.PAUSA and 0 < again.resta <= 300 and await r.t.pixel(G, 7, 7) is None
    assert (await r.t.colora(G, 2, 5, 6, 9)).esito is Esito.OK  # un'altra persona ricolora la stessa casella
    p = await r.t.pixel(G, 5, 6)
    assert (p.colore, p.user_id) == (9, 2) and await r.t.conta(G) == 1
    resta, bloccato, messi = await r.t.attesa(G, 1)
    assert 0 < resta <= 300 and not bloccato and messi == 1
    assert await r.t.attesa(G, 77) == (0.0, False, 0)
    for storto in ((100, 0, 1), (0, -1, 1), (0, 0, 16)):
        with pytest.raises(ValueError):
            await r.t.colora(G, 1, *storto)


@pytest.mark.asyncio
async def test_la_pausa_finisce_e_si_puo_cambiare(r):
    await r.t.imposta(G, pausa_secondi=30)
    assert (await r.t.colora(G, 1, 0, 0, 1)).esito is Esito.OK
    await r.pool.execute("UPDATE tela_utenti SET ultimo_at = now() - interval '31 seconds'")
    assert (await r.t.colora(G, 1, 1, 0, 1)).esito is Esito.OK
    imp = await r.t.imposta(G, costo_minuto=0, pubblica=True)
    assert (imp.pausa_secondi, imp.costo_minuto, imp.pubblica) == (30, 0, True)  # i campi non dati restano
    assert await r.t.impostazioni(999) == await r.t.impostazioni(998)  # server mai visto: valori di base
    for storto in ({"pausa_secondi": 5}, {"pausa_secondi": 99999}, {"costo_minuto": -1}):
        with pytest.raises(ValueError):
            await r.t.imposta(G, **storto)


@pytest.mark.asyncio
async def test_saltare_la_pausa_si_paga_una_volta_e_atomicamente(r):
    await r.t.colora(G, 1, 0, 0, 1)  # ora è in pausa (300 s = 5 minuti -> 50 monete di base)
    assert (await r.t.colora(G, 1, 1, 1, 2, accorcia=True)).esito is Esito.POCHE  # senza monete
    assert await r.t.pixel(G, 1, 1) is None
    await r.lev.add_coins(G, 1, 50)
    ris = await r.t.colora(G, 1, 1, 1, 2, accorcia=True)
    assert ris.esito is Esito.OK and ris.costo == 50 and (await r.lev.get_totals(G, 1)).coins_total == 0
    assert (await r.t.pixel(G, 1, 1)).colore == 2
    # dopo il pagamento la pausa riparte: un secondo salto costa di nuovo, e senza monete non passa
    assert (await r.t.colora(G, 1, 2, 2, 2, accorcia=True)).esito is Esito.POCHE
    # senza chiedere di pagare, la pausa resta una pausa
    assert (await r.t.colora(G, 1, 2, 2, 2)).esito is Esito.PAUSA
    await r.t.imposta(G, costo_minuto=0)  # costo 0 = non si può saltare
    await r.lev.add_coins(G, 1, 500)
    assert (await r.t.colora(G, 1, 2, 2, 2, accorcia=True)).esito is Esito.PAUSA
    assert (await r.lev.get_totals(G, 1)).coins_total == 500


@pytest.mark.asyncio
async def test_due_pixel_insieme_sulla_stessa_casella_ne_lasciano_uno(r):
    await apri_connessioni(r.pool, 6)
    esiti = await asyncio.gather(*(r.t.colora(G, u, 3, 3, u % 16) for u in range(1, 7)))
    assert all(e.esito is Esito.OK for e in esiti)  # sono persone diverse: nessuna è in pausa
    assert await r.pool.fetchval("SELECT count(*) FROM tela_pixel WHERE guild_id = $1 AND x = 3 AND y = 3", G) == 1
    p = await r.t.pixel(G, 3, 3)
    assert p.user_id in range(1, 7) and p.colore == p.user_id % 16  # autore e colore sono dello stesso pixel


@pytest.mark.asyncio
async def test_due_pixel_insieme_della_stessa_persona_rispettano_la_pausa(r):
    await apri_connessioni(r.pool, 6)
    esiti = await asyncio.gather(*(r.t.colora(G, 1, n, 0, 5) for n in range(5)))
    assert sorted(e.esito.value for e in esiti) == ["ok", "pausa", "pausa", "pausa", "pausa"]
    assert await r.t.conta(G) == 1 and (await r.t.attesa(G, 1))[2] == 1


@pytest.mark.asyncio
async def test_salti_a_pagamento_insieme_con_monete_per_uno_solo(r):
    await r.t.colora(G, 1, 0, 0, 1)
    await r.lev.add_coins(G, 1, 50)  # i soldi di un solo salto
    await apri_connessioni(r.pool, 4)
    esiti = await asyncio.gather(*(r.t.colora(G, 1, n, 1, 2, accorcia=True) for n in range(1, 4)))
    assert sorted(e.esito.value for e in esiti) == ["ok", "poche", "poche"]
    assert (await r.lev.get_totals(G, 1)).coins_total == 0 and await r.t.conta(G) == 2


@pytest.mark.asyncio
async def test_moderazione_azzera_togli_utente_e_blocca(r):
    await r.t.colora(G, 1, 0, 0, 1)
    await r.t.colora(G, 2, 1, 0, 1)
    await r.pool.execute("UPDATE tela_utenti SET ultimo_at = now() - interval '1 hour'")
    await r.t.colora(G, 1, 2, 0, 1)
    await r.t.colora(G, 7, 0, 0, 1, accorcia=False)  # in un altro server niente cambia
    await r.t.colora(G + 1, 1, 0, 0, 3)
    assert await r.t.togli_utente(G, 1) == 1  # il pixel (0, 0) era già passato a 7: restano solo quelli di 1
    assert (await r.t.pixel(G, 0, 0)).user_id == 7 and await r.t.pixel(G, 2, 0) is None
    assert (await r.t.pixel(G, 1, 0)).user_id == 2 and (await r.t.pixel(G + 1, 0, 0)).colore == 3
    # blocco: non colora più, anche con la pausa finita
    assert await r.t.imposta_blocco(G, 2, True) is True and await r.t.imposta_blocco(G, 2, True) is False
    assert await r.t.e_bloccato(G, 2)
    await r.pool.execute("UPDATE tela_utenti SET ultimo_at = now() - interval '1 hour'")
    assert (await r.t.colora(G, 2, 9, 9, 1)).esito is Esito.BLOCCATO and await r.t.pixel(G, 9, 9) is None
    assert await r.t.imposta_blocco(G, 2, False) is True and await r.t.imposta_blocco(G, 2, False) is False
    assert (await r.t.colora(G, 2, 9, 9, 1)).esito is Esito.OK
    assert await r.t.imposta_blocco(G, 55, True) is True  # anche chi non ha mai colorato si può bloccare
    assert (await r.t.colora(G, 55, 8, 8, 1)).esito is Esito.BLOCCATO
    assert await r.t.azzera(G) >= 1 and await r.t.conta(G) == 0 and await r.t.conta(G + 1) == 1


# ---------------------------------------------------------------- comandi
def _i(membro=None):
    i = fake_interaction(guild=fake_guild(G), user=membro or fake_member(1))
    return i


@pytest.mark.asyncio
async def test_comandi_colora_vedi_pixel_stato(r, monkeypatch):
    cog = TelaCog(MagicMock())
    i = _i()
    await TelaCog.colora.callback(cog, i, 10, 20, 4, False)
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    assert (await r.t.pixel(G, 10, 20)).colore == 4
    i = _i()
    await TelaCog.colora.callback(cog, i, 11, 20, 4, False)  # in pausa
    assert await r.t.pixel(G, 11, 20) is None and "ephemeral" in i.response.send_message.await_args.kwargs
    i = _i(fake_member(2))
    await TelaCog.pixel.callback(cog, i, 10, 20)
    testo = i.response.send_message.await_args.args[0]
    assert "<@1>" in testo and i.response.send_message.await_args.kwargs["allowed_mentions"].users is False  # nessuna menzione vera
    i = _i()
    await TelaCog.pixel.callback(cog, i, 0, 0)
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    i = _i()
    await TelaCog.stato.callback(cog, i)
    assert "ephemeral" in i.response.send_message.await_args.kwargs
    # vedi: l'immagine si disegna fuori dal ciclo principale
    chiamate = []
    from core import safe_image

    vera = cog_tela.run_image_task

    async def spia(f, *a):
        chiamate.append(f.__name__)
        return await vera(f, *a)

    monkeypatch.setattr(cog_tela, "run_image_task", spia)
    i = _i()
    await TelaCog.vedi.callback(cog, i, 10, 20, 3)
    assert chiamate == ["disegna"]
    f = i.followup.send.await_args.kwargs["file"]
    assert Image.open(io.BytesIO(f.fp.read())).format == "PNG"
    i = _i()
    i.guild = None
    await TelaCog.vedi.callback(cog, i, 50, 50, 1)  # fuori da un server
    assert chiamate == ["disegna"]


@pytest.mark.asyncio
async def test_comandi_staff(r):
    cog = TelaCog(MagicMock())
    utente = SimpleNamespace(id=1, mention="<@1>")
    await r.t.colora(G, 1, 0, 0, 1)
    await r.t.colora(G, 2, 1, 1, 1)
    i = _i(fake_member(9))
    await TelaCog.azzera.callback(cog, i, False)  # senza conferma non cancella niente
    assert await r.t.conta(G) == 2
    await TelaCog.togli_utente.callback(cog, _i(fake_member(9)), utente)
    assert await r.t.conta(G) == 1
    await TelaCog.blocca.callback(cog, _i(fake_member(9)), utente)
    assert await r.t.e_bloccato(G, 1)
    i = _i(fake_member(9))
    await TelaCog.blocca.callback(cog, i, utente)  # già bloccato
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    await TelaCog.sblocca.callback(cog, _i(fake_member(9)), utente)
    assert not await r.t.e_bloccato(G, 1)
    await TelaCog.impostazioni.callback(cog, _i(fake_member(9)), 60, 5, True)
    imp = await r.t.impostazioni(G)
    assert (imp.pausa_secondi, imp.costo_minuto, imp.pubblica) == (60, 5, True)
    await TelaCog.azzera.callback(cog, _i(fake_member(9)), True)
    assert await r.t.conta(G) == 0


def test_i_comandi_staff_hanno_il_controllo_del_livello():
    for nome in ("azzera", "togli_utente", "blocca", "sblocca", "impostazioni"):
        cmd = getattr(TelaCog, nome)
        assert getattr(cmd.callback, "__discord_app_commands_checks__", None), nome


# ---------------------------------------------------------------- pagina web pubblica
from tests.test_web_panel_server import GUILD, _client, ambiente  # noqa: E402,F401


@pytest.fixture
def web(ambiente, monkeypatch):
    ripo = TelaRepository(pool_provider=lambda: ambiente.pool)
    import core.web_panel_tela as wt

    async def attivo(*a, **k):
        return True

    monkeypatch.setattr(wt, "tela_repo", ripo)
    monkeypatch.setattr(wt.db, "is_module_active_for_guild", attivo)
    ambiente.tela = ripo
    return ambiente


@pytest.mark.asyncio
async def test_pagina_pubblica_spenta_e_server_sconosciuto_non_si_distinguono(web):
    client = await _client(web.app)
    try:
        spenta = await client.get(f"/tela/{GUILD}")
        assert spenta.status == 404
        assert (await client.get(f"/tela/{GUILD}/immagine.png")).status == 404
        altro = await client.get("/tela/12345")
        assert altro.status == 404 and (await altro.text()) == (await spenta.text())
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_pagina_pubblica_accesa_con_escape_senza_script_e_solo_lettura(web):
    await web.tela.imposta(GUILD, pubblica=True)
    await web.tela.colora(GUILD, 1, 10, 10, 4)
    client = await _client(web.app)
    try:
        r = await client.get(f"/tela/{GUILD}?x=abc&y=-5&zoom=99")  # numeri storti: nessun errore
        assert r.status == 200
        html = await r.text()
        assert "<b>di</b>" not in html and "&lt;b&gt;di&lt;/b&gt;" in html  # il nome del server è sotto escape
        assert "<script" not in html.lower() and "http://" not in html.replace("http://pannello.test", "")
        assert f"/tela/{GUILD}/immagine.png?x=0&amp;y=0&amp;zoom=4" in html or "zoom=4" in html
        assert "default-src 'none'" in r.headers["Content-Security-Policy"]
        img = await client.get(f"/tela/{GUILD}/immagine.png?zoom=1")
        assert img.status == 200 and img.content_type == "image/png"
        assert Image.open(io.BytesIO(await img.read())).format == "PNG"
        assert (await client.post(f"/tela/{GUILD}", data={"x": "1"})).status in (404, 405)  # nessuna scrittura dal sito
        assert (await client.post(f"/tela/{GUILD}/immagine.png", data={})).status in (404, 405)
        await web.tela.imposta(GUILD, pubblica=False)  # spenta di nuovo: sparisce
        assert (await client.get(f"/tela/{GUILD}")).status == 404
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_pagina_pubblica_ha_un_limite_di_frequenza(web):
    await web.tela.imposta(GUILD, pubblica=True)
    client = await _client(web.app)
    try:
        stati = [(await client.get(f"/tela/{GUILD}/immagine.png")).status for _ in range(25)]
        assert stati[:20] == [200] * 20 and 429 in stati[20:]
    finally:
        await client.close()

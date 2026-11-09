"""
tests/test_strumenti_rapidi.py
==============================
Catalogo #128 B1 (D69): caratteri, cronometro, novità, Wikipedia, Wikizionario,
emergenze. Logica pura, comandi del cog e posizione nell'albero.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands as ext

import cogs.utility.strumenti_rapidi as cogutil
import cogs.utility.web as cogweb
from core import strumenti_rapidi_logic as L
from tests.support.discord_fakes import fake_interaction
from tests.support.percorsi import comando_nel_gruppo


def test_caratteri_distinti_e_tetto_25():
    righe, tagliati = L.righe_caratteri("aab" + "".join(chr(0x4E00 + i) for i in range(30)))
    assert len(righe) == 25 and tagliati == 7
    assert righe[0][0].endswith("U+0061") and "LATIN SMALL LETTER A" in righe[0][1]


def test_carattere_combinante_mostrato_come_punto():
    righe, _ = L.righe_caratteri("́")
    assert righe[0][0].startswith("·")


def test_cronometro_giri_e_tetto():
    testo = L.corpo_cronometro(1000, [])
    for _ in range(L.MAX_GIRI):
        testo, ok = L.aggiungi_giro(testo, 1000, 1012.5)
        assert ok
    assert testo.count("Giro ") == 20 and "00:12.5" in testo
    assert L.aggiungi_giro(testo, 1000, 1013)[1] is False
    assert "fermo a 00:13.0" in L.ferma_cronometro(testo, 1000, 1013)


def test_durata_con_ore():
    assert L.formatta_durata(3725.4) == "1:02:05.4"


def test_custom_id_dei_bottoni_entra_nel_limite():
    assert len(L.id_cronometro("ferma", 2**40)) < 100


def test_novita_ordinate_pagine_e_ripiego(tmp_path):
    (tmp_path / "novita").mkdir()
    voci = [{"data": f"2026-01-{i:02d}", "titolo": f"v{i}", "testo": "x"} for i in range(1, 26)]
    (tmp_path / "novita" / "it.json").write_text(json.dumps(voci))
    letti = L.carica_novita("de", tmp_path)  # lingua assente: ripiego sull'italiano
    assert letti[0]["titolo"] == "v25"
    pagina, n = L.pagina_novita(letti, 99)
    assert n == 3 and len(pagina) == 5
    assert L.carica_novita("it", tmp_path / "vuoto") == []


def test_emergenze_del_repo_leggibili_e_ricerca():
    dati = L.carica_emergenze()
    assert dati["data"] and "Italia" in dati["paesi"]
    assert L.cerca_paesi("ital", dati["paesi"]) == ["Italia"]
    assert len(L.cerca_paesi("", dati["paesi"], 25)) <= 25


def test_lettura_risposte_wiki():
    assert L.lingua_wiki("en-US") == "en" and L.lingua_wiki(None) == "it"
    assert L.leggi_chiave_ricerca('{"pages":[{"key":"Roma"}]}') == "Roma"
    assert L.leggi_chiave_ricerca('{"pages":[]}') is None and L.leggi_chiave_ricerca("rotto") is None
    ok = L.leggi_sommario('{"title":"Roma","extract":"' + "a" * 3000 + '","content_urls":{"desktop":{"page":"https://x"}}}')
    assert ok["link"] == "https://x" and len(ok["testo"]) <= 1000
    assert L.leggi_sommario('{"type":"disambiguation","title":"x","extract":""}') is None
    w = L.leggi_wikizionario('{"query":{"pages":{"1":{"title":"casa","extract":"edificio"}}}}', "it")
    assert w["link"].endswith("/wiki/casa")
    assert L.leggi_wikizionario('{"query":{"pages":{"-1":{"title":"x","missing":""}}}}', "it") is None


@pytest.mark.asyncio
async def test_wiki_riprova_in_inglese_e_usa_la_cache(monkeypatch):
    L._cache.clear()
    chiamate = []

    async def finta(url, max_bytes=0):
        chiamate.append(url)
        if "//it." in url:
            return '{"pages":[]}'
        if "search" in url:
            return '{"pages":[{"key":"Rome"}]}'
        return '{"title":"Rome","extract":"city"}'

    monkeypatch.setattr(L, "safe_get", finta)
    r = await L.cerca_wikipedia("it", "Rome")
    assert r["titolo"] == "Rome"
    n = len(chiamate)
    await L.cerca_wikipedia("it", "rome")
    assert len(chiamate) == n  # dalla cache


@pytest.mark.asyncio
async def test_errore_di_rete_non_entra_in_cache(monkeypatch):
    L._cache.clear()
    monkeypatch.setattr(L, "safe_get", AsyncMock(return_value=None))
    assert await L.cerca_parola("it", "casa") is None
    assert len(L._cache) == 0


@pytest.mark.asyncio
async def test_wiki_comando_defer_prima_della_rete(monkeypatch):
    cog = cogweb.WebCog(MagicMock())
    ordine = []
    it = fake_interaction()
    it.response.defer = AsyncMock(side_effect=lambda **k: ordine.append("defer"))

    async def cerca(lingua, testo):
        ordine.append("rete")
        return None

    monkeypatch.setattr(cogweb.logica, "cerca_wikipedia", cerca)
    await cog.wiki.callback(cog, it, "Roma")
    assert ordine == ["defer", "rete"]
    it.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_emergenza_trova_il_paese_anche_scritto_a_meta():
    cog = cogweb.WebCog(MagicMock())
    it = fake_interaction()
    await cog.emergenza.callback(cog, it, "ital")
    embed = it.response.send_message.await_args.kwargs["embed"]
    assert "Italia" in embed.title and any(f.value == "118" for f in embed.fields)


@pytest.mark.asyncio
async def test_cronometro_giro_e_ferma():
    it = fake_interaction()
    it.message = MagicMock(content=L.corpo_cronometro(1000, []))
    it.response.edit_message = AsyncMock()
    b = cogutil.BottoneCronometro("giro", 1000)
    await b.callback(it)
    assert "Giro 1" in it.response.edit_message.await_args.kwargs["content"]
    await cogutil.BottoneCronometro("ferma", 1000).callback(it)
    assert it.response.edit_message.await_args.kwargs["view"] is None


@pytest.mark.asyncio
async def test_albero_utility_e_web():
    bot = ext.Bot(command_prefix="!", intents=discord.Intents.default())
    await cogutil.setup(bot)
    await cogweb.setup(bot)
    for g, p in (("utility", "caratteri"), ("utility", "cronometro"), ("utility", "novita"),
                 ("web", "wiki"), ("web", "dizionario"), ("web", "emergenza")):
        assert comando_nel_gruppo(g, p) is not None
    d = comando_nel_gruppo("web", "wiki").to_dict(bot.tree)
    assert d["options"][0]["max_length"] == 100
    assert comando_nel_gruppo("utility", "caratteri").to_dict(bot.tree)["options"][0]["max_length"] == 100

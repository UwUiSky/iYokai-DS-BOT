"""
tests/test_command_search_panel_logic.py
========================================
Logica pura del pannello e della ricerca di -cerca-comando (issue #147):
raccolta dei comandi con le opzioni, menzioni cliccabili, pagine,
suggerimenti (max 25), sinonimi italiani, filtro per accesso, cache degli ID.
Funzioni coperte: NF-06 (issue #147)
"""

from __future__ import annotations

import discord
from discord import app_commands

from core import command_search_logic as L


async def _nulla(interaction):  # pragma: no cover
    pass


def _albero():
    async def ban(interaction: discord.Interaction, utente: str, motivo: str = "x"):  # pragma: no cover
        pass

    gruppo = app_commands.Group(name="modban", description="Moderazione dura")
    gruppo.add_command(
        app_commands.Command(name="ban", description="Banna un utente dal server", callback=ban)
    )
    sotto = app_commands.Group(name="lista", description="Liste", parent=gruppo)
    sotto.add_command(app_commands.Command(name="mostra", description="Mostra la lista", callback=_nulla))
    piatto = app_commands.Command(name="-cerca-comando", description="Cerca un comando", callback=_nulla)
    return [gruppo, piatto]


def test_raccogli_comandi_espande_gruppi_e_opzioni():
    info = {c.percorso: c for c in L.raccogli_comandi(_albero())}
    assert set(info) == {"modban ban", "modban lista mostra", "-cerca-comando"}
    ban = info["modban ban"]
    assert ban.gruppo == "modban"
    assert [(o.nome, o.obbligatoria) for o in ban.opzioni] == [("utente", True), ("motivo", False)]
    assert info["-cerca-comando"].gruppo == "-cerca-comando"


def test_menzione_usa_l_id_del_comando_di_primo_livello():
    ids = {"modban": 42, "-cerca-comando": 7}
    assert L.menzione("modban ban", ids) == "</modban ban:42>"
    assert L.menzione("modban lista mostra", ids) == "</modban lista mostra:42>"
    assert L.menzione("-cerca-comando", ids) == "</-cerca-comando:7>"


def test_menzione_senza_id_ricade_sul_testo():
    assert L.menzione("modban ban", {}) == "`/modban ban`"


def test_pagine_non_superano_il_massimo_e_correggono_l_indice():
    voci = list(range(53))
    pezzo, pag, tot = L.pagina(voci, 0, 20)
    assert (len(pezzo), pag, tot) == (20, 0, 3)
    pezzo, pag, tot = L.pagina(voci, 99, 20)
    assert (len(pezzo), pag, tot) == (13, 2, 3)
    pezzo, pag, tot = L.pagina(voci, -4, 20)
    assert pag == 0
    assert L.pagina([], 0, 20) == ([], 0, 1)


def test_suggerimenti_al_massimo_25_con_nome_e_valore_corti():
    tanti = [
        L.ComandoInfo(percorso=f"fun cmd{i}", descrizione="d" * 100, gruppo="fun", opzioni=())
        for i in range(60)
    ]
    scelte = L.suggerimenti("", tanti)
    assert len(scelte) == 25
    assert all(len(n) <= 100 and len(v) <= 100 for n, v in scelte)
    scelte = L.suggerimenti("cmd", tanti)
    assert len(scelte) == 25


def test_suggerimenti_filtrano_per_testo():
    comandi = L.raccogli_comandi(_albero())
    valori = [v for _, v in L.suggerimenti("banna", comandi)]
    assert valori[0] == "modban ban"
    assert "-cerca-comando" not in valori


def test_cerca_trova_per_sinonimo_italiano():
    comandi = L.raccogli_comandi(_albero())
    # "cacciare" non compare nelle descrizioni: lo trova il sinonimo di "bannare".
    trovati = L.cerca("voglio cacciare un utente", comandi)
    assert trovati and trovati[0].percorso == "modban ban"


def test_cerca_percorso_esatto_vince_e_toglie_la_barra():
    comandi = L.raccogli_comandi(_albero())
    assert L.cerca("/modban lista mostra", comandi)[0].percorso == "modban lista mostra"


def test_cerca_senza_corrispondenze_e_vuota():
    assert L.cerca("zzzqqq", L.raccogli_comandi(_albero())) == []


async def test_filtra_per_livelli_tiene_solo_i_comandi_consentiti():
    chiamate = []

    async def puo(livello):
        chiamate.append(livello)
        return livello == "mod"

    def c(nome, *livelli):
        return L.ComandoInfo(nome, "d", nome, (), tuple(livelli))

    visibili = await L.filtra_per_livelli(
        [c("a", "mod"), c("b", "modban"), c("c"), c("d", "mod", "modban"), c("e", "modban")], puo
    )
    assert [v.percorso for v in visibili] == ["a", "c"]
    assert chiamate.count("modban") == 1


def test_url_wiki_solo_se_impostato_e_valido():
    assert L.url_wiki("", "mod ban") is None
    assert L.url_wiki("ftp://x", None) is None
    assert L.url_wiki("https://wiki.example/", None) == "https://wiki.example"
    assert L.url_wiki("https://wiki.example/", "mod ban") == "https://wiki.example/mod/ban"
    assert L.url_wiki("https://wiki.example", "-cerca-comando") == "https://wiki.example/-cerca-comando"


def test_embed_risultati_sotto_i_limiti_di_discord():
    opzioni = tuple(L.Opzione(f"opzione{i}", "x" * 100, i % 2 == 0) for i in range(25))
    grossi = [
        L.ComandoInfo(percorso=f"gruppo cmd{i}", descrizione="y" * 100, gruppo="gruppo", opzioni=opzioni)
        for i in range(10)
    ]
    embed = L.embed_risultati(grossi, {"gruppo": 1}, "q" * 100)
    assert len(embed.fields) <= L.MAX_RISULTATI
    assert all(len(f.value) <= 1024 and len(f.name) <= 256 for f in embed.fields)
    assert len(embed) <= 6000


def test_embed_risultati_elenca_le_opzioni_e_la_menzione():
    comandi = L.raccogli_comandi(_albero())
    ban = [c for c in comandi if c.percorso == "modban ban"]
    embed = L.embed_risultati(ban, {"modban": 42}, "ban")
    testo = embed.fields[0].value
    assert "</modban ban:42>" in testo
    assert "utente" in testo and "motivo" in testo


def test_embed_pannello_con_e_senza_ultimo_comando_e_dm():
    ids = {"fun": 5}
    con = L.embed_pannello("fun gioca", ids, in_dm=False)
    assert "</fun gioca:5>" in con.description
    senza = L.embed_pannello(None, ids, in_dm=False)
    assert "</" not in senza.description
    dm = L.embed_pannello(None, ids, in_dm=True)
    assert "server" in dm.description.lower()


def test_embed_categoria_pagina_e_taglia_le_righe():
    comandi = [
        L.ComandoInfo(percorso=f"fun c{i}", descrizione="z" * 100, gruppo="fun", opzioni=())
        for i in range(30)
    ]
    embed, pag, tot = L.embed_categoria("fun", comandi, {"fun": 1}, 0)
    assert tot == 3 and pag == 0
    assert len(embed.description) <= 4096 and len(embed) <= 6000


class _AppCmd:
    def __init__(self, nome, id_):
        self.name, self.id = nome, id_


async def test_cache_id_si_aggiorna_se_manca_un_id_ma_non_di_continuo():
    chiamate = []
    orologio = [1000.0]

    async def fetch(guild=None):
        chiamate.append(guild)
        return [_AppCmd("fun", 5)] if len(chiamate) == 1 else [_AppCmd("fun", 5), _AppCmd("mod", 9)]

    cache = L.CacheIdComandi(ttl=3600, attesa_minima=60, orologio=lambda: orologio[0])
    ids = await cache.ottieni(fetch)
    assert ids == {"fun": 5} and len(chiamate) == 1
    await cache.ottieni(fetch)
    assert len(chiamate) == 1  # ancora fresca
    # Manca "mod" (comando nuovo dopo una sync): entro 60 s non richiede, poi sì.
    assert await cache.ottieni(fetch, serve=["mod"]) == {"fun": 5}
    assert len(chiamate) == 1
    orologio[0] += 61
    assert (await cache.ottieni(fetch, serve=["mod"]))["mod"] == 9
    assert len(chiamate) == 2


async def test_cache_id_invalida_forza_il_ricaricamento_e_sopporta_errori():
    stato = {"n": 0, "rompi": False}

    async def fetch(guild=None):
        stato["n"] += 1
        if stato["rompi"]:
            raise discord.HTTPException(response=type("R", (), {"status": 500, "reason": "x"})(), message="x")
        return [_AppCmd("fun", stato["n"])]

    cache = L.CacheIdComandi(ttl=3600, attesa_minima=0, orologio=lambda: 1.0)
    assert (await cache.ottieni(fetch))["fun"] == 1
    cache.invalida()
    assert (await cache.ottieni(fetch))["fun"] == 2
    stato["rompi"] = True
    cache.invalida()
    assert await cache.ottieni(fetch) == {"fun": 2}  # errore: tiene i vecchi ID, nessuna eccezione

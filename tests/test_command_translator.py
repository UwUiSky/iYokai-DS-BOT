"""
tests/test_command_translator.py
================================
NF-06 (#77, D1): nomi e descrizioni dei comandi in inglese, controllati sull'albero VERO
(owner compreso) e sugli alberi delle istanze separate (NSFW, App). Senza locales/en-US/comandi.json o con una voce ripetuta il test fallisce.
"""

import collections

import discord
import pytest
from discord import app_commands

from core import command_translator as tr
from tests.support.full_tree import build_separate_trees
from tests.test_command_tree_invariants import _albero_vero, _chiudi, _radici, _tutti_i_nodi

pytestmark = pytest.mark.asyncio

# Cricchetto sulle descrizioni delle OPZIONI (comandi:opzione): si alza solo, mai si abbassa.
MINIMO_PARAMETRI_TRADOTTI = 0


def _percorso(nodo) -> str:
    return nodo.qualified_name


def _nome_en(nodo) -> str:
    return tr.nome_inglese(nodo.name) or nodo.name


async def test_ogni_comando_e_gruppo_ha_la_descrizione_inglese():
    creato_qui, bot = await _albero_vero()
    try:
        mancanti = [_percorso(n) for n in _tutti_i_nodi(_radici(bot)) if tr.descrizione_inglese(_percorso(n)) is None]
        assert mancanti == [], f"Senza descrizione in locales/en-US/comandi.json: {mancanti[:15]} (+{max(0, len(mancanti) - 15)})"
    finally:
        await _chiudi(creato_qui, bot)


async def _nodi_separati() -> list:
    """I nodi slash degli alberi propri delle istanze separate (NSFW, App); i menu non hanno descrizione."""
    nodi = []
    for altro in await build_separate_trees():
        nodi += list(_tutti_i_nodi(altro.tree.get_commands(type=discord.AppCommandType.chat_input)))
        await altro.close()
    return nodi


async def test_gli_alberi_separati_sono_tradotti_con_nomi_validi():
    nodi = await _nodi_separati()
    assert nodi
    assert [_percorso(n) for n in nodi if tr.descrizione_inglese(_percorso(n)) is None] == []
    for n in nodi:
        inglese = tr.carica_traduzioni()["nomi"].get(n.name)
        assert inglese is None or (tr.nome_valido(inglese) and len(inglese) <= tr.MAX_NOME)


async def test_i_menu_delle_app_separate_hanno_il_nome_inglese():
    """I menu del tasto destro (nomi con maiuscole e spazi) si traducono dalla sezione `menu`."""
    menu = []
    for altro in await build_separate_trees():
        for tipo in (discord.AppCommandType.user, discord.AppCommandType.message):
            menu += altro.tree.get_commands(type=tipo)
        await altro.close()
    creato_qui, bot = await _albero_vero()
    try:  # anche i menu del bot principale (es. «Apri ticket»)
        for tipo in (discord.AppCommandType.user, discord.AppCommandType.message):
            menu += bot.tree.get_commands(type=tipo)
    finally:
        await _chiudi(creato_qui, bot)
    assert menu
    L = app_commands.TranslationContextLocation
    for m in menu:
        contesto = app_commands.TranslationContext(location=L.command_name, data=m)
        inglese = tr.tradotto_per(contesto, "en")
        assert inglese and inglese != m.name and len(inglese) <= tr.MAX_NOME, m.name
    assert sorted(set(tr.carica_traduzioni(forza=True)["menu"]) - {m.name for m in menu}) == []


async def test_nessuna_voce_inglese_resta_senza_comando():
    creato_qui, bot = await _albero_vero()
    try:
        from cogs.utility.livelli_comandi import crea_gruppi

        nodi = list(_tutti_i_nodi(_radici(bot))) + await _nodi_separati()
        nodi += list(_tutti_i_nodi(list(crea_gruppi())))  # /premium e /vip nascono solo quando servono (D57)
        percorsi = {_percorso(n) for n in nodi}
        segmenti = {n.name for n in nodi}
        dati = tr.carica_traduzioni(forza=True)
        assert sorted(set(dati["descrizioni"]) - percorsi) == []
        assert sorted(set(dati["nomi"]) - segmenti) == []
        parametri = {f"{_percorso(n)}:{p.name}" for n in nodi if not isinstance(n, app_commands.Group) for p in n.parameters}
        assert sorted(set(dati["parametri"]) - parametri) == []
    finally:
        await _chiudi(creato_qui, bot)


async def test_i_nomi_inglesi_sono_validi_e_unici_tra_fratelli():
    creato_qui, bot = await _albero_vero()
    try:
        problemi = []
        gruppi = [(None, _radici(bot))]
        gruppi += [(n, list(n.commands)) for n in _tutti_i_nodi(_radici(bot)) if isinstance(n, app_commands.Group)]
        for padre, figli in gruppi:
            visti = collections.Counter(_nome_en(f) for f in figli)
            problemi += [f"{padre.qualified_name if padre else '/'}: {nome} x{n}" for nome, n in visti.items() if n > 1]
        for n in _tutti_i_nodi(_radici(bot)):
            inglese = tr.carica_traduzioni()["nomi"].get(n.name)
            if inglese is not None and (not tr.nome_valido(inglese) or len(inglese) > tr.MAX_NOME):
                problemi.append(f"nome non valido: {inglese}")
        assert problemi == []
    finally:
        await _chiudi(creato_qui, bot)


async def test_limiti_di_discord_con_le_traduzioni():
    creato_qui, bot = await _albero_vero()
    try:
        troppo_lunghe = [
            _percorso(n) for n in _tutti_i_nodi(_radici(bot))
            if (d := tr.carica_traduzioni()["descrizioni"].get(_percorso(n))) and len(d) > tr.MAX_DESCRIZIONE
        ]
        assert troppo_lunghe == []
        grandi = [r.name for r in _radici(bot) if tr.caratteri_con_traduzioni(r) > 8000]
        assert grandi == [], f"Oltre 8000 caratteri con le traduzioni: {grandi}"
    finally:
        await _chiudi(creato_qui, bot)


async def test_il_traduttore_risponde_solo_in_inglese_e_il_payload_ha_le_localizzazioni():
    import discord

    creato_qui, bot = await _albero_vero()
    try:
        await bot.tree.set_translator(tr.TraduttoreYokai())
        modban = bot.tree.get_command("mod-ban")
        carico = await modban.get_translated_payload(bot.tree, bot.tree.translator)
        assert carico["description_localizations"]["en-US"] == tr.descrizione_inglese("mod-ban")
        assert carico["description_localizations"]["en-GB"] == tr.descrizione_inglese("mod-ban")
        assert "it" not in carico["description_localizations"] and "fr" not in carico["description_localizations"]
        gestione = await bot.tree.get_command("admin-vocali").get_translated_payload(bot.tree, bot.tree.translator)
        assert gestione["name_localizations"]["en-US"] == "admin-voice"
        assert discord.Locale.italian.value == "it"
    finally:
        await _chiudi(creato_qui, bot)


async def test_l_impronta_della_sync_cambia_se_cambia_una_traduzione(monkeypatch):
    from core.command_sync import impronta_albero_tradotto

    creato_qui, bot = await _albero_vero()
    try:
        await bot.tree.set_translator(tr.TraduttoreYokai())
        comandi = bot.tree.get_commands()
        prima = await impronta_albero_tradotto(comandi, bot.tree)
        dati = tr.carica_traduzioni()
        monkeypatch.setitem(dati["descrizioni"], "mod-ban", "Another text.")
        assert await impronta_albero_tradotto(comandi, bot.tree) != prima
    finally:
        await _chiudi(creato_qui, bot)


async def test_parametri_tradotti_non_scendono_sotto_il_minimo():
    assert len(tr.carica_traduzioni(forza=True)["parametri"]) >= MINIMO_PARAMETRI_TRADOTTI


async def test_un_nome_tradotto_non_cambia_un_altro_comando_con_lo_stesso_nome():
    # La mappa dei nomi vale per ogni comando con quel nome: «pause» →
    # «cooldowns» (pensato per /level) rinominava anche /music pause.
    creato_qui, bot = await _albero_vero()
    try:
        nomi = {_percorso(n): _nome_en(n) for n in _tutti_i_nodi(_radici(bot))}
        assert nomi["music pause"] == "pause"
        assert nomi["monete attese"] == "cooldowns"
    finally:
        await _chiudi(creato_qui, bot)


async def test_i_nomi_tradotti_di_ogni_lingua_sono_validi_con_il_prefisso_dello_staff():
    """D58: in ogni lingua presente nomi validi per Discord, `admin-`/`mod-`/`founder` intatti, nessun duplicato tra fratelli."""
    creato_qui, bot = await _albero_vero()
    try:
        problemi = []
        nodi = list(_tutti_i_nodi(_radici(bot)))
        for lingua, sezioni in tr.carica_tutte(forza=True).items():
            if lingua == "it":
                continue
            for segmento, nome in sezioni["nomi"].items():
                if not tr.nome_valido(nome):
                    problemi.append(f"{lingua}: nome non valido {nome!r}")
                if segmento.startswith(tr.PREFISSI_NON_TRADOTTI) and tr.nome_tradotto(segmento, lingua) is None:
                    problemi.append(f"{lingua}: {segmento} -> {nome} cambia il prefisso")
            for padre in [None] + [n for n in nodi if isinstance(n, app_commands.Group)]:
                figli = _radici(bot) if padre is None else list(padre.commands)
                visti = collections.Counter(tr.nome_tradotto(f.name, lingua) or f.name for f in figli)
                problemi += [f"{lingua}: duplicato {nome}" for nome, n in visti.items() if n > 1]
            problemi += [f"{lingua}: descrizione oltre 100: {k}" for k, d in sezioni["descrizioni"].items() if len(d) > tr.MAX_DESCRIZIONE]
        assert problemi == []
    finally:
        await _chiudi(creato_qui, bot)

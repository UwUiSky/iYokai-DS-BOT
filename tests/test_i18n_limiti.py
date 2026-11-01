"""
tests/test_i18n_limiti.py
=========================
NF-06 (#77): ogni chiave del catalogo rispetta i limiti di Discord nella sua posizione
(titolo embed 256, nome campo 256, valore campo 1024, descrizione embed 4096, messaggio 2000),
in italiano e in inglese; ogni chiave usata nei cog esiste nel catalogo.
"""

import ast
import json
import pathlib

from core import i18n

RADICE = pathlib.Path(__file__).resolve().parent.parent
LIMITE_BASE = 2000
LIMITI_EMBED = {"title": 256, "description": 4096, "name": 256, "value": 1024}


def _catalogo(lingua):
    return json.loads((i18n.CARTELLA_LOCALES / f"{lingua}.json").read_text(encoding="utf-8"))


def _chiave_letterale(nodo):
    """La chiave se `nodo` e `[await] testo_per(x, "chiave", ...)` / `tr(...)`."""
    if isinstance(nodo, ast.Await):
        nodo = nodo.value
    if isinstance(nodo, ast.Call):
        nome = nodo.func.attr if isinstance(nodo.func, ast.Attribute) else getattr(nodo.func, "id", None)
        if nome == "testo_per" and len(nodo.args) >= 2:
            a = nodo.args[1]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                return a.value
    return None


def _usi():
    """{chiave: limite piu stretto} per ogni uso letterale di testo_per nei cog."""
    limiti = {}
    for percorso in (RADICE / "cogs").rglob("*.py"):
        albero = ast.parse(percorso.read_text(encoding="utf-8"))
        in_embed = set()
        for n in ast.walk(albero):
            if isinstance(n, ast.Call):
                nome = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None)
                if nome in ("Embed", "add_field"):
                    for k in n.keywords:
                        chiave = _chiave_letterale(k.value)
                        if chiave and k.arg in LIMITI_EMBED:
                            in_embed.add(id(k.value))
                            limiti[chiave] = min(limiti.get(chiave, 10**6), LIMITI_EMBED[k.arg] if nome == "Embed" or k.arg != "value" else 1024)
        for n in ast.walk(albero):
            chiave = _chiave_letterale(n) if isinstance(n, (ast.Await, ast.Call)) else None
            if chiave and id(n) not in in_embed and not _dentro_embed(n, in_embed):
                limiti.setdefault(chiave, LIMITE_BASE)
    return limiti


def _dentro_embed(nodo, in_embed):
    return id(nodo) in in_embed or (isinstance(nodo, ast.Await) and id(nodo.value) in in_embed)


def test_ogni_chiave_usata_nei_cog_esiste_nel_catalogo():
    it = _catalogo("it")
    mancanti = sorted(k for k in _usi() if k not in it)
    assert mancanti == []


def test_i_testi_rispettano_i_limiti_di_discord():
    cataloghi = {lingua: _catalogo(lingua) for lingua in i18n.LINGUE}
    troppo_lunghi = []
    for chiave, limite in _usi().items():
        for lingua, catalogo in cataloghi.items():
            if len(catalogo.get(chiave, "")) > limite:
                troppo_lunghi.append((chiave, lingua, len(catalogo[chiave]), limite))
    assert troppo_lunghi == []


def test_nessun_testo_del_catalogo_supera_il_massimo_assoluto():
    for lingua in i18n.LINGUE:
        lunghi = [k for k, v in _catalogo(lingua).items() if len(v) > 4096]
        assert lunghi == [], lingua

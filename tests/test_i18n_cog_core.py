"""
tests/test_i18n_cog_core.py
===========================
Cricchetto sulle lingue (SPEC 21.1): nei cog dell'area core nessuna risposta all'utente è una frase
italiana scritta nel codice; passa dal catalogo (`testo_per`). I comandi dell'owner restano in italiano.
"""

import ast
import pathlib
import re

FILE = [
    "cogs/utility/setup.py", "cogs/utility/_setup_wizard_views.py", "cogs/utility/config_history.py",
    "cogs/utility/premium_server.py", "cogs/utility/marchio.py", "cogs/utility/command_search.py",
    "cogs/user_app/personal.py", "cogs/user_app/strumenti.py", "cogs/utility/log_webhook.py",
    "cogs/user_app/messaggi.py", "cogs/user_app/risposte.py", "cogs/user_app/supporto.py",
    "cogs/user_app/impostazioni.py", "cogs/user_app/divertimento.py",
    "cogs/user_app/radio.py",
]
INVIO = {"send_message", "send", "edit_message", "edit", "edit_original_response"}
RADICE = pathlib.Path(__file__).resolve().parent.parent


def _testo(n):
    if isinstance(n, ast.Constant) and isinstance(n.value, str):
        return n.value
    if isinstance(n, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in n.values)
    return None


def test_nessuna_risposta_con_frase_scritta_nel_codice():
    trovate = []
    for nome in FILE:
        for nodo in ast.walk(ast.parse((RADICE / nome).read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) and nodo.func.attr in INVIO:
                for c in [*nodo.args[:1], *(k.value for k in nodo.keywords if k.arg == "content")]:
                    s = _testo(c)
                    if s and re.search(r"[a-zà-ù]{3}", s):
                        trovate.append(f"{nome}:{nodo.lineno}: {s[:60]!r}")
    assert trovate == [], "Frasi nel codice: spostale in locales/it.json e en.json: " + "; ".join(trovate)

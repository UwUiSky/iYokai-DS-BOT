"""
core/wiki_statica.py
====================
La wiki dei comandi come sito statico (issue #147, SPEC §24): una pagina per comando e un indice, generate
dall'albero dei comandi con gli stessi modelli del pannello. Il sito va servito dalla radice di un dominio
(`/wiki/...` e `/static/pannello.css`). Nessuna ricerca né accesso: sono solo del pannello vivo.
Funzioni coperte: SPEC §24, issue #147
Dipende da: pannello_web/templates/wiki.html e comando.html
"""

from __future__ import annotations

import pathlib
import shutil

import jinja2

CARTELLA = pathlib.Path(__file__).resolve().parent.parent / "pannello_web"
PERCORSO_VALIDO = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_- ")


def _ambiente() -> jinja2.Environment:
    return jinja2.Environment(loader=jinja2.FileSystemLoader(CARTELLA / "templates"), autoescape=True)


def cartella_del_comando(percorso: str) -> pathlib.PurePosixPath:
    """`mod ban` -> `wiki/mod/ban`. Un percorso con caratteri fuori da a-z, cifre, - e _ è rifiutato (ValueError)."""
    if not percorso or not set(percorso) <= PERCORSO_VALIDO or percorso.strip() != percorso or "  " in percorso:
        raise ValueError(f"percorso di comando non valido: {percorso!r}")
    return pathlib.PurePosixPath("wiki", *percorso.split(" "))


def genera(comandi, uscita: pathlib.Path) -> int:
    """Scrive il sito in `uscita` e ritorna quante pagine di comando ha fatto. Una pagina c'è per ogni comando."""
    uscita = pathlib.Path(uscita)
    ambiente = _ambiente()
    comuni = {"utente_id": None, "proprietario": False, "csrf": "", "messaggio": None, "errore": False, "statica": True}
    (uscita / "wiki").mkdir(parents=True, exist_ok=True)
    (uscita / "static").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CARTELLA / "static" / "pannello.css", uscita / "static" / "pannello.css")
    (uscita / "wiki" / "index.html").write_text(
        ambiente.get_template("wiki.html").render(comandi=comandi, q="", **comuni), encoding="utf-8"
    )
    modello = ambiente.get_template("comando.html")
    for c in comandi:
        cartella = uscita / cartella_del_comando(c.percorso)
        cartella.mkdir(parents=True, exist_ok=True)
        (cartella / "index.html").write_text(modello.render(c=c, **comuni), encoding="utf-8")
    return len(comandi)

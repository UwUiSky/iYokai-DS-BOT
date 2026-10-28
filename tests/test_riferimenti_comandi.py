"""
tests/test_riferimenti_comandi.py
=================================
Ogni `/comando sotto...` citato in una stringa o docstring di main.py,
cogs/ e core/ deve esistere nell'albero vero (tests/support/full_tree.py), o in quello
di un'istanza separata (NSFW, App).
Così un comando spostato non lascia messaggi con il nome vecchio.
Funzioni coperte: SPEC §20 (NF-05), F7 passo 4
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from discord import app_commands

from core.command_groups import GRUPPI
from tests.support.full_tree import build_full_bot, build_separate_trees, close_full_bot, connect_db_if_needed

RADICE = Path(__file__).resolve().parent.parent

# `/nome` (anche tra apici o virgolette; non preceduto da lettere, `/`, `<`, `:`, `.`, `@`) seguito da fino a 3 parole.
_RIFERIMENTO = re.compile(r"(?<![\w/<:.\-@#}])/([a-z][a-z0-9_-]*)(?![\w/])((?: [a-z][a-z0-9_-]*){0,3})")

# Parole italiane che, dopo un gruppo, iniziano la frase e non sono un sotto-comando.
_PAROLE_DI_FRASE = frozenset(
    "a al alla con da dal del della di e ed i il in la le lo nel nella nello o per se su un una "
    "non come che ma poi prima dopo anche solo senza quando dove".split()
)

# Riferimenti che non sono comandi del bot. Ogni voce ha il suo motivo.
ECCEZIONI: frozenset[str] = frozenset(
    {
        # segnaposto del modulo "richiedi comando": il nome che l'utente vorrebbe, non un comando vero
        "/esempio",
        "/esempio parametro",
        # percorsi delle pagine del pannello web (core/web_panel_server.py), non comandi
        "/accedi",
        "/callback",
        "/esci",
        "/wiki",
        "/marchio",
        "/aspetto",
        "/miei-dati",
        "/miei-inviti",
        "/inviti",
    }
)


def riferimenti_nel_codice() -> list[tuple[str, int, str]]:
    """(file, riga, riferimento grezzo) per ogni `/comando ...` nelle stringhe di main.py, cogs/ e core/."""
    trovati = []
    file = [RADICE / "main.py"] + [p for c in ("cogs", "core") for p in sorted((RADICE / c).rglob("*.py"))]
    for percorso in file:
        albero = ast.parse(percorso.read_text(encoding="utf-8"))
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
                for m in _RIFERIMENTO.finditer(nodo.value):
                    grezzo = "/" + m.group(1) + m.group(2)
                    riga = nodo.lineno + nodo.value.count("\n", 0, m.start())
                    trovati.append((str(percorso.relative_to(RADICE)), riga, grezzo))
    return trovati


def errore_del_riferimento(grezzo: str, radici: dict[str, object]) -> str | None:
    """None se il riferimento esiste nell'albero, altrimenti il motivo."""
    parole = grezzo[1:].split(" ")
    nodo = radici.get(parole[0])
    if nodo is None:
        return f"'/{parole[0]}' non è un comando di primo livello"
    percorso = [parole[0]]
    for parola in parole[1:]:
        if not isinstance(nodo, app_commands.Group):
            break  # dopo una foglia c'è prosa
        figlio = nodo.get_command(parola)
        if figlio is None:
            if parola in _PAROLE_DI_FRASE:
                break
            return f"'/{' '.join(percorso)}' non ha '{parola}'"
        nodo = figlio
        percorso.append(parola)
    return None


def test_il_riconoscitore_distingue_comandi_e_prosa():
    assert [g for _, _, g in _trovati_in("usa /admin setup attiva per attivarlo")] == ["/admin setup attiva per"]
    assert _trovati_in("vedi https://x.it/users/me e cogs/utility/setup.py") == []
    assert _trovati_in("percorso /guilds/123") == []
    assert [g for _, _, g in _trovati_in("Run `/admin setup attiva`.")] == ["/admin setup attiva"]
    assert [g for _, _, g in _trovati_in('scrivi "/setup" o \'/play\'')] == ["/setup", "/play"]


def _trovati_in(testo: str) -> list[tuple[str, int, str]]:
    return [("t", 0, "/" + m.group(1) + m.group(2)) for m in _RIFERIMENTO.finditer(testo)]


async def test_ogni_comando_citato_nei_messaggi_esiste_nell_albero():
    creato_qui = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti, f"Cog falliti nel caricamento: {falliti}"
        radici = {c.name: c for c in bot.tree.get_commands()}
        radici.setdefault("owner", GRUPPI["owner"])
        separati = await build_separate_trees()
        for altro in separati:  # istanze con un albero proprio (NSFW, App)
            radici.update({c.name: c for c in altro.tree.get_commands()})
            await altro.close()
        errori = []
        for file, riga, grezzo in riferimenti_nel_codice():
            if grezzo in ECCEZIONI:
                continue
            motivo = errore_del_riferimento(grezzo, radici)
            if motivo:
                errori.append(f"{file}:{riga} cita '{grezzo}': {motivo}")
        assert not errori, "Comandi citati che non esistono:\n" + "\n".join(errori)
    finally:
        await close_full_bot(bot)
        if creato_qui:
            from core.database import db as db_singleton

            await db_singleton.close()

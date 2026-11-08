"""
core/ticket_gestione_logic.py
=============================
Regole pure del menu «Gestisci» dei ticket: etichette colorate (TKT-068), spostamento in un altro pannello
(TKT-067) e articoli della base di conoscenza (TKT-079). Niente Discord, niente database.
Funzioni coperte: SPEC §13.23
"""

from __future__ import annotations

import re

from core.ticket_form_logic import ErroreConfigurazione
from core.ticket_standard_logic import Candidata, parole_chiave, parole_dal_testo_salvato, parole_di, trova_migliore

MAX_ETICHETTE = 25
MAX_NOME_ETICHETTA = 32
MAX_ARTICOLI = 200
MAX_TITOLO_ARTICOLO = 100
MAX_TESTO_ARTICOLO = 4000
MAX_PANNELLI_NEL_MENU = 24  # più una voce «Altri…» (25 voci)
VALORE_ALTRI = "altri"
COLORE_BASE = 0x5865F2
_ESADECIMALE = re.compile(r"^#?([0-9a-fA-F]{6})$")
_VALORE_ARTICOLO = re.compile(r"^a:(\d{1,10})$")


def etichetta_valida(nome: str) -> str:
    nome = (nome or "").strip()
    if not 1 <= len(nome) <= MAX_NOME_ETICHETTA:
        raise ErroreConfigurazione(f"Il nome dell'etichetta va da 1 a {MAX_NOME_ETICHETTA} caratteri.")
    return nome


def colore_valido(testo: str | None) -> int:
    """«#RRGGBB» (o senza #) come numero; vuoto = colore di base."""
    if not testo or not testo.strip():
        return COLORE_BASE
    trovato = _ESADECIMALE.match(testo.strip())
    if not trovato:
        raise ErroreConfigurazione("Il colore va scritto come #RRGGBB, per esempio #E67E22.")
    return int(trovato.group(1), 16)


def articolo_valido(titolo: str, testo: str) -> tuple[str, str]:
    titolo, testo = (titolo or "").strip(), (testo or "").strip()
    if not 1 <= len(titolo) <= MAX_TITOLO_ARTICOLO:
        raise ErroreConfigurazione(f"Il titolo va da 1 a {MAX_TITOLO_ARTICOLO} caratteri.")
    if not 1 <= len(testo) <= MAX_TESTO_ARTICOLO:
        raise ErroreConfigurazione(f"Il testo va da 1 a {MAX_TESTO_ARTICOLO} caratteri.")
    return titolo, testo


def parole_articolo(titolo: str, testo: str) -> str:
    """
    Parole chiave salvate con l'articolo: quelle del titolo (al massimo 6) e le 2 più ripetute nel testo.
    Poche, perché una richiesta breve deve poterne coprire almeno la metà (core.ticket_standard_logic).
    """
    parole = parole_di(titolo)[:6]
    parole += [p for p in parole_chiave(testo, 4) if p not in parole][:2]
    return ", ".join(parole)


def valore_articolo(articolo_id: int) -> str:
    """Valore di un suggerimento di completamento (≤ 100 caratteri): si passa l'ID, non il testo."""
    return f"a:{articolo_id}"


def id_articolo(testo: str | None) -> int | None:
    trovato = _VALORE_ARTICOLO.match((testo or "").strip())
    return int(trovato.group(1)) if trovato else None


def scegli_articolo(articoli, testo_richiesta: str):
    """L'articolo che risponde meglio al testo (o None). `articoli`: oggetti con id, parole (testo salvato), usi."""
    per_id = {a.id: a for a in articoli}
    candidate = [Candidata(a.id, frozenset(parole_dal_testo_salvato(a.parole)), a.usi) for a in articoli]
    scelta = trova_migliore(candidate, testo_richiesta)
    return per_id[scelta.id] if scelta else None


def voci_sposta(pannelli, corrente_id: int | None, altri: str = "Altri…") -> list[tuple[str, str]]:
    """(valore, etichetta) del menu «Sposta»: fino a 24 pannelli (escluso quello attuale) e «Altri…» se ce ne sono di più."""
    altri = [p for p in pannelli if p.id != corrente_id]
    voci = [(str(p.id), p.name[:100]) for p in altri[:MAX_PANNELLI_NEL_MENU]]
    if len(altri) > MAX_PANNELLI_NEL_MENU:
        voci.append((VALORE_ALTRI, altri[:100]))
    return voci


def applica_etichette(embed, etichette: list[tuple[str, int]], nome_campo: str) -> None:
    """Colora l'embed di benvenuto col colore della prima etichetta e ne scrive i nomi in un campo (≤ 1024)."""
    for i, campo in enumerate(list(embed.fields)):
        if campo.name == nome_campo:
            embed.remove_field(i)
            break
    if not etichette:
        return
    embed.color = etichette[0][1]
    if len(embed.fields) < 25:
        embed.add_field(name=nome_campo, value=" · ".join(n for n, _ in etichette)[:1024], inline=False)

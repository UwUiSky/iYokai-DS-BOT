"""
core/form_logic.py
==================
Domande, controllo e riepilogo dei moduli (NF-34). Funzioni pure, nessun Discord:
le usano il cog e (in futuro) il pannello web.
Limiti Discord: modale con 5 campi, titolo e etichette da 45, campo embed da 1024,
embed da 6000 in tutto.
Funzioni coperte: SPEC §23 (NF-34)
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_DOMANDE = 5
MAX_ETICHETTA = 45
MAX_TITOLO = 45
MAX_NOME = 32
MAX_RISPOSTA = 1024
MAX_MODULI = 10
MAX_VIEW_ALL_AVVIO = 2000  # candidature in attesa riattivate all'avvio (le più recenti)
SEPARATORE = "|"
PREFISSO_LUNGA = "+"

PENDING, ACCEPTED, REJECTED = "pending", "accepted", "rejected"


@dataclass(frozen=True)
class Domanda:
    etichetta: str
    lunga: bool = False

    def a_dict(self) -> dict:
        return {"label": self.etichetta, "long": self.lunga}

    @staticmethod
    def da_dict(d: dict) -> "Domanda":
        return Domanda(str(d["label"]), bool(d.get("long", False)))


def leggi_domande(testo: str) -> tuple[list[Domanda], str | None]:
    """'Nome|+Perché vuoi entrare?' -> domande; il '+' davanti vuol dire risposta lunga.
    Restituisce (domande, errore): se c'è un errore non si salva nulla."""
    pezzi = [p.strip() for p in testo.split(SEPARATORE)]
    pezzi = [p for p in pezzi if p]
    if not pezzi:
        return [], "Scrivi almeno una domanda."
    if len(pezzi) > MAX_DOMANDE:
        return [], f"Un modulo ha al massimo {MAX_DOMANDE} domande (Discord ne mostra al massimo 5 per finestra)."
    domande = []
    for p in pezzi:
        lunga = p.startswith(PREFISSO_LUNGA)
        etichetta = p[len(PREFISSO_LUNGA):].strip() if lunga else p
        if not etichetta:
            return [], "Una domanda è vuota."
        if len(etichetta) > MAX_ETICHETTA:
            return [], f"La domanda «{etichetta[:20]}…» supera i {MAX_ETICHETTA} caratteri."
        domande.append(Domanda(etichetta, lunga))
    return domande, None


def campi_riepilogo(domande: list[Domanda], risposte: list[str]) -> list[tuple[str, str]]:
    """Coppie (nome, valore) per l'embed: nomi da 256 al massimo, valori da 1024, mai vuoti."""
    campi = []
    for d, r in zip(domande, risposte):
        valore = (r or "").strip() or "—"
        campi.append((d.etichetta[:256], valore[:MAX_RISPOSTA]))
    return campi


def puo_decidere(stato: str) -> bool:
    return stato == PENDING

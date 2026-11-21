"""
core/ruoli_guidata_logic.py
===========================
Creazione guidata di un menu di ruoli, a passi (RUO-047): ordine dei passi, controllo di ciò che si scrive
e testo delle coppie «emoji ruolo» da passare al menu. Solo logica pura.
Funzioni coperte: SPEC RUO-047
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.role_menu_logic import MAX_COPPIE, valida_emoji

TEMPO_MASSIMO_SECONDI = 600  # la finestra guidata si chiude da sola dopo 10 minuti
MODALITA = ("button", "select", "reaction")
PASSI = ("modalita", "testo", "canale", "ruoli", "emoji", "conferma")


@dataclass
class StatoGuidato:
    autore_id: int
    modalita: str | None = None
    titolo: str | None = None
    descrizione: str = ""
    canale_id: int | None = None
    ruoli: list[int] = field(default_factory=list)
    emoji: list[str | None] = field(default_factory=list)
    emoji_fatte: bool = False

    def passo(self) -> str:
        """Il prossimo passo da fare. «emoji» si salta per le tendine (non servono) finché non si è scelto di metterle."""
        if self.modalita is None:
            return "modalita"
        if self.titolo is None:
            return "testo"
        if self.canale_id is None:
            return "canale"
        if not self.ruoli:
            return "ruoli"
        if self.modalita in ("reaction", "button") and not self.emoji_fatte:
            return "emoji"
        return "conferma"


def emoji_da_testo(testo: str, quanti: int, obbligatorie: bool) -> tuple[list[str | None], str | None]:
    """
    Un'emoji per riga, nell'ordine dei ruoli. Righe vuote = nessuna emoji (ammesso solo se non sono obbligatorie).
    Torna (emoji, errore in italiano).
    """
    righe = [r.strip() for r in (testo or "").splitlines()]
    while righe and not righe[-1]:
        righe.pop()
    if len(righe) > quanti:
        return [], f"Hai scritto {len(righe)} righe ma i ruoli sono {quanti}."
    righe += [""] * (quanti - len(righe))
    fuori: list[str | None] = []
    for numero, riga in enumerate(righe, start=1):
        if not riga:
            if obbligatorie:
                return [], f"Manca l'emoji della riga {numero}."
            fuori.append(None)
        elif not valida_emoji(riga):
            return [], f"La riga {numero} non è un'emoji valida."
        else:
            fuori.append(riga)
    return fuori, None


def coppie_in_testo(ruoli: list[int], emoji: list[str | None]) -> str:
    """Il testo «emoji <@&ruolo>; …» che il menu sa leggere (core/role_menu_logic.analizza_coppie)."""
    pezzi = []
    for numero, rid in enumerate(ruoli[:MAX_COPPIE]):
        e = emoji[numero] if numero < len(emoji) else None
        pezzi.append(f"{e} <@&{rid}>" if e else f"<@&{rid}>")
    return "; ".join(pezzi)

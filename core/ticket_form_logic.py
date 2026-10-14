"""
core/ticket_form_logic.py
=========================
Regole pure dei pannelli di ticket: domande del modulo, controllo delle
risposte, nomi dei pannelli di un messaggio, chiusura per inattività, voto.
Nessun accesso a Discord né al database: si prova senza server.
Funzioni coperte: SPEC §22 (NF-13)

Limiti rispettati (LIMITI.md §1.1 e §1.2): modulo con al massimo 5 campi,
etichetta del campo 45, segnaposto 100, risposta fino a 1000 caratteri (così
sta in un campo di embed da 1024); bottone con etichetta fino a 80; 25 bottoni
per messaggio (5 per riga, 5 righe); custom_id fino a 100.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

MAX_DOMANDE = 5
MAX_ETICHETTA_DOMANDA = 45
MAX_SEGNAPOSTO = 100
MAX_RISPOSTA_BREVE = 200
MAX_RISPOSTA_LUNGA = 1000
MAX_TITOLO_MODULO = 45

MAX_PANNELLI_PER_SERVER = 25
MAX_NOME_PANNELLO = 50
MAX_ETICHETTA_BOTTONE = 80
MAX_TESTO_BENVENUTO = 1000
MAX_BOTTONI_PER_MESSAGGIO = 25

MIN_MINUTI_CHIUSURA = 5
MAX_MINUTI_CHIUSURA = 43200  # 30 giorni

STELLE_MIN = 1
STELLE_MAX = 5

# Discord: 6000 caratteri in tutto per embed. Alle risposte ne spettano 4800: il resto è del
# titolo, della categoria e del testo di benvenuto (che comunque si accorcia se serve).
_MAX_CARATTERI_EMBED = 4800


class ErroreConfigurazione(ValueError):
    """Un valore scelto da un amministratore non rispetta un limite: il testo è per lui."""


def _taglia(testo: str, massimo: int) -> str:
    testo = testo.strip()
    if len(testo) <= massimo:
        return testo
    return testo[: massimo - 1].rstrip() + "…"


def nome_pannello_valido(nome: str) -> str:
    """Nome breve e senza spazi di troppo; è la chiave con cui lo staff sceglie il pannello."""
    pulito = " ".join(nome.split())
    if not pulito:
        raise ErroreConfigurazione("Il nome del pannello non può essere vuoto.")
    if "," in pulito:
        raise ErroreConfigurazione("Il nome del pannello non può contenere virgole.")
    if len(pulito) > MAX_NOME_PANNELLO:
        raise ErroreConfigurazione(f"Il nome del pannello può avere al massimo {MAX_NOME_PANNELLO} caratteri.")
    return pulito


def etichetta_bottone(testo: str) -> str:
    """Etichetta del bottone sempre accettata da Discord (1..80 caratteri)."""
    return _taglia(testo, MAX_ETICHETTA_BOTTONE) or "Apri ticket"


def domanda_valida(etichetta: str, segnaposto: str | None) -> tuple[str, str | None]:
    """Controlla etichetta (45) e segnaposto (100) di una domanda del modulo."""
    pulita = " ".join(etichetta.split())
    if not pulita:
        raise ErroreConfigurazione("La domanda non può essere vuota.")
    if len(pulita) > MAX_ETICHETTA_DOMANDA:
        raise ErroreConfigurazione(
            f"La domanda può avere al massimo {MAX_ETICHETTA_DOMANDA} caratteri (limite di Discord)."
        )
    if segnaposto is not None:
        segnaposto = segnaposto.strip() or None
    if segnaposto is not None and len(segnaposto) > MAX_SEGNAPOSTO:
        raise ErroreConfigurazione(f"Il suggerimento può avere al massimo {MAX_SEGNAPOSTO} caratteri.")
    return pulita, segnaposto


def minuti_chiusura_validi(minuti: int) -> int | None:
    """0 spegne la chiusura automatica (None); altrimenti da 5 minuti a 30 giorni."""
    if minuti == 0:
        return None
    if not MIN_MINUTI_CHIUSURA <= minuti <= MAX_MINUTI_CHIUSURA:
        raise ErroreConfigurazione(
            f"La chiusura automatica va da {MIN_MINUTI_CHIUSURA} minuti a {MAX_MINUTI_CHIUSURA} "
            "(30 giorni); 0 la spegne."
        )
    return minuti


def titolo_modulo(nome_pannello: str) -> str:
    """Titolo della finestra: massimo 45 caratteri."""
    return _taglia(nome_pannello, MAX_TITOLO_MODULO) or "Apri un ticket"


def lunghezza_massima_risposta(lunga: bool) -> int:
    return MAX_RISPOSTA_LUNGA if lunga else MAX_RISPOSTA_BREVE


def campi_risposte(domande, risposte: list[str]) -> list[tuple[str, str]]:
    """
    Coppie (nome campo, valore) per l'embed di benvenuto del ticket. Le risposte
    vuote di domande facoltative si saltano; ogni testo è tagliato ai limiti di un
    campo (256/1024) e il totale resta sotto il limite dell'embed.
    """
    coppie: list[tuple[str, str]] = []
    for domanda, risposta in zip(domande, risposte):
        risposta = (risposta or "").strip()
        if risposta:
            coppie.append((_taglia(domanda.label, 256), _taglia(risposta, 1024)))
    if not coppie:
        return []
    # Se non stanno tutte nel budget, ogni risposta si accorcia in parti uguali: nessuna va persa.
    if sum(len(n) + len(v) for n, v in coppie) > _MAX_CARATTERI_EMBED:
        per_valore = max(50, (_MAX_CARATTERI_EMBED - sum(len(n) for n, _ in coppie)) // len(coppie))
        coppie = [(n, _taglia(v, per_valore)) for n, v in coppie]
    return coppie


def risposte_mancanti(domande, risposte: list[str]) -> list[str]:
    """Etichette delle domande obbligatorie rimaste senza risposta."""
    return [
        d.label for d, r in zip(domande, risposte) if d.required and not (r or "").strip()
    ]


def nomi_da_elenco(testo: str) -> list[str]:
    """«Supporto, Candidature» -> ["Supporto", "Candidature"]; senza doppioni, ordine mantenuto."""
    visti: dict[str, str] = {}
    for pezzo in testo.split(","):
        nome = " ".join(pezzo.split())
        if nome and nome.casefold() not in visti:
            visti[nome.casefold()] = nome
    return list(visti.values())


def righe_di_bottoni(quanti: int) -> list[int]:
    """Quanti bottoni per riga (5 al massimo). Oltre 25 solleva ErroreConfigurazione."""
    if quanti > MAX_BOTTONI_PER_MESSAGGIO:
        raise ErroreConfigurazione(
            f"Un messaggio può avere al massimo {MAX_BOTTONI_PER_MESSAGGIO} pannelli."
        )
    righe = [5] * (quanti // 5)
    if quanti % 5:
        righe.append(quanti % 5)
    return righe


# ---------------------------------------------------------------- chiusura automatica
def prossimo_controllo(
    ultima_attivita: datetime, adesso: datetime, minuti: int
) -> datetime | None:
    """
    Quando riguardare un ticket con chiusura automatica. None = va chiuso adesso
    (fermo da almeno `minuti`); altrimenti l'istante in cui scadrebbe se nessuno
    scrive più. L'attività è l'ultimo messaggio o, se manca, la creazione.
    """
    scadenza = ultima_attivita + timedelta(minutes=minuti)
    if scadenza <= adesso:
        return None
    return scadenza


# ---------------------------------------------------------------- voto
def voto_valido(stelle: int) -> int:
    if not STELLE_MIN <= stelle <= STELLE_MAX:
        raise ErroreConfigurazione(f"Il voto va da {STELLE_MIN} a {STELLE_MAX}.")
    return stelle


def testo_stelle(stelle: int) -> str:
    return "⭐" * stelle


def custom_id_voto(ticket_id: int, stelle: int) -> str:
    return f"tkt:voto:{ticket_id}:{stelle}"


def custom_id_pannello(panel_id: int) -> str:
    return f"tkt:pan:{panel_id}"


@dataclass(frozen=True)
class Media:
    """Media dei voti di un server."""

    media: float | None
    voti: int

    def testo(self) -> str:
        if self.media is None:
            return "nessun voto"
        return f"{self.media:.1f}/5 ({self.voti} voti)"

"""
core/ticket_form_logic.py
=========================
Regole pure dei pannelli di ticket: domande del modulo, controllo delle
risposte, nomi dei pannelli di un messaggio, chiusura per inattività, voto.
Nessun accesso a Discord né al database: si prova senza server.
Funzioni coperte: SPEC §22 (NF-13), TKT-002 (bottoni per riga), TKT-004 (colore del bottone),
TKT-011 (minimo e massimo), TKT-012 (campi a scelta), TKT-036 (segnaposto del benvenuto)

Limiti rispettati (LIMITI.md §1.1 e §1.2): modulo con al massimo 5 campi,
etichetta del campo 45, segnaposto 100, risposta fino a 1000 caratteri (così
sta in un campo di embed da 1024); bottone con etichetta fino a 80; 25 bottoni
per messaggio (5 per riga, 5 righe); custom_id fino a 100.
"""

from __future__ import annotations

import re
import unicodedata
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


def righe_di_bottoni(quanti: int, per_riga: int = 5) -> list[int]:
    """
    Quanti bottoni in ogni riga (TKT-002: `per_riga` da 1 a 5). Oltre 25 bottoni, o oltre 5 righe,
    solleva ErroreConfigurazione.
    """
    if not 1 <= per_riga <= 5:
        raise ErroreConfigurazione("I bottoni per riga vanno da 1 a 5.")
    if quanti > MAX_BOTTONI_PER_MESSAGGIO:
        raise ErroreConfigurazione(
            f"Un messaggio può avere al massimo {MAX_BOTTONI_PER_MESSAGGIO} pannelli."
        )
    righe = [per_riga] * (quanti // per_riga)
    if quanti % per_riga:
        righe.append(quanti % per_riga)
    if len(righe) > 5:
        raise ErroreConfigurazione(
            f"Con {per_riga} bottoni per riga stanno al massimo {per_riga * 5} pannelli in un messaggio (5 righe)."
        )
    return righe


# ---------------------------------------------------------------- TKT-004: colore del bottone
STILI_BOTTONE = {"blu": "primary", "grigio": "secondary", "verde": "success", "rosso": "danger"}


def stile_bottone(nome: str) -> str:
    """Il colore scelto (blu, grigio, verde, rosso) come nome di Discord; uno sconosciuto è un errore."""
    try:
        return STILI_BOTTONE[(nome or "").strip().lower()]
    except KeyError:
        raise ErroreConfigurazione("Il colore del bottone è blu, grigio, verde o rosso.") from None


# ---------------------------------------------------------------- TKT-011, TKT-012: campi del modulo
TIPI_CAMPO = ("testo", "scelta", "utente", "ruolo", "canale")
MAX_RISPOSTA_CAMPO = 4000  # limite di Discord per un campo di testo
MAX_OPZIONI_SCELTA = 25
MAX_OPZIONE = 100


def limiti_testo(minimo: int | None, massimo: int | None) -> tuple[int | None, int | None]:
    """Minimo e massimo di caratteri di una risposta (0-4000); il minimo non supera il massimo."""
    if minimo is not None and not 0 <= minimo <= MAX_RISPOSTA_CAMPO:
        raise ErroreConfigurazione(f"Il minimo va da 0 a {MAX_RISPOSTA_CAMPO} caratteri.")
    if massimo is not None and not 1 <= massimo <= MAX_RISPOSTA_CAMPO:
        raise ErroreConfigurazione(f"Il massimo va da 1 a {MAX_RISPOSTA_CAMPO} caratteri.")
    if minimo is not None and massimo is not None and minimo > massimo:
        raise ErroreConfigurazione("Il minimo non può superare il massimo.")
    return (minimo or None), massimo


def opzioni_scelta(testo: str | None) -> tuple[str, ...]:
    """Le voci di un campo a scelta, separate da punto e virgola: da 2 a 25, ognuna fino a 100 caratteri, senza doppioni."""
    viste: dict[str, str] = {}
    for pezzo in (testo or "").split(";"):
        voce = " ".join(pezzo.split())
        if voce:
            viste.setdefault(voce.casefold(), voce)
    voci = tuple(viste.values())
    if len(voci) < 2:
        raise ErroreConfigurazione("Un campo a scelta ha almeno 2 voci, separate da punto e virgola.")
    if len(voci) > MAX_OPZIONI_SCELTA:
        raise ErroreConfigurazione(f"Un campo a scelta ha al massimo {MAX_OPZIONI_SCELTA} voci.")
    if any(len(v) > MAX_OPZIONE for v in voci):
        raise ErroreConfigurazione(f"Ogni voce ha al massimo {MAX_OPZIONE} caratteri.")
    return voci


def lunghezza_minima_massima(domanda) -> tuple[int, int]:
    """(minimo, massimo) effettivi di un campo di testo: senza scelta valgono 0 e il tetto di prima (200 o 1000)."""
    minimo = getattr(domanda, "min_length", None) or 0
    tetto = getattr(domanda, "max_length", None) or lunghezza_massima_risposta(domanda.long_answer)
    return minimo, max(tetto, minimo)  # un minimo sopra il tetto di prima alza il tetto: Discord rifiuta una finestra incoerente


def risposte_fuori_misura(domande, risposte: list[str]) -> list[str]:
    """Etichette delle domande di testo la cui risposta (se c'è) è sotto il minimo o sopra il massimo."""
    fuori = []
    for d, r in zip(domande, risposte):
        r = (r or "").strip()
        if getattr(d, "tipo", "testo") != "testo" or not r:
            continue
        minimo, massimo = lunghezza_minima_massima(d)
        if not minimo <= len(r) <= massimo:
            fuori.append(d.label)
    return fuori


def scelte_non_ammesse(domande, risposte_grezze: list[list[str] | None]) -> list[str]:
    """Etichette dei campi a scelta con un valore che non è fra le voci del campo (un invio manipolato)."""
    return [
        d.label
        for d, valori in zip(domande, risposte_grezze)
        if getattr(d, "tipo", "testo") == "scelta" and valori and any(v not in d.opzioni for v in valori)
    ]


# ---------------------------------------------------------------- TKT-036: segnaposto del benvenuto
SEGNAPOSTI_BENVENUTO = ("utente", "nome", "server", "numero", "pannello", "staff")
_SEGNAPOSTO = re.compile(r"\{(" + "|".join(SEGNAPOSTI_BENVENUTO) + r")\}")
_VIETATI_NEI_NOMI = set("`[]()<>*_~|\\@#")


def nome_sicuro(nome: str, massimo: int = 32) -> str:
    """Un nome scelto da un utente (o un titolo di pannello) reso innocuo dentro un testo: niente caratteri di
    controllo o invisibili, niente segni che aprono link mascherati, blocchi di codice, menzioni o formattazione."""
    pulito = "".join(
        c for c in nome
        if c.isprintable() and unicodedata.category(c) not in ("Cf", "Cc", "Zl", "Zp") and c not in _VIETATI_NEI_NOMI
    )
    return " ".join(pulito.split())[:massimo]


def testo_benvenuto(modello: str, valori: dict[str, str], massimo: int = 4000) -> str:
    """
    Il benvenuto con i segnaposto {utente} (menzione), {nome}, {server}, {numero}, {pannello}, {staff} (solo risposte pronte). Solo questi
    sono sostituiti, con un'unica passata (mai str.format): un valore che contiene a sua volta «{utente}» non
    viene sostituito di nuovo. Gli altri segnaposto restano scritti come sono.
    """
    return _SEGNAPOSTO.sub(lambda m: valori.get(m.group(1), m.group(0)), modello)[:massimo]


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


# ----------------------------------------------------------------------
# TKT-006: motivi pronti del pannello
# ----------------------------------------------------------------------
MAX_MOTIVI = 24  # più «Altro» = 25 voci, il tetto di un menu di Discord
MAX_ETICHETTA_MOTIVO = 80
MAX_TESTO_MOTIVO = 512
VALORE_ALTRO = "altro"


def motivo_valido(etichetta: str, testo: str | None) -> tuple[str, str | None]:
    """Etichetta (1–80) e testo (≤ 512, facoltativo) di un motivo pronto."""
    etichetta = (etichetta or "").strip()
    testo = (testo or "").strip() or None
    if not 1 <= len(etichetta) <= MAX_ETICHETTA_MOTIVO:
        raise ErroreConfigurazione(f"L'etichetta del motivo va da 1 a {MAX_ETICHETTA_MOTIVO} caratteri.")
    if testo is not None and len(testo) > MAX_TESTO_MOTIVO:
        raise ErroreConfigurazione(f"Il testo del motivo è lungo al massimo {MAX_TESTO_MOTIVO} caratteri.")
    return etichetta, testo


MAX_DESCRIZIONE_VOCE = 100  # TKT-005: la riga grigia di una voce di menu (limite di Discord)


def opzioni_motivi(motivi, altro: str = "Altro") -> list[tuple[str, str, str | None, str | None]]:
    """(valore, etichetta, emoji, descrizione) delle voci del menu: i motivi (valore = id) e in fondo «Altro» (testo del catalogo)."""
    voci = [
        (str(m.id), m.etichetta[:MAX_ETICHETTA_MOTIVO], m.emoji, (getattr(m, "descrizione", None) or "").strip()[:MAX_DESCRIZIONE_VOCE] or None)
        for m in list(motivi)[:MAX_MOTIVI]
    ]
    voci.append((VALORE_ALTRO, altro[:MAX_ETICHETTA_MOTIVO], None, None))
    return voci

"""
core/ticket_standard_logic.py
=============================
Parte senza AI di #139 (AI-R-104, AI-R-105): risposte standard imparate dallo
staff e sollecito dopo N minuti. Qui solo regole pure: parole chiave, ricerca
per parole tra le risposte salvate, scelta della coppia domanda/risposta,
limiti. Quando arriverà la parte AI (dev-ai) sostituirà l'estrazione e la
ricerca; i dati e i bottoni restano questi. Con l'AI ferma funziona già così.
Funzioni coperte: SPEC §25.97, §25.98
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

MAX_TITOLO = 100
MAX_CORPO = 2000
MAX_PAROLE_TESTO = 300
MAX_PAROLE = 20
MAX_ALLEGATI = 5
MAX_BYTE_ALLEGATO = 8 * 1024 * 1024
MAX_BYTE_TOTALI = 10 * 1024 * 1024  # LIM-55: tutto il messaggio sotto i 10 MiB
MAX_RISPOSTE_PER_SERVER = 200

MIN_MINUTI_SOLLECITO = 1
MAX_MINUTI_SOLLECITO = 1440
MINUTI_SOLLECITO_PREDEFINITI = 10

# Una risposta scatta se condivide almeno 2 parole (1 se ne ha una sola) e almeno metà delle sue.
SOGLIA_FRAZIONE = 0.5
MIN_PAROLE_CONDIVISE = 2

_LUNGHEZZA_RADICE = 6

STOPWORDS = frozenset(
    """
    il lo la i gli le un uno una di a da in con su per tra fra e ed o ma se che chi cui non
    del dello della dei degli delle al allo alla ai agli alle dal dallo dalla dai dagli dalle
    nel nello nella nei negli nelle sul sullo sulla sui sugli sulle
    mi ti ci vi si ho hai ha abbiamo avete hanno sono sei siamo siete essere avere fare fatto
    vorrei volevo vorremmo posso puoi puo potete potrei come cosa quando dove perche perché
    questo questa questi queste quello quella quelli quelle mio mia miei mie tuo tua suo sua
    ciao salve buongiorno buonasera grazie prego scusa scusate per favore please help aiuto
    the and for you your with that this have from are was but not can how what when where
    """.split()
)

_TOKEN = re.compile(r"[a-z0-9]+")
_SEPARATORI = re.compile(r"[,;\n]+")


def _senza_accenti(testo: str) -> str:
    return unicodedata.normalize("NFKD", testo).encode("ascii", "ignore").decode()


def radice(parola: str) -> str:
    """Radice grezza: le prime lettere. «affiliazione» e «affiliare» danno la stessa."""
    return parola[:_LUNGHEZZA_RADICE]


def parole_di(testo: str) -> list[str]:
    """Parole significative di un testo (radici, senza doppioni di forma, in ordine di comparsa)."""
    viste: dict[str, None] = {}
    for token in _TOKEN.findall(_senza_accenti(testo.lower())):
        if len(token) < 3 or token in STOPWORDS or token.isdigit():
            continue
        viste.setdefault(radice(token), None)
    return list(viste)


def parole_chiave(testo: str, massimo: int = 12) -> list[str]:
    """Le parole che descrivono la richiesta: le più ripetute, a parità le prime scritte."""
    contate: Counter[str] = Counter()
    ordine: dict[str, int] = {}
    for token in _TOKEN.findall(_senza_accenti(testo.lower())):
        if len(token) < 3 or token in STOPWORDS or token.isdigit():
            continue
        r = radice(token)
        contate[r] += 1
        ordine.setdefault(r, len(ordine))
    migliori = sorted(contate, key=lambda r: (-contate[r], ordine[r]))
    return migliori[:massimo]


def parole_da_testo_staff(testo: str) -> list[str]:
    """Le parole chiave scritte (o corrette) dallo staff: separate da virgola o a capo, senza doppioni, al massimo 20."""
    trovate: dict[str, None] = {}
    for pezzo in _SEPARATORI.split(testo):
        for r in parole_di(pezzo):
            trovate.setdefault(r, None)
    return list(trovate)[:MAX_PAROLE]


def parole_come_testo(parole: list[str]) -> str:
    return ", ".join(parole)


def parole_dal_testo_salvato(testo: str) -> set[str]:
    return {p for p in (x.strip() for x in testo.split(",")) if p}


def punteggio(parole_richiesta: set[str], parole_risposta: set[str]) -> tuple[int, float]:
    """(parole in comune, frazione delle parole della risposta trovate nella richiesta)."""
    if not parole_risposta:
        return 0, 0.0
    comuni = len(parole_richiesta & parole_risposta)
    return comuni, comuni / len(parole_risposta)


def corrisponde(parole_richiesta: set[str], parole_risposta: set[str]) -> bool:
    comuni, frazione = punteggio(parole_richiesta, parole_risposta)
    minimo = min(MIN_PAROLE_CONDIVISE, len(parole_risposta))
    return comuni >= max(1, minimo) and frazione >= SOGLIA_FRAZIONE


@dataclass(frozen=True)
class Candidata:
    id: int
    parole: frozenset[str]
    usi: int = 0


def trova_migliore(candidate: list[Candidata], testo_richiesta: str) -> Candidata | None:
    """La risposta salvata che meglio risponde al testo, o None. Parità: più parole in comune, poi la più usata."""
    richiesta = set(parole_di(testo_richiesta))
    if not richiesta:
        return None
    migliore: tuple | None = None
    scelta: Candidata | None = None
    for c in candidate:
        if not corrisponde(richiesta, set(c.parole)):
            continue
        comuni, frazione = punteggio(richiesta, set(c.parole))
        chiave = (frazione, comuni, c.usi, -c.id)
        if migliore is None or chiave > migliore:
            migliore, scelta = chiave, c
    return scelta


@dataclass(frozen=True)
class MessaggioStorico:
    autore_id: int
    bot: bool
    testo: str
    allegati: int


@dataclass(frozen=True)
class Coppia:
    richiesta: str
    indice_risposta: int  # posizione del messaggio dello staff nella lista


def scegli_coppia(messaggi: list[MessaggioStorico], aperto_da: int) -> Coppia | None:
    """
    Dalla storia del ticket: la prima richiesta scritta da chi lo ha aperto e la prima
    risposta di una persona diversa (non un bot) con testo o allegati. None se manca una delle due.
    """
    richiesta_parti: list[str] = []
    for i, m in enumerate(messaggi):
        if m.bot:
            continue
        if m.autore_id == aperto_da:
            if m.testo.strip():
                richiesta_parti.append(m.testo.strip())
            continue
        if m.testo.strip() or m.allegati:
            if not richiesta_parti:
                return None  # lo staff ha scritto per primo: non c'è una richiesta a cui rispondere
            return Coppia(" ".join(richiesta_parti), i)
    return None


def titolo_da(testo: str) -> str:
    una_riga = " ".join(testo.split())
    if len(una_riga) <= 60:
        return una_riga or "Risposta standard"
    return una_riga[:59].rstrip() + "…"


def taglia(testo: str, massimo: int) -> str:
    testo = testo.strip()
    return testo if len(testo) <= massimo else testo[: massimo - 1].rstrip() + "…"


def allegati_da_scaricare(dimensioni: list[int]) -> list[int]:
    """Indici degli allegati da copiare: al massimo 5, ognuno sotto 8 MiB, in tutto sotto 10 MiB."""
    scelti: list[int] = []
    totale = 0
    for i, peso in enumerate(dimensioni):
        if len(scelti) >= MAX_ALLEGATI:
            break
        if peso > MAX_BYTE_ALLEGATO or totale + peso > MAX_BYTE_TOTALI:
            continue
        scelti.append(i)
        totale += peso
    return scelti


def minuti_sollecito_validi(minuti: int) -> int | None:
    """0 spegne il sollecito (None)."""
    if minuti == 0:
        return None
    if not MIN_MINUTI_SOLLECITO <= minuti <= MAX_MINUTI_SOLLECITO:
        raise ValueError(
            f"Il sollecito va da {MIN_MINUTI_SOLLECITO} minuto a {MAX_MINUTI_SOLLECITO} minuti (24 ore); 0 lo spegne."
        )
    return minuti


def custom_id_bottone(azione: str, reply_id: int) -> str:
    return f"tkt:std:{azione}:{reply_id}"


# ----------------------------------------------------------------------
# Dati personali: né nel titolo, né nelle parole, né nel corpo approvato
# ----------------------------------------------------------------------
SEGNAPOSTO_UTENTE = "{utente}"
_MENZIONE_UTENTE = re.compile(r"<@!?\d+>")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_LINK = re.compile(r"https?://\S+")
# Telefoni, carte, codici: almeno 6 cifre, anche separate da UNO spazio, punto, trattino o parentesi.
_NUMERO_LUNGO = re.compile(r"\+?\d(?:[\s.\-()]?\d){5,}")
# IBAN: due lettere, due cifre, poi gruppi da 3-4 caratteri (con o senza spazi).
_IBAN = re.compile(r"\b[A-Za-z]{2}\d{2}(?:\s?[A-Za-z0-9]{3,4}){3,8}\b")


def senza_dati_personali(testo: str, nomi: tuple[str, ...] = ()) -> str:
    """Il testo di una richiesta senza menzioni, e-mail, link, numeri lunghi e nomi dell'utente."""
    testo = _MENZIONE_UTENTE.sub(" ", testo)
    testo = _EMAIL.sub(" ", testo)
    testo = _LINK.sub(" ", testo)
    testo = _IBAN.sub(" ", testo)
    testo = _NUMERO_LUNGO.sub(" ", testo)
    for nome in nomi:
        if len(nome) >= 3:
            testo = re.sub(re.escape(nome), " ", testo, flags=re.IGNORECASE)
    return " ".join(testo.split())


def corpo_con_segnaposto(testo: str, nomi: tuple[str, ...] = ()) -> str:
    """Il corpo scritto dallo staff: la menzione e il nome dell'utente diventano {utente}, le e-mail spariscono."""
    testo = _MENZIONE_UTENTE.sub(SEGNAPOSTO_UTENTE, testo)
    testo = _EMAIL.sub("[email]", testo)
    testo = _IBAN.sub("[codice]", testo)
    testo = _NUMERO_LUNGO.sub("[numero]", testo)
    for nome in nomi:
        if len(nome) >= 3:
            testo = re.sub(re.escape(nome), SEGNAPOSTO_UTENTE, testo, flags=re.IGNORECASE)
    return testo


def corpo_per_utente(corpo: str, user_id: int) -> str:
    """Al momento dell'uso: {utente} diventa la menzione di chi ha aperto il ticket."""
    return corpo.replace(SEGNAPOSTO_UTENTE, f"<@{user_id}>")


def nomi_dell_utente(*nomi) -> tuple[str, ...]:
    """Il nome intero e ogni sua parola (da 3 lettere in su): da togliere da titolo, parole e corpo."""
    trovati: dict[str, None] = {}
    for nome in nomi:
        if not isinstance(nome, str):
            continue
        trovati.setdefault(nome.strip(), None)
        for parte in re.split(r"[\s_.\-]+", nome):
            trovati.setdefault(parte, None)
    return tuple(n for n in trovati if len(n) >= 3)

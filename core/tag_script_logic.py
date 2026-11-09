"""
core/tag_script_logic.py
========================
Motore degli script dei tag (B25-B26): un linguaggio piccolo dentro il testo del tag, come
`{se:{x}>3|grande|piccolo}`. Interprete nostro: niente `eval`, niente `exec`, niente moduli di
terzi per i modelli; nessun accesso a rete, file o oggetti Python. Tetti su passi, profondità,
uscita, variabili, tempo e scritture; le espressioni regolari passano da re2 (tempo lineare).
Funzioni coperte: SPEC §22 (NF-09), UTL-027..032
Dipende da: user_app_strumenti (calcolatrice con AST sicuro), google-re2
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Callable

import discord

from core.user_app_strumenti import ErroreStrumento, calcola

MAX_SCRIPT = 4000       # lunghezza dello script (come il testo del tag)
MAX_OPERAZIONI = 200    # chiamate, letture e confronti per esecuzione
MAX_PROFONDITA = 10     # graffe dentro graffe
MAX_USCITA = 4000       # il testo finale (esce in due messaggi se oltre 2.000)
MAX_VALORE = 2000       # ogni valore intermedio e ogni variabile
MAX_VARIABILI = 50
MAX_RIPETIZIONI = 50
MAX_REGEX = 100
MAX_TEMPO = 1.0         # secondi
MAX_SCRITTURE = 10      # {dati:set|del} per esecuzione
MAX_INTERVALLO = 10**9
MAX_VALORE_DATO = 1024  # byte, per chiave
MAX_CHIAVI = 1000       # per server (Premium: MAX_CHIAVI_PREMIUM)
MAX_CHIAVI_PREMIUM = 5000
MAX_CHIAVI_AUTORE = 200  # per chi ha creato il tag (lo staff non ha questo tetto)
CHIAVE_DATI = re.compile(r"^[a-z0-9_.-]{1,64}$")
AZIONI_DATI = {"get": "get", "leggi": "get", "set": "set", "scrivi": "set", "imposta": "set", "del": "del", "togli": "del",
               "elimina": "del", "cancella": "del"}
MAX_TRA = 365 * 86400

DA_UTENTI = frozenset({"args", "username"})  # testo scritto da chi usa il tag: le menzioni restano inerti
_NOME_VAR = re.compile(r"^[a-z_][a-z0-9_]{0,31}$")
_NOME_FUNZIONE = re.compile(r"^[a-zà-ÿ_]{1,16}$")

# nome -> funzione canonica (italiano con alias inglesi)
ALIAS: dict[str, str] = {}
for _canonico, _alias in {
    "se": ("if",), "e": ("and",), "o": ("or",), "non": ("not",), "var": ("set", "imposta"),
    "lista": ("list", "scegli", "choice"), "calcola": ("calc", "math"), "caso": ("random", "rand"),
    "maiuscolo": ("upper",), "minuscolo": ("lower",), "titolo": ("title",), "sostituisci": ("replace",),
    "regex": (), "data": ("date",), "tra": ("in",), "lunghezza": ("len", "length"), "ripeti": ("repeat",),
    "dati": ("store", "db"),
}.items():
    ALIAS[_canonico] = _canonico
    for _a in _alias:
        ALIAS[_a] = _canonico

_GIORNI = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
_MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
         "ottobre", "novembre", "dicembre")
_UNITA_TRA = {"s": 1, "m": 60, "min": 60, "h": 3600, "ore": 3600, "g": 86400, "d": 86400, "sett": 604800, "w": 604800}
_VERO_NO = {"", "0", "false", "no", "falso"}


class ErroreScript(Exception):
    """`chiave`: la chiave del messaggio per l'utente (locales); `dettaglio`: testo breve per il registro degli errori."""

    def __init__(self, chiave: str, dettaglio: str = "") -> None:
        super().__init__(chiave)
        self.chiave = chiave
        self.dettaglio = dettaglio


@dataclass
class Contesto:
    """Quello che lo script può vedere: valori fissi, ora, caso, e (B26) l'archivio dei dati del server."""

    valori: dict[str, str] = field(default_factory=dict)
    adesso: datetime = field(default_factory=lambda: datetime.now().astimezone())
    rng: random.Random = field(default_factory=random.Random)
    orologio: Callable[[], float] = time.monotonic
    tempo_max: float = MAX_TEMPO
    archivio: object | None = None  # ha get(chiave), set(chiave, valore), delete(chiave): tutte async


@dataclass
class Risultato:
    testo: str
    errore: ErroreScript | None = None
    operazioni: int = 0
    variabili: dict[str, str] = field(default_factory=dict)


class ArchivioMemoria:
    """Dati in memoria (per i test e come base della prova). Stessa interfaccia dell'archivio su database."""

    def __init__(self, dati: dict[str, str] | None = None, massimo: int = MAX_CHIAVI) -> None:
        self.dati = dict(dati or {})
        self.massimo = massimo

    async def get(self, chiave: str) -> str | None:
        return self.dati.get(chiave)

    async def set(self, chiave: str, valore: str) -> None:
        if chiave not in self.dati and len(self.dati) >= self.massimo:
            raise ErroreScript("tag_script_dati_pieni")
        self.dati[chiave] = valore

    async def delete(self, chiave: str) -> None:
        self.dati.pop(chiave, None)


class ArchivioProva:
    """Legge i dati veri, scrive solo in memoria: la prova (`/tag prova`) non salva niente."""

    def __init__(self, base) -> None:
        self.base = base
        self.scritti: dict[str, str | None] = {}

    async def get(self, chiave: str) -> str | None:
        if chiave in self.scritti:
            return self.scritti[chiave]
        return await self.base.get(chiave)

    async def set(self, chiave: str, valore: str) -> None:
        self.scritti[chiave] = valore

    async def delete(self, chiave: str) -> None:
        self.scritti[chiave] = None


def ha_script(testo: str) -> bool:
    """Vero se il testo ha almeno una chiamata `{funzione:...}` del linguaggio (gli altri tag non passano dal motore)."""
    return any(ALIAS.get(m.group(1).lower()) for m in re.finditer(r"\{([A-Za-zà-ÿ_]{1,16})[:}]", testo))


@lru_cache(maxsize=256)
def _compila(modello: str):
    import re2

    opzioni = re2.Options()
    opzioni.max_mem = 1 << 19
    return re2.compile(modello, opzioni)


def _abbina(testo: str) -> dict[int, int]:
    """Per ogni `{` chiusa dalla sua `}`: posizione di apertura -> di chiusura. Le graffe senza coppia sono testo."""
    pila: list[int] = []
    coppie: dict[int, int] = {}
    i, n = 0, len(testo)
    while i < n:
        c = testo[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            pila.append(i)
        elif c == "}" and pila:
            coppie[pila.pop()] = i
        i += 1
    return coppie


def _dividi(testo: str) -> list[str]:
    """Spezza sui `|` che non stanno dentro graffe e non hanno la barra davanti."""
    coppie = _abbina(testo)
    pezzi: list[str] = []
    inizio = i = 0
    while i < len(testo):
        c = testo[i]
        if c == "\\":
            i += 2
        elif c == "{" and i in coppie:
            i = coppie[i] + 1
        elif c == "|":
            pezzi.append(testo[inizio:i])
            inizio = i = i + 1
        else:
            i += 1
    pezzi.append(testo[inizio:])
    return pezzi


def _operatore(testo: str) -> tuple[int, str] | None:
    """Il primo operatore di confronto fuori dalle graffe: (posizione, simbolo)."""
    coppie = _abbina(testo)
    i = 0
    while i < len(testo):
        c = testo[i]
        if c == "\\":
            i += 2
        elif c == "{" and i in coppie:
            i = coppie[i] + 1
        elif testo[i:i + 2] in (">=", "<=", "==", "!=", "!~"):
            return i, testo[i:i + 2]
        elif c in "<>~":
            return i, c
        else:
            i += 1
    return None


def _numero(testo: str) -> float | None:
    try:
        v = float(testo.replace(",", "."))
    except ValueError:
        return None
    return v if v == v and abs(v) != float("inf") else None


def _vero(valore: str) -> bool:
    return valore.strip().casefold() not in _VERO_NO


def _confronta(a: str, op: str, b: str) -> bool:
    if op == "~":
        return b.casefold() in a.casefold()
    if op == "!~":
        return b.casefold() not in a.casefold()
    na, nb = _numero(a), _numero(b)
    x, y = (na, nb) if na is not None and nb is not None else (a.casefold(), b.casefold())
    return {"==": x == y, "!=": x != y, ">": x > y, "<": x < y, ">=": x >= y, "<=": x <= y}[op]


def _formatta_data(formato: str, quando: datetime) -> str:
    def un_pezzo(m: re.Match) -> str:
        d = m.group(1)
        tabella = {
            "d": f"{quando.day:02d}", "m": f"{quando.month:02d}", "Y": f"{quando.year}", "y": f"{quando.year % 100:02d}",
            "H": f"{quando.hour:02d}", "M": f"{quando.minute:02d}", "S": f"{quando.second:02d}",
            "B": _MESI[quando.month - 1], "b": _MESI[quando.month - 1][:3], "A": _GIORNI[quando.weekday()],
            "a": _GIORNI[quando.weekday()][:3], "j": f"{quando.timetuple().tm_yday:03d}", "%": "%",
        }
        if d not in tabella:
            raise ErroreScript("tag_script_formato_data", f"%{d}")
        return tabella[d]

    if formato.endswith("%") and not formato.endswith("%%"):
        raise ErroreScript("tag_script_formato_data", "%")
    return re.sub(r"%(.)", un_pezzo, formato, flags=re.DOTALL)


def _durata(testo: str) -> int:
    resto = testo.strip().casefold().replace(" ", "")
    totale = 0
    while resto:
        m = re.match(r"(\d{1,6})([a-z]+)", resto)
        if not m or m.group(2) not in _UNITA_TRA:
            raise ErroreScript("tag_script_durata", testo[:30])
        totale += int(m.group(1)) * _UNITA_TRA[m.group(2)]
        resto = resto[m.end():]
    if not 1 <= totale <= MAX_TRA:
        raise ErroreScript("tag_script_durata", testo[:30])
    return totale


class _Esecuzione:
    def __init__(self, contesto: Contesto) -> None:
        self.c = contesto
        self.operazioni = 0
        self.scritture = 0
        self.variabili: dict[str, str] = {}
        self.inizio = contesto.orologio()

    def _passo(self) -> None:
        self.operazioni += 1
        if self.operazioni > MAX_OPERAZIONI:
            raise ErroreScript("tag_script_troppi_passi")
        if self.c.orologio() - self.inizio > self.c.tempo_max:
            raise ErroreScript("tag_script_tempo")

    async def valuta(self, testo: str, prof: int, limite: int) -> str:
        if prof > MAX_PROFONDITA:
            raise ErroreScript("tag_script_troppo_profondo")
        coppie = _abbina(testo)
        fuori: list[str] = []
        lunghezza = 0
        i, n = 0, len(testo)
        while i < n:
            c = testo[i]
            if c == "\\" and i + 1 < n and testo[i + 1] in "{}|\\":
                pezzo, i = testo[i + 1], i + 2
            elif c == "{" and i in coppie:
                fine = coppie[i]
                valore = await self._chiamata(testo[i + 1:fine], prof)
                pezzo, i = (testo[i:fine + 1] if valore is None else valore), fine + 1
            else:
                pezzo, i = c, i + 1
            fuori.append(pezzo)
            lunghezza += len(pezzo)
            if lunghezza > limite:
                raise ErroreScript("tag_script_uscita_lunga")
        return "".join(fuori)

    async def _arg(self, args: list[str], posto: int, prof: int, predefinito: str = "") -> str:
        return await self.valuta(args[posto], prof + 1, MAX_VALORE) if posto < len(args) else predefinito

    async def _chiamata(self, corpo: str, prof: int) -> str | None:
        """Il valore di `{...}`; None se non è del linguaggio (resta scritta com'è, per i segnaposto di render_template)."""
        nome, due_punti, resto = corpo.partition(":")
        nome = nome.strip().lower()
        if not _NOME_FUNZIONE.match(nome) and not _NOME_VAR.match(nome):
            return None
        if not due_punti:
            if nome in self.variabili:
                self._passo()
                return self.variabili[nome]
            if nome in self.c.valori:
                self._passo()
                valore = self.c.valori[nome]
                return discord.utils.escape_mentions(valore) if nome in DA_UTENTI else valore
            return None
        funzione = ALIAS.get(nome)
        if funzione is None:
            return None
        self._passo()
        return await getattr(self, "_f_" + funzione)(resto, prof)

    # ---------------------------------------------------------------- logica
    async def _condizione(self, grezzo: str, prof: int) -> bool:
        trovato = _operatore(grezzo)
        if trovato is None:
            return _vero(await self.valuta(grezzo, prof + 1, MAX_VALORE))
        pos, op = trovato
        a = (await self.valuta(grezzo[:pos], prof + 1, MAX_VALORE)).strip()
        b = (await self.valuta(grezzo[pos + len(op):], prof + 1, MAX_VALORE)).strip()
        self._passo()
        return _confronta(a, op, b)

    async def _f_se(self, resto: str, prof: int) -> str:
        args = _dividi(resto)
        scelto = 1 if await self._condizione(args[0], prof) else 2
        return await self._arg(args, scelto, prof)

    async def _f_e(self, resto: str, prof: int) -> str:
        for a in _dividi(resto):
            if not await self._condizione(a, prof):
                return ""
        return "1"

    async def _f_o(self, resto: str, prof: int) -> str:
        for a in _dividi(resto):
            if await self._condizione(a, prof):
                return "1"
        return ""

    async def _f_non(self, resto: str, prof: int) -> str:
        return "" if await self._condizione(resto, prof) else "1"

    async def _f_var(self, resto: str, prof: int) -> str:
        nome, _, valore = resto.partition("=")
        nome = nome.strip().lower()
        if not _NOME_VAR.match(nome):
            raise ErroreScript("tag_script_nome_variabile", nome[:32])
        if nome not in self.variabili and len(self.variabili) >= MAX_VARIABILI:
            raise ErroreScript("tag_script_troppe_variabili")
        self.variabili[nome] = await self.valuta(valore, prof + 1, MAX_VALORE)
        return ""

    # ---------------------------------------------------------------- testo e numeri
    async def _f_lista(self, resto: str, prof: int) -> str:
        args = _dividi(resto)
        return await self._arg(args, self.c.rng.randrange(len(args)), prof)

    async def _f_caso(self, resto: str, prof: int) -> str:
        m = re.fullmatch(r"\s*(-?\d{1,10})\s*(?:-\s*(-?\d{1,10}))?\s*", await self.valuta(resto, prof + 1, MAX_VALORE))
        if not m:
            raise ErroreScript("tag_script_intervallo", resto[:30])
        a, b = (int(m.group(1)), int(m.group(2))) if m.group(2) is not None else (1, int(m.group(1)))
        if a > b or max(abs(a), abs(b)) > MAX_INTERVALLO:
            raise ErroreScript("tag_script_intervallo", resto[:30])
        return str(self.c.rng.randint(a, b))

    async def _f_ripeti(self, resto: str, prof: int) -> str:
        args = _dividi(resto)
        n = _numero(await self._arg(args, 0, prof))
        if n is None or not 0 <= n <= MAX_RIPETIZIONI:
            raise ErroreScript("tag_script_intervallo", str(args[0])[:30])
        corpo = "|".join(args[1:])
        pezzi: list[str] = []
        totale = 0
        for _ in range(int(n)):
            pezzo = await self.valuta(corpo, prof + 1, MAX_VALORE)
            totale += len(pezzo)
            if totale > MAX_VALORE:
                raise ErroreScript("tag_script_uscita_lunga")
            pezzi.append(pezzo)
        return "".join(pezzi)

    async def _f_calcola(self, resto: str, prof: int) -> str:
        try:
            return calcola(await self.valuta(resto, prof + 1, MAX_VALORE))
        except ErroreStrumento as exc:
            raise ErroreScript("tag_script_calcolo", exc.chiave) from None

    async def _f_maiuscolo(self, resto: str, prof: int) -> str:
        return (await self.valuta(resto, prof + 1, MAX_VALORE)).upper()

    async def _f_minuscolo(self, resto: str, prof: int) -> str:
        return (await self.valuta(resto, prof + 1, MAX_VALORE)).lower()

    async def _f_titolo(self, resto: str, prof: int) -> str:
        return (await self.valuta(resto, prof + 1, MAX_VALORE)).title()

    async def _f_lunghezza(self, resto: str, prof: int) -> str:
        return str(len(await self.valuta(resto, prof + 1, MAX_VALORE)))

    async def _f_sostituisci(self, resto: str, prof: int) -> str:
        args = _dividi(resto)
        testo, cerca, con = [await self._arg(args, i, prof) for i in range(3)]
        if not cerca:
            return testo
        if len(testo) + testo.count(cerca) * (len(con) - len(cerca)) > MAX_VALORE:
            raise ErroreScript("tag_script_uscita_lunga")
        return testo.replace(cerca, con)

    async def _f_regex(self, resto: str, prof: int) -> str:
        args = _dividi(resto)
        testo, modello, con = [await self._arg(args, i, prof) for i in range(3)]
        if not 1 <= len(modello) <= MAX_REGEX:
            raise ErroreScript("tag_script_regex", "lunghezza")
        try:
            risultato = _compila(modello).sub(con, testo)
        except Exception:  # re2.error non ha una base comune
            raise ErroreScript("tag_script_regex", modello[:40]) from None
        if len(risultato) > MAX_VALORE:
            raise ErroreScript("tag_script_uscita_lunga")
        return risultato

    # ---------------------------------------------------------------- tempo
    async def _f_data(self, resto: str, prof: int) -> str:
        formato = (await self.valuta(resto, prof + 1, MAX_VALORE)) or "%d/%m/%Y %H:%M"
        return _formatta_data(formato, self.c.adesso)

    async def _f_tra(self, resto: str, prof: int) -> str:
        secondi = _durata(await self.valuta(resto, prof + 1, MAX_VALORE))
        return f"<t:{int((self.c.adesso + timedelta(seconds=secondi)).timestamp())}:R>"

    # ---------------------------------------------------------------- dati del server
    async def _f_dati(self, resto: str, prof: int) -> str:
        args = _dividi(resto)
        azione = AZIONI_DATI.get((await self._arg(args, 0, prof)).strip().lower())
        if azione is None:
            raise ErroreScript("tag_script_dati_azione", args[0][:20])
        if self.c.archivio is None:
            raise ErroreScript("tag_script_dati_non_disponibili")
        chiave = (await self._arg(args, 1, prof)).strip().lower()
        if not CHIAVE_DATI.match(chiave):
            raise ErroreScript("tag_script_dati_chiave", chiave[:30])
        try:
            if azione == "get":
                valore = await self.c.archivio.get(chiave)
                return valore if valore is not None else await self._arg(args, 2, prof)
            self.scritture += 1
            if self.scritture > MAX_SCRITTURE:
                raise ErroreScript("tag_script_troppe_scritture")
            if azione == "del":
                await self.c.archivio.delete(chiave)
                return ""
            valore = await self._arg(args, 2, prof)
            if len(valore.encode()) > MAX_VALORE_DATO:
                raise ErroreScript("tag_script_dati_valore", chiave)
            await self.c.archivio.set(chiave, valore)
            return ""
        except ErroreScript:
            raise
        except Exception:
            raise ErroreScript("tag_script_dati_errore", chiave) from None


async def esegui(testo: str, contesto: Contesto | None = None) -> Risultato:
    """Esegue lo script. Un errore (tetto, sintassi, valore) ferma tutto: `errore` dice quale, `testo` è vuoto."""
    contesto = contesto or Contesto()
    corsa = _Esecuzione(contesto)
    try:
        if len(testo) > MAX_SCRIPT:
            raise ErroreScript("tag_script_troppo_lungo")
        uscita = await corsa.valuta(testo, 0, MAX_USCITA)
    except ErroreScript as exc:
        return Risultato("", exc, corsa.operazioni, corsa.variabili)
    return Risultato(uscita, None, corsa.operazioni, corsa.variabili)

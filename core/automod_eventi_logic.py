"""
core/automod_eventi_logic.py
============================
Quando scatta una regola personale su un evento che non è un messaggio (D63, AMD-009/010/017/018/075): spostamenti
continui tra vocali, thread a raffica, nome o stato vietato, ingresso, uscita, ruolo dato o tolto, caso di
moderazione. In più i freni contro i giri a vuoto: gli eventi causati dalle azioni del bot si ignorano per 30
secondi e una persona non fa scattare più di 3 regole per evento ogni 10 secondi. Logica pura, niente Discord.
Funzioni coperte: SPEC §6 (AMD-009, 010, 017, 018, 075), D63
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from core.automod_innesco_logic import innesco_scatta
from core.bounded_cache import BoundedCache

SPOSTAMENTI_DI_BASE = (5, 30)  # numero, secondi
THREAD_DI_BASE = (3, 300)
EFFETTO_VITA_S = 30
MAX_REGOLE_PER_EVENTO = 3
PAUSA_REGOLE_S = 10
EVENTI_SENZA_MESSAGGIO = ("nome", "stato", "vocale", "thread", "ingresso", "uscita", "ruolo_dato", "ruolo_tolto", "caso")
_TETTO = 20_000


@dataclass(frozen=True)
class DatiEvento:
    """Quello che serve all'innesco: il testo del nome o dello stato, il ruolo cambiato, il tipo di caso."""

    testo: str = ""
    ruolo_id: int | None = None
    tipo_caso: str | None = None


class Conteggi:
    """Quanti eventi uguali in una finestra scorrevole, per chiave (server, persona, regola). In memoria, con tetto."""

    def __init__(self) -> None:
        self._eventi: BoundedCache[tuple, deque] = BoundedCache(_TETTO)

    def conta(self, chiave: tuple, ora: float, finestra_s: int, soglia: int) -> int:
        """
        Segna l'evento di adesso e restituisce quanti ce ne sono nella finestra (adesso compreso), fino alla soglia:
        bastano gli ultimi `soglia` eventi per sapere se è raggiunta, e la memoria resta piccola.
        """
        coda = self._eventi.get(chiave)
        if coda is None or coda.maxlen != max(1, soglia):
            coda = deque(maxlen=max(1, soglia))
            self._eventi.set(chiave, coda)
        coda.append(ora)
        while coda and ora - coda[0] > finestra_s:
            coda.popleft()
        return len(coda)


class Effetti:
    """Cambiamenti fatti dal bot stesso (ruolo, nickname, uscita): l'evento che ne nasce non fa scattare nessuna regola."""

    def __init__(self) -> None:
        self._visti: BoundedCache[tuple, float] = BoundedCache(_TETTO)

    def segna(self, guild_id: int, user_id: int, tipo: str, dettaglio: int | None, ora: float) -> None:
        self._visti.set((guild_id, user_id, tipo, dettaglio), ora)

    def e_nostro(self, guild_id: int, user_id: int, tipo: str, dettaglio: int | None, ora: float) -> bool:
        visto = self._visti.get((guild_id, user_id, tipo, dettaglio))
        return visto is not None and ora - visto <= EFFETTO_VITA_S


class LimiteRegole:
    """Al massimo 3 regole per persona ed evento ogni 10 secondi: nessun ciclo regola, azione, evento, regola."""

    def __init__(self) -> None:
        self._scattate: BoundedCache[tuple, deque] = BoundedCache(_TETTO)

    def consente(self, guild_id: int, user_id: int, evento: str, ora: float) -> bool:
        """True e segna se c'è ancora posto; False se le 3 regole sono già scattate negli ultimi 10 secondi."""
        coda = self._scattate.get((guild_id, user_id, evento))
        if coda is None:
            coda = deque()
            self._scattate.set((guild_id, user_id, evento), coda)
        while coda and ora - coda[0] > PAUSA_REGOLE_S:
            coda.popleft()
        if len(coda) >= MAX_REGOLE_PER_EVENTO:
            return False
        coda.append(ora)
        return True


def _filtro_ok(elenco, valore) -> bool:
    return not elenco or valore in elenco


def innesco_evento_scatta(
    evento: str,
    innesco: dict,
    dati: DatiEvento,
    liste: dict[str, tuple[str, ...]] | None,
    conteggi: Conteggi,
    chiave: tuple,
    ora: float,
) -> bool:
    """True se l'innesco della regola scatta su questo evento. Un innesco vuoto o fuori posto non scatta mai."""
    tipo = innesco.get("tipo")
    if not tipo:
        return False
    if evento in ("ingresso", "uscita"):
        return tipo == "sempre"
    if evento == "ruolo_dato" or evento == "ruolo_tolto":
        return tipo == "sempre" and _filtro_ok(innesco.get("ruoli"), dati.ruolo_id)
    if evento == "caso":
        return tipo == "sempre" and _filtro_ok(innesco.get("casi"), dati.tipo_caso)
    if evento == "vocale":
        if tipo == "sempre":
            return True
        if tipo == "spostamenti_vocali":
            numero, secondi = innesco.get("numero", SPOSTAMENTI_DI_BASE[0]), innesco.get("secondi", SPOSTAMENTI_DI_BASE[1])
            return conteggi.conta(chiave, ora, secondi, numero) >= numero
        return False
    if evento == "thread":
        if tipo == "sempre":
            return True
        if tipo == "thread_raffica":
            numero, secondi = innesco.get("numero", THREAD_DI_BASE[0]), innesco.get("secondi", THREAD_DI_BASE[1])
            return conteggi.conta(chiave, ora, secondi, numero) >= numero
        return False
    if evento in ("nome", "stato"):
        if tipo == "sempre":
            return True
        if tipo in ("nome", "stato"):  # come una regola sul testo: regex se c'è, altrimenti parole e liste
            tipo = "regex" if innesco.get("regex") else "lista"
        return innesco_scatta({**innesco, "tipo": tipo}, dati.testo, liste)
    return False


# Un solo registro per processo; i test ne fanno di nuovi.
conteggi = Conteggi()
effetti = Effetti()
limite_regole = LimiteRegole()

# Azioni del bot che fanno nascere un evento: (tipo di effetto, dettaglio o None per «qualsiasi»).
EFFETTO_DELL_AZIONE = {"ruolo": "ruolo", "mute_ruolo": "ruolo", "nickname": "nome", "kick": "uscita", "ban": "uscita", "ban_tempo": "uscita"}
EFFETTO_DELL_EVENTO = {"ruolo_dato": "ruolo", "ruolo_tolto": "ruolo", "nome": "nome", "uscita": "uscita"}

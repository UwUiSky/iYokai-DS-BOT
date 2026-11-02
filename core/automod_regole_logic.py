"""
core/automod_regole_logic.py
============================
Logica pura (niente discord.py, niente database) delle regole AutoMod: una regola ha condizioni
(chi, dove, quando) e azioni (cosa fare), con un contatore facoltativo. Legge e scrive il JSON,
rifiuta chiavi sconosciute e tetti superati, decide se una regola vale per un messaggio.
Funzioni coperte: SPEC §6 (AMD-029, 032-040, 042-056, 058-061), D63
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

VERSIONE = 1

# Tetti (LIMITI: stessi numeri dei menu e dell'AutoMod nativo di Discord).
MAX_REGOLE_PERSONALI = 50
MAX_REGOLE_PERSONALI_PREMIUM = 100
MAX_LISTE = 20
MAX_VOCI_LISTA = 1000
MAX_LUNG_VOCE = 60
MAX_REGEX = 10
MAX_LUNG_REGEX = 260
MAX_ID_PER_CONDIZIONE = 25
MAX_AZIONI = 8
MAX_SOGLIE = 3
MAX_NOME = 32
MAX_GRUPPO = 32
MAX_AVVISO_CANALE = 300
MAX_TESTO_DM = 1000
MAX_CANCELLA_ULTIMI = 50
MAX_CANCELLA_MINUTI = 60
MAX_TIMEOUT_S = 2_419_200  # 28 giorni
MAX_BAN_GIORNI = 365
MAX_SLOWMODE_S = 21_600
MAX_SLOWMODE_DURATA_S = 86_400
MAX_NICKNAME = 32
MAX_NOME_THREAD = 100
MAX_STAFF_DM = 5
MAX_CANALI_PERMESSI = 5
MAX_AVVISO_DOPO_S = 60
MAX_MOTIVO = 512
MAX_TESTO_PROVA = 4000

EVENTI = (
    "messaggio", "modifica", "nome", "stato", "vocale", "thread",
    "ingresso", "uscita", "ruolo_dato", "ruolo_tolto", "caso",
)
TIPI_REGOLA = ("filtro", "personale")
AUTORI = ("persone", "bot", "webhook")
MODI_RUOLI = ("almeno_uno", "tutti")
MODI_THREAD = ("anche", "no", "solo")
MODELLI_PERMESSI = ("blocca_scrittura",)

# Ordine di esecuzione (D63): il numero è il passo, le azioni dello stesso passo restano come scritte.
PASSO_AZIONE = {
    "cancella": 1, "cancella_ultimi": 1,
    "dm": 2,
    "warn": 3, "timeout": 3, "mute_ruolo": 3, "kick": 3, "ban": 3, "ban_tempo": 3,
    "ruolo": 4, "nickname": 4,
    "slowmode": 5, "permessi": 5, "thread_archivia": 5, "thread_apri": 5,
    "avviso_canale": 6,
    "log": 7, "dm_staff": 7, "decide_staff": 7,
    "azzera": 8,
}
TIPI_AZIONE = tuple(PASSO_AZIONE)
AZIONI_SULL_UTENTE = ("timeout", "mute_ruolo", "kick", "ban", "ban_tempo", "ruolo", "nickname")  # scudo dei protetti
AZIONI_UTENTE_MENU = ("cancella", "cancella_ultimi", "dm", "warn", "timeout", "mute_ruolo", "kick", "ban", "ban_tempo", "ruolo", "nickname")
AZIONI_CANALE_STAFF_MENU = (
    "slowmode", "permessi", "thread_archivia", "thread_apri", "avviso_canale", "log", "dm_staff", "decide_staff", "azzera",
)

# Segnaposto dei testi; il controllo dei tetti usa i valori peggiori.
_SEGNAPOSTO_PEGGIORI = {"utente": "x" * 37, "canale": "x" * 22, "regola": "x" * MAX_NOME, "server": "x" * 100}
_SEGNAPOSTO = re.compile(r"\{(utente|canale|regola|server)\}")


class RegolaNonValida(ValueError):
    """Il JSON della regola ha una chiave sconosciuta o un valore fuori dai tetti."""


def espandi_segnaposto(testo: str, valori: dict[str, str] | None = None) -> str:
    """Sostituisce {utente} {canale} {regola} {server}; senza valori usa i casi peggiori (per i tetti)."""
    fonte = valori if valori is not None else _SEGNAPOSTO_PEGGIORI
    return _SEGNAPOSTO.sub(lambda m: str(fonte.get(m.group(1), "")), testo)


# ---------------------------------------------------------------- strumenti di controllo

def _solo_chiavi(dati: Any, ammesse: set[str], dove: str) -> dict:
    if not isinstance(dati, dict):
        raise RegolaNonValida(f"{dove}: serve un oggetto")
    sconosciute = set(dati) - ammesse
    if sconosciute:
        raise RegolaNonValida(f"{dove}: chiave sconosciuta {sorted(sconosciute)[0]!r}")
    return dati


def _intero(valore: Any, dove: str, minimo: int, massimo: int) -> int:
    if isinstance(valore, bool) or not isinstance(valore, int) or not minimo <= valore <= massimo:
        raise RegolaNonValida(f"{dove}: serve un intero tra {minimo} e {massimo}")
    return valore


def _intero_o_none(valore: Any, dove: str, minimo: int, massimo: int) -> int | None:
    return None if valore is None else _intero(valore, dove, minimo, massimo)


def _testo(valore: Any, dove: str, massimo: int, *, vuoto: bool = False) -> str:
    if not isinstance(valore, str) or (not vuoto and not valore.strip()):
        raise RegolaNonValida(f"{dove}: serve un testo")
    if len(espandi_segnaposto(valore)) > massimo:
        raise RegolaNonValida(f"{dove}: massimo {massimo} caratteri (segnaposto compresi)")
    return valore


def _ids(valore: Any, dove: str, massimo: int = MAX_ID_PER_CONDIZIONE) -> tuple[int, ...]:
    if not isinstance(valore, (list, tuple)) or len(valore) > massimo:
        raise RegolaNonValida(f"{dove}: al massimo {massimo} voci")
    return tuple(_intero(v, dove, 1, 2**63 - 1) for v in dict.fromkeys(valore))


def _scelta(valore: Any, dove: str, ammessi: tuple[str, ...]) -> str:
    if valore not in ammessi:
        raise RegolaNonValida(f"{dove}: ammessi {', '.join(ammessi)}")
    return valore


def _intervallo(valore: Any, dove: str, massimo: int) -> tuple[int | None, int | None]:
    dati = _solo_chiavi(valore if valore is not None else {}, {"min", "max"}, dove)
    minimo = _intero_o_none(dati.get("min"), f"{dove}.min", 0, massimo)
    alto = _intero_o_none(dati.get("max"), f"{dove}.max", 0, massimo)
    if minimo is not None and alto is not None and minimo > alto:
        raise RegolaNonValida(f"{dove}: il minimo supera il massimo")
    return minimo, alto


def _ora(valore: Any, dove: str) -> time:
    try:
        ore, minuti = str(valore).split(":")
        return time(int(ore), int(minuti))
    except (ValueError, TypeError):
        raise RegolaNonValida(f"{dove}: serve un orario come 23:00") from None


# ---------------------------------------------------------------- condizioni

@dataclass(frozen=True)
class Orari:
    fuso: str = "Europe/Rome"
    dalle: str = "00:00"
    alle: str = "23:59"
    giorni: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)


@dataclass(frozen=True)
class Condizioni:
    esenzioni_globali: bool = True
    canali_inclusi: tuple[int, ...] = ()
    canali_esclusi: tuple[int, ...] = ()
    ruoli_inclusi: tuple[int, ...] = ()
    ruoli_modo: str = "almeno_uno"
    ruoli_esclusi: tuple[int, ...] = ()
    senza_ruoli: bool = False
    utenti_esclusi: tuple[int, ...] = ()
    eta_account_giorni: tuple[int | None, int | None] = (None, None)
    nel_server_giorni: tuple[int | None, int | None] = (None, None)
    livello: tuple[int | None, int | None] = (None, None)
    orari: Orari | None = None
    thread: str = "anche"
    autori: tuple[str, ...] = ("persone",)


_CHIAVI_CONDIZIONI = {
    "v", "esenzioni_globali", "canali_inclusi", "canali_esclusi", "ruoli_inclusi", "ruoli_modo", "ruoli_esclusi",
    "senza_ruoli", "utenti_esclusi", "eta_account_giorni", "nel_server_giorni", "livello", "orari", "thread", "autori",
}


def condizioni_da_json(dati: Any) -> Condizioni:
    d = _solo_chiavi(dati if dati is not None else {}, _CHIAVI_CONDIZIONI, "condizioni")
    if d.get("v", VERSIONE) != VERSIONE:
        raise RegolaNonValida("condizioni: versione non supportata")
    orari = None
    if d.get("orari") is not None:
        o = _solo_chiavi(d["orari"], {"fuso", "dalle", "alle", "giorni"}, "orari")
        fuso = str(o.get("fuso", "Europe/Rome"))
        try:
            ZoneInfo(fuso)
        except Exception:
            raise RegolaNonValida("orari: fuso orario sconosciuto") from None
        dalle, alle = _ora(o.get("dalle", "00:00"), "orari.dalle"), _ora(o.get("alle", "23:59"), "orari.alle")
        giorni = tuple(sorted({_intero(g, "orari.giorni", 1, 7) for g in o.get("giorni", range(1, 8))}))
        if not giorni:
            raise RegolaNonValida("orari: serve almeno un giorno")
        orari = Orari(fuso, f"{dalle:%H:%M}", f"{alle:%H:%M}", giorni)
    autori = tuple(dict.fromkeys(_scelta(a, "autori", AUTORI) for a in d.get("autori", ["persone"])))
    if not autori:
        raise RegolaNonValida("autori: serve almeno un tipo")
    return Condizioni(
        esenzioni_globali=bool(d.get("esenzioni_globali", True)),
        canali_inclusi=_ids(d.get("canali_inclusi", []), "canali_inclusi"),
        canali_esclusi=_ids(d.get("canali_esclusi", []), "canali_esclusi"),
        ruoli_inclusi=_ids(d.get("ruoli_inclusi", []), "ruoli_inclusi"),
        ruoli_modo=_scelta(d.get("ruoli_modo", "almeno_uno"), "ruoli_modo", MODI_RUOLI),
        ruoli_esclusi=_ids(d.get("ruoli_esclusi", []), "ruoli_esclusi"),
        senza_ruoli=bool(d.get("senza_ruoli", False)),
        utenti_esclusi=_ids(d.get("utenti_esclusi", []), "utenti_esclusi"),
        eta_account_giorni=_intervallo(d.get("eta_account_giorni"), "eta_account_giorni", 36_500),
        nel_server_giorni=_intervallo(d.get("nel_server_giorni"), "nel_server_giorni", 36_500),
        livello=_intervallo(d.get("livello"), "livello", 1000),
        orari=orari,
        thread=_scelta(d.get("thread", "anche"), "thread", MODI_THREAD),
        autori=autori,
    )


def condizioni_a_json(c: Condizioni) -> dict:
    """Solo i campi diversi dalla base: un campo che manca non filtra."""
    base = Condizioni()
    fuori: dict[str, Any] = {"v": VERSIONE}
    for campo in _CHIAVI_CONDIZIONI - {"v", "orari", "eta_account_giorni", "nel_server_giorni", "livello"}:
        valore = getattr(c, campo)
        if valore != getattr(base, campo):
            fuori[campo] = list(valore) if isinstance(valore, tuple) else valore
    for campo in ("eta_account_giorni", "nel_server_giorni", "livello"):
        minimo, alto = getattr(c, campo)
        if (minimo, alto) != (None, None):
            fuori[campo] = {"min": minimo, "max": alto}
    if c.orari is not None:
        fuori["orari"] = {"fuso": c.orari.fuso, "dalle": c.orari.dalle, "alle": c.orari.alle, "giorni": list(c.orari.giorni)}
    return fuori


@dataclass(frozen=True)
class Contesto:
    """Cosa serve a `condizioni_ok`: niente oggetti Discord."""

    evento: str
    autore_id: int
    ruoli_ids: frozenset[int] = frozenset()  # senza @everyone
    e_bot: bool = False
    e_webhook: bool = False
    e_proprio: bool = False  # il bot stesso, i suoi worker, i suoi webhook: mai giudicati
    eta_account_giorni: int | None = None
    nel_server_giorni: int | None = None
    livello: int | None = None
    canale_id: int | None = None
    categoria_id: int | None = None
    thread_padre_id: int | None = None
    in_thread: bool = False
    ora: datetime | None = None  # con fuso (UTC)


def _nell_intervallo(valore: int | None, intervallo: tuple[int | None, int | None]) -> bool:
    minimo, alto = intervallo
    if minimo is None and alto is None:
        return True
    if valore is None:  # non si sa: nel dubbio non si punisce
        return False
    return (minimo is None or valore >= minimo) and (alto is None or valore <= alto)


def _nell_orario(o: Orari, ora: datetime | None) -> bool:
    if ora is None:
        return False
    locale = ora.astimezone(ZoneInfo(o.fuso))
    dalle, alle = _ora(o.dalle, "orari"), _ora(o.alle, "orari")
    adesso = locale.time().replace(second=0, microsecond=0)
    if dalle <= alle:
        dentro, giorno = dalle <= adesso <= alle, locale.isoweekday()
    else:  # a cavallo della mezzanotte: la parte dopo le 00:00 appartiene al giorno di partenza
        dentro = adesso >= dalle or adesso <= alle
        giorno = locale.isoweekday() if adesso >= dalle else (locale.isoweekday() - 2) % 7 + 1
    return dentro and giorno in o.giorni


def condizioni_ok(c: Condizioni, ctx: Contesto) -> bool:
    """True se la regola vale per questo contesto. Il bot non giudica mai sé stesso."""
    if ctx.e_proprio:
        return False
    if ctx.e_webhook:
        tipo = "webhook"
    elif ctx.e_bot:
        tipo = "bot"
    else:
        tipo = "persone"
    if tipo not in c.autori:
        return False
    if ctx.autore_id in c.utenti_esclusi:
        return False
    posti = {p for p in (ctx.canale_id, ctx.categoria_id, ctx.thread_padre_id) if p is not None}
    if c.canali_inclusi and not posti & set(c.canali_inclusi):
        return False
    if posti & set(c.canali_esclusi):
        return False
    if c.thread == "no" and ctx.in_thread:
        return False
    if c.thread == "solo" and not ctx.in_thread:
        return False
    if c.senza_ruoli and ctx.ruoli_ids:
        return False
    if c.ruoli_inclusi:
        richiesti = set(c.ruoli_inclusi)
        if c.ruoli_modo == "tutti":
            if not richiesti <= ctx.ruoli_ids:
                return False
        elif not richiesti & ctx.ruoli_ids:
            return False
    if ctx.ruoli_ids & set(c.ruoli_esclusi):
        return False
    if not (_nell_intervallo(ctx.eta_account_giorni, c.eta_account_giorni)
            and _nell_intervallo(ctx.nel_server_giorni, c.nel_server_giorni)
            and _nell_intervallo(ctx.livello, c.livello)):
        return False
    return c.orari is None or _nell_orario(c.orari, ctx.ora)


# ---------------------------------------------------------------- azioni

@dataclass(frozen=True)
class Azione:
    t: str
    parametri: tuple[tuple[str, Any], ...] = ()

    def get(self, nome: str, difetto: Any = None) -> Any:
        return dict(self.parametri).get(nome, difetto)


def _p_nessuno(d: dict) -> dict:
    return {}


def _p_cancella_ultimi(d: dict) -> dict:
    return {
        "n": _intero(d.get("n", 10), "cancella_ultimi.n", 1, MAX_CANCELLA_ULTIMI),
        "minuti": _intero(d.get("minuti", 10), "cancella_ultimi.minuti", 1, MAX_CANCELLA_MINUTI),
    }


def _p_dm(d: dict) -> dict:
    return {"testo": _testo(d["testo"], "dm.testo", MAX_TESTO_DM)} if d.get("testo") else {}


def _p_timeout(d: dict) -> dict:
    return {"secondi": _intero(d.get("secondi"), "timeout.secondi", 1, MAX_TIMEOUT_S)}


def _p_mute_ruolo(d: dict) -> dict:
    return {"secondi": _intero(d.get("secondi"), "mute_ruolo.secondi", 60, MAX_TIMEOUT_S)}


def _p_ban_tempo(d: dict) -> dict:
    return {"giorni": _intero(d.get("giorni"), "ban_tempo.giorni", 1, MAX_BAN_GIORNI)}


def _p_ruolo(d: dict) -> dict:
    fuori = {"ruolo_id": _intero(d.get("ruolo_id"), "ruolo.ruolo_id", 1, 2**63 - 1),
             "op": _scelta(d.get("op", "dai"), "ruolo.op", ("dai", "togli"))}
    if d.get("secondi") is not None:
        fuori["secondi"] = _intero(d["secondi"], "ruolo.secondi", 60, MAX_TIMEOUT_S)
    return fuori


def _p_nickname(d: dict) -> dict:
    return {"testo": _testo(d.get("testo", ""), "nickname.testo", MAX_NICKNAME, vuoto=True)}  # vuoto = pulisci


def _p_slowmode(d: dict) -> dict:
    return {"secondi": _intero(d.get("secondi"), "slowmode.secondi", 1, MAX_SLOWMODE_S),
            "durata_s": _intero(d.get("durata_s", 600), "slowmode.durata_s", 60, MAX_SLOWMODE_DURATA_S)}


def _p_permessi(d: dict) -> dict:
    fuori = {"modello": _scelta(d.get("modello", "blocca_scrittura"), "permessi.modello", MODELLI_PERMESSI),
             "durata_s": _intero(d.get("durata_s"), "permessi.durata_s", 60, MAX_SLOWMODE_DURATA_S),  # sempre con ripristino
             "canali": list(_ids(d.get("canali", []), "permessi.canali", MAX_CANALI_PERMESSI))}
    if d.get("ruolo_id") is not None:  # senza ruolo vale @everyone
        fuori["ruolo_id"] = _intero(d["ruolo_id"], "permessi.ruolo_id", 1, 2**63 - 1)
    return fuori


def _p_thread_apri(d: dict) -> dict:
    return {"nome": _testo(d.get("nome"), "thread_apri.nome", MAX_NOME_THREAD)}


def _p_avviso_canale(d: dict) -> dict:
    return {"testo": _testo(d.get("testo"), "avviso_canale.testo", MAX_AVVISO_CANALE),
            "dopo_s": _intero(d.get("dopo_s", 10), "avviso_canale.dopo_s", 1, MAX_AVVISO_DOPO_S)}


def _p_log(d: dict) -> dict:
    return {"ping_ruolo": _intero(d["ping_ruolo"], "log.ping_ruolo", 1, 2**63 - 1)} if d.get("ping_ruolo") else {}


def _p_dm_staff(d: dict) -> dict:
    utenti = _ids(d.get("utenti"), "dm_staff.utenti", MAX_STAFF_DM)
    if not utenti:
        raise RegolaNonValida("dm_staff.utenti: serve almeno una persona")
    return {"utenti": list(utenti)}


def _p_azzera(d: dict) -> dict:
    nomi = d.get("contatori", [])
    if not isinstance(nomi, list) or len(nomi) > MAX_AZIONI:
        raise RegolaNonValida(f"azzera.contatori: al massimo {MAX_AZIONI} nomi")
    return {"contatori": [_testo(n, "azzera.contatori", MAX_NOME) for n in nomi], "scala": bool(d.get("scala", False))}


_PARAMETRI = {
    "cancella": (_p_nessuno, set()), "cancella_ultimi": (_p_cancella_ultimi, {"n", "minuti"}),
    "dm": (_p_dm, {"testo"}), "warn": (_p_nessuno, set()), "timeout": (_p_timeout, {"secondi"}),
    "mute_ruolo": (_p_mute_ruolo, {"secondi"}), "kick": (_p_nessuno, set()), "ban": (_p_nessuno, set()),
    "ban_tempo": (_p_ban_tempo, {"giorni"}), "ruolo": (_p_ruolo, {"ruolo_id", "op", "secondi"}),
    "nickname": (_p_nickname, {"testo"}), "slowmode": (_p_slowmode, {"secondi", "durata_s"}),
    "permessi": (_p_permessi, {"modello", "durata_s", "canali", "ruolo_id"}),
    "thread_archivia": (_p_nessuno, set()), "thread_apri": (_p_thread_apri, {"nome"}),
    "avviso_canale": (_p_avviso_canale, {"testo", "dopo_s"}), "log": (_p_log, {"ping_ruolo"}),
    "dm_staff": (_p_dm_staff, {"utenti"}), "decide_staff": (_p_nessuno, set()),
    "azzera": (_p_azzera, {"contatori", "scala"}),
}


def azione_da_json(dati: Any) -> Azione:
    if not isinstance(dati, dict) or dati.get("t") not in _PARAMETRI:
        raise RegolaNonValida(f"azione: tipo non valido ({dati.get('t') if isinstance(dati, dict) else dati!r})")
    leggi, ammessi = _PARAMETRI[dati["t"]]
    _solo_chiavi(dati, ammessi | {"t"}, f"azione {dati['t']}")
    return Azione(dati["t"], tuple(sorted(leggi(dati).items())))


def azione_a_json(a: Azione) -> dict:
    return {"t": a.t, **dict(a.parametri)}


def azioni_da_json(dati: Any) -> tuple[Azione, ...]:
    if not isinstance(dati, (list, tuple)) or len(dati) > MAX_AZIONI:
        raise RegolaNonValida(f"azioni: al massimo {MAX_AZIONI}")
    return tuple(azione_da_json(a) for a in dati)


def ordina_azioni(azioni: tuple[Azione, ...] | list[Azione]) -> tuple[Azione, ...]:
    """Ordine fisso di D63; a parità di passo resta quello scritto (sorted è stabile)."""
    return tuple(sorted(azioni, key=lambda a: PASSO_AZIONE[a.t]))


# ---------------------------------------------------------------- contatore

@dataclass(frozen=True)
class Soglia:
    violazioni: int
    minuti: int
    azioni: tuple[Azione, ...]


@dataclass(frozen=True)
class Contatore:
    nome: str
    scadenza_giorni: int | None = None
    soglie: tuple[Soglia, ...] = ()


def contatore_da_json(dati: Any) -> Contatore | None:
    if dati is None:
        return None
    d = _solo_chiavi(dati, {"nome", "scadenza_giorni", "soglie"}, "contatore")
    soglie = d.get("soglie", [])
    if not isinstance(soglie, list) or len(soglie) > MAX_SOGLIE:
        raise RegolaNonValida(f"contatore.soglie: al massimo {MAX_SOGLIE}")
    lette = []
    for s in soglie:
        s = _solo_chiavi(s, {"violazioni", "minuti", "azioni"}, "soglia")
        lette.append(Soglia(_intero(s.get("violazioni"), "soglia.violazioni", 1, 100),
                            _intero(s.get("minuti"), "soglia.minuti", 1, 1440), azioni_da_json(s.get("azioni", []))))
    return Contatore(_testo(d.get("nome"), "contatore.nome", MAX_NOME),
                     _intero_o_none(d.get("scadenza_giorni"), "contatore.scadenza_giorni", 1, 365), tuple(lette))


def contatore_a_json(c: Contatore | None) -> dict | None:
    if c is None:
        return None
    fuori: dict[str, Any] = {"nome": c.nome}
    if c.scadenza_giorni is not None:
        fuori["scadenza_giorni"] = c.scadenza_giorni
    fuori["soglie"] = [{"violazioni": s.violazioni, "minuti": s.minuti, "azioni": [azione_a_json(a) for a in s.azioni]}
                       for s in c.soglie]
    return fuori


# ---------------------------------------------------------------- innesco delle regole personali

INNESCHI = ("regex", "lista", "domini", "solo_permesse", "soglia_canale", "spostamenti_vocali", "thread_raffica",
            "nome", "stato", "sempre")


def innesco_da_json(dati: Any) -> dict:
    """Controlla i tetti dell'innesco (le regex solo RE2, ≤ 10, ≤ 260). Restituisce un dizionario pulito."""
    if dati in (None, {}):
        return {}
    d = _solo_chiavi(dati, {"tipo", "regex", "liste", "modo", "numero", "secondi", "parole", "testo_in", "limite"}, "innesco")
    tipo = _scelta(d.get("tipo"), "innesco.tipo", INNESCHI)
    fuori: dict[str, Any] = {"tipo": tipo}
    if "regex" in d:
        lista = d["regex"]
        if not isinstance(lista, list) or len(lista) > MAX_REGEX:
            raise RegolaNonValida(f"innesco.regex: al massimo {MAX_REGEX}")
        for r in lista:
            controlla_regex(r)
        fuori["regex"] = list(lista)
    if "liste" in d:
        if not isinstance(d["liste"], list) or len(d["liste"]) > MAX_LISTE:
            raise RegolaNonValida(f"innesco.liste: al massimo {MAX_LISTE}")
        fuori["liste"] = [_testo(n, "innesco.liste", MAX_NOME) for n in d["liste"]]
    if "parole" in d:
        if not isinstance(d["parole"], list) or len(d["parole"]) > MAX_VOCI_LISTA:
            raise RegolaNonValida(f"innesco.parole: al massimo {MAX_VOCI_LISTA}")
        fuori["parole"] = [_testo(p, "innesco.parole", MAX_LUNG_VOCE) for p in d["parole"]]
    if "modo" in d:
        fuori["modo"] = _scelta(d["modo"], "innesco.modo", ("vietati", "permessi"))
    for nome, alto in (("numero", 10_000), ("secondi", 86_400), ("limite", 10_000)):
        if nome in d:
            fuori[nome] = _intero(d[nome], f"innesco.{nome}", 1, alto)
    return fuori


def controlla_regex(modello: Any) -> None:
    """Una regex del server: ≤ 260 caratteri, sintassi RE2 (niente ReDoS)."""
    if not isinstance(modello, str) or not modello or len(modello) > MAX_LUNG_REGEX:
        raise RegolaNonValida(f"regex: da 1 a {MAX_LUNG_REGEX} caratteri")
    import re2

    try:
        re2.compile(modello)
    except Exception as errore:
        raise RegolaNonValida(f"regex non valida in RE2: {str(errore)[:80]}") from None


# ---------------------------------------------------------------- regola

@dataclass(frozen=True)
class Regola:
    chiave: str
    tipo: str
    nome: str
    id: int | None = None
    guild_id: int | None = None
    evento: str = "messaggio"
    attiva: bool = True
    gruppo: str | None = None
    innesco: dict = field(default_factory=dict)
    condizioni: Condizioni = field(default_factory=Condizioni)
    azioni: tuple[Azione, ...] = ()
    contatore: Contatore | None = None
    calore: int = 0


def regola_da_json(dati: dict) -> Regola:
    """Legge una regola come la dà il database (colonne + JSON)."""
    d = _solo_chiavi(dati, {"id", "guild_id", "chiave", "tipo", "nome", "evento", "attiva", "gruppo",
                            "innesco", "condizioni", "azioni", "contatore", "calore"}, "regola")
    tipo = _scelta(d.get("tipo"), "tipo", TIPI_REGOLA)
    chiave = _testo(d.get("chiave"), "chiave", 40)
    if tipo == "personale" and not re.fullmatch(r"p:\d+", chiave):
        raise RegolaNonValida("chiave: una regola personale si chiama p:<numero>")
    gruppo = d.get("gruppo")
    return Regola(
        chiave=chiave, tipo=tipo, nome=_testo(d.get("nome"), "nome", MAX_NOME), id=d.get("id"), guild_id=d.get("guild_id"),
        evento=_scelta(d.get("evento", "messaggio"), "evento", EVENTI), attiva=bool(d.get("attiva", True)),
        gruppo=None if not gruppo else _testo(gruppo, "gruppo", MAX_GRUPPO),
        innesco=innesco_da_json(d.get("innesco")), condizioni=condizioni_da_json(d.get("condizioni")),
        azioni=azioni_da_json(d.get("azioni", [])), contatore=contatore_da_json(d.get("contatore")),
        calore=_intero(d.get("calore", 0), "calore", 0, 100),
    )


def regola_a_json(r: Regola) -> dict:
    return {
        "chiave": r.chiave, "tipo": r.tipo, "nome": r.nome, "evento": r.evento, "attiva": r.attiva, "gruppo": r.gruppo,
        "innesco": r.innesco, "condizioni": condizioni_a_json(r.condizioni),
        "azioni": [azione_a_json(a) for a in r.azioni], "contatore": contatore_a_json(r.contatore), "calore": r.calore,
    }


def azioni_dai_nomi_vecchi(nomi: tuple[str, ...] | list[str], mute_secondi: int) -> tuple[Azione, ...]:
    """Le azioni di prima (`delete`, `warn`, `mute`, `kick`, `ban`) nel formato nuovo, per la migrazione 0501 e i filtri."""
    mappa = {"delete": "cancella", "warn": "warn", "mute": "timeout", "kick": "kick", "ban": "ban"}
    fuori = []
    for nome in mappa:  # ordine di prima: delete, warn, mute, kick, ban
        if nome not in nomi:
            continue
        if nome == "mute":
            fuori.append(azione_da_json({"t": "timeout", "secondi": min(max(mute_secondi, 1), MAX_TIMEOUT_S)}))
        else:
            fuori.append(azione_da_json({"t": mappa[nome]}))
    return ordina_azioni(fuori)

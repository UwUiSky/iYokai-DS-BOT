"""
core/progressi_logic.py
=======================
Missioni (del giorno, della settimana, di tutto il server), serie di giorni con protezione, traguardi
(a categorie, anche nascosti), pass di 90 giorni con 50 livelli e traccia premium, profilo globale con
soli dati positivi. Funzioni pure, senza Discord né database.
Funzioni coperte: SPEC §23.17 (NF-41, D49, D51)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------- eventi contati
EVENTO_MESSAGGI = "messaggi"  # un messaggio che ha dato XP
EVENTO_VOCALE = "vocale"  # un minuto di presenza vocale che ha dato XP
EVENTO_DAILY = "daily"  # la ricompensa giornaliera riscossa
EVENTI = (EVENTO_MESSAGGI, EVENTO_VOCALE, EVENTO_DAILY)

SEZIONI = ("missioni", "traguardi", "serie", "pass", "globale")


# ---------------------------------------------------------------- missioni
PERIODO_GIORNO = "giorno"
PERIODO_SETTIMANA = "settimana"


@dataclass(frozen=True)
class Missione:
    chiave: str
    evento: str
    testo: str
    obiettivo: int
    premio: int  # monete
    periodo: str = PERIODO_GIORNO


MISSIONI_GIORNO: tuple[Missione, ...] = (
    Missione("messaggi", EVENTO_MESSAGGI, "Scrivi 15 messaggi che danno XP", 15, 30),
    Missione("vocale", EVENTO_VOCALE, "Passa 30 minuti in vocale", 30, 40),
    Missione("daily", EVENTO_DAILY, "Riscuoti la ricompensa giornaliera", 1, 20),
)
MISSIONI_SETTIMANA: tuple[Missione, ...] = (
    Missione("sett_messaggi", EVENTO_MESSAGGI, "Scrivi 120 messaggi che danno XP", 120, 150, PERIODO_SETTIMANA),
    Missione("sett_vocale", EVENTO_VOCALE, "Passa 300 minuti in vocale", 300, 200, PERIODO_SETTIMANA),
    Missione("sett_daily", EVENTO_DAILY, "Riscuoti la ricompensa giornaliera 5 volte", 5, 100, PERIODO_SETTIMANA),
)
MISSIONI: tuple[Missione, ...] = MISSIONI_GIORNO + MISSIONI_SETTIMANA
MISSIONE_PER_CHIAVE = {m.chiave: m for m in MISSIONI}


def missioni_dell_evento(evento: str) -> tuple[Missione, ...]:
    return tuple(m for m in MISSIONI if m.evento == evento)


def lunedi_di(giorno: date) -> date:
    """Il lunedì della settimana (ISO) del giorno: da qui si contano le missioni della settimana."""
    return giorno - timedelta(days=giorno.weekday())


def giorno_del_periodo(missione: Missione, giorno: date) -> date:
    """La data con cui si salva l'avanzamento: il giorno stesso, o il lunedì per le missioni della settimana."""
    return lunedi_di(giorno) if missione.periodo == PERIODO_SETTIMANA else giorno


def stato_missione(missione: Missione, progresso: int, riscattata: bool) -> str:
    """Una riga: casella, testo, avanzamento. Il progresso non supera mai l'obiettivo."""
    fatto = min(progresso, missione.obiettivo)
    casella = "✅" if riscattata else ("🎁" if fatto >= missione.obiettivo else "⬜")
    return f"{casella} {missione.testo} ({fatto}/{missione.obiettivo}, premio {missione.premio})"


# ---------------------------------------------------------------- missioni di tutto il server
OBIETTIVO_SERVER_BASE = 1000  # messaggi della settimana, di base; il server lo cambia
OBIETTIVO_SERVER_MIN = 50
OBIETTIVO_SERVER_MAX = 100_000
PARTECIPAZIONE_MIN_PERCENTO = 10  # per avere il premio serve il 10% della propria missione della settimana


@dataclass(frozen=True)
class MissioneServer:
    chiave: str
    evento: str
    testo: str  # con {n}, l'obiettivo del server
    percento: int  # dell'obiettivo base del server
    premio: int  # monete, a ognuno che ha partecipato
    personale: str  # la missione della settimana che misura il contributo di ognuno


MISSIONI_SERVER: tuple[MissioneServer, ...] = (
    MissioneServer("srv_messaggi", EVENTO_MESSAGGI, "Il server scrive {n} messaggi in settimana", 100, 60, "sett_messaggi"),
    MissioneServer("srv_vocale", EVENTO_VOCALE, "Il server passa {n} minuti in vocale in settimana", 60, 80, "sett_vocale"),
)
MISSIONE_SERVER_PER_CHIAVE = {m.chiave: m for m in MISSIONI_SERVER}


def obiettivo_server(missione: MissioneServer, base: int = OBIETTIVO_SERVER_BASE) -> int:
    base = max(OBIETTIVO_SERVER_MIN, min(OBIETTIVO_SERVER_MAX, base))
    return max(1, base * missione.percento // 100)


def minimo_partecipazione(missione: MissioneServer) -> int:
    """Quanto deve aver fatto ognuno nella sua missione della settimana per avere il premio."""
    personale = MISSIONE_PER_CHIAVE[missione.personale]
    return max(1, personale.obiettivo * PARTECIPAZIONE_MIN_PERCENTO // 100)


def stato_missione_server(
    missione: MissioneServer, base: int, totale: int, mio: int, riscattata: bool
) -> str:
    """Il totale del server conta ciò che ognuno ha fatto fino alla sua missione della settimana: nessuno vince da solo."""
    obiettivo = obiettivo_server(missione, base)
    fatto = min(totale, obiettivo)
    testo = missione.testo.format(n=obiettivo)
    if riscattata:
        return f"✅ {testo} ({fatto}/{obiettivo})"
    minimo = minimo_partecipazione(missione)
    if totale >= obiettivo:
        casella = "🎁" if mio >= minimo else "⬜"
        resto = "" if mio >= minimo else f", ti mancano {minimo - mio} per partecipare"
        return f"{casella} {testo} (fatto!, premio {missione.premio}{resto})"
    return f"⬜ {testo} ({fatto}/{obiettivo}, premio {missione.premio} se dai almeno {minimo})"


# ---------------------------------------------------------------- serie
SERIE_LIMITE_ORE = 36  # oltre queste ore dall'ultima riscossione la serie si azzera
SERIE_PROMEMORIA_ORE = 20  # a questo punto parte il promemoria, per chi l'ha chiesto
SERIE_PAUSA_MIN_ORE = 12  # due riscossioni più vicine di così sono la stessa
SCUDO_PREZZO = 150  # monete
SCUDI_MAX = 2
SERIE_MIN_PROMEMORIA = 3  # il promemoria serve da questa serie in su

# Premi solo estetici (oggetti del profilo): serie raggiunta -> id dell'oggetto.
PREMI_SERIE = {7: "scintilla", 14: "cometa", 30: "alba", 60: "aquila", 100: "cosmo"}


@dataclass(frozen=True)
class EsitoSerie:
    serie: int
    record: int
    scudi: int
    scudi_usati: int  # quelli consumati da questa riscossione
    contata: bool  # False se è la stessa riscossione di poco fa


def _ore(da: datetime, a: datetime) -> float:
    return (a - da).total_seconds() / 3600


def aggiorna_serie(serie: int, record: int, ultima: datetime | None, scudi: int, adesso: datetime) -> EsitoSerie:
    """
    Una riscossione giornaliera `adesso`. Entro 36 ore dall'ultima la serie sale; oltre, ogni scudo copre
    24 ore in più (e si consuma); se gli scudi non bastano la serie riparte da 1 e gli scudi restano.
    """
    if ultima is None:
        return EsitoSerie(1, max(record, 1), scudi, 0, True)
    ore = _ore(ultima, adesso)
    if ore < SERIE_PAUSA_MIN_ORE:
        return EsitoSerie(serie, max(record, serie), scudi, 0, False)
    if ore <= SERIE_LIMITE_ORE:
        return EsitoSerie(serie + 1, max(record, serie + 1), scudi, 0, True)
    saltati = math.ceil((ore - SERIE_LIMITE_ORE) / 24)
    if saltati <= scudi:
        return EsitoSerie(serie + 1, max(record, serie + 1), scudi - saltati, saltati, True)
    return EsitoSerie(1, max(record, 1), scudi, 0, True)


def serie_attuale(serie: int, ultima: datetime | None, scudi: int, adesso: datetime) -> int:
    """La serie che si vede adesso: se è passato troppo tempo (scudi compresi) la serie è finita."""
    if ultima is None or serie <= 0:
        return 0
    if _ore(ultima, adesso) > SERIE_LIMITE_ORE + 24 * scudi:
        return 0
    return serie


def scade_tra_ore(ultima: datetime | None, scudi: int, adesso: datetime) -> float | None:
    """Ore che restano prima che la serie si azzeri (con gli scudi); None se non c'è una serie."""
    if ultima is None:
        return None
    return max(0.0, SERIE_LIMITE_ORE + 24 * scudi - _ore(ultima, adesso))


def serve_promemoria(serie: int, ultima: datetime | None, scudi: int, adesso: datetime) -> bool:
    """Tra 20 ore dall'ultima riscossione e la perdita della serie, per chi ha una serie da difendere."""
    if ultima is None or serie < SERIE_MIN_PROMEMORIA:
        return False
    return SERIE_PROMEMORIA_ORE <= _ore(ultima, adesso) <= SERIE_LIMITE_ORE + 24 * scudi


def premi_serie_raggiunti(serie: int) -> list[str]:
    """Gli oggetti estetici delle tappe già superate (l'assegnazione non li dà due volte)."""
    return [oggetto for tappa, oggetto in sorted(PREMI_SERIE.items()) if serie >= tappa]


def prossima_tappa(serie: int) -> int | None:
    return next((t for t in sorted(PREMI_SERIE) if t > serie), None)


# ---------------------------------------------------------------- traguardi
@dataclass(frozen=True)
class Traguardo:
    chiave: str
    emoji: str
    testo: str
    statistica: str  # nome del campo di Statistiche
    soglia: int
    categoria: str = "Livello"
    nascosto: bool = False  # non si vede finché non lo si ottiene


@dataclass(frozen=True)
class Statistiche:
    livello: int = 0
    record_serie: int = 0
    missioni_completate: int = 0
    stagioni_complete: int = 0
    scudi_usati: int = 0
    missioni_settimana: int = 0
    missioni_server: int = 0
    pass_premium: int = 0


TRAGUARDI: tuple[Traguardo, ...] = (
    Traguardo("livello_5", "🌱", "Livello 5", "livello", 5),
    Traguardo("livello_10", "🌿", "Livello 10", "livello", 10),
    Traguardo("livello_25", "🌳", "Livello 25", "livello", 25),
    Traguardo("livello_50", "🏔️", "Livello 50", "livello", 50),
    Traguardo("serie_7", "🔥", "7 giorni di fila", "record_serie", 7, "Serie"),
    Traguardo("serie_30", "☄️", "30 giorni di fila", "record_serie", 30, "Serie"),
    Traguardo("serie_100", "🌌", "100 giorni di fila", "record_serie", 100, "Serie"),
    Traguardo("missioni_10", "🎯", "10 missioni completate", "missioni_completate", 10, "Missioni"),
    Traguardo("missioni_100", "🏆", "100 missioni completate", "missioni_completate", 100, "Missioni"),
    Traguardo("stagione_completa", "🎖️", "Un pass completato (50 livelli)", "stagioni_complete", 1, "Pass"),
    Traguardo("scudo_salvaserie", "🛡️", "Salvato dallo scudo", "scudi_usati", 1, "Segreti", True),
    Traguardo("settimana_piena", "📅", "Tutte le missioni di una settimana", "missioni_settimana", 3, "Segreti", True),
    Traguardo("squadra", "🤝", "Una missione di tutto il server", "missioni_server", 1, "Segreti", True),
    Traguardo("pass_premium", "💎", "Traccia premium del pass", "pass_premium", 1, "Segreti", True),
)
TRAGUARDO_PER_CHIAVE = {t.chiave: t for t in TRAGUARDI}
CATEGORIE = tuple(dict.fromkeys(t.categoria for t in TRAGUARDI))


def traguardi_raggiunti(stat: Statistiche) -> set[str]:
    """Le chiavi dei traguardi che le statistiche soddisfano."""
    return {t.chiave for t in TRAGUARDI if getattr(stat, t.statistica) >= t.soglia}


def testo_traguardi(ottenuti: set[str]) -> str:
    """
    Per categoria: quelli presi con la loro emoji, gli altri in grigio. I nascosti compaiono solo da
    ottenuti; di quelli ancora da scoprire si dice quanti sono.
    """
    righe: list[str] = []
    for categoria in CATEGORIE:
        voci = [t for t in TRAGUARDI if t.categoria == categoria]
        visibili = [t for t in voci if not t.nascosto or t.chiave in ottenuti]
        if not visibili:
            continue
        righe.append(f"**{categoria}**")
        righe += [f"{t.emoji} {t.testo}" if t.chiave in ottenuti else f"▫️ ~~{t.testo}~~" for t in visibili]
    nascosti = sum(1 for t in TRAGUARDI if t.nascosto and t.chiave not in ottenuti)
    if nascosti:
        righe.append(f"\n❓ {nascosti} traguardi nascosti da scoprire")
    return "\n".join(righe)


# ---------------------------------------------------------------- pass di 90 giorni
STAGIONE_GIORNI = 90
STAGIONE_INIZIO = date(2026, 1, 1)  # la prima stagione; le altre seguono ogni 90 giorni
PASS_LIVELLI = 50
PASS_XP_PER_LIVELLO = 500
PASS_PREZZO_PREMIUM = 500_000  # monete: in alternativa basta essere booster del server

# Premi estetici della traccia premium: livello -> id dell'oggetto del profilo.
PREMI_PASS_PREMIUM = {10: "sigillo", 25: "zenit", 50: "trofeo"}


def stagione_di(giorno: date) -> tuple[str, date, date]:
    """(chiave, primo giorno, ultimo giorno) della stagione che contiene `giorno`. La chiave è «AAAA-MM» dell'inizio."""
    indice = (giorno - STAGIONE_INIZIO).days // STAGIONE_GIORNI
    inizio = STAGIONE_INIZIO + timedelta(days=indice * STAGIONE_GIORNI)
    return f"{inizio.year:04d}-{inizio.month:02d}", inizio, inizio + timedelta(days=STAGIONE_GIORNI - 1)


def livelli_raggiunti(xp: int) -> int:
    return max(0, min(PASS_LIVELLI, xp // PASS_XP_PER_LIVELLO))


def premio_livello(n: int, premium: bool) -> int:
    """Monete del livello n: 10 + 2n sulla traccia libera, 20 + 4n su quella premium."""
    return 20 + 4 * n if premium else 10 + 2 * n


def monete_livelli(da_escluso: int, a_incluso: int, premium: bool) -> int:
    return sum(premio_livello(n, premium) for n in range(da_escluso + 1, a_incluso + 1))


def oggetti_livelli(da_escluso: int, a_incluso: int) -> list[str]:
    """Gli oggetti estetici della traccia premium nei livelli da `da_escluso + 1` a `a_incluso`."""
    return [oggetto for livello, oggetto in sorted(PREMI_PASS_PREMIUM.items()) if da_escluso < livello <= a_incluso]


def testo_pass(
    xp: int, liberi: int, premium_riscossi: int, premium: bool, fine: date, boost: bool = False
) -> str:
    raggiunti = livelli_raggiunti(xp)
    righe = [
        f"**Livello {raggiunti}/{PASS_LIVELLI}** · {xp} XP · la stagione finisce il {fine:%d/%m/%Y}",
        f"Traccia libera: {liberi} livelli riscossi"
        + (f", {raggiunti - liberi} da riscuotere ({monete_livelli(liberi, raggiunti, False)} coin)" if raggiunti > liberi else ""),
    ]
    if premium:
        righe.append(
            f"Traccia premium: {premium_riscossi} livelli riscossi"
            + (
                f", {raggiunti - premium_riscossi} da riscuotere ({monete_livelli(premium_riscossi, raggiunti, True)} coin)"
                if raggiunti > premium_riscossi else ""
            )
        )
    else:
        righe.append(
            f"Traccia premium: spenta. Si apre con il boost del server ({'ce l\'hai' if boost else 'non ce l\'hai'}) "
            f"o con {PASS_PREZZO_PREMIUM:,} coin. Ha il doppio delle coin e premi estetici ai livelli "
            + ", ".join(str(n) for n in sorted(PREMI_PASS_PREMIUM)) + "."
        )
    if raggiunti < PASS_LIVELLI:
        righe.append(f"Al livello {raggiunti + 1} mancano {(raggiunti + 1) * PASS_XP_PER_LIVELLO - xp} XP.")
    return "\n".join(righe)


# ---------------------------------------------------------------- profilo globale (solo dati positivi)
@dataclass(frozen=True)
class ProfiloGlobale:
    server: int  # in quanti server ha un livello
    livello_massimo: int
    record_serie: int
    traguardi: int  # numero di traguardi (chiavi diverse) ottenuti in almeno un server


def testo_profilo_globale(p: ProfiloGlobale) -> str:
    """Solo cose belle e solo numeri: niente nomi di server, niente sanzioni, niente monete."""
    return (
        f"Server in cui giochi: **{p.server}**\n"
        f"Livello più alto: **{p.livello_massimo}**\n"
        f"Serie più lunga: **{p.record_serie}** giorni\n"
        f"Traguardi diversi ottenuti: **{p.traguardi}** su {len(TRAGUARDI)}"
    )

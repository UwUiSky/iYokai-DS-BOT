"""
core/leveling_logic.py
=========================
Logica pura per il sistema di livelli/economia — stesso principio di
core/permissions.py, core/automod_sync.py, core/voice_temp_logic.py:
solo numeri e stringhe qui dentro, niente oggetti discord.py.

Design del reset mensile: NESSUN RESET
------------------------------------------
Invece di azzerare un contatore ogni mese (che richiede un job
schedulato — e un job che fallisce silenziosamente lascerebbe la
classifica mensile bloccata sui dati del mese sbagliato), ogni
guadagno di XP/coin viene registrato in una riga per-periodo
(vedi period_key() più sotto: "2026-09", "2026-10", ...). La
classifica mensile è solo una query filtrata sul periodo corrente;
il mese "si resetta" da solo perché un nuovo mese è semplicemente
un nuovo period_key senza righe, non uno stato da azzerare.
"""

# DA FARE (issue #65, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §9 (Livelli, economia,
#   clan).

from __future__ import annotations

import math
import random
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


def period_key(when: datetime | None = None) -> str:
    """
    Chiave del periodo (mese) corrente, es. "2026-09". Sempre in UTC
    per evitare ambiguità tra fusi orari diversi di membri dello
    stesso server.
    """
    moment = when or datetime.now(timezone.utc)
    return f"{moment.year:04d}-{moment.month:02d}"


def week_key(when: datetime | None = None) -> str:
    """
    Chiave della settimana ISO corrente, es. "2026-W39". Usata per il
    decadimento settimanale del 10% sui coin personali (SPEC.md
    §15.14 economia — decadimento distinto da quello mensile della
    tesoreria di clan, core/guild_clan_logic.py). Sempre in UTC, come
    period_key(), per evitare ambiguità tra fusi orari diversi di
    membri dello stesso server: la settimana ISO inizia il lunedì.
    """
    moment = when or datetime.now(timezone.utc)
    iso_year, iso_week, _ = moment.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}"


def previous_period_start(when: datetime | None = None) -> datetime:
    """
    Inizio (UTC) del mese precedente a quello di `when`. Serve ai
    decadimenti: chi è nato dopo questa data non ha ancora vissuto un
    mese intero, quindi il decadimento mensile non lo tocca.
    """
    moment = when or datetime.now(timezone.utc)
    inizio_mese = moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ultimo_giorno_mese_prima = inizio_mese - timedelta(days=1)
    return ultimo_giorno_mese_prima.replace(day=1)


def previous_week_start(when: datetime | None = None) -> datetime:
    """
    Inizio (lunedì, 00:00 UTC) della settimana ISO precedente a quella
    di `when`. Chi è nato dopo questa data non ha ancora vissuto una
    settimana intera, quindi il decadimento settimanale non lo tocca.
    """
    moment = when or datetime.now(timezone.utc)
    inizio_settimana = (moment - timedelta(days=moment.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return inizio_settimana - timedelta(weeks=1)


# ======================================================================
# XP testuale — cooldown anti-spam
# ======================================================================

TEXT_XP_COOLDOWN_SECONDS = 60
TEXT_XP_AMOUNT = 15


def can_earn_text_xp(
    last_xp_at: datetime | None,
    now: datetime | None = None,
    cooldown_seconds: int = TEXT_XP_COOLDOWN_SECONDS,
) -> bool:
    """
    True se è passato abbastanza tempo dall'ultimo guadagno di XP
    testuale di questo utente. Impedisce che scrivere messaggi a
    raffica dia XP a raffica — il guadagno resta legato al tempo
    trascorso, non al numero di messaggi.
    """
    if last_xp_at is None:
        return True
    current = now or datetime.now(timezone.utc)
    return (current - last_xp_at).total_seconds() >= cooldown_seconds


# ======================================================================
# XP vocale — idoneità e conteggio, con le regole anti-farm già decise
# ======================================================================

VOICE_XP_PER_MINUTE = 5
VOICE_COINS_PER_MINUTE = 2
MAX_CONSECUTIVE_MINUTES_SAME_CHANNEL = 120  # 2 ore, poi azzeramento
DAILY_CAP_MINUTES = 360  # 6 ore


def is_eligible_for_voice_xp(
    is_self_deaf: bool,
    is_afk_channel: bool,
    other_members_not_self_muted: int,
    min_persone: int = 2,
    anti_farm: bool = True,
) -> bool:
    """
    Le condizioni anti-farm decise in fase di progettazione, tutte
    necessarie insieme:
    - l'utente non è self_deaf (chi farma si assorda per non sentire)
    - il canale non è il canale AFK del server
    - c'è almeno un'ALTRA persona nel canale che non è self_mute
      (un canale con solo bot silenziati o solo l'utente stesso non
      conta come attività reale)
    LIV-011: `min_persone` è la soglia di persone nel canale (lui compreso), da 1 a 10.
    LIV-012: con `anti_farm` spento non conta l'essere assordati (e il chiamante conta
    anche chi è muto); il canale AFK resta escluso, e i tetti di minuti restano.
    """
    if is_afk_channel or (anti_farm and is_self_deaf):
        return False
    return other_members_not_self_muted >= max(0, min_persone - 1)


def contesto_con_xp(i: "LevelingSettings", tipo: str) -> bool:
    """LIV-014/015/016: se i messaggi di questo tipo di canale danno XP (thread, forum, chat vocale)."""
    return {
        "thread": i.xp_thread, "forum": i.xp_forum, "chat_vocale": i.xp_chat_vocale,
    }.get(tipo, True)


@dataclass(frozen=True)
class VoiceMinuteResult:
    """Risultato del conteggio di un minuto di attività vocale."""
    xp_granted: int
    coins_granted: int
    new_consecutive_minutes: int
    new_minutes_today: int
    capped: bool  # True se il cap giornaliero ha bloccato il guadagno


def compute_voice_minute(
    consecutive_minutes_in_channel: int,
    minutes_today: int,
    changed_channel: bool,
    cap_minuti: int = DAILY_CAP_MINUTES,
) -> VoiceMinuteResult:
    """
    Calcola l'esito di UN minuto di presenza vocale idonea (l'idoneità
    di base è già stata verificata da is_eligible_for_voice_xp prima
    di chiamare questa funzione). Gestisce le due regole restanti:

    - se l'utente ha cambiato canale rispetto al minuto precedente,
      il contatore "minuti consecutivi nello stesso canale" riparte
      da 1 (non da 0: questo stesso minuto conta)
    - se ha superato le 2 ore consecutive nello STESSO canale, non
      guadagna XP per questo minuto (ma il contatore continua a
      salire, così se il cap fosse innalzato in futuro il
      comportamento resterebbe coerente senza bisogno di logica
      aggiuntiva)
    - se ha raggiunto il cap giornaliero di minuti conteggiabili, non
      guadagna XP indipendentemente da tutto il resto
    """
    new_consecutive = 1 if changed_channel else consecutive_minutes_in_channel + 1
    new_minutes_today = minutes_today + 1

    if new_consecutive > MAX_CONSECUTIVE_MINUTES_SAME_CHANNEL:
        return VoiceMinuteResult(0, 0, new_consecutive, new_minutes_today, capped=False)

    if minutes_today >= cap_minuti:  # ECO-161: tetto scelto dal server
        return VoiceMinuteResult(0, 0, new_consecutive, new_minutes_today, capped=True)

    return VoiceMinuteResult(
        VOICE_XP_PER_MINUTE, VOICE_COINS_PER_MINUTE, new_consecutive, new_minutes_today, capped=False
    )


# ======================================================================
# Formula di livello
# ======================================================================
# Soglia progressiva: livello n richiede 5*n^2 + 50*n XP cumulativi
# (una curva quadratica moderata — comune per i bot di livelli,
# cresce abbastanza da rendere i livelli alti un traguardo reale
# senza diventare proibitiva nei primi livelli).


FORMULE = ("classica", "lineare", "esponenziale", "costante")  # LIV-004
COSTO_COSTANTE = 200  # LIV-004: XP di ogni livello con la formula "costante"
LIVELLO_TETTO_ESPONENZIALE = 3000  # oltre, la potenza non entra più in un numero decimale


def xp_for_level(level: int, formula: str = "classica") -> int:
    """
    XP cumulativo necessario per RAGGIUNGERE questo livello (LIV-004: `formula`
    sceglie la curva; una formula sconosciuta vale come "classica").
    classica 5L^2+50L, lineare 25L^2+75L, costante 200L, esponenziale 500(1,2^L-1).
    """
    if level <= 0:
        return 0
    if formula == "lineare":
        return 25 * level * level + 75 * level
    if formula == "costante":
        return COSTO_COSTANTE * level
    if formula == "esponenziale":
        return int(500 * (1.2 ** min(level, LIVELLO_TETTO_ESPONENZIALE) - 1))
    return 5 * level * level + 50 * level


LIVELLO_MASSIMO = 1000  # tetto assoluto dei livelli impostabili a mano


def _livello_da_xp_senza_tetto(total_xp: int, formula: str) -> int:
    if formula == "costante":
        return total_xp // COSTO_COSTANTE
    if formula == "lineare":
        level = max(0, (math.isqrt(5625 + 100 * total_xp) - 75) // 50)
    elif formula == "esponenziale":
        # Ricerca binaria: la curva cresce a ogni passo.
        basso, alto = 0, LIVELLO_TETTO_ESPONENZIALE
        while basso < alto:
            medio = (basso + alto + 1) // 2
            if xp_for_level(medio, formula) <= total_xp:
                basso = medio
            else:
                alto = medio - 1
        return basso
    else:
        level = max(0, (math.isqrt(2500 + 20 * total_xp) - 50) // 10)
    while level > 0 and xp_for_level(level, formula) > total_xp:
        level -= 1
    while xp_for_level(level + 1, formula) <= total_xp:
        level += 1
    return level


def level_for_xp(total_xp: int, max_level: int = 0, formula: str = "classica") -> int:
    """
    Livello corrispondente a un totale di XP (`max_level` > 0 è il tetto
    del server, LIV-005; 0 = nessun tetto; `formula`: LIV-004). Formule
    chiuse con radice intera e correzione di un passo: nessun ciclo sul
    numero di livelli, costa lo stesso con 1.000 XP o con 10^15.
    """
    if total_xp <= 0:
        return 0
    level = _livello_da_xp_senza_tetto(total_xp, formula)
    if max_level:
        level = min(level, max_level)
    return level


def did_level_up(
    xp_before: int, xp_after: int, max_level: int = 0, formula: str = "classica"
) -> tuple[bool, int]:
    """
    Restituisce (è salito di livello, nuovo livello). Un singolo
    guadagno di XP potrebbe in teoria far salire più di un livello
    in un colpo solo (raro con gli importi in gioco, ma possibile con
    bonus grandi) — level_for_xp gestisce comunque il caso corretto.
    """
    level_before = level_for_xp(xp_before, max_level, formula)
    level_after = level_for_xp(xp_after, max_level, formula)
    return (level_after > level_before), level_after


@dataclass(frozen=True)
class StimaLivello:
    xp_mancanti: int
    messaggi: int
    minuti_vocale: int | None  # None se in vocale non si guadagnano XP
    secondi_minimi_testo: int  # con un messaggio a ogni attesa, senza moltiplicatori


def stima_per_livello(
    xp_attuale: int,
    livello_obiettivo: int,
    xp_per_messaggio: int,
    attesa_secondi: int,
    xp_voce_minuto: int,
    formula: str = "classica",
) -> StimaLivello:
    """Quanto manca a un livello (LIV-074): XP, messaggi e minuti in vocale, senza moltiplicatori."""
    mancanti = max(0, xp_for_level(livello_obiettivo, formula) - xp_attuale)
    messaggi = -(-mancanti // xp_per_messaggio) if xp_per_messaggio > 0 else 0
    minuti = -(-mancanti // xp_voce_minuto) if xp_voce_minuto > 0 else None
    return StimaLivello(mancanti, messaggi, minuti, messaggi * attesa_secondi)


def xp_dopo_modifica(
    xp_attuale: int, azione: str, valore: int, max_level: int = 0, formula: str = "classica"
) -> int:
    """
    Gli XP totali dopo una modifica dello staff (LIV-064..067). Mai sotto
    zero. "livello" porta all'inizio del livello (con il tetto del server);
    "xp_nel_livello" tiene il livello attuale e cambia solo gli XP al suo interno.
    """
    if azione == "aggiungi":
        return xp_attuale + valore
    if azione == "togli":
        return max(0, xp_attuale - valore)
    if azione == "livello":
        tetto = min(valore, LIVELLO_MASSIMO)
        return xp_for_level(min(tetto, max_level) if max_level else tetto, formula)
    if azione == "xp_nel_livello":
        livello = level_for_xp(xp_attuale, max_level, formula)
        base = xp_for_level(livello, formula)
        ampiezza = xp_for_level(livello + 1, formula) - base
        return base + min(valore, ampiezza - 1)
    if azione == "azzera":
        return 0
    raise ValueError(f"Azione sugli XP sconosciuta: {azione}")


def monete_dopo_modifica(saldo: int, azione: str, valore: int) -> int:
    """Il saldo dopo una modifica dello staff (ECO-009, ECO-011). Mai negativo."""
    if azione == "aggiungi":
        return saldo + valore
    if azione == "togli":
        return max(0, saldo - valore)
    if azione == "imposta":
        return max(0, valore)
    if azione == "azzera":
        return 0
    raise ValueError(f"Azione sulle monete sconosciuta: {azione}")


# ======================================================================
# Economy — daily / work
# ======================================================================

DAILY_COOLDOWN_SECONDS = 24 * 3600
DAILY_REWARD_COINS = 200

WORK_COOLDOWN_SECONDS = 3600
WORK_REWARD_MIN = 20
WORK_REWARD_MAX = 80


# ======================================================================
# Economy — decadimento settimanale coin personali
# ======================================================================

WEEKLY_PERSONAL_DECAY_RATE = 0.10
MINIMUM_BALANCE_AFTER_DECAY = 1


def apply_weekly_personal_decay(balance: int) -> int:
    """
    Decadimento settimanale del 10% sui coin PERSONALI di chiunque
    nel server (confermato esplicitamente dall'utente: chiunque, non
    solo chi è in un clan — la tesoreria di clan ha invece un
    decadimento MENSILE separato, core/guild_clan_logic.py). Non
    scende mai sotto 1 (mai zero, mai negativo), sempre un intero
    (mai un decimale — 10% di 105 diventa 10 o 11, non 10.5).

    Chi ha già un saldo <= 1 non perde nulla: non c'è "10% di 1" che
    abbia senso restituire come intero senza svuotare comunque il
    saldo a zero, quindi il floor si applica prima ancora di
    calcolare la sottrazione.
    """
    if balance <= MINIMUM_BALANCE_AFTER_DECAY:
        return balance
    decaduto = balance - round(balance * WEEKLY_PERSONAL_DECAY_RATE)
    return max(decaduto, MINIMUM_BALANCE_AFTER_DECAY)


def can_claim_daily(last_daily_at: datetime | None, now: datetime | None = None) -> bool:
    if last_daily_at is None:
        return True
    current = now or datetime.now(timezone.utc)
    return (current - last_daily_at).total_seconds() >= DAILY_COOLDOWN_SECONDS


def can_claim_work(last_work_at: datetime | None, now: datetime | None = None) -> bool:
    if last_work_at is None:
        return True
    current = now or datetime.now(timezone.utc)
    return (current - last_work_at).total_seconds() >= WORK_COOLDOWN_SECONDS


def seconds_until_next_claim(
    last_claim_at: datetime | None, cooldown_seconds: int, now: datetime | None = None
) -> int:
    """
    Quanti secondi mancano al prossimo claim possibile (0 se già
    disponibile). Usato per mostrare all'utente un messaggio tipo
    'riprova tra 3h 12m' invece di un generico 'non ancora'.
    """
    if last_claim_at is None:
        return 0
    current = now or datetime.now(timezone.utc)
    elapsed = (current - last_claim_at).total_seconds()
    remaining = cooldown_seconds - elapsed
    return max(0, int(remaining))


# ======================================================================
# Impostazioni dei livelli per server (NF-15, #86)
# ======================================================================
MODI_ANNUNCIO = ("spento", "canale_corrente", "dm", "canale_scelto")
MODI_PREMI = ("accumula", "sostituisci")
MODI_AZZERA_SU = ("nessuno", "uscita", "ban", "entrambi")  # LIV-070
MODI_MOLTIPLICATORI = ("somma", "massimo")
MODI_XP_MESSAGGIO = ("fisso", "parola")  # LIV-006
MODI_CANALI = ("tutti", "solo_questi")  # LIV-021
MAX_PREFISSI = 10  # LIV-018
MAX_LUNGHEZZA_PREFISSO = 8
MAX_REAZIONI_AL_GIORNO = 50  # LIV-008/009: reazioni che danno XP in un giorno, per persona e per verso
TETTO_XP_MESSAGGIO = 150  # LIV-006/007: mai di più per un solo messaggio

# Minimo e massimo di ogni numero configurabile. Un solo posto: lo usano
# i comandi, l'archivio e (D16) il futuro pannello web.
LIMITI_IMPOSTAZIONI = {
    "text_xp": (1, 100),
    "text_xp_max": (0, 100),  # LIV-001: 0 = importo fisso
    "xp_percentuale": (25, 500),  # LIV-003: velocità generale, in percentuale
    "text_cooldown_seconds": (10, 3600),  # LIV-002
    "voice_xp_per_minute": (0, 50),
    "voice_coins_per_minute": (0, 50),
    "levelup_min_level": (0, 1000),
    "levelup_every": (1, 100),
    "daily_coins": (0, 10_000),
    "work_min": (0, 10_000),
    "work_max": (0, 10_000),
    "max_level": (0, 1000),  # 0 = nessun tetto
    "xp_per_parola": (1, 10),  # LIV-006
    "parole_max": (1, 100),  # LIV-006: parole contate per messaggio
    "voce_min_persone": (1, 10),  # LIV-011
    "xp_reazione_messa": (0, 20),  # LIV-008: 0 = spento
    "xp_reazione_ricevuta": (0, 20),  # LIV-009: 0 = spento
    "reazioni_attesa": (60, 3600),  # LIV-008/009
    "bonus_impegno": (0, 50),  # LIV-007: 0 = spento
    "impegno_caratteri": (20, 2000),  # LIV-007
    "pay_tax_pct": (0, 50),  # ECO-015: percentuale che va alla cassa del server
    "pay_max": (0, 1_000_000),  # ECO-015: tetto per trasferimento, 0 = nessuno
    "pay_min": (0, 1_000_000),  # ECO-015: minimo per trasferimento, 0 = nessuno
    "saldo_iniziale": (0, 1_000_000),  # ECO-002: monete date a chi entra, 0 = niente
    "tetto_saldo": (0, 1_000_000_000),  # ECO-003: saldo massimo, 0 = nessun tetto
    "puntata_min": (1, 1_000_000),  # ECO-021
    "puntata_max": (1, 1_000_000),  # ECO-021
    "attesa_gioco": (0, 3600),  # ECO-022: secondi tra due partite
    "daily_ore": (1, 720),  # ECO-024: ogni quante ore si riscuote il premio periodico
    "work_attesa_min": (1, 1440),  # ECO-019/028: minuti tra due lavori
    "daily_bonus_serie": (0, 1000),  # ECO-025: monete in più per ogni giorno di serie
    "daily_serie_max": (1, 365),  # ECO-025: giorni di serie che contano
    "settimanale_coins": (0, 100_000),  # ECO-026: 0 = spento
    "mensile_coins": (0, 1_000_000),  # ECO-026: 0 = spento
    "drop_per_mille": (0, 100),  # ECO-053: probabilità per messaggio, in millesimi (5 = 0,5%); 0 = spento
    "drop_min": (1, 100_000),  # ECO-053
    "drop_max": (1, 100_000),  # ECO-053
    "drop_pausa": (0, 3600),  # ECO-053: secondi minimi tra due drop nello stesso server
    "furto_percentuale": (1, 50),  # ECO-031: quota dei contanti della vittima che si può rubare
    "furto_successo": (1, 90),  # ECO-031: probabilità (%) che il furto riesca
    "colpo_successo": (1, 90),  # ECO-030: probabilità (%) che il colpo riesca
    "msg_coins": (0, 100),  # ECO-033: monete per messaggio nei canali scelti, 0 = spento
    "msg_coins_pausa": (10, 3600),  # ECO-033: secondi tra due messaggi che pagano, per persona
    "msg_coins_tetto": (1, 10_000),  # ECO-033: monete al giorno per persona
    "stipendio_ora": (0, 23),  # ECO-037: ora (UTC) del pagamento automatico
    "lotteria_prezzo": (0, 10_000),  # ECO-118: prezzo di un biglietto, 0 = lotteria spenta
    "rimborso_pct": (0, 20),  # ECO-117: quota delle perdite nette che torna indietro
    "voce_max_minuti": (30, 1440),  # ECO-161: minuti al giorno in vocale che danno XP e monete
    "controllo_per_mille": (0, 500),  # ECO-158: probabilità (in millesimi) del controllo anti-automazione, 0 = spento
}
MODI_SALDO_USCITA = ("tieni", "cancella")  # ECO-014
MAX_NOME_MONETA = 20  # ECO-001
MAX_RUOLI_PER_LIVELLO = 3  # LIV-042
MAX_TESTO_ANNUNCIO = 1800  # LIV-034: lascia posto ai valori sostituiti (messaggio ≤ 2000)
FATTORE_MINIMO = 0.1
FATTORE_MASSIMO = 10.0
MAX_REGOLE_PER_TIPO = 25  # 25 scelte per opzione (LIMITI.md)

TIPI_REGOLA = ("canale_escluso", "ruolo_escluso", "mult_canale", "mult_ruolo")
TIPI_REGOLA_CON_FATTORE = ("mult_canale", "mult_ruolo")


@dataclass(frozen=True)
class LevelingSettings:
    """Impostazioni di un server. I valori di partenza sono il comportamento di prima."""

    text_xp: int = TEXT_XP_AMOUNT
    text_cooldown_seconds: int = TEXT_XP_COOLDOWN_SECONDS
    text_xp_max: int = 0  # LIV-001: se più del minimo, l'XP è a sorte tra i due
    xp_percentuale: int = 100  # LIV-003
    voice_xp_per_minute: int = VOICE_XP_PER_MINUTE
    voice_coins_per_minute: int = VOICE_COINS_PER_MINUTE
    levelup_mode: str = "canale_corrente"
    levelup_channel_id: int | None = None
    levelup_min_level: int = 0
    levelup_every: int = 1
    levelup_only_rewards: bool = False
    reward_mode: str = "accumula"
    multiplier_mode: str = "somma"
    daily_coins: int = DAILY_REWARD_COINS
    work_min: int = WORK_REWARD_MIN
    work_max: int = WORK_REWARD_MAX
    max_level: int = 0
    shop_confirm: bool = False  # ECO-069: chiede conferma prima di comprare
    card_colore: str = ""  # LIV-056: colore predefinito delle card: "#RRGGBB", "auto" (icona) o vuoto
    card_images: bool = True  # NF-12: sfondi con immagine propria su card e profilo
    currency_name: str = "coin"  # ECO-001: come il server chiama la moneta
    pay_tax_pct: int = 0  # ECO-015
    pay_max: int = 0  # ECO-015
    pay_min: int = 0  # ECO-015
    azzera_su: str = "nessuno"  # LIV-070: azzera gli XP di chi esce o viene bannato
    copia_su_uscita: bool = False  # LIV-070: tiene una copia di 30 giorni di quegli XP
    blocca_xp: bool = False  # LIV-071: gli XP a mano li cambia solo il proprietario del server
    blocca_azzeramento: bool = False  # LIV-071: azzerare e ripristinare solo il proprietario
    formula: str = "classica"  # LIV-004
    xp_modo: str = "fisso"  # LIV-006: "parola" = XP a parola
    xp_per_parola: int = 1  # LIV-006
    parole_max: int = 30  # LIV-006
    bonus_impegno: int = 0  # LIV-007: 0 = spento
    impegno_caratteri: int = 200  # LIV-007
    voce_min_persone: int = 2  # LIV-011: persone nel canale vocale (lui compreso)
    anti_farm: bool = True  # LIV-012
    xp_thread: bool = True  # LIV-014
    xp_forum: bool = True  # LIV-015
    xp_chat_vocale: bool = True  # LIV-016
    xp_reazione_messa: int = 0  # LIV-008
    xp_reazione_ricevuta: int = 0  # LIV-009
    reazioni_attesa: int = 300  # LIV-008/009: secondi tra due reazioni che danno XP, per persona
    xp_comandi: bool = False  # LIV-017: XP per i comandi slash
    prefissi_ignorati: tuple = ()  # LIV-018
    canali_modo: str = "tutti"  # LIV-021: "solo_questi" = l'elenco dei canali è una lista bianca
    levelup_testo: str = ""  # LIV-034: testo dell'annuncio con segnaposto; vuoto = quello di base
    saldo_iniziale: int = 0  # ECO-002
    tetto_saldo: int = 0  # ECO-003
    puntata_min: int = 1  # ECO-021
    puntata_max: int = 10_000  # ECO-021
    attesa_gioco: int = 5  # ECO-022
    daily_ore: int = 24  # ECO-024
    work_attesa_min: int = 60  # ECO-019/028
    daily_bonus_serie: int = 0  # ECO-025
    daily_serie_max: int = 30  # ECO-025
    settimanale_coins: int = 0  # ECO-026
    mensile_coins: int = 0  # ECO-026
    saldo_uscita: str = "tieni"  # ECO-014: cosa fare del saldo di chi esce
    drop_per_mille: int = 5  # ECO-053
    drop_min: int = 10  # ECO-053
    drop_max: int = 50  # ECO-053
    drop_pausa: int = 0  # ECO-053
    drop_canale_id: int | None = None  # ECO-053: solo in questo canale (None = ovunque)
    furto_attivo: bool = False  # ECO-031: spento di base
    furto_percentuale: int = 10  # ECO-031
    furto_successo: int = 40  # ECO-031
    colpo_successo: int = 40  # ECO-030
    msg_coins: int = 0  # ECO-033
    msg_coins_pausa: int = 60  # ECO-033
    msg_coins_tetto: int = 200  # ECO-033
    stipendio_auto: bool = False  # ECO-035
    stipendio_ora: int = 12  # ECO-037
    lotteria_prezzo: int = 0  # ECO-118
    rimborso_pct: int = 0  # ECO-117
    voce_max_minuti: int = 360  # ECO-161
    controllo_per_mille: int = 0  # ECO-158


@dataclass(frozen=True)
class ConfigLivelli:
    """Impostazioni più regole (canali e ruoli esclusi, moltiplicatori) di un server."""

    impostazioni: LevelingSettings = field(default_factory=LevelingSettings)
    canali_esclusi: frozenset = frozenset()
    ruoli_esclusi: frozenset = frozenset()
    mult_canali: dict = field(default_factory=dict)
    mult_ruoli: dict = field(default_factory=dict)

    def fattori_attivi(self, channel_ids, role_ids) -> list[float]:
        """
        I fattori che valgono per questo canale e per questi ruoli.
        `channel_ids`: un id o la lista di id_canali_per_le_regole (vale la
        prima regola trovata, dal più specifico).
        """
        if isinstance(channel_ids, int):
            channel_ids = [channel_ids]
        fattori = []
        for cid in channel_ids:
            if cid in self.mult_canali:
                fattori.append(self.mult_canali[cid])
                break
        fattori.extend(self.mult_ruoli[r] for r in role_ids if r in self.mult_ruoli)
        return fattori

    def moltiplicatore(self, channel_ids, role_ids) -> float:
        base = moltiplicatore_xp(
            self.impostazioni.multiplier_mode, self.fattori_attivi(channel_ids, role_ids)
        )
        return round(base * self.impostazioni.xp_percentuale / 100, 4)  # LIV-003

    def e_escluso(self, channel_ids, role_ids) -> bool:
        """
        Escluso se lo è il canale (o il suo canale di origine o la sua categoria) o un ruolo.
        LIV-021: con `canali_modo` "solo_questi" l'elenco dei canali vale al contrario
        (solo quelli danno XP); un elenco vuoto non blocca nessuno.
        """
        if isinstance(channel_ids, int):
            channel_ids = [channel_ids]
        if any(r in self.ruoli_esclusi for r in role_ids):
            return True
        nell_elenco = any(c in self.canali_esclusi for c in channel_ids)
        if self.impostazioni.canali_modo == "solo_questi" and self.canali_esclusi:
            return not nell_elenco
        return nell_elenco


_PAROLA = re.compile(r"[^\W_]{3,}")


def xp_messaggio(i: LevelingSettings, testo: str, ha_immagine: bool, scelta=random.randint) -> int:
    """
    XP di base di un messaggio, prima del moltiplicatore. LIV-006: in modo "parola"
    contano le parole da 3 lettere in su (al massimo `parole_max`). LIV-007: bonus
    fisso, una volta sola, se il messaggio è lungo o ha un'immagine. Mai oltre
    TETTO_XP_MESSAGGIO.
    """
    testo = (testo or "")[:4000]
    if i.xp_modo == "parola":
        parole = min(len(_PAROLA.findall(testo)), i.parole_max)
        base = min(parole * i.xp_per_parola, LIMITI_IMPOSTAZIONI["text_xp"][1])
    else:
        # LIV-001: con un massimo più alto del minimo l'XP è a sorte tra i due.
        base = scelta(i.text_xp, i.text_xp_max) if i.text_xp_max > i.text_xp else i.text_xp
    if i.bonus_impegno and (ha_immagine or len(testo) >= i.impegno_caratteri):
        base += i.bonus_impegno
    return min(base, TETTO_XP_MESSAGGIO)


def ha_prefisso_ignorato(testo: str, prefissi) -> bool:
    """LIV-018: il messaggio inizia con il prefisso di un altro bot."""
    inizio = (testo or "").lstrip()
    return any(p and inizio.startswith(p) for p in prefissi)


def prefisso_valido(testo: str) -> str | None:
    """LIV-018: il prefisso pulito, o None. Niente spazi dentro né caratteri invisibili; solo lettere/cifre: almeno 2."""
    p = (testo or "").strip()
    if not p or len(p) > MAX_LUNGHEZZA_PREFISSO:
        return None
    if any(c.isspace() or unicodedata.category(c)[0] in "CZ" for c in p):
        return None
    if p.isalnum() and len(p) < 2:
        return None
    if p.isalnum() and p.isdigit():
        return None
    return p


def moltiplicatore_xp(modo: str, fattori: list[float]) -> float:
    """
    "somma": 1 più lo scarto di ogni fattore (2.0 e 1.5 danno 2.5).
    "massimo": vale solo il più alto. Senza fattori: 1.
    """
    if not fattori:
        return 1.0
    if modo == "massimo":
        return max(fattori)
    return round(1.0 + sum(f - 1.0 for f in fattori), 4)


def xp_con_moltiplicatore(base: int, moltiplicatore: float) -> int:
    """XP intero; il mezzo arrotonda in su, mai sotto zero."""
    return max(0, int(base * moltiplicatore + 0.5))


def deve_annunciare(
    livello: int,
    impostazioni: LevelingSettings,
    ha_ruolo_premio: bool,
    livello_precedente: int | None = None,
) -> bool:
    """
    Se il level-up a `livello` va annunciato (spento, livello minimo, ogni N,
    solo premi). Se in un colpo solo si salta più di un livello
    (`livello_precedente` più basso di uno), "ogni N" conta ogni livello
    saltato; `ha_ruolo_premio` lo calcola il chiamante su tutti i saltati.
    """
    if impostazioni.levelup_mode == "spento":
        return False
    if livello < impostazioni.levelup_min_level:
        return False
    prima = livello - 1 if livello_precedente is None else min(livello_precedente, livello - 1)
    ogni = impostazioni.levelup_every
    if livello // ogni <= prima // ogni:  # nessun multiplo di N tra i livelli saltati
        return False
    if impostazioni.levelup_only_rewards and not ha_ruolo_premio:
        return False
    return True


_BLOCCO_PREMIO = re.compile(r"\{premio:((?:[^{}]|\{ruolo_premio\})*)\}")
_SEGNAPOSTO = re.compile(r"\{(utente|livello|xp|server|ruolo_premio)\}")


def rendi_annuncio(
    testo: str, *, utente: str, livello: int, server: str, ruoli_premio: list[str], xp: int = 0
) -> str:
    """
    LIV-034, LIV-031: il testo dell'annuncio con i segnaposto {utente} {livello} {xp} {server} {ruolo_premio}.
    Il blocco {premio:...} compare solo se il livello dà un ruolo. Una sola passata: un valore
    che contiene un segnaposto (il nome del server) non viene sostituito di nuovo.
    """
    valori = {"utente": utente, "livello": str(livello), "xp": str(xp), "server": server, "ruolo_premio": ", ".join(ruoli_premio)}
    senza_blocchi = _BLOCCO_PREMIO.sub(lambda m: m.group(1) if ruoli_premio else "", testo)
    return _SEGNAPOSTO.sub(lambda m: valori[m.group(1)], senza_blocchi)[:2000]


def id_canali_per_le_regole(canale) -> list[int]:
    """
    Gli id che contano per esclusioni e moltiplicatori di un canale, dal più
    specifico: il canale stesso, il canale di origine di un thread o di un
    post di forum, la categoria (le regole su una categoria valgono per i
    canali che contiene).
    """
    ids = [canale.id]
    origine = getattr(canale, "parent", None)
    for candidato in (getattr(canale, "parent_id", None), getattr(canale, "category_id", None),
                      getattr(origine, "category_id", None)):
        if isinstance(candidato, int) and candidato not in ids:
            ids.append(candidato)
    return ids


def scegli_premi(ricompense, modo: str) -> tuple[list[int], list[int]]:
    """
    Dai premi fino al livello raggiunto (ordinati per livello) sceglie
    (ruoli da dare, ruoli da togliere). "accumula": tutti, niente da
    togliere. "sostituisci": solo quelli del livello più alto, gli altri
    si tolgono.
    """
    if not ricompense:
        return [], []
    if modo != "sostituisci":
        return [r.role_id for r in ricompense], []
    massimo = max(r.level_threshold for r in ricompense)
    da_dare = [r.role_id for r in ricompense if r.level_threshold == massimo]
    da_togliere = [r.role_id for r in ricompense if r.level_threshold != massimo]
    return da_dare, da_togliere


# ======================================================================
# Rank card (NF-12, #83): colore e tema scelti da ciascuno
# ======================================================================
NOMI_TEMI_RANK_CARD = ("scuro", "chiaro", "notte")
_FORMA_COLORE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def colore_valido(testo: str) -> str | None:
    """'#RRGGBB' (maiuscolo) se il testo è un colore esadecimale a sei cifre, altrimenti None."""
    trovato = _FORMA_COLORE.match((testo or "").strip())
    return f"#{trovato.group(1).upper()}" if trovato else None


def tassa_su_pagamento(importo: int, percentuale: int) -> int:
    """
    ECO-015: la parte di `importo` che va alla cassa, arrotondata per eccesso:
    per difetto, tanti pagamenti piccoli non pagherebbero mai la tassa.
    """
    return -(-max(0, importo) * max(0, percentuale) // 100)


def contiene_emoji(testo: str) -> bool:
    """True se nel testo c'è un'emoji (unicode o personalizzata) o un codice :nome:."""
    for c in testo:
        cp = ord(c)
        if cp >= 0x1F000 or 0x2600 <= cp <= 0x27BF or cp in (0xFE0F, 0x200D, 0x20E3):
            return True
        if unicodedata.category(c) == "So":
            return True
    return ":" in testo


def nome_moneta_valido(nome: str) -> str:
    """ECO-001: il nome ripulito, o ValueError. Niente a capo né menzioni: finisce in tanti messaggi."""
    pulito = " ".join(nome.split())
    if not 1 <= len(pulito) <= MAX_NOME_MONETA:
        raise ValueError(f"Il nome della moneta deve avere da 1 a {MAX_NOME_MONETA} caratteri.")
    if any(c in pulito for c in "@#`*_~|<>[]"):
        raise ValueError("Il nome della moneta non può contenere simboli di formattazione o menzioni.")
    if contiene_emoji(pulito):
        raise ValueError("Il nome della moneta è solo testo: niente emoji. L'immagine si carica a parte.")
    return pulito


# ======================================================================
# Economia — regole scelte dal server (#125)
# ======================================================================
def attesa_daily_secondi(impostazioni: "LevelingSettings") -> int:
    """ECO-024: l'attesa tra due premi periodici, scelta dal server."""
    return impostazioni.daily_ore * 3600


def attesa_work_secondi(impostazioni: "LevelingSettings") -> int:
    """ECO-019/028: l'attesa tra due lavori, scelta dal server."""
    return impostazioni.work_attesa_min * 60


def bonus_serie(serie_dopo: int, per_giorno: int, massimo_giorni: int) -> int:
    """
    ECO-025: monete in più per una serie di giorni di fila. Il primo giorno non dà
    bonus; contano al massimo `massimo_giorni` giorni oltre il primo.
    """
    if per_giorno <= 0 or serie_dopo <= 1:
        return 0
    return per_giorno * min(serie_dopo - 1, max(0, massimo_giorni))


def controlla_puntata(puntata: int, impostazioni: "LevelingSettings") -> str | None:
    """ECO-021: None se la puntata va bene, altrimenti il motivo (testo breve)."""
    minimo, massimo = impostazioni.puntata_min, impostazioni.puntata_max
    if puntata < max(1, minimo):
        return f"La puntata minima è {max(1, minimo)}."
    if puntata > massimo:
        return f"La puntata massima è {massimo}."
    return None


ATTESA_PERIODICI = {"settimanale": 7 * 24 * 3600, "mensile": 30 * 24 * 3600}  # ECO-026

PERCENTUALE_RIVENDITA = 50  # ECO-072: rivendendo un oggetto si riceve metà del prezzo di oggi


def prezzo_rivendita(prezzo: int, percentuale: int = PERCENTUALE_RIVENDITA) -> int:
    """ECO-072: monete per la rivendita, sempre meno del prezzo (arrotondato per difetto)."""
    return max(0, prezzo) * min(max(0, percentuale), 99) // 100


def tasso_del_giorno(guild_id: int, giorno) -> int:
    """
    ECO-082: la percentuale di rivendita di oggi, tra 40 e 60, uguale per tutto il server e per tutto il giorno
    (calcolata dalla data: nessuno stato da salvare, nessuno la può prevedere dal cliente).
    """
    import hashlib

    h = hashlib.sha256(f"cambio:{guild_id}:{giorno.isoformat()}".encode()).digest()
    return 40 + int.from_bytes(h[:4], "big") % 21


# ECO-081: potenziamenti a livelli. Il livello L dà +10% a ogni livello; il costo cresce a ogni livello.
LIVELLI_POTENZIAMENTO = 5
TIPI_POTENZIAMENTO = ("lavoro", "premio")
BONUS_PER_LIVELLO = 10


def costo_potenziamento(livello_attuale: int) -> int | None:
    """Costo per passare al livello dopo; None se si è già al massimo."""
    if not 0 <= livello_attuale < LIVELLI_POTENZIAMENTO:
        return None
    return 500 * 2**livello_attuale


def con_potenziamento(importo: int, livello: int) -> int:
    """L'importo con il bonus del livello (mai meno dell'importo)."""
    return max(0, importo) * (100 + BONUS_PER_LIVELLO * min(max(0, livello), LIVELLI_POTENZIAMENTO)) // 100

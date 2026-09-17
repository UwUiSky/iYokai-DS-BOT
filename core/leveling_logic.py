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

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


def period_key(when: datetime | None = None) -> str:
    """
    Chiave del periodo (mese) corrente, es. "2026-09". Sempre in UTC
    per evitare ambiguità tra fusi orari diversi di membri dello
    stesso server.
    """
    moment = when or datetime.now(timezone.utc)
    return f"{moment.year:04d}-{moment.month:02d}"


# ======================================================================
# XP testuale — cooldown anti-spam
# ======================================================================

TEXT_XP_COOLDOWN_SECONDS = 60
TEXT_XP_AMOUNT = 15


def can_earn_text_xp(last_xp_at: datetime | None, now: datetime | None = None) -> bool:
    """
    True se è passato abbastanza tempo dall'ultimo guadagno di XP
    testuale di questo utente. Impedisce che scrivere messaggi a
    raffica dia XP a raffica — il guadagno resta legato al tempo
    trascorso, non al numero di messaggi.
    """
    if last_xp_at is None:
        return True
    current = now or datetime.now(timezone.utc)
    return (current - last_xp_at).total_seconds() >= TEXT_XP_COOLDOWN_SECONDS


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
) -> bool:
    """
    Le condizioni anti-farm decise in fase di progettazione, tutte
    necessarie insieme:
    - l'utente non è self_deaf (chi farma si assorda per non sentire)
    - il canale non è il canale AFK del server
    - c'è almeno un'ALTRA persona nel canale che non è self_mute
      (un canale con solo bot silenziati o solo l'utente stesso non
      conta come attività reale)
    """
    if is_self_deaf or is_afk_channel:
        return False
    return other_members_not_self_muted >= 1


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

    if minutes_today >= DAILY_CAP_MINUTES:
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


def xp_for_level(level: int) -> int:
    """XP cumulativo necessario per RAGGIUNGERE questo livello."""
    if level <= 0:
        return 0
    return 5 * level * level + 50 * level


def level_for_xp(total_xp: int) -> int:
    """
    Livello corrispondente a un totale di XP. Cerca linearmente dal
    basso: per i volumi di XP in gioco qui (mai milioni) è più che
    sufficiente e resta banale da verificare per correttezza — non
    serve la formula chiusa (che richiederebbe risolvere l'equazione
    di secondo grado con arrotondamenti da verificare comunque).
    """
    level = 0
    while xp_for_level(level + 1) <= total_xp:
        level += 1
    return level


def did_level_up(xp_before: int, xp_after: int) -> tuple[bool, int]:
    """
    Restituisce (è salito di livello, nuovo livello). Un singolo
    guadagno di XP potrebbe in teoria far salire più di un livello
    in un colpo solo (raro con gli importi in gioco, ma possibile con
    bonus grandi) — level_for_xp gestisce comunque il caso corretto.
    """
    level_before = level_for_xp(xp_before)
    level_after = level_for_xp(xp_after)
    return (level_after > level_before), level_after


# ======================================================================
# Economy — daily / work
# ======================================================================

DAILY_COOLDOWN_SECONDS = 24 * 3600
DAILY_REWARD_COINS = 200

WORK_COOLDOWN_SECONDS = 3600
WORK_REWARD_MIN = 20
WORK_REWARD_MAX = 80


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

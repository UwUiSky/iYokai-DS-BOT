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
import re
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


LIVELLO_MASSIMO = 1000  # tetto assoluto dei livelli impostabili a mano


def level_for_xp(total_xp: int, max_level: int = 0) -> int:
    """
    Livello corrispondente a un totale di XP (`max_level` > 0 è il tetto
    del server, LIV-005; 0 = nessun tetto). Formula chiusa: dalla
    5L^2 + 50L <= xp si ricava L con la radice intera, poi si corregge di
    un passo per sicurezza. Nessun ciclo sul numero di livelli, quindi
    costa lo stesso con 1.000 XP o con 10^15.
    """
    if total_xp <= 0:
        return 0
    level = max(0, (math.isqrt(2500 + 20 * total_xp) - 50) // 10)
    while level > 0 and xp_for_level(level) > total_xp:
        level -= 1
    while xp_for_level(level + 1) <= total_xp:
        level += 1
    if max_level:
        level = min(level, max_level)
    return level


def did_level_up(xp_before: int, xp_after: int, max_level: int = 0) -> tuple[bool, int]:
    """
    Restituisce (è salito di livello, nuovo livello). Un singolo
    guadagno di XP potrebbe in teoria far salire più di un livello
    in un colpo solo (raro con gli importi in gioco, ma possibile con
    bonus grandi) — level_for_xp gestisce comunque il caso corretto.
    """
    level_before = level_for_xp(xp_before, max_level)
    level_after = level_for_xp(xp_after, max_level)
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
) -> StimaLivello:
    """Quanto manca a un livello (LIV-074): XP, messaggi e minuti in vocale, senza moltiplicatori."""
    mancanti = max(0, xp_for_level(livello_obiettivo) - xp_attuale)
    messaggi = -(-mancanti // xp_per_messaggio) if xp_per_messaggio > 0 else 0
    minuti = -(-mancanti // xp_voce_minuto) if xp_voce_minuto > 0 else None
    return StimaLivello(mancanti, messaggi, minuti, messaggi * attesa_secondi)


def xp_dopo_modifica(xp_attuale: int, azione: str, valore: int, max_level: int = 0) -> int:
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
        return xp_for_level(min(tetto, max_level) if max_level else tetto)
    if azione == "xp_nel_livello":
        livello = level_for_xp(xp_attuale, max_level)
        base = xp_for_level(livello)
        ampiezza = xp_for_level(livello + 1) - base
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
MODI_MOLTIPLICATORI = ("somma", "massimo")

# Minimo e massimo di ogni numero configurabile. Un solo posto: lo usano
# i comandi, l'archivio e (D16) il futuro pannello web.
LIMITI_IMPOSTAZIONI = {
    "text_xp": (1, 100),
    "text_cooldown_seconds": (10, 600),
    "voice_xp_per_minute": (0, 50),
    "voice_coins_per_minute": (0, 50),
    "levelup_min_level": (0, 1000),
    "levelup_every": (1, 100),
    "daily_coins": (0, 10_000),
    "work_min": (0, 10_000),
    "work_max": (0, 10_000),
    "max_level": (0, 1000),  # 0 = nessun tetto
}
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
        return moltiplicatore_xp(
            self.impostazioni.multiplier_mode, self.fattori_attivi(channel_ids, role_ids)
        )

    def e_escluso(self, channel_ids, role_ids) -> bool:
        """Escluso se lo è il canale (o il suo canale di origine o la sua categoria) o un ruolo."""
        if isinstance(channel_ids, int):
            channel_ids = [channel_ids]
        return any(c in self.canali_esclusi for c in channel_ids) or any(
            r in self.ruoli_esclusi for r in role_ids
        )


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

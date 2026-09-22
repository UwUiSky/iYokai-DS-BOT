"""
core/guild_clan_logic.py
============================
Logica pura del Sistema Gilde/Clan (SPEC.md §15.14) — nessuna rete,
nessun Discord, nessuna query qui dentro. Numeri e regole confermati
con l'utente in conversazione prima di scrivere questo file:

- Tick al MINUTO (non ai 2 minuti — la finestra 23:59->00:01 è solo
  manutenzione/reset giornaliero, non un tick vero).
- Tasso base: 30 XP + 2 coin di gilda per membro attivo per tick,
  calibrato per far arrivare un utente molto attivo (12h/giorno,
  ogni giorno, senza restare mai troppo a lungo nello stesso
  vocale) a circa 500-750k XP/mese e sotto i 50k coin/mese.
- Decadimento: lineare fino a zero dopo 3 ore filate (180 tick) nello
  stesso canale vocale, azzerato al cambio canale.
- Tetto giornaliero: 12h = 720 tick/giorno (00:01-23:59 dello stesso
  giorno).
- Decadimento mensile 10% sulla tesoreria coin NON SPESA (non tocca
  ciò che è già stato investito in canali sbloccati).
- Deficit di creazione: 15.000 coin da colmare entro 24h o il clan
  viene cancellato automaticamente.
- Costi canale extra: 25.000 / 50.000 / 200.000 / 800.000 coin
  (raddoppio, poi quadruplo dal terzo in poi — valori arrotondati a
  cifra tonda dalla scala 12h/24h/96h/384h persona-ora discussa).
- Tesoreria a SENSO UNICO: membro -> gilda sempre permesso,
  gilda -> membro MAI (nessun prelievo individuale dalla tesoreria).
"""

from __future__ import annotations

TICK_XP = 30
TICK_COINS = 2

DECAY_TICKS = 180  # 3 ore filate nello stesso vocale -> guadagno zero
DAILY_TICK_CAP = 720  # 12 ore/giorno

MONTHLY_TREASURY_DECAY_RATE = 0.10  # 10% sulla tesoreria inutilizzata

CREATION_DEFICIT = 15_000
CREATION_GRACE_HOURS = 24

CHANNEL_UNLOCK_COSTS = (25_000, 50_000, 200_000, 800_000)

# Blocchi Unicode delle emoji più comuni — un tag di gilda non può
# contenerle (richiesta esplicita: "non accetta emoji o immagini").
# Le immagini non sono testo, quindi non serve gestirle qui: un
# modal Discord accetta solo testo per un campo stringa.
_EMOJI_RANGES = (
    (0x1F300, 0x1FAFF),
    (0x2600, 0x27BF),
    (0x1F1E6, 0x1F1FF),
    (0x2190, 0x21FF),
    (0x2B00, 0x2BFF),
    (0xFE00, 0xFE0F),
    (0x1F000, 0x1F0FF),
    (0x200D, 0x200D),
)

TAG_MIN_LENGTH = 1
TAG_MAX_LENGTH = 5


def _is_emoji_char(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _EMOJI_RANGES)


def validate_guild_tag(tag: str) -> tuple[bool, str | None]:
    """
    (valido, motivo_del_rifiuto). Lettere/numeri/simboli di
    qualunque lingua (incluso CJK) sono ammessi, le emoji no — la
    lunghezza è misurata in caratteri Unicode (non byte): un
    carattere CJK conta 1, non 2 o 3.
    """
    if not (TAG_MIN_LENGTH <= len(tag) <= TAG_MAX_LENGTH):
        return False, f"Il tag deve avere tra {TAG_MIN_LENGTH} e {TAG_MAX_LENGTH} caratteri."

    for ch in tag:
        if _is_emoji_char(ch):
            return False, "Il tag non può contenere emoji."
        if ch.isspace():
            return False, "Il tag non può contenere spazi."

    return True, None


def compute_tick_decay_factor(ticks_in_same_channel: int) -> float:
    """
    Fattore moltiplicativo [0, 1] applicato a TICK_XP/TICK_COINS in
    base a quanti tick consecutivi l'utente è rimasto nello STESSO
    canale vocale. Lineare: 1.0 a zero tick, 0.0 a DECAY_TICKS o
    oltre. Azzerato dal chiamante quando l'utente cambia canale
    (questa funzione non sa nulla di "cambio canale", riceve solo
    il conteggio già azzerato al momento giusto da chi la chiama).
    """
    if ticks_in_same_channel <= 0:
        return 1.0
    if ticks_in_same_channel >= DECAY_TICKS:
        return 0.0
    return 1.0 - (ticks_in_same_channel / DECAY_TICKS)


def compute_tick_reward(ticks_in_same_channel: int, ticks_today: int) -> tuple[int, int]:
    """
    (xp, coin) guadagnati in QUESTO tick — zero se il tetto
    giornaliero è già stato raggiunto, altrimenti scalati dal
    decadimento per permanenza nello stesso vocale. Arrotondato per
    difetto (un membro non guadagna mai più del tasso base per un
    arrotondamento a suo favore).
    """
    if ticks_today >= DAILY_TICK_CAP:
        return 0, 0

    fattore = compute_tick_decay_factor(ticks_in_same_channel)
    return int(TICK_XP * fattore), int(TICK_COINS * fattore)


def apply_monthly_treasury_decay(unspent_balance: int) -> int:
    """
    Il saldo tesoreria dopo il decadimento mensile del 10% — solo
    sulla parte NON spesa (i canali già sbloccati restano sbloccati
    per sempre, questa funzione non li tocca in alcun modo, riceve
    già solo il saldo libero). Arrotondato per difetto.
    """
    if unspent_balance <= 0:
        return unspent_balance
    return unspent_balance - int(unspent_balance * MONTHLY_TREASURY_DECAY_RATE)


def next_channel_unlock_cost(channels_already_unlocked: int) -> int | None:
    """
    Il costo del PROSSIMO canale extra da sbloccare, dato quanti ne
    sono già stati sbloccati (0 = nessuno ancora, quindi il prossimo
    è il primo della scala). None se la scala è esaurita — il
    chiamante decide cosa fare (es. restare all'ultimo costo per
    canali successivi, o bloccare ulteriori acquisti).
    """
    if channels_already_unlocked < 0:
        raise ValueError("channels_already_unlocked non può essere negativo.")
    if channels_already_unlocked >= len(CHANNEL_UNLOCK_COSTS):
        return None
    return CHANNEL_UNLOCK_COSTS[channels_already_unlocked]


def is_creation_deficit_covered(current_treasury_balance: int) -> bool:
    """Vero se il saldo tesoreria (che parte a -CREATION_DEFICIT) è
    tornato a zero o superiore — condizione per ufficializzare la
    creazione del clan."""
    return current_treasury_balance >= 0

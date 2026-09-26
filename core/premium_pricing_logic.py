"""
core/premium_pricing_logic.py
=================================
Logica pura per lo sblocco del bot premium via cassa di server
(SPEC.md §15.15) — nessuna rete, nessun Discord, nessuna query qui
dentro. Regole confermate esplicitamente con l'utente in
conversazione:

- Doppio cancello per ogni "mese" di premium sbloccabile: un tempo
  minimo trascorso dal join del bot nel server (1° mese dopo 6 mesi,
  2° dopo 1 anno, 3° dopo 2 anni) E un costo in coin dalla cassa del
  server.
- Il costo varia per fascia di membri del server: sotto i 1.000
  membri i costi di base (500.000 / 5.000.000 / 50.000.000 per il
  1°/2°/3° mese); ogni fascia successiva (sotto i 10.000, sotto i
  100.000, ...) moltiplica per 10 la fascia precedente — pattern
  confermato dall'utente ("dal server successivo in avanti è un 10x
  tutte le volte").
- Ogni costo è arrotondato IN ECCESSO a multipli di 25.000 (per le
  tre fasce base i numeri sono già multipli esatti, ma la funzione
  resta corretta per qualunque fascia futura o aggiustamento).
- Se il server spende le coin della cassa in premi invece che sul
  premium non è un problema: i tempi minimi restano solo un limite
  su QUANDO si può comprare, non un obbligo a comprare.
"""

from __future__ import annotations

MEMBER_BRACKET_BASE = 1_000
PRICE_ROUNDING_STEP = 25_000

# Costo di base (fascia 0: server con MENO di MEMBER_BRACKET_BASE
# membri) per ciascun "mese" sbloccabile, indicizzato per tier (1,2,3).
BASE_TIER_COSTS: dict[int, int] = {
    1: 500_000,
    2: 5_000_000,
    3: 50_000_000,
}

# Mesi minimi trascorsi dal join del bot nel server per poter
# comprare quel tier (indipendentemente dal costo).
TIER_MONTHS_REQUIRED: dict[int, int] = {
    1: 6,
    2: 12,
    3: 24,
}

MAX_DEFINED_TIER = 3


def months_elapsed(join_at, now) -> int:
    """
    Mesi civili pieni trascorsi tra join_at e now (mai negativo). Un
    mese si considera "pieno" solo se si è arrivati almeno al giorno
    del mese in cui il bot è entrato — coerente con "il mese comincia
    il giorno 1 per tutti anche per chi è entrato il giorno prima"
    dell'ALTRO decadimento (qui il riferimento è la data di join, non
    il giorno 1 del mese civile: sono due regole diverse per due
    scopi diversi, non vanno confuse).
    """
    if now <= join_at:
        return 0
    mesi = (now.year - join_at.year) * 12 + (now.month - join_at.month)
    if now.day < join_at.day:
        mesi -= 1
    return max(mesi, 0)


def member_count_bracket(member_count: int) -> int:
    """
    0 per server con meno di MEMBER_BRACKET_BASE (1.000) membri, 1
    per meno di 10.000, 2 per meno di 100.000, e così via — ogni
    fascia successiva è ×10 la soglia precedente, generalizzando il
    pattern confermato dall'utente per un server arbitrariamente
    grande.
    """
    if member_count < 0:
        raise ValueError("member_count non può essere negativo.")
    bracket = 0
    soglia = MEMBER_BRACKET_BASE
    while member_count >= soglia:
        bracket += 1
        soglia *= 10
    return bracket


def round_up_to_step(amount: int, step: int = PRICE_ROUNDING_STEP) -> int:
    """Arrotonda IN ECCESSO al multiplo di `step` più vicino (mai in
    difetto — un costo arrotondato per difetto costerebbe meno del
    dovuto)."""
    if step <= 0:
        raise ValueError("step deve essere positivo.")
    if amount <= 0:
        return 0
    resto = amount % step
    return amount if resto == 0 else amount + (step - resto)


def premium_tier_cost(tier: int, member_count: int) -> int:
    """
    Costo in coin dalla cassa per sbloccare quel tier (1, 2 o 3),
    scalato per fascia membri e arrotondato in eccesso a multipli di
    25.000.
    """
    if tier not in BASE_TIER_COSTS:
        raise ValueError(f"Tier premium non definito: {tier}.")
    base = BASE_TIER_COSTS[tier]
    bracket = member_count_bracket(member_count)
    costo_grezzo = base * (10 ** bracket)
    return round_up_to_step(costo_grezzo)


def is_tier_time_unlocked(tier: int, join_at, now) -> bool:
    """True se è passato abbastanza tempo dal join del bot per poter
    ANCHE solo tentare l'acquisto di quel tier (il costo va comunque
    verificato separatamente)."""
    if tier not in TIER_MONTHS_REQUIRED:
        raise ValueError(f"Tier premium non definito: {tier}.")
    return months_elapsed(join_at, now) >= TIER_MONTHS_REQUIRED[tier]

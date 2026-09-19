"""
core/memory_guard_logic.py
=============================
Logica pura del Memory Guard — stesso principio di
core/permissions.py, core/automod_sync.py, core/voice_temp_logic.py,
core/leveling_logic.py: solo numeri qui dentro, niente psutil, niente
oggetti discord.py. La lettura vera della memoria (psutil) e l'invio
del DM vivono in core/memory_guard.py, che chiama queste funzioni per
decidere COSA fare con il numero letto.

Quattro livelli (BACKLOG.md §4, ultima priorità del backlog accettato
dall'analisi di Gemini/ChatGPT/Grok — versione RIDIMENSIONATA:
soglie scalate con risposta graduata, ma solo sulle metriche che
questo codice può già misurare senza nuove dipendenze — RSS, pool
DB, numero di task — non le ~10 metriche complete proposte
originariamente, per scelta già motivata in BACKLOG.md):

    NORMAL    < 70% della soglia configurata (MEMORY_ALERT_THRESHOLD_MB)
    WARNING   >= 70%  -> GC forzato, nessun DM (non è ancora un'emergenza)
    CRITICAL  >= 100% -> GC forzato + DM (con cooldown, come il
                         comportamento a soglia singola di prima)
    EMERGENCY >= 130% -> GC forzato + DM SEMPRE, cooldown bypassato
                         (a questo livello un ritardo nell'avviso non
                         è accettabile)

Le soglie WARNING/EMERGENCY sono derivate da MEMORY_ALERT_THRESHOLD_MB
già esistente (CRITICAL ne conserva esattamente il significato
originale — "qui l'admin vuole essere avvisato") con due rapporti
fissi, non un nuovo schema di configurazione da imparare.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

# Tra un alert DM e il successivo deve passare almeno questo tempo,
# anche se la soglia resta superata ad ogni giro del tick (che gira
# ogni 60s — vedi core/memory_guard.py): altrimenti l'owner riceve un
# DM ogni minuto finché la RAM non scende, che è rumore, non un alert.
# Non si applica al livello EMERGENCY, che bypassa sempre il cooldown.
ALERT_COOLDOWN_SECONDS = 30 * 60  # 30 minuti

WARNING_RATIO = 0.7
EMERGENCY_RATIO = 1.3


class MemoryTier(Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


def bytes_to_mb(num_bytes: int) -> float:
    return num_bytes / (1024 * 1024)


def is_over_threshold(rss_bytes: int, threshold_mb: int) -> bool:
    return bytes_to_mb(rss_bytes) > threshold_mb


def classify_memory_tier(rss_bytes: int, critical_threshold_mb: int) -> MemoryTier:
    mb = bytes_to_mb(rss_bytes)
    if mb >= critical_threshold_mb * EMERGENCY_RATIO:
        return MemoryTier.EMERGENCY
    if mb >= critical_threshold_mb:
        return MemoryTier.CRITICAL
    if mb >= critical_threshold_mb * WARNING_RATIO:
        return MemoryTier.WARNING
    return MemoryTier.NORMAL


def should_force_gc(rss_bytes: int, critical_threshold_mb: int) -> bool:
    """GC forzato da WARNING in su — non solo a CRITICAL come prima:
    intervenire prima (quando costa meno, un GC è comunque economico)
    invece di aspettare che il problema sia già serio."""
    return classify_memory_tier(rss_bytes, critical_threshold_mb) != MemoryTier.NORMAL


def should_send_alert(
    rss_bytes: int,
    threshold_mb: int,
    last_alert_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    """
    True se in questo momento va mandato un DM di alert. Il livello
    WARNING non manda mai un DM (il GC forzato basta, la situazione
    non è ancora critica). Il livello EMERGENCY manda SEMPRE un DM,
    a prescindere dal cooldown — un ritardo qui non è accettabile.
    Il livello CRITICAL si comporta come la vecchia soglia singola:
    rispetta il cooldown.
    """
    tier = classify_memory_tier(rss_bytes, threshold_mb)
    if tier in (MemoryTier.NORMAL, MemoryTier.WARNING):
        return False
    if tier is MemoryTier.EMERGENCY:
        return True
    if last_alert_at is None:
        return True
    current = now or datetime.now(timezone.utc)
    return (current - last_alert_at) >= timedelta(seconds=ALERT_COOLDOWN_SECONDS)


def format_memory_alert(
    rss_bytes: int,
    threshold_mb: int,
    pool_size: int | None = None,
    pool_idle: int | None = None,
    task_count: int | None = None,
) -> str:
    mb = bytes_to_mb(rss_bytes)
    tier = classify_memory_tier(rss_bytes, threshold_mb)
    etichette_tier = {
        MemoryTier.WARNING: "⚠️ WARNING",
        MemoryTier.CRITICAL: "🔴 CRITICAL",
        MemoryTier.EMERGENCY: "🚨 EMERGENCY",
    }
    etichetta = etichette_tier.get(tier, "⚠️")

    righe = [
        f"{etichetta} **Memory Guard**: il processo di iYokai sta usando "
        f"**{mb:.0f} MB** di RAM, oltre la soglia configurata di "
        f"{threshold_mb} MB.",
        "È stato forzato un garbage collection.",
    ]
    if pool_size is not None and pool_idle is not None:
        righe.append(f"Pool DB: {pool_size - pool_idle}/{pool_size} connessioni in uso.")
    if task_count is not None:
        righe.append(f"Task asyncio attivi: {task_count}.")
    if tier is MemoryTier.EMERGENCY:
        righe.append(
            "Livello EMERGENCY: valuta un riavvio quanto prima, il consumo "
            "è oltre il 130% della soglia configurata."
        )
    else:
        righe.append("Se il consumo resta alto, valuta un riavvio o un controllo dei log.")
    return "\n".join(righe)


def format_memory_status(rss_bytes: int, threshold_mb: int) -> str:
    mb = bytes_to_mb(rss_bytes)
    percentuale = (mb / threshold_mb) * 100 if threshold_mb > 0 else 0
    tier = classify_memory_tier(rss_bytes, threshold_mb)
    return (
        f"RAM in uso: **{mb:.1f} MB** / {threshold_mb} MB soglia "
        f"({percentuale:.0f}%) — livello: {tier.value}"
    )


def should_disconnect_voice_client(member_count_excluding_bot: int) -> bool:
    """
    Un VoiceClient va disconnesso se il canale in cui si trova è
    rimasto senza nessun altro membro umano (solo il bot, o
    completamente vuoto). Logica minima e deliberatamente semplice:
    il modulo Music (non ancora scritto, vedi SPEC.md §9) avrà una
    propria logica di auto-leave più sofisticata (con timer di
    grazia); questa è la rete di sicurezza generica del Memory Guard,
    per qualunque VoiceClient rimasto agganciato per qualsiasi motivo.
    """
    return member_count_excluding_bot == 0

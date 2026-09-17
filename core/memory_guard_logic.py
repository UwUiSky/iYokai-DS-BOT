"""
core/memory_guard_logic.py
=============================
Logica pura del Memory Guard — stesso principio di
core/permissions.py, core/automod_sync.py, core/voice_temp_logic.py,
core/leveling_logic.py: solo numeri qui dentro, niente psutil, niente
oggetti discord.py. La lettura vera della memoria (psutil) e l'invio
del DM vivono in core/memory_guard.py, che chiama queste funzioni per
decidere COSA fare con il numero letto.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Tra un alert DM e il successivo deve passare almeno questo tempo,
# anche se la soglia resta superata ad ogni giro del tick (che gira
# ogni 60s — vedi core/memory_guard.py): altrimenti l'owner riceve un
# DM ogni minuto finché la RAM non scende, che è rumore, non un alert.
ALERT_COOLDOWN_SECONDS = 30 * 60  # 30 minuti


def bytes_to_mb(num_bytes: int) -> float:
    return num_bytes / (1024 * 1024)


def is_over_threshold(rss_bytes: int, threshold_mb: int) -> bool:
    return bytes_to_mb(rss_bytes) > threshold_mb


def should_send_alert(
    rss_bytes: int,
    threshold_mb: int,
    last_alert_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    """
    True se in questo momento va mandato un DM di alert:
    - la soglia deve essere superata ORA
    - E deve essere passato almeno ALERT_COOLDOWN_SECONDS dall'ultimo
      alert (o non essercene mai stato uno)
    """
    if not is_over_threshold(rss_bytes, threshold_mb):
        return False
    if last_alert_at is None:
        return True
    current = now or datetime.now(timezone.utc)
    return (current - last_alert_at) >= timedelta(seconds=ALERT_COOLDOWN_SECONDS)


def format_memory_alert(rss_bytes: int, threshold_mb: int) -> str:
    mb = bytes_to_mb(rss_bytes)
    return (
        f"⚠️ **Memory Guard**: il processo di iYokai sta usando "
        f"**{mb:.0f} MB** di RAM, oltre la soglia configurata di "
        f"{threshold_mb} MB.\n"
        f"È stato forzato un garbage collection. Se il consumo resta "
        f"alto, valuta un riavvio o un controllo dei log."
    )


def format_memory_status(rss_bytes: int, threshold_mb: int) -> str:
    mb = bytes_to_mb(rss_bytes)
    percentuale = (mb / threshold_mb) * 100 if threshold_mb > 0 else 0
    return (
        f"RAM in uso: **{mb:.1f} MB** / {threshold_mb} MB soglia "
        f"({percentuale:.0f}%)"
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

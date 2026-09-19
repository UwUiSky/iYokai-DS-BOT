"""
core/event_log_retention_logic.py
=====================================
Logica pura della retention del log eventi unificato (BACKLOG.md §3
"Logging strutturato" — Free 30 giorni, Premium 180+).
"""

from __future__ import annotations

FREE_RETENTION_DAYS = 30
PREMIUM_RETENTION_DAYS = 180


def retention_days_for(is_premium: bool) -> int:
    return PREMIUM_RETENTION_DAYS if is_premium else FREE_RETENTION_DAYS
